"""Domain events — CRM publishes, OrgOS/Shora consume.

The CRM never calls Shora directly. Events are persisted (outbox) and fanned
out to registered in-process listeners + webhook endpoints. External systems
should consume via the outbox/API or webhooks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

# Canonical event names (contract for OrgOS integration).
EVENTS = {
    "customer.created",
    "customer.updated",
    "contact.created",
    "lead.created",
    "lead.status_changed",
    "lead.qualified",
    "lead.converted",
    "lead.lost",
    "opportunity.created",
    "opportunity.stage_changed",
    "opportunity.won",
    "opportunity.lost",
    "opportunity.updated",
    "activity.created",
    "activity.completed",
    "activity.overdue",
}

_listeners: list[Callable[[str, dict], None]] = []


def subscribe(listener: Callable[[str, dict], None]) -> None:
    """Register an in-process listener (test/dev hook; prod uses webhooks)."""
    _listeners.append(listener)


def reset_listeners() -> None:
    _listeners.clear()


def emit(
    session: Session,
    event_type: str,
    tenant_id: str,
    entity: str,
    entity_id: str,
    payload: dict[str, Any] | None = None,
    actor_id: str | None = None,
) -> None:
    """Persist an event to the outbox table and notify listeners.

    Must be called inside the SAME transaction as the state change so that
    state + event are atomic (transactional outbox pattern).
    """
    from crm.domain.models import DomainEvent  # local import: avoid cycles

    if event_type not in EVENTS:
        raise ValueError(f"Unknown event type: {event_type}")

    evt = DomainEvent(
        event_type=event_type,
        tenant_id=tenant_id,
        entity=entity,
        entity_id=str(entity_id),
        payload=json.dumps(payload or {}, ensure_ascii=False),
        actor_id=actor_id,
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(evt)
    session.flush()

    body = {
        "event": event_type,
        "tenant_id": tenant_id,
        "entity": entity,
        "entity_id": str(entity_id),
        "payload": payload or {},
        "actor_id": actor_id,
        "occurred_at": evt.occurred_at.isoformat(),
    }
    for fn in _listeners:
        fn(event_type, body)
