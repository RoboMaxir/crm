"""Quick Capture — the single most important workflow.

'Met a CNC factory today, likely will become Modiryar customer' must become
Organization + Contact + Lead + Owner + Next Action in ONE request (<1 min),
with every step audited and events emitted. All inside one transaction;
duplicate-safe on organization name.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from crm.core.auth import Identity
from crm.domain.models import Contact, Lead, Organization, utcnow
from crm.services import activities as act_svc
from crm.services import leads as lead_svc
from crm.services import orgs as org_svc
from crm.services.common import unprocessable


def quick_capture(session: Session, identity: Identity, data: dict) -> dict:
    """data = {organization:{...}, contact:{...}, lead:{...},
                next_action:{type,subject,due_at,priority}}"""
    org_data = data.get("organization") or {}
    contact_data = data.get("contact") or {}
    lead_data = data.get("lead") or {}
    na = data.get("next_action") or None
    if not org_data.get("name") and not lead_data.get("title"):
        raise unprocessable("quick_capture requires organization.name or lead.title")

    # --- Organization (dedupe by exact name, case-insensitive) --------------
    org_name = (org_data.get("name") or lead_data.get("title") or "").strip()
    org = session.execute(select(Organization).where(
        Organization.tenant_id == identity.tenant_id,
        func.lower(Organization.name) == org_name.lower())).scalar_one_or_none()
    org_created = False
    if org is None:
        org = org_svc.create_organization(session, identity, {**org_data, "name": org_name})
        org_created = True

    # --- Contact --------------------------------------------------------------
    contact = None
    contact_created = False
    if contact_data.get("first_name"):
        contact = org_svc.create_contact(session, identity, {
            **contact_data, "organization_id": org.id,
            "owner_id": contact_data.get("owner_id") or identity.user_id})
        contact_created = True

    # --- Lead -------------------------------------------------------------------
    lead = lead_svc.create_lead(session, identity, {
        "title": lead_data.get("title") or f"{org.name} — New lead",
        "organization_id": org.id,
        "contact_id": contact.id if contact else None,
        "source": lead_data.get("source", "manual"),
        "estimated_value": lead_data.get("estimated_value", 0),
        "currency": lead_data.get("currency", "IRR"),
        "score": lead_data.get("score", 0),
        "owner_id": lead_data.get("owner_id") or identity.user_id,
        "notes": lead_data.get("notes"),
        "expected_close_date": lead_data.get("expected_close_date"),
        "tags": lead_data.get("tags") or [],
    })

    # --- Next action (optional but strongly encouraged) -------------------------
    activity = None
    if na and na.get("subject"):
        activity = act_svc.create_activity(session, identity, {
            "type": na.get("type", "follow_up"),
            "subject": na["subject"],
            "description": na.get("description"),
            "lead_id": lead.id,
            "organization_id": org.id,
            "assigned_to": na.get("assigned_to") or lead.owner_id,
            "due_at": na.get("due_at") or _default_due(),
            "priority": na.get("priority", "medium"),
            "status": "pending",
        })

    return {"organization": org, "organization_created": org_created,
            "contact": contact, "contact_created": contact_created,
            "lead": lead, "next_action": activity}


def _default_due():
    from datetime import timedelta
    return utcnow() + timedelta(days=2)
