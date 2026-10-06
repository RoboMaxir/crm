"""/api/v1/tags — generic tag system (usable on all CRM entities)."""
from __future__ import annotations

from fastapi import Depends, APIRouter, Body

from crm.api.deps import DB, IDP, dump
from crm.core.auth import PERM_CREATE, PERM_DELETE, PERM_UPDATE, require
from crm.domain.models import Tag, TaggedItem
from crm.services import orgs as org_svc
from crm.services.common import get_tenant, not_found, unprocessable
from crm.services.tags_bridge import (TAGGABLE_MODELS, entity_ids_with_tag,
                                      set_entity_tags, tags_of)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
def list_tags(db=DB, me=IDP):
    return {"items": [dump(t) for t in org_svc.list_tags(db, me)]}


@router.post("", status_code=201)
def create_tag(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    name = (data.get("name") or "").strip()
    if not name:
        raise unprocessable("Tag name required")
    return dump(org_svc.ensure_tag(db, me, name))


# NOTE: static sub-path routes are declared BEFORE the "/{tid}" dynamic route
# so "/tags/lead/{id}" is never swallowed by the id-based delete/get.
@router.get("/{entity}/{entity_id}")
def get_entity_tags(entity: str, entity_id: str, db=DB, me=IDP):
    if entity not in TAGGABLE_MODELS:
        raise not_found(f"Taggable entity type '{entity}'")
    return {"tags": tags_of(db, me, entity, entity_id)}


@router.put("/{entity}/{entity_id}")
def replace_entity_tags(entity: str, entity_id: str, tags: list[str] = Body(...),
                        db=DB, me=Depends(require(PERM_UPDATE))):
    if entity not in TAGGABLE_MODELS:
        raise not_found(f"Taggable entity type '{entity}'")
    return {"tags": set_entity_tags(db, me, entity, entity_id, tags)}


@router.delete("/{tid}", status_code=204)
def delete_tag(tid: str, db=DB, me=Depends(require(PERM_DELETE))):
    tag = get_tenant(db, Tag, me, tid)
    db.query(TaggedItem).filter(TaggedItem.tag_id == tid).delete()
    db.delete(tag)
    db.flush()
