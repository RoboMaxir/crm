"""Activities: logged interactions + actionable items (tasks / follow-ups).

Next Action (first-class concept):
  For any Lead / Opportunity / Organization, the "next action" is the earliest
  PENDING activity linked to it that has a due_at. It is surfaced on every
  record payload and in Customer 360 — never buried in notes.

Side effects kept deterministic and in-transaction:
  * creating an activity updates last_activity_at/next_activity_at on linked
    records;
  * completing one refreshes those pointers from remaining pending activities.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from crm.core.audit import audit
from crm.core.auth import Identity
from crm.core.events import emit
from crm.domain.models import Activity, Contact, Lead, Opportunity, Organization, utcnow
from crm.services.common import apply_list_query, finalize_list, get_tenant, unprocessable

LINKED_MODELS = {"lead": Lead, "opportunity": Opportunity, "organization": Organization,
                 "contact": Contact}


def _snapshot(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key not in ("created_at", "updated_at")}


def _validate_links(session: Session, identity: Identity, data: dict) -> None:
    for key, model in (("lead_id", Lead), ("opportunity_id", Opportunity),
                       ("organization_id", Organization), ("contact_id", Contact)):
        if data.get(key):
            get_tenant(session, model, identity, data[key])
    # An activity about an opportunity inherits its organization unless given.
    if data.get("opportunity_id") and not data.get("organization_id"):
        opp = session.get(Opportunity, data["opportunity_id"])
        data["organization_id"] = opp.organization_id
    if data.get("lead_id") and not data.get("organization_id"):
        lead = session.get(Lead, data["lead_id"])
        data["organization_id"] = lead.organization_id


# ------------------------------------------------------------- pointer sync
def pending_activities(session: Session, identity: Identity, **link) -> list[Activity]:
    """Pending activities with a due date for a linked record, soonest first."""
    col_name = next(k for k in link if k.endswith("_id"))
    col = getattr(Activity, col_name)
    stmt = select(Activity).where(
        Activity.tenant_id == identity.tenant_id,
        Activity.status == "pending",
        col == link[col_name]).order_by(Activity.due_at.asc().nulls_last())
    return list(session.execute(stmt).scalars().all())


def next_action_for(session: Session, identity: Identity, **link) -> Activity | None:
    acts = [a for a in pending_activities(session, identity, **link) if a.due_at]
    return acts[0] if acts else None


def last_logged_activity(session: Session, identity: Identity, **link):
    col_name = next(k for k in link if k.endswith("_id"))
    col = getattr(Activity, col_name)
    stmt = select(Activity).where(
        Activity.tenant_id == identity.tenant_id,
        col == link[col_name],
        Activity.status != "cancelled",
        or_(Activity.occurred_at.is_not(None), Activity.completed_at.is_not(None)),
    ).order_by(Activity.created_at.desc()).limit(1)
    return session.execute(stmt).scalars().first()


def sync_record_pointers(session: Session, identity: Identity, model, record) -> None:
    """Recompute last_activity_at / next_activity_at deterministically."""
    link_key = {Lead: "lead_id", Opportunity: "opportunity_id",
                Organization: "organization_id"}.get(model)
    if link_key is None:
        return
    acts = pending_activities(session, identity, **{link_key: record.id})
    upcoming = [a for a in acts if a.due_at and a.due_at >= utcnow()]
    record.next_activity_at = upcoming[0].due_at if upcoming else None
    last = last_logged_activity(session, identity, **{link_key: record.id})
    if last is not None:
        record.last_activity_at = last.occurred_at or last.completed_at or last.created_at


# ------------------------------------------------------------------- CRUD
def create_activity(session: Session, identity: Identity, data: dict) -> Activity:
    if not (data.get("subject") or "").strip():
        raise unprocessable("Activity subject is required")
    atype = data.get("type", "note")
    status = data.get("status", "pending")
    _validate_links(session, identity, data)
    now = utcnow()
    act = Activity(
        tenant_id=identity.tenant_id, type=atype, subject=data["subject"].strip(),
        description=data.get("description"),
        organization_id=data.get("organization_id"), contact_id=data.get("contact_id"),
        lead_id=data.get("lead_id"), opportunity_id=data.get("opportunity_id"),
        assigned_to=data.get("assigned_to") or identity.user_id,
        status=status, priority=data.get("priority", "medium"),
        due_at=data.get("due_at"), created_by=identity.user_id,
        occurred_at=now if status == "completed" else None,
        completed_at=now if status == "completed" else None,
    )
    session.add(act)
    session.flush()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="create", entity="activity", entity_id=act.id, after=_snapshot(act))
    emit(session, "activity.created", identity.tenant_id, "activity", act.id,
         {"type": act.type, "subject": act.subject, "lead_id": act.lead_id,
          "opportunity_id": act.opportunity_id, "organization_id": act.organization_id},
         actor_id=identity.user_id)
    # keep denormalized pointers consistent on linked records
    for model, key in ((Lead, "lead_id"), (Opportunity, "opportunity_id"),
                       (Organization, "organization_id")):
        rid = getattr(act, key)
        if rid:
            rec = session.get(model, rid)
            sync_record_pointers(session, identity, model, rec)
    if act.status == "completed":
        _bump_lead_on_activity(session, act)
    session.flush()
    return act


def _bump_lead_on_activity(session: Session, act: Activity) -> None:
    """A completed interaction on a brand-new lead moves it to contacted."""
    if act.lead_id and act.status == "completed":
        lead = session.get(Lead, act.lead_id)
        if lead and lead.status == "new":
            lead.status = "contacted"


def complete_activity(session: Session, identity: Identity, aid: str) -> Activity:
    act = get_tenant(session, Activity, identity, aid)
    if act.status == "completed":
        return act
    before = _snapshot(act)
    act.status = "completed"
    act.completed_at = utcnow()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="complete", entity="activity", entity_id=aid,
          before=before, after=_snapshot(act))
    emit(session, "activity.completed", identity.tenant_id, "activity", aid,
         {"type": act.type, "subject": act.subject, "lead_id": act.lead_id,
          "opportunity_id": act.opportunity_id, "organization_id": act.organization_id},
         actor_id=identity.user_id)
    _bump_lead_on_activity(session, act)
    for model, key in ((Lead, "lead_id"), (Opportunity, "opportunity_id"),
                       (Organization, "organization_id")):
        rid = getattr(act, key)
        if rid:
            rec = session.get(model, rid)
            sync_record_pointers(session, identity, model, rec)
    session.flush()
    return act


def cancel_activity(session: Session, identity: Identity, aid: str) -> Activity:
    act = get_tenant(session, Activity, identity, aid)
    act.status = "cancelled"
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="update", entity="activity", entity_id=aid, after={"status": "cancelled"})
    session.flush()
    return act


def update_activity(session: Session, identity: Identity, aid: str,
                    data: dict) -> Activity:
    act = get_tenant(session, Activity, identity, aid)
    before = _snapshot(act)
    for k in ("subject", "description", "type", "priority", "due_at", "assigned_to",
              "status"):
        if k in data and data[k] is not None:
            setattr(act, k, data[k])
    if data.get("status") == "completed" and before["status"] != "completed":
        act.completed_at = utcnow()
    audit(session, tenant_id=identity.tenant_id, actor_id=identity.user_id,
          action="update", entity="activity", entity_id=aid, before=before,
          after=_snapshot(act))
    session.flush()
    return act


def list_activities(session: Session, identity: Identity, *, q=None, type=None,
                    status=None, priority=None, assigned_to=None, organization_id=None,
                    lead_id=None, opportunity_id=None, contact_id=None,
                    due_before: datetime | None = None, due_after: datetime | None = None,
                    sort=None, order="desc", page=1, per_page=25):
    stmt = select(Activity).where(Activity.tenant_id == identity.tenant_id)
    filters = {
        "type": type, "status": status, "priority": priority,
        "assigned_to": assigned_to, "organization_id": organization_id,
        "lead_id": lead_id, "opportunity_id": opportunity_id, "contact_id": contact_id,
    }
    if due_before:
        filters["due_at__lte"] = due_before
    if due_after:
        filters["due_at__gte"] = due_after
    stmt, count_stmt = apply_list_query(
        stmt, search_fields=[Activity.subject, Activity.description],
        q=q, filters=filters, model=Activity)
    return finalize_list(session, stmt, count_stmt, Activity,
                         sort=sort or "created_at", order=order, page=page, per_page=per_page)


def mark_overdue_events(session: Session, identity: Identity) -> int:
    """Deterministic sweep: emit activity.overdue once per overdue pending item."""
    now = utcnow()
    rows = session.execute(select(Activity).where(
        Activity.tenant_id == identity.tenant_id,
        Activity.status == "pending",
        Activity.due_at.is_not(None),
        Activity.due_at < now,
        Activity.overdue_notified.is_(False))).scalars().all()
    for act in rows:
        act.overdue_notified = True
        emit(session, "activity.overdue", identity.tenant_id, "activity", act.id,
             {"type": act.type, "subject": act.subject, "due_at": act.due_at.isoformat(),
              "lead_id": act.lead_id, "opportunity_id": act.opportunity_id,
              "organization_id": act.organization_id},
             actor_id=None)
    session.flush()
    return len(rows)
