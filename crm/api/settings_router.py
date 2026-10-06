"""/api/v1/settings — tenant settings + canonical enumerations (read-mostly).

Tenant preferences are stored in a dedicated table so no DB architecture
change was needed elsewhere; the list endpoint is available to any
authenticated member, mutations require 'manage'.
"""
from __future__ import annotations

import json

from fastapi import Depends, APIRouter, Body
from sqlalchemy import select

from crm.api.deps import DB, IDP
from crm.core.auth import PERM_MANAGE, require
from crm.core.config import RISK_RULES
from crm.domain.enums import (ActivityStatus, ActivityType, LeadStatus,
                              OpportunityStatus, OrganizationType, Priority,
                              Qualification)
from crm.domain.models import TenantSetting
from crm.services.common import unprocessable

router = APIRouter(prefix="/settings", tags=["settings"])


def _values(e):
    return [m.value for m in e]


@router.get("/enums")
def enums(db=DB, me=IDP):
    """Canonical domain vocabularies — single source of truth for clients."""
    from crm.domain.enums import LEAD_LOST_REASONS, LEAD_SOURCES, OPPORTUNITY_LOST_REASONS
    return {
        "organization_types": _values(OrganizationType),
        "lead_statuses": _values(LeadStatus),
        "lead_qualifications": _values(Qualification),
        "lead_sources": LEAD_SOURCES,
        "lead_lost_reasons": LEAD_LOST_REASONS,
        "opportunity_statuses": _values(OpportunityStatus),
        "opportunity_lost_reasons": OPPORTUNITY_LOST_REASONS,
        "activity_types": _values(ActivityType),
        "activity_statuses": _values(ActivityStatus),
        "priorities": _values(Priority),
    }


@router.get("/risk-rules")
def risk_rules(db=DB, me=IDP):
    """Documented deterministic thresholds behind every risk flag."""
    return dict(RISK_RULES)


@router.get("")
def get_settings(db=DB, me=IDP):
    row = db.execute(select(TenantSetting).where(
        TenantSetting.tenant_id == me.tenant_id)).scalars().first()
    return json.loads(row.data_json) if row else {}


@router.put("")
def put_settings(data: dict = Body(...), db=DB, me=Depends(require(PERM_MANAGE))):
    if not isinstance(data, dict):
        raise unprocessable("Settings payload must be an object")
    row = db.execute(select(TenantSetting).where(
        TenantSetting.tenant_id == me.tenant_id)).scalars().first()
    if row is None:
        row = TenantSetting(tenant_id=me.tenant_id, data_json=json.dumps(data))
        db.add(row)
    else:
        merged = json.loads(row.data_json or "{}")
        merged.update(data)
        row.data_json = json.dumps(merged)
    db.flush()
    return json.loads(row.data_json)
