"""/api/v1/dashboard — operational KPIs, Kanban board, CEO view, reports."""
from __future__ import annotations

from fastapi import APIRouter, Query

from crm.api.deps import DB, IDP
from crm.services import dashboard as svc


def _json_safe(obj):
    """Recursively convert datetimes to ISO strings for the response."""
    if hasattr(obj, "isoformat") and not isinstance(obj, str):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
def full_dashboard(db=DB, me=IDP):
    return _json_safe({"sales": svc.sales_metrics(db, me),
                       "activity": svc.activity_metrics(db, me)})


@router.get("/sales")
def sales(db=DB, me=IDP):
    return _json_safe(svc.sales_metrics(db, me))


@router.get("/activity")
def activity(db=DB, me=IDP):
    return _json_safe(svc.activity_metrics(db, me))


@router.get("/pipeline")
def pipeline(db=DB, me=IDP, pipeline_id: str | None = Query(None)):
    return _json_safe(svc.pipeline_board(db, me, pipeline_id))


@router.get("/ceo")
def ceo(db=DB, me=IDP):
    return _json_safe(svc.ceo_dashboard(db, me))


@router.get("/sources")
def sources(db=DB, me=IDP):
    return {"items": _json_safe(svc.source_report(db, me))}
