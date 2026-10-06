"""Customer 360 — one aggregated, action-oriented view of an Organization.

Sections: identity, contacts, commercial (leads/opportunities/revenue),
relationship state, activity timeline, tasks (open/overdue/upcoming),
notes (= note activities + org.notes), tags, intelligence (read-only, pushed
by the external Intelligence layer — never computed here).
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.core.config import RISK_RULES
from crm.domain.models import (Activity, Contact, DomainEvent, IntelligenceItem, Lead,
                               Opportunity, Organization, Stage, utcnow)
from crm.services import tags_bridge
from crm.services.activities import next_action_for
from crm.services.risk import opportunity_risk


def customer_360(session: Session, identity: Identity, org_id: str) -> dict:
    t = identity.tenant_id
    now = utcnow()
    org = session.get(Organization, org_id)
    if org is None or org.tenant_id != t:
        from crm.services.common import not_found
        raise not_found("Organization")

    contacts = list(session.execute(select(Contact).where(
        Contact.tenant_id == t, Contact.organization_id == org_id)
        .order_by(Contact.created_at)).scalars().all())
    opps = list(session.execute(select(Opportunity).where(
        Opportunity.tenant_id == t, Opportunity.organization_id == org_id)
        .order_by(Opportunity.created_at.desc())).scalars().all())
    leads = list(session.execute(select(Lead).where(
        Lead.tenant_id == t, Lead.organization_id == org_id)
        .order_by(Lead.created_at.desc())).scalars().all())
    acts = list(session.execute(select(Activity).where(
        Activity.tenant_id == t, Activity.organization_id == org_id)
        .order_by(Activity.created_at.desc()).limit(200)).scalars().all())

    open_opps = [o for o in opps if o.status == "open"]
    won = [o for o in opps if o.status == "won"]
    lost = [o for o in opps if o.status == "lost"]
    pipeline_value = sum(o.value for o in open_opps)
    weighted = sum(o.weighted_value for o in open_opps)
    revenue = sum(o.value for o in won)

    logged = [a for a in acts if a.status != "cancelled"
              and (a.occurred_at or a.completed_at)]
    last_touch = max((a.occurred_at or a.completed_at for a in logged), default=None)
    days_since_touch = (now - last_touch).days if last_touch else None
    relationship_days = (now - org.created_at).days

    pending = [a for a in acts if a.status == "pending"]
    overdue_tasks = [a for a in pending if a.due_at and a.due_at < now]
    today_end = now.replace(hour=23, minute=59, second=59) + timedelta(microseconds=1)
    todays = [a for a in pending if a.due_at and now <= a.due_at <= today_end]
    upcoming = [a for a in pending if a.due_at and a.due_at > today_end]

    # Next action across all open deals + org level; earliest due wins.
    candidates = []
    na_org = next_action_for(session, identity, organization_id=org_id)
    if na_org:
        candidates.append(na_org)
    for o in open_opps:
        na = next_action_for(session, identity, opportunity_id=o.id)
        if na:
            candidates.append(na)
    for l in leads:
        if l.status in ("new", "contacted", "qualified"):
            na = next_action_for(session, identity, lead_id=l.id)
            if na:
                candidates.append(na)
    seen, next_actions = set(), []
    for c in sorted([c for c in candidates if c.due_at], key=lambda a: a.due_at):
        if c.id not in seen:
            seen.add(c.id)
            next_actions.append(_act_full(c))

    channels = sorted({a.type for a in logged})
    risk_flags = {
        "no_activity_14d": bool(days_since_touch is None or
                                days_since_touch >= RISK_RULES["opportunity_stale_days"]),
        "has_overdue_tasks": bool(overdue_tasks),
        "no_next_action": not next_actions and bool(open_opps or leads),
    }

    stage_names = {s.id: s.name for s in session.execute(
        select(Stage).where(Stage.tenant_id == t)).scalars()}

    intelligence = list(session.execute(select(IntelligenceItem).where(
        IntelligenceItem.tenant_id == t,
        IntelligenceItem.entity == "organization",
        IntelligenceItem.entity_id == org_id)
        .order_by(IntelligenceItem.created_at.desc()).limit(20)).scalars().all())

    events = list(session.execute(select(DomainEvent).where(
        DomainEvent.tenant_id == t,
        DomainEvent.entity.in_(["lead", "opportunity"]),
        DomainEvent.entity_id.in_([o.id for o in opps] + [l.id for l in leads] or ["-1"]))
        .order_by(DomainEvent.occurred_at.desc()).limit(50)).scalars().all())

    return {
        "identity": _org_dict(org),
        "tags": tags_bridge.tags_of(session, identity, "organization", org_id),
        "contacts": [_contact_dict(c) for c in contacts],
        "commercial": {
            "leads": [{k: getattr(l, k) for k in ("id", "title", "status", "score",
                                                  "estimated_value", "owner_id",
                                                  "next_activity_at", "created_at")}
                      for l in leads],
            "opportunities": [_opp_dict(o, stage_names) for o in opps],
            "won_deals": len(won), "lost_deals": len(lost), "open_deals": len(open_opps),
            "revenue_won": revenue,
            "pipeline_value": pipeline_value,
            "weighted_pipeline": weighted,
        },
        "relationship": {
            "last_touch_at": last_touch,
            "days_since_last_touch": days_since_touch,
            "interaction_count": len(logged),
            "channels": channels,
            "relationship_days": relationship_days,
            "risk_flags": risk_flags,
        },
        "timeline": [_act_full(a) for a in acts[:100]],
        "tasks": {
            "open": [_act_full(a) for a in pending],
            "overdue": [_act_full(a) for a in overdue_tasks],
            "today": [_act_full(a) for a in todays],
            "upcoming": [_act_full(a) for a in upcoming[:20]],
        },
        "next_actions": next_actions[:5],
        "notes": [{"id": a.id, "subject": a.subject, "description": a.description,
                   "created_at": a.created_at}
                  for a in acts if a.type == "note"],
        "events": [{"event": e.event_type, "entity": e.entity, "entity_id": e.entity_id,
                    "occurred_at": e.occurred_at,
                    "payload": json.loads(e.payload or "{}")} for e in events],
        "intelligence": [{k: getattr(i, k) for k in ("id", "kind", "text", "source_system",
                                                     "confidence", "created_at")}
                         for i in intelligence],
    }


def _act_full(a: Activity) -> dict:
    return {"id": a.id, "type": a.type, "subject": a.subject,
            "description": a.description, "status": a.status, "priority": a.priority,
            "due_at": a.due_at, "completed_at": a.completed_at,
            "occurred_at": a.occurred_at, "assigned_to": a.assigned_to,
            "lead_id": a.lead_id, "opportunity_id": a.opportunity_id,
            "contact_id": a.contact_id, "created_at": a.created_at}


def _contact_dict(c: Contact) -> dict:
    return {k: getattr(c, k) for k in ("id", "first_name", "last_name", "job_title",
                                       "department", "phone", "mobile", "email",
                                       "linkedin", "status", "owner_id")} | \
        {"full_name": c.full_name}


def _opp_dict(o: Opportunity, stage_names: dict) -> dict:
    d = {k: getattr(o, k) for k in ("id", "name", "status", "value", "currency",
                                    "probability", "weighted_value", "stage_id",
                                    "owner_id", "expected_close_date", "source",
                                    "next_activity_at", "last_activity_at",
                                    "stage_entered_at", "lost_reason")}
    d["stage_name"] = stage_names.get(o.stage_id)
    d["risk"] = opportunity_risk(o)
    return d


def _org_dict(o: Organization) -> dict:
    return {k: getattr(o, k) for k in o.__table__.columns.keys()}
