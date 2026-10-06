"""Webhook infrastructure: endpoints, signed payloads, retry with backoff.

Delivery model (MVP): durable queue + dispatcher.
  * enqueue_deliveries() runs INSIDE the state-change transaction (reads the
    outbox events flushed in that same transaction) -> at-least-once semantics.
  * dispatch_due() is called by a scheduler/worker (or manually); it retries
    with exponential backoff and records status per attempt.
  * Payloads are HMAC-SHA256 signed (X-CRM-Signature header) so receivers can
    verify authenticity — contract for OrgOS consumption.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.request
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.core.config import WEBHOOK_SECRET
from crm.domain.models import DomainEvent, WebhookDelivery, WebhookEndpoint, utcnow

RETRY_BASE_SECONDS = 30   # 30s, 60s, 120s, 240s, 480s


def sign(secret: str, body: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def create_endpoint(session: Session, identity: Identity, url: str,
                    events: list[str] | None, secret: str | None = None,
                    active: bool = True) -> WebhookEndpoint:
    ep = WebhookEndpoint(tenant_id=identity.tenant_id, url=url.strip(),
                         events=",".join(events) if events else "*",
                         secret=secret or WEBHOOK_SECRET, active=active)
    session.add(ep)
    session.flush()
    return ep


def list_endpoints(session: Session, identity: Identity):
    return list(session.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == identity.tenant_id)
        .order_by(WebhookEndpoint.created_at)).scalars().all())


def delete_endpoint(session: Session, identity: Identity, eid: str) -> bool:
    ep = session.get(WebhookEndpoint, eid)
    if ep is None or ep.tenant_id != identity.tenant_id:
        return False
    session.delete(ep)
    session.flush()
    return True


def _wants(ep: WebhookEndpoint, event_type: str) -> bool:
    if ep.events == "*":
        return True
    return event_type in [e.strip() for e in ep.events.split(",")]


def enqueue_deliveries(session: Session, since_minutes: int = 60) -> int:
    """Queue deliveries for undelivered outbox events (called post-commit or
    within the same unit of work; idempotent via DomainEvent.delivered flag)."""
    cutoff = utcnow() - timedelta(minutes=since_minutes)
    events = list(session.execute(select(DomainEvent).where(
        DomainEvent.delivered.is_(False),
        DomainEvent.occurred_at >= cutoff)).scalars().all())
    endpoints = list(session.execute(select(WebhookEndpoint).where(
        WebhookEndpoint.active.is_(True))).scalars().all())
    n = 0
    for ev in events:
        for ep in endpoints:
            if ep.tenant_id != ev.tenant_id or not _wants(ep, ev.event_type):
                continue
            body = json.dumps({
                "event": ev.event_type, "tenant_id": ev.tenant_id,
                "entity": ev.entity, "entity_id": ev.entity_id,
                "payload": json.loads(ev.payload or "{}"),
                "actor_id": ev.actor_id,
                "occurred_at": ev.occurred_at.isoformat(),
                "event_id": ev.id,
            }, ensure_ascii=False, sort_keys=True)
            session.add(WebhookDelivery(
                tenant_id=ev.tenant_id, endpoint_id=ep.id, event_type=ev.event_type,
                payload=body, signature=sign(ep.secret or WEBHOOK_SECRET, body),
                next_retry_at=utcnow()))
            n += 1
        ev.delivered = True  # fan-out queued; per-endpoint status tracked on delivery rows
    session.flush()
    return n


class DeliveryTransport:
    """Network seam; tests inject a fake."""

    def post(self, url: str, body: str, signature: str, event_type: str) -> tuple[int, str]:
        req = urllib.request.Request(url, data=body.encode(), method="POST", headers={
            "Content-Type": "application/json",
            "X-CRM-Event": event_type,
            "X-CRM-Signature": f"sha256={signature}",
        })
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, ""
        except Exception as exc:  # noqa: BLE001 – record any transport error
            return 0, str(exc)


transport = DeliveryTransport()


def dispatch_due(session: Session, limit: int = 50) -> dict:
    """Attempt all deliveries whose next_retry_at <= now. Retry/backoff."""
    now = utcnow()
    rows = list(session.execute(select(WebhookDelivery).where(
        WebhookDelivery.status == "pending",
        WebhookDelivery.next_retry_at.is_not(None),
        WebhookDelivery.next_retry_at <= now).limit(limit)).scalars().all())
    delivered = failed = 0
    for d in rows:
        ep = session.get(WebhookEndpoint, d.endpoint_id)
        if ep is None or not ep.active:
            d.status = "failed"
            d.last_error = "endpoint removed or inactive"
            failed += 1
            continue
        code, err = transport.post(ep.url, d.payload, d.signature, d.event_type)
        d.attempts += 1
        d.response_code = code or None
        if 200 <= code < 300:
            d.status = "delivered"
            d.delivered_at = now
            d.last_error = None
            delivered += 1
        else:
            d.last_error = err or f"HTTP {code}"
            if d.attempts >= d.max_retries:
                d.status = "failed"
                failed += 1
            else:
                d.next_retry_at = now + timedelta(seconds=RETRY_BASE_SECONDS *
                                                  (2 ** (d.attempts - 1)))
    session.flush()
    return {"attempted": len(rows), "delivered": delivered, "failed": failed}


def list_deliveries(session: Session, identity: Identity, limit: int = 100):
    rows = list(session.execute(select(WebhookDelivery).where(
        WebhookDelivery.tenant_id == identity.tenant_id)
        .order_by(WebhookDelivery.created_at.desc()).limit(limit)).scalars().all())
    return [{"id": d.id, "endpoint_id": d.endpoint_id, "event_type": d.event_type,
             "status": d.status, "attempts": d.attempts, "response_code": d.response_code,
             "last_error": d.last_error, "created_at": d.created_at,
             "delivered_at": d.delivered_at} for d in rows]
