"""/api/v1/organizations — Customers & Companies."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Query

from crm.api.deps import DB, IDP, coerce_dates, dump
from crm.core.auth import PERM_CREATE, PERM_DELETE, PERM_UPDATE, require
from crm.services import customer360, orgs
from crm.services.tags_bridge import set_entity_tags, tags_of

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("")
def list_orgs(db=DB, me=IDP, q: str | None = None, status: str | None = None,
              type: str | None = None, owner_id: str | None = None,
              city: str | None = None, tag: str | None = None,
              sort: str | None = None, order: str = "desc",
              page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    res = orgs.list_organizations(db, me, q=q, status=status, type=type,
                                  owner_id=owner_id, city=city, tag=tag,
                                  sort=sort, order=order, page=page, per_page=per_page)
    return {"items": [dump(o) | {"tags": tags_of(db, me, "organization", o.id)}
                      for o in res["items"]],
            "total": res["total"], "page": res["page"], "per_page": res["per_page"],
            "pages": res["pages"]}


@router.post("", status_code=201)
def create_org(data: dict = Body(...), db=DB, me=IDP(require(PERM_CREATE))):
    return dump(orgs.create_organization(db, me, coerce_dates(dict(data))))


@router.get("/{oid}")
def get_org(oid: str, db=DB, me=IDP):
    return dump(orgs.get_organization(db, me, oid)) | \
        {"tags": tags_of(db, me, "organization", oid)}


@router.patch("/{oid}")
def update_org(oid: str, data: dict = Body(...), db=DB, me=IDP(require(PERM_UPDATE))):
    return dump(orgs.update_organization(db, me, oid, coerce_dates(dict(data))))


@router.delete("/{oid}", status_code=204)
def delete_org(oid: str, db=DB, me=IDP(require(PERM_DELETE))):
    orgs.delete_organization(db, me, oid)


@router.get("/{oid}/360")
def customer_360_view(oid: str, db=DB, me=IDP):
    return customer360.customer_360(db, me, oid)


@router.put("/{oid}/tags")
def replace_tags(oid: str, tags: list[str] = Body(...), db=DB,
                 me=IDP(require(PERM_UPDATE))):
    return {"tags": set_entity_tags(db, me, "organization", oid, tags)}
