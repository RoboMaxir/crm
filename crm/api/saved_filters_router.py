"""/api/v1/saved-filters — user-saved list views (entity + query params)."""
from __future__ import annotations

import json

from fastapi import Depends, APIRouter, Body, Query
from sqlalchemy import select

from crm.api.deps import DB, IDP
from crm.core.auth import PERM_CREATE, PERM_DELETE, require
from crm.domain.models import SavedFilter
from crm.services.common import get_tenant, not_found, unprocessable

router = APIRouter(prefix="/saved-filters", tags=["saved-filters"])

ALLOWED_ENTITIES = {"organizations", "contacts", "leads", "opportunities", "activities"}


def _view(f: SavedFilter) -> dict:
    return {"id": f.id, "entity": f.entity, "name": f.name,
            "user_id": f.user_id, "params": json.loads(f.params_json or "{}"),
            "created_at": f.created_at.isoformat()}


@router.get("")
def list_filters(db=DB, me=IDP, entity: str | None = None):
    stmt = select(SavedFilter).where(SavedFilter.tenant_id == me.tenant_id)
    if entity:
        stmt = stmt.where(SavedFilter.entity == entity)
    rows = db.execute(stmt.order_by(SavedFilter.created_at)).scalars().all()
    return {"items": [_view(f) for f in rows]}


@router.post("", status_code=201)
def create_filter(data: dict = Body(...), db=DB, me=Depends(require(PERM_CREATE))):
    entity = data.get("entity")
    name = (data.get("name") or "").strip()
    if entity not in ALLOWED_ENTITIES:
        raise unprocessable(f"entity must be one of {sorted(ALLOWED_ENTITIES)}")
    if not name:
        raise unprocessable("name is required")
    f = SavedFilter(tenant_id=me.tenant_id, user_id=me.user_id, entity=entity,
                    name=name, params_json=json.dumps(data.get("params") or {}))
    db.add(f)
    db.flush()
    return _view(f)


@router.delete("/{fid}", status_code=204)
def delete_filter(fid: str, db=DB, me=Depends(require(PERM_DELETE))):
    f = get_tenant(db, SavedFilter, me, fid)
    # only owner or a manager/admin may remove someone else's filter
    if f.user_id and f.user_id != me.user_id and not me.can("manage"):
        raise not_found("SavedFilter")
    db.delete(f)
    db.flush()
