"""Shared API helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import Depends, Query, Request
from sqlalchemy.orm import Session

from crm.core.auth import Identity, get_identity


def db_dep(request: Request) -> Session:
    return request.state.db


def identity_dep(request: Request) -> Identity:
    return request.state.identity


DB = Depends(db_dep)
IDP = Depends(identity_dep)


def auth(permission: str):
    """Dependency for handlers that require a specific RBAC permission.

    Usage (thin routers only – enforcement is backend-side):
        def create_org(data=Body(...), db=DB, me=auth(PERM_CREATE)): ...
    """
    return require(permission)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)  # store naive UTC
    return dt


def coerce_dates(d: dict[str, Any]) -> dict[str, Any]:
    """Convert ISO strings on *_at / *_date fields to datetimes."""
    for k, v in list(d.items()):
        if isinstance(v, str) and (k.endswith("_at") or k.endswith("_date")):
            try:
                d[k] = parse_dt(v)
            except ValueError:
                pass
    return d


def dump(obj) -> dict:
    """Serialize ORM object to JSON-safe dict."""
    out: dict[str, Any] = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.key)
        out[c.key] = v.isoformat() if isinstance(v, datetime) else v
    return out


def page_params(page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=200)):
    return page, per_page
