"""FastAPI application factory + middleware (tenant context, events, commits).

Request lifecycle:
  1. resolve Identity from Bearer API key (Auth seam for OrgOS SSO),
  2. attach it to request.state.identity (frontend never asserts its own tenant),
  3. router handler runs service functions (all tenant-scoped),
  4. on success: enqueue webhook deliveries from the outbox and COMMIT,
  5. on DomainError/exception: ROLLBACK (state + events are atomic).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from crm.core.auth import get_identity, seed_default_users
from crm.core.config import API_PREFIX
from crm.core.db import Base, SessionLocal, engine, get_session
from crm.services.common import DomainError


def create_app() -> FastAPI:
    app = FastAPI(title="Simorgh CRM", version="1.0.0",
                  description="Operational CRM — System of Record for "
                              "Customer / Lead / Opportunity / Activity state.")
    seed_default_users()

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status,
                            content={"error": exc.code, "detail": exc.message})

    @app.middleware("http")
    async def identity_and_session(request: Request, call_next):
        # Resolve identity early so 401 happens before touching the DB.
        if request.url.path.startswith(API_PREFIX) and request.url.path != f"{API_PREFIX}/health":
            try:
                request.state.identity = get_identity(
                    authorization=request.headers.get("Authorization"))
            except Exception as exc:  # HTTPException from get_identity
                from fastapi.exceptions import HTTPException
                if isinstance(exc, HTTPException):
                    return JSONResponse(status_code=exc.status_code,
                                        content={"error": "unauthorized",
                                                 "detail": exc.detail})
                raise
            sess = next(get_session())
            request.state.db = sess
            try:
                response = await call_next(request)
                if 200 <= response.status_code < 300:
                    _post_commit(sess)
                    sess.commit()
                else:
                    sess.rollback()
                return response
            except Exception:
                sess.rollback()
                raise
            finally:
                sess.close()
        return await call_next(request)

    # ------------------------------------------------------------- routers
    from crm.api import (activities_router, audit_router, contacts_router,
                         dashboard_router, intelligence_router, leads_router,
                         orgs_router, opportunities_router, pipelines_router,
                         quick_router, saved_filters_router, search_router,
                         settings_router, tags_router, webhooks_router)

    app.include_router(orgs_router.router, prefix=API_PREFIX)
    app.include_router(contacts_router.router, prefix=API_PREFIX)
    app.include_router(leads_router.router, prefix=API_PREFIX)
    app.include_router(opportunities_router.router, prefix=API_PREFIX)
    app.include_router(pipelines_router.router, prefix=API_PREFIX)
    app.include_router(activities_router.router, prefix=API_PREFIX)
    app.include_router(dashboard_router.router, prefix=API_PREFIX)
    app.include_router(search_router.router, prefix=API_PREFIX)
    app.include_router(tags_router.router, prefix=API_PREFIX)
    app.include_router(audit_router.router, prefix=API_PREFIX)
    app.include_router(webhooks_router.router, prefix=API_PREFIX)
    app.include_router(intelligence_router.router, prefix=API_PREFIX)
    app.include_router(saved_filters_router.router, prefix=API_PREFIX)
    app.include_router(settings_router.router, prefix=API_PREFIX)
    app.include_router(quick_router.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health")
    def health():
        return {"status": "ok", "service": "simorgh-crm", "version": "1.0.0"}

    @app.on_event("startup")
    def _startup():
        Base.metadata.create_all(engine)

    return app


def _post_commit(session) -> None:
    """Queue webhook deliveries for events flushed in this transaction."""
    try:
        from crm.services.webhooks import enqueue_deliveries
        enqueue_deliveries(session)
    except Exception:  # noqa: BLE001 – queueing must never break the request
        pass


app = create_app()
