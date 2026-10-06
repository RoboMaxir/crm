"""Auth / Tenant / RBAC.

API keys map to a user with (tenant_id, role). Every request resolves an
`Identity`; ALL queries are filtered by identity.tenant_id at the service
layer (backend-enforced isolation, never trust the client).

Roles: admin > manager > sales > member.
Permissions: view, create, update, delete, assign, export, manage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from crm.core.db import get_session

# ---------------------------------------------------------------- roles/RBAC
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_SALES = "sales"
ROLE_MEMBER = "member"

PERM_VIEW = "view"
PERM_CREATE = "create"
PERM_UPDATE = "update"
PERM_DELETE = "delete"
PERM_ASSIGN = "assign"
PERM_EXPORT = "export"
PERM_MANAGE = "manage"          # pipelines, webhooks, users, settings

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: {PERM_VIEW, PERM_CREATE, PERM_UPDATE, PERM_DELETE,
                 PERM_ASSIGN, PERM_EXPORT, PERM_MANAGE},
    ROLE_MANAGER: {PERM_VIEW, PERM_CREATE, PERM_UPDATE, PERM_ASSIGN, PERM_EXPORT},
    ROLE_SALES: {PERM_VIEW, PERM_CREATE, PERM_UPDATE, PERM_ASSIGN},
    ROLE_MEMBER: {PERM_VIEW},
}


@dataclass(frozen=True)
class Identity:
    user_id: str
    tenant_id: str
    role: str
    full_name: str = ""
    permissions: frozenset = field(default_factory=frozenset)

    def can(self, perm: str) -> bool:
        return perm in self.permissions


def permissions_for(role: str) -> frozenset:
    return frozenset(ROLE_PERMISSIONS.get(role, set()))


def make_identity(user_id: str, tenant_id: str, role: str, full_name: str = "") -> Identity:
    return Identity(user_id=user_id, tenant_id=tenant_id, role=role,
                    full_name=full_name, permissions=permissions_for(role))


# --------------------------------------------------------------- user store
class UserStore:
    """In-memory user/API-key store.

    Seam for OrgOS SSO integration: replace this implementation (or back it
    with the `users` table + a real identity provider) without touching any
    CRM business logic — everything depends only on `Identity`.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, Identity] = {}

    def register(self, api_key: str, identity: Identity) -> None:
        self._by_key[api_key] = identity

    def resolve(self, api_key: str | None) -> Identity | None:
        if not api_key:
            return None
        return self._by_key.get(api_key)


user_store = UserStore()


def seed_default_users() -> None:
    """Dev/demo identities. In production these come from OrgOS SSO."""
    if user_store._by_key:
        return
    user_store.register("key-admin-a", make_identity("u-admin-a", "tenant-a", ROLE_ADMIN, "Admin A"))
    user_store.register("key-manager-a", make_identity("u-mgr-a", "tenant-a", ROLE_MANAGER, "Manager A"))
    user_store.register("key-sales-a", make_identity("u-sales-a", "tenant-a", ROLE_SALES, "Sales A"))
    user_store.register("key-member-a", make_identity("u-member-a", "tenant-a", ROLE_MEMBER, "Member A"))
    user_store.register("key-admin-b", make_identity("u-admin-b", "tenant-b", ROLE_ADMIN, "Admin B"))
    user_store.register("key-sales-b", make_identity("u-sales-b", "tenant-b", ROLE_SALES, "Sales B"))


# ------------------------------------------------------------- FastAPI deps
def get_db(request: Request) -> Session:
    """Overridable via app.dependency_overrides (used by tests)."""
    yield from get_session()


def get_identity(authorization: str | None = Header(default=None)) -> Identity:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    identity = user_store.resolve(token)
    if identity is None:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return identity


def require(permission: str):
    def dep(identity: Identity = Depends(get_identity)) -> Identity:
        if not identity.can(permission):
            raise HTTPException(status_code=403,
                                detail=f"Role '{identity.role}' lacks '{permission}' permission")
        return identity
    return dep
