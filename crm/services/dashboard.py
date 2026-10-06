"""Dashboards: operational metrics + CEO view + Pipeline Kanban.

All numbers are computed from CRM state with deterministic SQL — no AI, no
guessing. "Today" boundaries are UTC (documented simplification; a tenant
timezone can be layered on later).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.core.config import RISK_RULES
from crm.domain.models import Activity, Lead, Opportunity, Organization, Stage, utcnow
from crm.services import tags_bridge
from crm.services.risk import lead_risk, opportunity_risk


def _today_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ------------------------------------------------------------- sales KPIs
def sales_metrics(session: Session, identity: Identity) -> dict:
    t = identity.tenant_id
    now = utcnow()
    day_start, day_end = _today_bounds(now)
    month_start = _month_start(now)

    def count(model, *conds):
        return session.execute(select(func.count()).select_from(model).where(
            model.tenant_id == t, *conds)).scalar_one()

    total_leads = count(Lead)
    new_leads = count(Lead, Lead.created_at >= month_start)
    qualified = count(Lead, Lead.status.in_(["qualified", "converted"]))
    converted = count(Lead, Lead.status == "converted")
    lost_leads = count(Lead, Lead.status == "lost")
    decided = converted + lost_leads
    conversion_rate = round(converted / decided * 100, 1) if decided else 0.0

    open_opps = session.execute(select(func.count(), func.coalesce(func.sum(Opportunity.value), 0),
                                        func.coalesce(func.sum(Opportunity.weighted_value), 0))
                                .where(Opportunity.tenant_id == t,
                                       Opportunity.status == "open")).one()
    won_row = session.execute(select(func.count(),
                                     func.coalesce(func.sum(Opportunity.value), 0))
                              .where(Opportunity.tenant_id == t,
                                     Opportunity.status == "won",
                                     Opportunity.closed_at >= month_start)).one()
    lost_row = session.execute(select(func.count(),
                                      func.coalesce(func.sum(Opportunity.value), 0))
                               .where(Opportunity.tenant_id == t,
                                      Opportunity.status == "lost",
                                      Opportunity.closed_at >= month_start)).one()
    won_alltime = session.execute(select(func.count(),
                                         func.coalesce(func.sum(Opportunity.value), 0))
                                  .where(Opportunity.tenant_id == t,
                                         Opportunity.status == "won")).one()
    opp_decided = won_row[0] + lost_row[0]
    return {
        "total_leads": total_leads,
        "new_leads_this_month": new_leads,
        "qualified_leads": qualified,
        "lead_conversion_rate_pct": conversion_rate,
        "open_opportunities": open_opps[0],
        "pipeline_value": open_opps[1],
        "weighted_pipeline": open_opps[2],
        "won_this_month": {"count": won_row[0], "value": won_row[1]},
        "lost_this_month": {"count": lost_row[0], "value": lost_row[1]},
        "win_rate_month_pct": round(won_row[0] / opp_decided * 100, 1) if opp_decided else 0.0,
        "revenue_won_alltime": won_alltime[1],
        "customers_count": count(Organization, Organization.type == "customer"),
        "organizations_count": count(Organization),
    }


# --------------------------------------------------------- activity KPIs
def activity_metrics(session: Session, identity: Identity) -> dict:
    t = identity.tenant_id
    now = utcnow()
    day_start, day_end = _today_bounds(now)

    def rows(stmt):
        return list(session.execute(stmt).scalars().all())

    todays_tasks = rows(select(Activity).where(
        Activity.tenant_id == t, Activity.status == "pending",
        Activity.due_at.is_not(None), Activity.due_at >= day_start,
        Activity.due_at < day_end).order_by(Activity.due_at))
    overdue = rows(select(Activity).where(
        Activity.tenant_id == t, Activity.status == "pending",
        Activity.due_at.is_not(None), Activity.due_at < day_start)
        .order_by(Activity.due_at.asc()))
    upcoming = rows(select(Activity).where(
        Activity.tenant_id == t, Activity.status == "pending",
        Activity.due_at.is_not(None), Activity.due_at >= day_start,
        Activity.due_at < day_start + timedelta(days=7),
        Activity.type.in_(["follow_up", "call", "meeting", "demo"]))
        .order_by(Activity.due_at.asc()))

    stale_cutoff = now - timedelta(days=RISK_RULES["lead_stale_days"])
    no_activity_leads = rows(select(Lead).where(
        Lead.tenant_id == t, Lead.status.in_(["new", "contacted"]),
        or_(Lead.last_activity_at.is_(None) & (Lead.created_at < stale_cutoff),
            Lead.last_activity_at < stale_cutoff)).order_by(Lead.created_at.asc()))
    opp_stale_cutoff = now - timedelta(days=RISK_RULES["opportunity_stale_days"])
    no_activity_opps = rows(select(Opportunity).where(
        Opportunity.tenant_id == t, Opportunity.status == "open",
        or_(Opportunity.last_activity_at.is_(None) & (Opportunity.created_at < opp_stale_cutoff),
            Opportunity.last_activity_at < opp_stale_cutoff))
        .order_by(Opportunity.created_at.asc()))

    return {
        "todays_tasks": [_act_brief(a) for a in todays_tasks],
        "overdue_tasks": [_act_brief(a) for a in overdue],
        "upcoming_followups": [_act_brief(a) for a in upcoming[:20]],
        "no_activity_leads": [{"id": l.id, "title": l.title, "status": l.status,
                               "owner_id": l.owner_id,
                               "last_activity_at": l.last_activity_at}
                              for l in no_activity_leads[:20]],
        "no_activity_opportunities": [{"id": o.id, "name": o.name,
                                       "organization_id": o.organization_id,
                                       "owner_id": o.owner_id,
                                       "last_activity_at": o.last_activity_at}
                                      for o in no_activity_opps[:20]],
        "counts": {
            "todays_tasks": len(todays_tasks),
            "overdue_tasks": len(overdue),
            "upcoming_followups_7d": len(upcoming),
            "no_activity_leads": len(no_activity_leads),
            "no_activity_opportunities": len(no_activity_opps),
        },
    }


def _act_brief(a: Activity) -> dict:
    return {"id": a.id, "type": a.type, "subject": a.subject, "due_at": a.due_at,
            "assigned_to": a.assigned_to, "priority": a.priority,
            "organization_id": a.organization_id, "lead_id": a.lead_id,
            "opportunity_id": a.opportunity_id, "status": a.status}


# ------------------------------------------------------------ pipeline board
def pipeline_board(session: Session, identity: Identity, pipeline_id: str | None = None) -> dict:
    t = identity.tenant_id
    from crm.services.pipelines import ensure_default_pipeline
    pipe = None
    if pipeline_id:
        from crm.services.common import get_tenant
        from crm.domain.models import Pipeline
        pipe = get_tenant(session, Pipeline, identity, pipeline_id)
    else:
        pipe = ensure_default_pipeline(session, identity)
    stages = list(session.execute(select(Stage).where(
        Stage.pipeline_id == pipe.id).order_by(Stage.order)).scalars().all())
    opps = list(session.execute(select(Opportunity).where(
        Opportunity.tenant_id == t, Opportunity.pipeline_id == pipe.id,
        Opportunity.status == "open")).scalars().all())
    org_names = {}
    for o in session.execute(select(Organization.id, Organization.name).where(
            Organization.tenant_id == t)).all():
        org_names[o[0]] = o[1]
    board = []
    totals_value = totals_weighted = 0
    for st in stages:
        cards = []
        for o in opps:
            if o.stage_id != st.id:
                continue
            na = session.execute(select(Activity).where(
                Activity.tenant_id == t, Activity.opportunity_id == o.id,
                Activity.status == "pending", Activity.due_at.is_not(None))
                .order_by(Activity.due_at.asc()).limit(1)).scalars().first()
            risk = opportunity_risk(o)
            cards.append({
                "id": o.id, "name": o.name,
                "organization_name": org_names.get(o.organization_id),
                "value": o.value, "probability": o.probability,
                "weighted_value": o.weighted_value, "currency": o.currency,
                "owner_id": o.owner_id, "expected_close_date": o.expected_close_date,
                "next_action": _act_brief(na) if na else None,
                "days_in_stage": (utcnow() - (o.stage_entered_at or o.created_at)).days,
                "risk_level": risk["risk_level"], "risk_flags": risk["flags"],
            })
        stage_value = sum(c["value"] for c in cards)
        totals_value += stage_value
        totals_weighted += sum(c["weighted_value"] for c in cards)
        board.append({"stage": {"id": st.id, "name": st.name, "order": st.order,
                                "color": st.color, "probability": st.probability},
                      "count": len(cards), "value": stage_value, "cards": cards})
    return {"pipeline": {"id": pipe.id, "name": pipe.name},
            "stages": board, "totals": {"value": totals_value,
                                        "weighted": totals_weighted}}


# ------------------------------------------------------------------ reports
def source_report(session: Session, identity: Identity) -> list[dict]:
    """Conversion funnel per lead source (deterministic SQL aggregation)."""
    from sqlalchemy import case
    t = identity.tenant_id
    rows = session.execute(
        select(Lead.source,
               func.count().label("total"),
               func.sum(case((Lead.status.in_(["qualified", "converted"]), 1),
                             else_=0)).label("qualified_plus"),
               func.sum(case((Lead.status == "converted", 1), else_=0)).label("converted"),
               func.sum(case((Lead.status == "lost", 1), else_=0)).label("lost"))
        .where(Lead.tenant_id == t).group_by(Lead.source)).all()
    out = []
    for r in rows:
        decided = (r.converted or 0) + (r.lost or 0)
        out.append({
            "source": r.source or "unknown",
            "leads": r.total,
            "qualified_or_converted": int(r.qualified_plus or 0),
            "converted": int(r.converted or 0),
            "lost": int(r.lost or 0),
            "conversion_rate_pct": round(int(r.converted or 0) / decided * 100, 1)
            if decided else 0.0,
        })
    return sorted(out, key=lambda x: -x["leads"])


# -------------------------------------------------------------------- CEO view
def ceo_dashboard(session: Session, identity: Identity) -> dict:
    t = identity.tenant_id
    now = utcnow()
    day_start, day_end = _today_bounds(now)

    # TODAY ---------------------------------------------------------------
    today_items = list(session.execute(select(Activity).where(
        Activity.tenant_id == t, Activity.status == "pending",
        Activity.due_at.is_not(None), Activity.due_at >= day_start,
        Activity.due_at < day_end).order_by(Activity.due_at)).scalars().all())
    meetings = [_act_brief(a) for a in today_items if a.type in ("meeting", "demo")]
    calls = [_act_brief(a) for a in today_items if a.type in ("call", "follow_up")]
    tasks = [_act_brief(a) for a in today_items if a.type == "task"]

    act = activity_metrics(session, identity)
    sales = sales_metrics(session, identity)

    # AT RISK ---------------------------------------------------------------
    stale_cutoff = now - timedelta(days=RISK_RULES["opportunity_stale_days"])
    open_opps = list(session.execute(select(Opportunity).where(
        Opportunity.tenant_id == t, Opportunity.status == "open")).scalars().all())
    at_risk = []
    for o in open_opps:
        r = opportunity_risk(o)
        if r["risk_score"] >= 30:
            at_risk.append({"id": o.id, "name": o.name, "value": o.value,
                            "probability": o.probability, "owner_id": o.owner_id,
                            "risk_score": r["risk_score"], "risk_level": r["risk_level"],
                            "flags": r["flags"],
                            "days_inactive": (now - (o.last_activity_at or o.created_at)).days})
    at_risk.sort(key=lambda x: -x["risk_score"])

    # OPPORTUNITIES -----------------------------------------------------------
    hot_leads = []
    leads = list(session.execute(select(Lead).where(
        Lead.tenant_id == t, Lead.status.in_(["new", "contacted", "qualified"]))
        .order_by(Lead.score.desc()).limit(50)).scalars().all())
    for l in leads:
        lr = lead_risk(l)
        if l.score >= RISK_RULES["hot_lead_score"]:
            hot_leads.append({"id": l.id, "title": l.title, "score": l.score,
                              "status": l.status, "estimated_value": l.estimated_value,
                              "owner_id": l.owner_id, "cooling": lr["flags"]["stale"]})
    high_value = [{"id": o.id, "name": o.name, "value": o.value,
                   "probability": o.probability, "weighted_value": o.weighted_value,
                   "expected_close_date": o.expected_close_date, "owner_id": o.owner_id}
                  for o in sorted([o for o in open_opps if o.status == "open"],
                                  key=lambda x: -x.weighted_value)[:10]]

    # expansion candidates: customers with a won deal and an open opportunity
    won_org_ids = set(session.execute(select(Opportunity.organization_id).where(
        Opportunity.tenant_id == t, Opportunity.status == "won")).scalars().all())
    open_org_ids = set(session.execute(select(Opportunity.organization_id).where(
        Opportunity.tenant_id == t, Opportunity.status == "open")).scalars().all())
    expansion_ids = won_org_ids & open_org_ids
    expansion = [{"id": oid, "name": n} for oid, n in
                 session.execute(select(Organization.id, Organization.name).where(
                     Organization.tenant_id == t,
                     Organization.id.in_(expansion_ids or {"-1"}))) ] if expansion_ids else []

    # RECENT -------------------------------------------------------------------
    def recent(model, fields):
        rows = list(session.execute(select(model).where(
            model.tenant_id == t).order_by(model.created_at.desc()).limit(5)
        ).scalars().all())
        return [{k: getattr(r, k) for k in ["id"] + fields} for r in rows]

    return {
        "today": {"tasks": tasks, "calls_and_followups": calls, "meetings": meetings,
                  "overdue_count": act["counts"]["overdue_tasks"]},
        "sales": sales,
        "at_risk": {"deals": at_risk[:15],
                    "no_next_action_count": sum(1 for o in open_opps
                                                if o.next_activity_at is None),
                    "aging_overdue_tasks": act["overdue_tasks"][:15]},
        "opportunities": {"hot_leads": hot_leads[:10],
                          "high_value_deals": high_value,
                          "expansion_customers": expansion[:10]},
        "recent": {"customers": recent(Organization, ["name", "type", "owner_id"]),
                   "leads": recent(Lead, ["title", "status", "score", "owner_id"]),
                   "opportunities": recent(Opportunity, ["name", "status", "value",
                                                          "stage_id", "owner_id"])},
        "activity": act["counts"],
    }
