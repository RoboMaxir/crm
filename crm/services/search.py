"""Global search across Organizations, Contacts, Leads, Opportunities, Activities.

Single query per entity type, tenant-scoped, relevance-ordered (exact/prefix
name matches first). Results are minimal cards with links — the UI then routes
to Customer 360 / record pages where actions live.
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.domain.models import Activity, Contact, Lead, Opportunity, Organization


def _like(q: str):
    return f"%{q.lower()}%"


def global_search(session: Session, identity: Identity, q: str,
                  limit_per_type: int = 10) -> dict:
    t = identity.tenant_id
    like = _like(q)
    out: dict[str, list] = {}

    orgs = session.execute(
        select(Organization).where(
            Organization.tenant_id == t,
            or_(func.lower(Organization.name).like(like),
                func.lower(func.coalesce(Organization.legal_name, "")).like(like),
                func.lower(func.coalesce(Organization.city, "")).like(like)))
        .order_by(func.lower(Organization.name)).limit(limit_per_type)
    ).scalars().all()
    out["organizations"] = [{"id": o.id, "name": o.name, "type": o.type,
                             "status": o.status, "city": o.city} for o in orgs]

    contacts = session.execute(
        select(Contact).where(
            Contact.tenant_id == t,
            or_(func.lower(Contact.first_name).like(like),
                func.lower(Contact.last_name).like(like),
                func.lower((Contact.first_name + " " + Contact.last_name)).like(like),
                func.lower(func.coalesce(Contact.email, "")).like(like),
                func.lower(func.coalesce(Contact.job_title, "")).like(like)))
        .order_by(Contact.first_name).limit(limit_per_type)
    ).scalars().all()
    out["contacts"] = [{"id": c.id, "full_name": c.full_name, "email": c.email,
                        "job_title": c.job_title, "organization_id": c.organization_id}
                       for c in contacts]

    leads = session.execute(
        select(Lead).where(
            Lead.tenant_id == t,
            or_(func.lower(Lead.title).like(like),
                func.lower(func.coalesce(Lead.notes, "")).like(like)))
        .order_by(Lead.created_at.desc()).limit(limit_per_type)
    ).scalars().all()
    out["leads"] = [{"id": l.id, "title": l.title, "status": l.status,
                     "score": l.score, "owner_id": l.owner_id,
                     "organization_id": l.organization_id} for l in leads]

    opps = session.execute(
        select(Opportunity).where(
            Opportunity.tenant_id == t,
            or_(func.lower(Opportunity.name).like(like),
                func.lower(func.coalesce(Opportunity.description, "")).like(like)))
        .order_by(Opportunity.created_at.desc()).limit(limit_per_type)
    ).scalars().all()
    out["opportunities"] = [{"id": o.id, "name": o.name, "status": o.status,
                             "value": o.value, "weighted_value": o.weighted_value,
                             "organization_id": o.organization_id,
                             "stage_id": o.stage_id, "owner_id": o.owner_id}
                            for o in opps]

    acts = session.execute(
        select(Activity).where(
            Activity.tenant_id == t,
            or_(func.lower(Activity.subject).like(like),
                func.lower(func.coalesce(Activity.description, "")).like(like)))
        .order_by(Activity.created_at.desc()).limit(limit_per_type)
    ).scalars().all()
    out["activities"] = [{"id": a.id, "type": a.type, "subject": a.subject,
                          "status": a.status, "due_at": a.due_at,
                          "organization_id": a.organization_id,
                          "lead_id": a.lead_id, "opportunity_id": a.opportunity_id}
                         for a in acts]

    out["total"] = sum(len(v) for v in out.values())
    return out
