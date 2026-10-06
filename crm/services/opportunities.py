"""Opportunity service: creation, stage transitions, win/lose.

Deterministic invariants:
  * weighted_value = round(value * probability / 100) — recomputed on every
    value/probability/stage change and stored (so pipeline queries are cheap
    and consistent).
  * Moving to a Won/Lost stage sets status + closed_at; probability snaps to
    100/0 respectively (unless the user overrode it before — override is
    honoured only while the deal is open).
  * stage_entered_at resets on every stage change => aging is measurable.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from crm.core.audit import audit
from crm.core.auth import Identity
from crm.core.events import emit
from crm.domain.models import (Activity, Contact, Lead, Opportunity, Organization,
                               Pipeline, Stage, utcnow)
from crm.services import activities as act_svc
from crm.services import tags_bridge
from crm.services.common import apply_list_query, conflict, finalize_list, get_tenant, unprocessable


def compute_weighted(value: int, probability: int) -> int:
    return round((value or 0) * (probability or 0) / 100)


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in ("created_at", "updated_at")}


# ------------------------------------------------------------------- CRUD
def create_opportunity(session: Session, identity: Identity, data: dict) -> Opportunity:
    if not (data.get("name") or "").strip():
        raise unprocessable("Opportunity name is required")
    org = get_tenant(session, Organization, identity, data["organization_id"])
    if data.get("primary_contact_id"):
        get_tenant(session, Contact, identity, data["primary_contact_id"])
    if data.get("lead_id"):
        lead = get_tenant(session, Lead, identity, data["lead_id"])
        if lead.converted_opportunity_id:
            raise conflict("This lead already has an opportunity (duplicate conversion)")
    from crm.services.pipelines import ensure_default_pipeline
    pipe_id = data.get("pipeline_id")
    if pipe_id:
        get_tenant(session, Pipeline, identity, pipe_id)
    else:
        pipe_id = ensure_default_pipeline(session, identity).id
    stage_id = data.get("stage_id")
    if stage_id:
        stage = get_tenant(session, Stage, identity, stage_id)
        if stage.pipeline_id != pipe_id:
            raise unprocessable("Stage does not belong to the given pipeline")
    else:
        stage = session.execute(select(Stage).where(
            Stage.pipeline_id == pipe_id, Stage.is_won.is_(False), Stage.is_lost.is_(False))
            .order_by(Stage.order)).scalars().first()
    now = utcnow()
    value = int(data.get("value") or 0)
    probability = int(data.get("probability") if data.get("probability") is not None
                      else stage.probability)
    opp = Opportunity(
        tenant_id=identity.tenant_id, name=data["name"].strip(),
        organization_id=org.id, primary_contact_id=data.get("primary_contact_id"),
        lead_id=data.get("lead_id"), pipeline_id=pipe_id, stage_id=stage.id,
        owner_id=data.get("owner_id") or identity.user_id,
        value=value, currency=data.get("currency", "IRR"), probability=probability,
        weighted_value=compute_weighted(value, probability),
        expected_close_date=data.get("expected_close_date"),
        status="open", source=data.get("source") or (org.source if org else None),
        description=data.get("description"), next_activity_at=data.get("next_activity_at"),
        stage_entered_at=now)
    session.add(opp)
    session.flush()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="opportunity", entity_id=opp.id, after=_snapshot(opp))
    emit(session, "opportunity.created", identity.tenant_id, "opportunity", opp.id,
         {"name": opp.name, "value": opp.value, "organization_id": opp.organization_id},
         actor_id=identity.user_id)
    if data.get("tags"):
        tags_bridge.set_entity_tags(session, identity, "opportunity", opp.id, data["tags"])
    return opp


def list_opportunities(session: Session, identity: Identity, *, q=None, status=None,
                       stage_id=None, pipeline_id=None, owner_id=None, organization_id=None,
                       value__gt=None, value__lt=None, tag=None,
                       expected_close_before=None, expected_close_after=None,
                       sort=None, order="desc", page=1, per_page=25):
    stmt = select(Opportunity).where(Opportunity.tenant_id == identity.tenant_id)
    filters = {
        "status": status, "stage_id": stage_id, "pipeline_id": pipeline_id,
        "owner_id": owner_id, "organization_id": organization_id,
        "value__gt": value__gt, "value__lt": value__lt,
        "expected_close_date__lte": expected_close_before,
        "expected_close_date__gte": expected_close_after,
    }
    if tag:
        ids = tags_bridge.entity_ids_with_tag(session, identity, "opportunity", tag)
        stmt = stmt.where(Opportunity.id.in_(ids))
    stmt, count_stmt = apply_list_query(
        stmt, search_fields=[Opportunity.name, Opportunity.description],
        q=q, filters=filters, model=Opportunity)
    return finalize_list(session, stmt, count_stmt, Opportunity,
                         sort=sort or "created_at", order=order, page=page, per_page=per_page)


def get_opportunity(session: Session, identity: Identity, oid: str) -> Opportunity:
    return get_tenant(session, Opportunity, identity, oid)


def update_opportunity(session: Session, identity: Identity, oid: str,
                       data: dict) -> Opportunity:
    """Generic update; stage changes MUST go through move_stage (use PATCH stage_id)."""
    opp = get_tenant(session, Opportunity, identity, oid)
    if opp.status != "open" and any(k in data for k in ("stage_id", "value", "probability")):
        raise conflict("Cannot modify a closed opportunity")
    before = _snapshot(opp)
    tags = data.pop("tags", None)
    if "stage_id" in data and data["stage_id"] != opp.stage_id:
        new_stage = get_tenant(session, Stage, identity, data.pop("stage_id"))
        _move_to_stage(session, identity, opp, new_stage,
                       probability_override=data.pop("probability", None))
    else:
        data.pop("stage_id", None)
        for k in ("name", "value", "currency", "probability", "expected_close_date",
                  "description", "primary_contact_id", "source", "next_activity_at"):
            if k in data and data[k] is not None:
                setattr(opp, k, data[k])
        owner_changed = "owner_id" in data and data["owner_id"] != opp.owner_id
        if owner_changed:
            audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
                  action="owner_change", entity="opportunity", entity_id=oid,
                  before={"owner_id": before["owner_id"]},
                  after={"owner_id": data["owner_id"]})
    if "value" in data or "probability" in data:
        opp.weighted_value = compute_weighted(opp.value, opp.probability)
    session.flush()
    after = _snapshot(opp)
    changed = sorted(k for k in after if before.get(k) != after.get(k))
    if changed:
        audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
              action="update", entity="opportunity", entity_id=oid, before=before,
              after=after)
        emit(session, "opportunity.updated", identity.tenant_id, "opportunity", oid,
             {"changed": changed}, actor_id=identity.user_id)
    if tags is not None:
        tags_bridge.set_entity_tags(session, identity, "opportunity", oid, tags)
    return opp


# --------------------------------------------------------- stage transitions
def _move_to_stage(session: Session, identity: Identity, opp: Opportunity,
                   new_stage: Stage, probability_override: int | None = None) -> None:
    old_stage_id = opp.stage_id
    now = utcnow()
    opp.stage_id = new_stage.id
    opp.stage_entered_at = now
    opp.probability = (int(probability_override) if probability_override is not None
                       else new_stage.probability)
    if new_stage.is_won:
        opp.status = "won"
        opp.probability = 100
        opp.closed_at = now
        emit(session, "opportunity.won", identity.tenant_id, "opportunity", opp.id,
             {"name": opp.name, "value": opp.value,
              "organization_id": opp.organization_id}, actor_id=identity.user_id)
    elif new_stage.is_lost:
        opp.status = "lost"
        opp.probability = 0
        opp.closed_at = now
        opp.lost_reason = opp.lost_reason or "other"
        emit(session, "opportunity.lost", identity.tenant_id, "opportunity", opp.id,
             {"name": opp.name, "lost_reason": opp.lost_reason}, actor_id=identity.user_id)
    opp.weighted_value = compute_weighted(opp.value, opp.probability)
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="stage_change", entity="opportunity", entity_id=opp.id,
          before={"stage_id": old_stage_id}, after={"stage_id": new_stage.id})
    emit(session, "opportunity.stage_changed", identity.tenant_id, "opportunity", opp.id,
         {"from_stage_id": old_stage_id, "to_stage_id": new_stage.id,
          "to_stage_name": new_stage.name}, actor_id=identity.user_id)


def move_stage(session: Session, identity: Identity, oid: str, stage_id: str,
               lost_reason: str | None = None,
               probability_override: int | None = None) -> Opportunity:
    opp = get_tenant(session, Opportunity, identity, oid)
    stage = get_tenant(session, Stage, identity, stage_id)
    if stage.pipeline_id != opp.pipeline_id:
        raise unprocessable("Stage belongs to a different pipeline")
    if opp.status != "open":
        raise conflict(f"Opportunity is already {opp.status}")
    if stage.is_lost:
        opp.lost_reason = lost_reason or "other"
    _move_to_stage(session, identity, opp, stage, probability_override)
    session.flush()
    return opp


def reopen(session: Session, identity: Identity, oid: str, stage_id: str) -> Opportunity:
    opp = get_tenant(session, Opportunity, identity, oid)
    if opp.status == "open":
        return opp
    stage = get_tenant(session, Stage, identity, stage_id)
    if stage.is_won or stage.is_lost:
        raise unprocessable("Reopen target must be an open stage")
    opp.status = "open"
    opp.closed_at = None
    opp.lost_reason = None
    _move_to_stage(session, identity, opp, stage)
    session.flush()
    return opp


# ------------------------------------------------------------- payload view
def opportunity_view(session: Session, identity: Identity, opp: Opportunity) -> dict:
    from crm.services.risk import opportunity_risk
    na = act_svc.next_action_for(session, identity, opportunity_id=opp.id)
    la = act_svc.last_logged_activity(session, identity, opportunity_id=opp.id)
    stage = session.get(Stage, opp.stage_id)
    org = session.get(Organization, opp.organization_id)
    d = {c.key: getattr(opp, c.key) for c in Opportunity.__table__.columns}
    d["stage_name"] = stage.name if stage else None
    d["stage_color"] = stage.color if stage else None
    d["organization_name"] = org.name if org else None
    d["days_in_stage"] = ((utcnow() - (opp.stage_entered_at or opp.created_at)).days
                          if opp.status == "open" else None)
    d["next_action"] = _act_brief(na)
    d["last_activity"] = _act_brief(la)
    d["risk"] = opportunity_risk(opp)
    return d


def _act_brief(a: Activity | None) -> dict | None:
    if a is None:
        return None
    return {"id": a.id, "type": a.type, "subject": a.subject, "due_at": a.due_at,
            "assigned_to": a.assigned_to, "status": a.status, "priority": a.priority}
