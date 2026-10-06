from __future__ import annotations

import os

# Database URL; defaults to a local SQLite file. Any SQLAlchemy URL works
# (e.g. postgresql+psycopg://... in production).
DATABASE_URL: str = os.environ.get("CRM_DATABASE_URL", "sqlite:///./crm.db")

# Secret used to sign webhook payloads (HMAC-SHA256).
WEBHOOK_SECRET: str = os.environ.get("CRM_WEBHOOK_SECRET", "change-me-in-prod")

API_PREFIX: str = "/api/v1"

# Deterministic thresholds for risk flags (documented business rules).
RISK_RULES = {
    "lead_stale_days": 7,          # lead without activity for N days => stale/cooling
    "opportunity_stale_days": 14,  # opportunity without activity for N days => stale
    "aging_stage_days": 21,        # days in current stage beyond which aging_score maxes
    "hot_lead_score": 80,          # score threshold for "hot leads" widget
}

# Comma-separated allowed origins for the SPA dev server. Empty disables CORS.
CORS_ORIGINS: list[str] = [o.strip() for o in
                           os.environ.get("CRM_CORS_ORIGINS",
                                          "http://localhost:5173,http://127.0.0.1:5173").split(",")
                           if o.strip()]
