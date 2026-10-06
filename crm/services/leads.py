"""Lead service: lifecycle + transactional conversion.

Lifecycle (deterministic):
    new -> contacted -> qualified -> converted | lost
                        \-> unqualified

Conversion (single transaction, duplicate-safe):
    Lead -> Organization (reuse if lead already linked or name matches)
         -> Contact     (reuse if linked)
         -> Opportunity (one per lead; second attempt => 409)
and marks the lead converted with links back to the created records.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crm.core.audit import audit
from crm.core.auth import Identity
from crm.core.events import emit
from crm.domain.models import Activity, Contact, Lead, Opportunity, Organization, Stage, utcnow
from crm.services import activities as act_svc
from crm.services import tags_bridge
from crm.services.common import (apply_list_query, conflict, finalize_list, get_tenant,
                                 unprocessable)
from crm.services.pipelines import ensure_default_pipeline

ALLOWED_TRANSITIONS = {
    "new": {"contacted", "qualified", "unqualified", "lost"},
    "contacted": {"qualified", "unqualified", "lost"},
    "qualified": {"converted", "lost", "unqualified"},
    "unqualified": {"contacted", "qualified", "lost"},   # revive paths
    "converted": set(),
    "lost": {"contacted"},                               # rare revival
}


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in ("created_at", "updated_at")}


# ------------------------------------------------------------------- CRUD
def create_lead(session: Session, identity: Identity, data: dict) -> Lead:
    title = (data.get("title") or "").strip()
    if not title:
        raise unprocessable("Lead title is required")
    for key, model in (("organization_id", Organization), ("contact_id", Contact)):
        if data.get(key):
            get_tenant(session, model, identity, data[key])
    tags = data.pop("tags", None)
    lead = Lead(tenant_id=identity.tenant_id, title=title,
                owner_id=data.get("owner_id") or identity.user_id,
                **{k: v for k, v in data.items()
                   if k in Lead.__table__.columns.keys() and k not in
                   ("id", "tenant_id", "title", "owner_id", "status")})
    session.add(lead)
    session.flush()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="lead", entity_id=lead.id, after=_snapshot(lead))
    emit(session, "lead.created", identity.tenant_id, "lead", lead.id,
         {"title": lead.title, "source": lead.source, "owner_id": lead.owner_id},
         actor_id=identity.user_id)
    if tags:
        tags_bridge.set_entity_tags(session, identity, "lead", lead.id, tags)
    return lead


def list_leads(session: Session, identity: Identity, *, q=None, status=None, source=None,
               owner_id=None, score__gte=None, tag=None,
               sort=None, order="desc", page=1, per_page=25):
    stmt = select(Lead).where(Lead.tenant_id == identity.tenant_id)
    filters = {"status": status, "source": source, "owner_id": owner_id,
               "score__gte": score__gte}
    if tag:
        ids = tags_bridge.entity_ids_with_tag(session, identity, "lead", tag)
        stmt = stmt.where(Lead.id.in_(ids))
    stmt, count_stmt = apply_list_query(
        stmt, search_fields=[Lead.title, Lead.notes], q=q, filters=filters, model=Lead)
    return finalize_list(session, stmt, count_stmt, Lead,
                         sort=sort or "created_at", order=order, page=page, per_page=per_page)


def get_lead(session: Session, identity: Identity, lid: str) -> Lead:
    return get_tenant(session, Lead, identity, lid)


def update_lead(session: Session, identity: Identity, lid: str, data: dict) -> Lead:
    lead = get_tenant(session, Lead, identity, lid)
    before = _snapshot(lead)
    if "status" in data and data["status"] != lead.status:
        _set_status(session, identity, lead, data.pop("status"))
    owner_changed = "owner_id" in data and data["owner_id"] != lead.owner_id
    tags = data.pop("tags", None)
    for k, v in data.items():
        if k in Lead.__table__.columns.keys() and k not in ("id", "tenant_id", "created_at"):
            setattr(lead, k, v)
    session.flush()
    after = _snapshot(lead)
    changed = sorted(k for k in after if before.get(k) != after.get(k))
    action = "owner_change" if owner_changed else ("status_change" if "status" in changed
                                                   else "update")
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action=action, entity="lead", entity_id=lid, before=before, after=after)
    if tags is not None:
        tags_bridge.set_entity_tags(session, identity, "lead", lid, tags)
    return lead


def _set_status(session: Session, identity: Identity, lead: Lead, new_status: str) -> None:
    if new_status == lead.status:
        return
    if new_status in ("converted",):
        raise unprocessable("Use POST /leads/{id}/convert to convert a lead")
    if new_status not in ALLOWED_TRANSITIONS.get(lead.status, set()):
        raise conflict(f"Illegal lead transition: {lead.status} -> {new_status}")
    old = lead.status
    lead.status = new_status
    if new_status == "qualified":
        lead.qualification = "qualified"
        emit(session, "lead.qualified", identity.tenant_id, "lead", lead.id,
             {"title": lead.title}, actor_id=identity.user_id)
    if new_status == "lost":
        lead.lost_reason = lead.lost_reason or "other"
        emit(session, "lead.lost", identity.tenant_id, "lead", lead.id,
             {"lost_reason": lead.lost_reason}, actor_id=identity.user_id)
    emit(session, "lead.status_changed", identity.tenant_id, "lead", lead.id,
         {"from": old, "to": new_status}, actor_id=identity.user_id)


def mark_lost(session: Session, identity: Identity, lid: str, reason: str | None) -> Lead:
    lead = get_tenant(session, Lead, identity, lid)
    if lead.status in ("converted",):
        raise conflict("Cannot lose a converted lead")
    before = _snapshot(lead)
    if lead.status != "lost":
        _set_status(session, identity, lead, "lost")
    lead.lost_reason = reason or lead.lost_reason or "other"
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="status_change", entity="lead", entity_id=lid, before=before,
          after=_snapshot(lead))
    return lead


# --------------------------------------------------------------- conversion
def convert_lead(session: Session, identity: Identity, lid: str,
                 overrides: dict | None = None) -> dict:
    """Transactional Lead -> Organization + Contact + Opportunity.

    Duplicate-safe:
      * converting twice raises 409 (lead already converted);
      * existing organization/contact on the lead are reused, not recreated;
      * unique (tenant, org name) constraint prevents org duplicates.
    """
    overrides = overrides or {}
    lead = get_tenant(session, Lead, identity, lid)
    if lead.status == "converted":
        raise conflict("Lead already converted")
    if lead.status == "lost":
        raise unprocessable("Cannot convert a lost lead; revive it first")
    if lead.status not in ("qualified", "contacted", "new", "unqualified"):
        raise unprocessable(f"Cannot convert lead in status '{lead.status}'")

    now = utcnow()

    # --- Organization (reuse or create) ------------------------------------
    org: Organization | None = None
    org_created = False
    if lead.organization_id:
        org = get_tenant(session, Organization, identity, lead.organization_id)
    elif overrides.get("organization_id"):
        org = get_tenant(session, Organization, identity, overrides["organization_id"])
    if org is None:
        org_name = (overrides.get("organization_name") or lead.title).strip()
        org = session.execute(select(Organization).where(
            Organization.tenant_id == identity.tenant_id,
            func.lower(Organization.name) == org_name.lower())).scalar_one_or_none()
        if org is None:
            org = create_org_for_conversion(session, identity, org_name, lead)
            org_created = True

    # --- Contact (reuse or create) ------------------------------------------
    contact: Contact | None = None
    contact_created = False
    if lead.contact_id:
        contact = get_tenant(session, Contact, identity, lead.contact_id)
    elif overrides.get("contact_id"):
        contact = get_tenant(session, Contact, identity, overrides["contact_id"])
    if contact is None and overrides.get("contact_first_name"):
        contact = Contact(tenant_id=identity.tenant_id, organization_id=org.id,
                          first_name=overrides["contact_first_name"],
                          last_name=overrides.get("contact_last_name", ""),
                          job_title=overrides.get("contact_job_title"),
                          email=overrides.get("contact_email"),
                          phone=overrides.get("contact_phone"),
                          owner_id=lead.owner_id)
        session.add(contact)
        session.flush()
        contact_created = True
        audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
              action="create", entity="contact", entity_id=contact.id,
              after={"from_lead": lead.id})

    # --- Opportunity ---------------------------------------------------------
    pipe = ensure_default_pipeline(session, identity)
    first_stage = session.execute(select(Stage).where(
        Stage.pipeline_id == pipe.id, Stage.is_won.is_(False), Stage.is_lost.is_(False))
        .order_by(Stage.order)).scalars().first()
    value = int(overrides.get("value") or lead.estimated_value or 0)
    opp_name = overrides.get("opportunity_name") or f"{lead.title} — Deal"
    opp = Opportunity(
        tenant_id=identity.tenant_id, name=opp_name, organization_id=org.id,
        primary_contact_id=contact.id if contact else lead.contact_id,
        lead_id=lead.id, pipeline_id=pipe.id, stage_id=first_stage.id,
        owner_id=overrides.get("owner_id") or lead.owner_id,
        value=value, currency=lead.currency,
        probability=first_stage.probability,
        weighted_value=round(value * first_stage.probability / 100),
        expected_close_date=overrides.get("expected_close_date") or lead.expected_close_date,
        status="open", source=lead.source, description=lead.notes,
        next_activity_at=lead.next_activity_at, stage_entered_at=now)
    session.add(opp)
    session.flush()

    # --- mark lead converted --------------------------------------------------
    before = _snapshot(lead)
    lead.status = "converted"
    lead.converted_at = now
    lead.organization_id = org.id
    if contact:
        lead.contact_id = contact.id
    lead.converted_organization_id = org.id
    lead.converted_opportunity_id = opp.id
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="conversion", entity="lead", entity_id=lead.id, before=before,
          after=_snapshot(lead))
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="opportunity", entity_id=opp.id,
          after={"from_lead": lead.id, "name": opp.name})
    emit(session, "lead.converted", identity.tenant_id, "lead", lead.id,
         {"organization_id": org.id, "contact_id": contact.id if contact else None,
          "opportunity_id": opp.id, "org_created": org_created,
          "contact_created": contact_created}, actor_id=identity.user_id)
    emit(session, "opportunity.created", identity.tenant_id, "opportunity", opp.id,
         {"name": opp.name, "value": opp.value, "lead_id": lead.id},
         actor_id=identity.user_id)
    return {"lead": lead, "organization": org, "contact": contact, "opportunity": opp}


def create_org_for_conversion(session: Session, identity: Identity, name: str,
                              lead: Lead) -> Organization:
    org = Organization(tenant_id=identity.tenant_id, name=name, type="prospect",
                       owner_id=lead.owner_id, source=lead.source)
    session.add(org)
    session.flush()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="organization", entity_id=org.id,
          after={"from_lead": lead.id, "name": name})
    emit(session, "customer.created", identity.tenant_id, "organization", org.id,
         {"name": name, "from_lead": lead.id}, actor_id=identity.user_id)
    return org


# ------------------------------------------------------ lead payload extras
def lead_view(session: Session, identity: Identity, lead: Lead) -> dict:
    from crm.services.risk import lead_risk
    na = act_svc.next_action_for(session, identity, lead_id=lead.id)
    la = act_svc.last_logged_activity(session, identity, lead_id=lead.id)
    d = {c.key: getattr(lead, c.key) for c in Lead.__table__.columns}
    d["next_action"] = _act_brief(na)
    d["last_activity"] = _act_brief(la)
    d["risk"] = lead_risk(lead)
    return d


def _act_brief(a: Activity | None) -> dict | None:
    if a is None:
        return None
    return {"id": a.id, "type": a.type, "subject": a.subject, "due_at": a.due_at,
            "assigned_to": a.assigned_to, "status": a.status, "priority": a.priority}
