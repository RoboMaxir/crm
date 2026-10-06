"""/api/v1/leads — thin HTTP layer over crm.services.leads."""
from __future__ import annotations

from fastapi import Depends, APIRouter, Body, Query

from crm.api.deps import DB, IDP, coerce_dates
from crm.core.auth import PERM_ASSIGN, PERM_CREATE, PERM_UPDATE, require
from crm.services import leads as svc
from crm.services.tags_bridge import set_entity_tags, tags_of

router = APIRouter(prefix="/leads", tags=["leads"])


def _view(db, me, lead) -> dict:
    d = svc.lead_view(db, me, lead)
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
    d["tags"] = tags_of(db, me, "lead", lead.id)
    return d


@router.get("")
def list_leads(db=DB, me=IDP, q: str | None = None, status: str | None = None,
               source: str | None = None, owner_id: str | None = None,
               score__gte: int | None = None, tag: str | None = None,
               sort: str | None = None, order: str = "desc",
               page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    res = svc.list_leads(db, me, q=q, status=status, source=source, owner_id=owner_id,
                         score__gte=score__gte, tag=tag, sort=sort, order=order,
                         page=page, per_page=per_page)
    return {"items": [_view(db, me, l) for l in res["items"]],
            "total": res["total"], "page": res["page"], "per_page": res["per_page"],
            "pages": res["pages"]}


@router.post("", status_code=201)
def create_lead(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    return _view(db, me, svc.create_lead(db, me, coerce_dates(dict(data))))


@router.get("/{lid}")
def get_lead(lid: str, db=DB, me=IDP):
    return _view(db, me, svc.get_lead(db, me, lid))


@router.patch("/{lid}")
def update_lead(lid: str, data: dict = Body(...), db=DB,
                me=Depends(require(PERM_UPDATE))):
    if data.get("owner_id") and not me.can(PERM_ASSIGN):
        from crm.services.common import unprocessable
        raise unprocessable("Role lacks 'assign' permission to change owner")
    return _view(db, me, svc.update_lead(db, me, lid, coerce_dates(dict(data))))


@router.post("/{lid}/convert")
def convert_lead(lid: str, data: dict = Body(default={}), db=DB,
                 me=Depends(require(PERM_CREATE))):
    res = svc.convert_lead(db, me, lid, coerce_dates(dict(data)))
    return {
        "lead": _view(db, me, res["lead"]),
        "organization": _plain(res["organization"]),
        "contact": _plain(res["contact"]) if res["contact"] else None,
        "opportunity": _plain(res["opportunity"]),
    }


@router.post("/{lid}/lose")
def lose_lead(lid: str, data: dict = Body(default={}), db=DB,
              me=Depends(require(PERM_UPDATE))):
    return _view(db, me, svc.mark_lost(db, me, lid, data.get("lost_reason")))


@router.put("/{lid}/tags")
def replace_tags(lid: str, tags: list[str] = Body(...), db=DB,
                 me=Depends(require(PERM_UPDATE))):
    return {"tags": set_entity_tags(db, me, "lead", lid, tags)}


def _plain(obj) -> dict:
    out = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.key)
        out[c.key] = v.isoformat() if hasattr(v, "isoformat") else v
    return out
