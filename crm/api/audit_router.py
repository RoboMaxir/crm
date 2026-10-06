"""/api/v1/audit — read-only audit trail (tenant-scoped)."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, APIRouter, Query
from sqlalchemy import select

from crm.api.deps import DB, IDP
from crm.core.auth import PERM_VIEW, require
from crm.domain.models import AuditLog
from crm.services.common import apply_list_query, finalize_list

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit(db=DB, me=Depends(require(PERM_VIEW)), entity: str | None = None,
               entity_id: str | None = None, action: str | None = None,
               actor_id: str | None = None, created_after: datetime | None = None,
               sort: str | None = None, order: str = "desc",
               page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    stmt = select(AuditLog).where(AuditLog.tenant_id == me.tenant_id)
    filters = {"entity": entity, "entity_id": entity_id, "action": action,
               "actor_id": actor_id}
    if created_after:
        filters["created_at__gte"] = created_after
    stmt, count_stmt = apply_list_query(stmt, filters=filters, model=AuditLog)
    res = finalize_list(db, stmt, count_stmt, AuditLog, sort=sort or "created_at",
                        order=order, page=page, per_page=per_page)
    items = []
    for a in res["items"]:
        import json
        items.append({"id": a.id, "actor_id": a.actor_id, "action": a.action,
                      "entity": a.entity, "entity_id": a.entity_id,
                      "before": json.loads(a.before_json) if a.before_json else None,
                      "after": json.loads(a.after_json) if a.after_json else None,
                      "timestamp": a.created_at.isoformat()})
    return {"items": items, "total": res["total"], "page": res["page"],
            "per_page": res["per_page"], "pages": res["pages"]}


@router.get("/events")
def list_events(db=DB, me=Depends(require(PERM_VIEW)), event_type: str | None = None,
                entity: str | None = None, entity_id: str | None = None,
                page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    """Outbox view — the canonical event stream OrgOS/Shora consume."""
    import json
    from crm.domain.models import DomainEvent
    stmt = select(DomainEvent).where(DomainEvent.tenant_id == me.tenant_id)
    filters = {"event_type": event_type, "entity": entity, "entity_id": entity_id}
    stmt, count_stmt = apply_list_query(stmt, filters=filters, model=DomainEvent)
    res = finalize_list(db, stmt, count_stmt, DomainEvent, sort="occurred_at",
                        order="desc", page=page, per_page=per_page)
    items = [{"id": e.id, "event": e.event_type, "entity": e.entity,
              "entity_id": e.entity_id, "payload": json.loads(e.payload or "{}"),
              "actor_id": e.actor_id, "occurred_at": e.occurred_at.isoformat(),
              "delivered": e.delivered} for e in res["items"]]
    return {"items": items, "total": res["total"], "page": res["page"],
            "per_page": res["per_page"], "pages": res["pages"]}
