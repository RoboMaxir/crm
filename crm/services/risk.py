"""Deterministic risk engine — NO AI/LLM here, by design.

Risk is a pure function of stored CRM state + documented thresholds
(crm.core.config.RISK_RULES). The Intelligence layer may later CONSUME these
signals; it must never be required to produce them.

Opportunity risk_score (0..100):
    stale_score        up to 35  (no logged activity for >= stale_days)
    overdue_score      up to 25  (next_activity_at in the past)
    aging_score        up to 25  (days in current stage vs aging_stage_days)
    no_next_action     up to 15  (open deal with no scheduled next action)

Lead risk (cooling) mirrors the same shape with tighter thresholds.
"""
from __future__ import annotations

from crm.core.config import RISK_RULES
from crm.domain.models import Lead, Opportunity, utcnow


def _days_since(dt) -> int | None:
    if dt is None:
        return None
    return max(0, (utcnow() - dt).days)


def opportunity_risk(opp: Opportunity) -> dict:
    now = utcnow()
    flags: dict[str, bool] = {}
    score = 0
    detail: dict[str, int] = {}

    # --- stale --------------------------------------------------------------
    days_inactive = _days_since(opp.last_activity_at or opp.created_at)
    stale_days = RISK_RULES["opportunity_stale_days"]
    stale = days_inactive is not None and days_inactive >= stale_days
    flags["stale"] = bool(stale and opp.status == "open")
    stale_score = 0
    if flags["stale"]:
        stale_score = min(35, 15 + (days_inactive - stale_days) * 2)
    detail["stale_score"] = stale_score

    # --- overdue ------------------------------------------------------------
    overdue = bool(opp.next_activity_at and opp.next_activity_at < now
                   and opp.status == "open")
    flags["overdue"] = overdue
    overdue_score = 25 if overdue else 0
    detail["overdue_score"] = overdue_score

    # --- aging in stage -------------------------------------------------------
    aging_days = _days_since(opp.stage_entered_at or opp.created_at)
    flags["aging"] = False
    aging_score = 0
    if opp.status == "open" and aging_days is not None:
        limit = RISK_RULES["aging_stage_days"]
        if aging_days > limit:
            aging_score = min(25, (aging_days - limit))
            flags["aging"] = aging_days >= limit * 2
    detail["aging_score"] = aging_score
    detail["days_in_stage"] = aging_days or 0

    # --- no next action --------------------------------------------------------
    no_next = opp.next_activity_at is None and opp.status == "open"
    flags["no_next_action"] = no_next
    nna_score = 15 if no_next else 0
    detail["no_next_action_score"] = nna_score

    score = min(100, stale_score + overdue_score + aging_score + nna_score)
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    return {"flags": flags, "risk_score": score, "risk_level": level, "detail": detail}


def lead_risk(lead: Lead) -> dict:
    now = utcnow()
    flags: dict[str, bool] = {}
    detail: dict[str, int] = {}
    closed = lead.status in ("converted", "lost", "unqualified")

    days_inactive = _days_since(lead.last_activity_at or lead.created_at)
    stale_days = RISK_RULES["lead_stale_days"]
    stale = days_inactive is not None and days_inactive >= stale_days and not closed
    flags["stale"] = bool(stale)
    stale_score = min(40, 20 + (days_inactive - stale_days) * 3) if stale else 0
    detail["stale_score"] = stale_score

    overdue = bool(lead.next_activity_at and lead.next_activity_at < now and not closed)
    flags["overdue"] = overdue
    detail["overdue_score"] = 30 if overdue else 0

    no_next = lead.next_activity_at is None and not closed
    flags["no_next_action"] = no_next
    detail["no_next_action_score"] = 20 if no_next else 0

    no_contact = lead.status == "new" and lead.last_activity_at is None
    flags["never_contacted"] = no_contact
    detail["never_contacted_score"] = 10 if no_contact else 0

    score = min(100, sum(detail.values()))
    level = "high" if score >= 60 else "medium" if score >= 30 else "low"
    return {"flags": flags, "risk_score": score, "risk_level": level, "detail": detail}
