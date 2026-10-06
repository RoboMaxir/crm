"""Database session management.

SQLite special-case for tests/dev: a single shared connection so in-memory /
file DBs work with multiple sessions. Production Postgres needs no changes.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    connect_args = {}
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool
            kwargs["poolclass"] = StaticPool
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = _make_engine(DATABASE_URL)

if DATABASE_URL.startswith("sqlite") and ":memory:" not in DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _):  # enforce FKs on SQLite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create all tables (idempotent). Alembic can replace this in prod."""
    from crm.domain import models  # noqa: F401 – register mappers
    Base.metadata.create_all(engine)


def get_session():
    sess: Session = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
