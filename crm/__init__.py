"""Simorgh / OrgOS — Operational CRM.

Layers:
  core      – db, auth (tenant + roles + RBAC), audit log, domain events
  domain    – ORM models + enums (single source of truth for CRM state)
  services  – deterministic business logic (conversion, risk, dashboard)
  api       – versioned FastAPI routers (/api/v1/...)

Boundary rules:
  * CRM is a System of Record — not a decision engine, not a chatbot.
  * AI/Intelligence is a CONSUMER of CRM data via API/Events only.
  * No LLM inside core transactions; DB + deterministic rules = truth.
"""

__version__ = "1.0.0"
