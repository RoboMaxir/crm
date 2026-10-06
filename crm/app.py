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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from crm.core.auth import get_identity, seed_default_users
from crm.core.config import API_PREFIX
from crm.core import db as _db
from crm.services.common import DomainError

def create_app() -> FastAPI:
    app = FastAPI(title="Simorgh CRM", version="1.0.0",
                  description="Operational CRM — System of Record for "
                              "Customer / Lead / Opportunity / Activity state.")
    seed_default_users()

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError):
        # Flag the request so the ASGI middleware rolls back instead of commit.
        try:
            request.state.domain_error = True
        except AssertionError:  # state not initialized (shouldn't happen)
            pass
        return JSONResponse(status_code=exc.status,
                            content={"error": exc.code, "detail": exc.message})

    class IdentityAndSessionMiddleware:
        """Pure ASGI middleware (starlette>=0.38 no longer supports function
        middleware via @app.middleware). Lifecycle:
          1. resolve identity -> 401 before touching the DB,
          2. open a session on request.state, run downstream,
          3. commit only if the final status is 2xx AND no DomainError escaped
             (DomainError sets request.state.domain_error; its handler already
             produced the error response), otherwise rollback — state + outbox
             events are atomic either way.
        """

        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            request = Request(scope, receive)
            path = request.url.path
            if not path.startswith(API_PREFIX) or path == f"{API_PREFIX}/health":
                await self.app(scope, receive, send)
                return
            from fastapi.exceptions import HTTPException
            try:
                request.state.identity = get_identity(
                    authorization=request.headers.get("Authorization"))
            except HTTPException as exc:
                resp = JSONResponse(status_code=exc.status_code,
                                    content={"error": "unauthorized",
                                             "detail": exc.detail})
                await resp(scope, receive, send)
                return
            sess = _db.SessionLocal()
            request.state.db = sess
            request.state.domain_error = False

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    request.state.final_status = message["status"]
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            except DomainError:
                # Escaped past ExceptionMiddleware only when handlers disabled;
                # treat as rollback case.
                sess.rollback()
                raise
            finally:
                status = getattr(request.state, "final_status", 500)
                errored = getattr(request.state, "domain_error", False)
                if 200 <= status < 300 and not errored:
                    _post_commit(sess)
                    sess.commit()
                else:
                    sess.rollback()
                sess.close()

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

    # Register AFTER routers so it wraps the whole downstream stack (incl. the
    # exception middleware that converts DomainError into error responses).
    app.add_middleware(IdentityAndSessionMiddleware)

    # CORS: allows the bundled SPA dev server (Vite :5173) to call this API with
    # a Bearer key. Origin-scoped (not "*") because requests carry credentials-
    # style Authorization headers; tighten CRM_CORS_ORIGINS in production.
    from crm.core.config import CORS_ORIGINS
    if CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS,
                           allow_methods=["*"], allow_headers=["*"])

    @app.get(f"{API_PREFIX}/me")
    def me(request: Request):
        """Current identity (user_id/tenant/role/permissions) for UI hints.
        Auth itself stays in IdentityAndSessionMiddleware."""
        ident = getattr(request.state, "identity", None)
        if ident is None:
            return JSONResponse(status_code=401,
                                content={"error": "unauthorized",
                                         "detail": "Missing or invalid API key"})
        return {"user_id": ident.user_id, "tenant_id": ident.tenant_id,
                "role": ident.role, "full_name": ident.full_name,
                "permissions": sorted(ident.permissions)}

    @app.get(f"{API_PREFIX}/health")
    def health():
        return {"status": "ok", "service": "simorgh-crm", "version": "1.0.0"}

    @app.on_event("startup")
    def _startup():
        _db.Base.metadata.create_all(_db.engine)

    return app


def _post_commit(session) -> None:
    """Queue webhook deliveries for events flushed in this transaction."""
    try:
        from crm.services.webhooks import enqueue_deliveries
        enqueue_deliveries(session)
    except Exception:  # noqa: BLE001 – queueing must never break the request
        pass


app = create_app()
