"""Shared service helpers: tenant-scoped queries, pagination/filtering, errors."""
from __future__ import annotations

from typing import Any, Iterable, TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.domain.models import utcnow

T = TypeVar("T")


class DomainError(Exception):
    def __init__(self, status: int, message: str, code: str = "domain_error"):
        self.status = status
        self.message = message
        self.code = code
        super().__init__(message)


def not_found(entity: str) -> DomainError:
    return DomainError(404, f"{entity} not found", "not_found")


def conflict(message: str) -> DomainError:
    return DomainError(409, message, "conflict")


def unprocessable(message: str) -> DomainError:
    return DomainError(422, message, "unprocessable")


def get_tenant(session: Session, model, identity: Identity, obj_id: str):
    """Fetch by id STRICTLY within the caller's tenant. Cross-tenant => 404."""
    obj = session.get(model, obj_id)
    if obj is None or obj.tenant_id != identity.tenant_id:
        raise not_found(model.__name__)
    return obj


SORTABLE = {
    "created_at", "updated_at", "name", "title", "status", "value",
    "estimated_value", "weighted_value", "probability", "score",
    "expected_close_date", "due_at", "last_activity_at", "next_activity_at",
}


def apply_list_query(stmt, *, search_fields: Iterable[Any] | None = None,
                     q: str | None = None, filters: dict | None = None,
                     sort: str | None = None, order: str = "desc",
                     page: int = 1, per_page: int = 25,
                     model=None):
    """Apply search + equality/comparison filters + sort + pagination.

    filters keys may carry suffixes: ``field__gt``, ``field__lt``,
    ``field__gte``, ``field__lte``, ``field__in`` (comma list).
    Returns (stmt, total_count).
    """
    if q and search_fields:
        clauses = [func.lower(f).like(f"%{q.lower()}%") for f in search_fields]
        stmt = stmt.where(or_(*clauses))

    for key, val in (filters or {}).items():
        if val is None or val == "":
            continue
        field, _, op = key.partition("__")
        col = getattr(model, field, None)
        if col is None:
            continue  # ignore unknown filter keys rather than error
        if op == "gt":
            stmt = stmt.where(col > val)
        elif op == "lt":
            stmt = stmt.where(col < val)
        elif op == "gte":
            stmt = stmt.where(col >= val)
        elif op == "lte":
            stmt = stmt.where(col <= val)
        elif op == "in":
            vals = [v.strip() for v in str(val).split(",") if v.strip()]
            stmt = stmt.where(col.in_(vals))
        else:
            stmt = stmt.where(col == val)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return stmt, count_stmt


def finalize_list(session: Session, stmt, count_stmt, model, *,
                  sort: str | None, order: str, page: int, per_page: int):
    total = session.execute(count_stmt).scalar_one()
    sort_col = getattr(model, sort, None) if sort in SORTABLE else None
    if sort_col is None and sort:
        sort_col = getattr(model, "created_at", None)
    elif sort_col is None:
        sort_col = getattr(model, "created_at", None)
    stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    page = max(page, 1)
    per_page = min(max(per_page, 1), 200)
    items = session.execute(stmt.limit(per_page).offset((page - 1) * per_page)).scalars().all()
    return {
        "items": list(items),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


def now():
    return utcnow()
