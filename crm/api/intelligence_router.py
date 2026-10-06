"""/api/v1/intelligence — CONSUMER-side store for insights pushed by the
external Intelligence layer (Shora/OrgOS). The CRM never computes these;
they are read-only context surfaced in Customer 360. Core business logic
must never depend on them (by architectural rule)."""
from __future__ import annotations

import json

from fastapi import Depends, APIRouter, Body, Query
from sqlalchemy import select

from crm.api.deps import DB, IDP
from crm.core.auth import PERM_MANAGE, PERM_VIEW, require
from crm.domain.models import IntelligenceItem
from crm.services.common import get_tenant, not_found, unprocessable

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _view(i: IntelligenceItem) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in {c.key: getattr(i, c.key)
                         for c in IntelligenceItem.__table__.columns}.items()}


@router.get("")
def list_items(db=DB, me=Depends(require(PERM_VIEW)), entity: str | None = None,
               entity_id: str | None = None, kind: str | None = None,
               page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    stmt = select(IntelligenceItem).where(IntelligenceItem.tenant_id == me.tenant_id)
    filters = {"entity": entity, "entity_id": entity_id, "kind": kind}
    from crm.services.common import apply_list_query, finalize_list
    stmt, count_stmt = apply_list_query(stmt, filters=filters, model=IntelligenceItem)
    res = finalize_list(db, stmt, count_stmt, IntelligenceItem, sort="created_at",
                        order="desc", page=page, per_page=per_page)
    return {"items": [_view(i) for i in res["items"]], "total": res["total"],
            "page": res["page"], "per_page": res["per_page"], "pages": res["pages"]}


@router.post("", status_code=201)
def push_item(data: dict = Body(...), db=DB, me=Depends(require(PERM_MANAGE))):
    """Ingestion endpoint for the Intelligence layer (service credential)."""
    for f in ("entity", "entity_id", "kind", "text"):
        if not data.get(f):
            raise unprocessable(f"'{f}' is required")
    item = IntelligenceItem(
        tenant_id=me.tenant_id, entity=data["entity"], entity_id=data["entity_id"],
        kind=data["kind"], text=data["text"],
        source_system=data.get("source_system", "shora"),
        confidence=float(data.get("confidence", 0.0)))
    db.add(item)
    db.flush()
    return _view(item)


@router.delete("/{iid}", status_code=204)
def delete_item(iid: str, db=DB, me=Depends(require(PERM_MANAGE))):
    item = get_tenant(db, IntelligenceItem, me, iid)
    db.delete(item)
    db.flush()
