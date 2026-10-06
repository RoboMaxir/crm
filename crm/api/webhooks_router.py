"""/api/v1/webhooks — endpoint management + delivery log (signed, retried)."""
from __future__ import annotations

from fastapi import Depends, APIRouter, Body, Query

from crm.api.deps import DB, IDP
from crm.core.auth import PERM_MANAGE, require
from crm.domain.models import WebhookEndpoint
from crm.services import webhooks as svc

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _endpoint_view(ep: WebhookEndpoint) -> dict:
    """Safe projection — never expose the signing secret over the API."""
    return {"id": ep.id, "tenant_id": ep.tenant_id, "url": ep.url,
            "events": ep.events, "active": ep.active,
            "created_at": ep.created_at.isoformat(),
            "updated_at": ep.updated_at.isoformat()}


@router.get("")
def list_endpoints(db=DB, me=IDP):
    return {"items": [_endpoint_view(e) for e in svc.list_endpoints(db, me)]}


@router.post("", status_code=201)
def create_endpoint(data: dict = Body(...), db=DB, me=Depends(require(PERM_MANAGE))):
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        from crm.services.common import unprocessable
        raise unprocessable("Webhook url must be http(s)")
    ep = svc.create_endpoint(db, me, url, data.get("events"),
                             secret=data.get("secret"),
                             active=bool(data.get("active", True)))
    return _endpoint_view(ep)


# static path before dynamic "/{eid}"
@router.get("/deliveries")
def deliveries(db=DB, me=IDP, limit: int = Query(100, ge=1, le=500)):
    rows = svc.list_deliveries(db, me, limit=limit)
    return {"items": [{**r, "created_at": r["created_at"].isoformat(),
                       "delivered_at": r["delivered_at"].isoformat()
                       if r["delivered_at"] else None} for r in rows]}


@router.post("/dispatch")
def dispatch(db=DB, me=Depends(require(PERM_MANAGE)),
             limit: int = Query(50, ge=1, le=200)):
    """Manually trigger due deliveries (scheduler seam)."""
    return svc.dispatch_due(db, limit=limit)


@router.delete("/{eid}", status_code=204)
def delete_endpoint(eid: str, db=DB, me=Depends(require(PERM_MANAGE))):
    from crm.services.common import not_found
    if not svc.delete_endpoint(db, me, eid):
        raise not_found("WebhookEndpoint")
