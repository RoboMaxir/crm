"""/api/v1/contacts"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from crm.api.deps import DB, IDP, coerce_dates, dump
from crm.core.auth import PERM_CREATE, PERM_DELETE, PERM_UPDATE, require
from crm.services import orgs
from crm.services.tags_bridge import set_entity_tags, tags_of

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _view(db, me, c):
    d = dump(c)
    d["full_name"] = c.full_name
    d["tags"] = tags_of(db, me, "contact", c.id)
    return d


@router.get("")
def list_contacts(db=DB, me=IDP, q: str | None = None, status: str | None = None,
                  organization_id: str | None = None, owner_id: str | None = None,
                  tag: str | None = None, sort: str | None = None, order: str = "desc",
                  page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    res = orgs.list_contacts(db, me, q=q, status=status, organization_id=organization_id,
                             owner_id=owner_id, tag=tag, sort=sort, order=order,
                             page=page, per_page=per_page)
    return {"items": [_view(db, me, c) for c in res["items"]],
            "total": res["total"], "page": res["page"], "per_page": res["per_page"],
            "pages": res["pages"]}


@router.post("", status_code=201)
def create_contact(data: dict = Body(...), db=DB, me=IDP(require(PERM_CREATE))):
    return _view(db, me, orgs.create_contact(db, me, coerce_dates(dict(data))))


@router.get("/{cid}")
def get_contact(cid: str, db=DB, me=IDP):
    return _view(db, me, orgs.get_contact(db, me, cid))


@router.patch("/{cid}")
def update_contact(cid: str, data: dict = Body(...), db=DB,
                   me=IDP(require(PERM_UPDATE))):
    return _view(db, me, orgs.update_contact(db, me, cid, coerce_dates(dict(data))))


@router.delete("/{cid}", status_code=204)
def delete_contact(cid: str, db=DB, me=IDP(require(PERM_DELETE))):
    orgs.delete_contact(db, me, cid)


@router.put("/{cid}/tags")
def replace_tags(cid: str, tags: list[str] = Body(...), db=DB,
                 me=IDP(require(PERM_UPDATE))):
    return {"tags": set_entity_tags(db, me, "contact", cid, tags)}
