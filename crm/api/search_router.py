"""/api/v1/search — global tenant-scoped search across all CRM records."""
from __future__ import annotations

from fastapi import APIRouter, Query

from crm.api.deps import DB, IDP
from crm.api.dashboard_router import _json_safe
from crm.services import search as svc

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def global_search(db=DB, me=IDP, q: str = Query(..., min_length=1),
                  limit_per_type: int = Query(10, ge=1, le=50)):
    return _json_safe(svc.global_search(db, me, q, limit_per_type))
