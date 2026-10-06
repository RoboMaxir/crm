"""Audit log — append-only record of important mutations.

Written exclusively through audit() so every create/update/delete/status
change/owner change/stage change/conversion/assignment is captured with
actor, before/after snapshots and timestamp.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session


def _json_default(obj):
    """Snapshots may contain datetimes (due_at, expected_close_date, ...)."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def audit(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None,
    action: str,           # create | update | delete | status_change | owner_change |
                          # stage_change | conversion | assignment | complete
    entity: str,
    entity_id: Any,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    from crm.domain.models import AuditLog  # local import: avoid cycles

    session.add(AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        before_json=json.dumps(before, ensure_ascii=False, default=_json_default)
        if before else None,
        after_json=json.dumps(after, ensure_ascii=False, default=_json_default)
        if after else None,
    ))
