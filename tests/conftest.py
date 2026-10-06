"""Test harness: one shared in-memory SQLite DB for the whole app.

Design (per spec):
  * crm.core.db.configure_engine("sqlite:///:memory:") -> StaticPool engine so
    every SessionLocal() (including the one the ASGI middleware opens per
    request) shares the SAME in-memory database.
  * FK enforcement is attached to that engine (SQLite ignores FKs by default).
  * Tables are recreated + users re-seeded for every test (clean isolation).
  * No @pytest.mark on fixtures (pytest 9 rejects marks on fixtures).
"""
from __future__ import annotations

import pytest
from sqlalchemy import event as sa_event
from fastapi.testclient import TestClient

from crm.core import db as core_db
from crm.core.auth import user_store


@pytest.fixture()
def client():
    core_db.configure_engine("sqlite:///:memory:")

    @sa_event.listens_for(core_db.engine, "connect")
    def _fk_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    core_db.init_db()

    # Fresh identities for this test's engine/user store.
    user_store._by_key.clear()
    from crm.core.auth import seed_default_users
    seed_default_users()

    from crm.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c

    core_db.Base.metadata.drop_all(core_db.engine)
    user_store._by_key.clear()


class Api:
    """Tiny HTTP helper — every call goes through the real ASGI stack."""

    def __init__(self, client, key: str):
        self.client = client
        self.headers = {"Authorization": f"Bearer {key}"}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, data=None, **kw):
        return self.client.post(path, json=data if data is not None else {},
                                headers=self.headers, **kw)

    def patch(self, path, data=None, **kw):
        return self.client.patch(path, json=data or {}, headers=self.headers, **kw)

    def put(self, path, data=None, **kw):
        return self.client.put(path, json=data, headers=self.headers, **kw)

    def delete(self, path, **kw):
        return self.client.delete(path, headers=self.headers, **kw)


def _api(client, key):
    return Api(client, key)


@pytest.fixture()
def admin_a(client):
    return _api(client, "key-admin-a")      # tenant-a, full perms


@pytest.fixture()
def manager_a(client):
    return _api(client, "key-manager-a")    # tenant-a, no delete/manage


@pytest.fixture()
def sales_a(client):
    return _api(client, "key-sales-a")      # tenant-a, no delete/manage/export


@pytest.fixture()
def member_a(client):
    return _api(client, "key-member-a")     # tenant-a, view only


@pytest.fixture()
def admin_b(client):
    return _api(client, "key-admin-b")      # tenant-b, full perms


@pytest.fixture()
def sales_b(client):
    return _api(client, "key-sales-b")      # tenant-b


@pytest.fixture()
def anon(client):
    return _api(client, "bogus-key")
