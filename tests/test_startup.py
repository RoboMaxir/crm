"""Step 2 — startup smoke."""
from __future__ import annotations


def test_import_and_create_app():
    import crm.app as m
    app = m.create_app()
    assert app.title == "Simorgh CRM"
    # all routers registered under /api/v1
    paths = {r.path for r in app.routes}
    for p in ("/api/v1/organizations", "/api/v1/contacts", "/api/v1/leads",
              "/api/v1/opportunities", "/api/v1/pipelines", "/api/v1/activities",
              "/api/v1/dashboard", "/api/v1/search", "/api/v1/tags",
              "/api/v1/audit", "/api/v1/webhooks", "/api/v1/intelligence",
              "/api/v1/saved-filters", "/api/v1/settings", "/api/v1/quick/capture"):
        assert p in paths, f"missing route {p}"


def test_health_and_auth(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    r = client.get("/api/v1/organizations")            # no key -> 401
    assert r.status_code == 401
    r = client.get("/api/v1/organizations", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_uvicorn_module_loads():
    # `uvicorn crm.app:app` must resolve without ImportError/middleware errors
    import importlib
    mod = importlib.import_module("crm.app")
    assert hasattr(mod, "app")
