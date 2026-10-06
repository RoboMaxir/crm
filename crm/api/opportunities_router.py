"""/api/v1/opportunities — thin HTTP layer over crm.services.opportunities."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, APIRouter, Body, Query

from crm.api.deps import DB, IDP, coerce_dates
from crm.core.auth import PERM_ASSIGN, PERM_CREATE, PERM_UPDATE, require
from crm.services import opportunities as svc
from crm.services.tags_bridge import set_entity_tags, tags_of

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _view(db, me, opp) -> dict:
    d = svc.opportunity_view(db, me, opp)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif isinstance(v, dict):
            d[k] = {kk: (vv.isoformat() if isinstance(vv, datetime) else vv)
                    for kk, vv in v.items()}
    d["tags"] = tags_of(db, me, "opportunity", opp.id)
    return d


@router.get("")
def list_opps(db=DB, me=IDP, q: str | None = None, status: str | None = None,
              stage_id: str | None = None, pipeline_id: str | None = None,
              owner_id: str | None = None, organization_id: str | None = None,
              value__gt: int | None = None, value__lt: int | None = None,
              tag: str | None = None,
              expected_close_before: datetime | None = None,
              expected_close_after: datetime | None = None,
              sort: str | None = None, order: str = "desc",
              page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    res = svc.list_opportunities(db, me, q=q, status=status, stage_id=stage_id,
                                 pipeline_id=pipeline_id, owner_id=owner_id,
                                 organization_id=organization_id,
                                 value__gt=value__gt, value__lt=value__lt, tag=tag,
                                 expected_close_before=expected_close_before,
                                 expected_close_after=expected_close_after,
                                 sort=sort, order=order, page=page, per_page=per_page)
    return {"items": [_view(db, me, o) for o in res["items"]],
            "total": res["total"], "page": res["page"], "per_page": res["per_page"],
            "pages": res["pages"]}


@router.post("", status_code=201)
def create_opp(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    return _view(db, me, svc.create_opportunity(db, me, coerce_dates(dict(data))))


@router.get("/{oid}")
def get_opp(oid: str, db=DB, me=IDP):
    return _view(db, me, svc.get_opportunity(db, me, oid))


@router.patch("/{oid}")
def update_opp(oid: str, data: dict = Body(...), db=DB, me=Depends(require(PERM_UPDATE))):
    if data.get("owner_id") and not me.can(PERM_ASSIGN):
        from crm.services.common import unprocessable
        raise unprocessable("Role lacks 'assign' permission to change owner")
    return _view(db, me, svc.update_opportunity(db, me, oid, coerce_dates(dict(data))))


@router.post("/{oid}/move-stage")
def move_stage(oid: str, data: dict = Body(...), db=DB, me=Depends(require(PERM_UPDATE))):
    """Explicit stage transition endpoint (Kanban drag-drop target)."""
    opp = svc.move_stage(db, me, oid, data["stage_id"],
                         lost_reason=data.get("lost_reason"),
                         probability_override=data.get("probability"))
    return _view(db, me, opp)


@router.post("/{oid}/reopen")
def reopen(oid: str, data: dict = Body(...), db=DB, me=Depends(require(PERM_UPDATE))):
    return _view(db, me, svc.reopen(db, me, oid, data["stage_id"]))


@router.put("/{oid}/tags")
def replace_tags(oid: str, tags: list[str] = Body(...), db=DB,
                 me=Depends(require(PERM_UPDATE))):
    return {"tags": set_entity_tags(db, me, "opportunity", oid, tags)}
