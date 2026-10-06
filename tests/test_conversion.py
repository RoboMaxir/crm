"""Step 4 — Lead conversion: success, duplicate (409), atomic rollback."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from crm.core import db as core_db
from crm.domain.models import AuditLog, DomainEvent, Lead, Opportunity, Organization, Contact

V1 = "/api/v1"


def _mk_org_contact_lead(api):
    org = api.post(f"{V1}/organizations", {"name": "فولاد مبارکه"}).json()
    c = api.post(f"{V1}/contacts", {"first_name": "مریم", "last_name": "کاظمی",
                                    "organization_id": org["id"]}).json()
    lead = api.post(f"{V1}/leads", {"title": "مدیریار فولاد", "source": "website",
                                    "estimated_value": 800000000}).json()
    return org, c, lead


def test_convert_creates_full_chain_in_one_transaction(admin_a):
    # lead WITHOUT pre-linked org/contact -> conversion must create them
    lead = admin_a.post(f"{V1}/leads", {"title": "ذوب‌آهن اصفهان", "source": "event",
                                        "estimated_value": 300000000}).json()
    r = admin_a.post(f"{V1}/leads/{lead['id']}/convert",
                     {"contact_first_name": "حسن", "contact_last_name": "موسوی",
                      "value": 300000000})
    assert r.status_code == 200, r.text
    body = r.json()
    org, contact, opp = body["organization"], body["contact"], body["opportunity"]

    # chain + FK integrity
    assert body["lead"]["status"] == "converted"
    assert body["lead"]["converted_organization_id"] == org["id"]
    assert body["lead"]["converted_opportunity_id"] == opp["id"]
    assert opp["organization_id"] == org["id"]
    assert opp["lead_id"] == lead["id"]
    assert contact["organization_id"] == org["id"]
    assert opp["primary_contact_id"] == contact["id"]
    # tenant correctness on every created row
    for rec in (body["lead"], org, contact, opp):
        assert rec["tenant_id"] == "tenant-a"
    # owner inherited from lead owner (creator)
    assert opp["owner_id"] == "u-admin-a" and contact["owner_id"] == "u-admin-a"
    # weighted value deterministic at first stage (New => 10%)
    assert opp["probability"] == 10
    assert opp["weighted_value"] == 30000000

    # audit + canonical events persisted in the SAME transaction
    sess = core_db.SessionLocal()
    try:
        actions = {a.action for a in sess.execute(select(AuditLog).where(
            AuditLog.tenant_id == "tenant-a")).scalars()}
        assert {"conversion", "create"} <= actions
        evts = {e.event_type for e in sess.execute(select(DomainEvent).where(
            DomainEvent.tenant_id == "tenant-a")).scalars()}
        assert {"lead.created", "lead.converted", "customer.created",
                "opportunity.created"} <= evts
        assert sess.get(Lead, lead["id"]).status == "converted"
    finally:
        sess.close()


def test_duplicate_conversion_returns_409_and_no_duplicates(admin_a):
    lead = admin_a.post(f"{V1}/leads", {"title": "چادرمال"}).json()
    r1 = admin_a.post(f"{V1}/leads/{lead['id']}/convert", {})
    assert r1.status_code == 200
    first_opp = r1.json()["opportunity"]["id"]
    first_org = r1.json()["organization"]["id"]

    r2 = admin_a.post(f"{V1}/leads/{lead['id']}/convert", {})
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"] == "conflict"

    # no duplicate rows, no duplicate events
    sess = core_db.SessionLocal()
    try:
        assert sess.execute(select(Organization).where(
            Organization.tenant_id == "tenant-a")).scalars().all().__len__() == 1
        assert sess.execute(select(Opportunity).where(
            Opportunity.tenant_id == "tenant-a")).scalars().all().__len__() == 1
        conv_evts = sess.execute(select(DomainEvent).where(
            DomainEvent.event_type == "lead.converted")).scalars().all()
        assert len(conv_evts) == 1
        assert sess.get(Lead, lead["id"]).converted_opportunity_id == first_opp
        assert sess.get(Organization, first_org).name == "چادرمال"
    finally:
        sess.close()


def test_conversion_rolls_back_atomically_on_failure(admin_a, monkeypatch):
    """Fail AFTER the organization is created inside convert_lead.

    Expected: nothing persists — not the org, not the opportunity, not the
    lead status, not the audit rows, not the outbox events.
    """
    lead = admin_a.post(f"{V1}/leads", {"title": "سازمان نوردکو"}).json()
    baseline_events = None
    sess = core_db.SessionLocal()
    try:
        baseline_events = sess.execute(select(DomainEvent)).scalars().all().__len__()
    finally:
        sess.close()

    import crm.services.leads as leads_svc
    real = leads_svc.create_org_for_conversion

    def boom(session, identity, name, l):
        org = real(session, identity, name, l)   # org + customer.created flushed
        raise RuntimeError("simulated mid-transaction failure")

    monkeypatch.setattr(leads_svc, "create_org_for_conversion", boom)

    with pytest.raises(RuntimeError):
        admin_a.post(f"{V1}/leads/{lead['id']}/convert", {})

    # direct DB verification of full rollback
    sess = core_db.SessionLocal()
    try:
        assert sess.execute(select(Organization).where(
            Organization.tenant_id == "tenant-a")).scalars().all() == []
        assert sess.execute(select(Opportunity).where(
            Opportunity.tenant_id == "tenant-a")).scalars().all() == []
        assert sess.get(Lead, lead["id"]).status == "new"          # unchanged
        assert sess.get(Lead, lead["id"]).converted_at is None
        assert sess.execute(select(DomainEvent)).scalars().all().__len__() \
            == baseline_events                                    # no leaked events
        assert sess.execute(select(AuditLog).where(
            AuditLog.entity == "organization",
            AuditLog.tenant_id == "tenant-a")).scalars().all() == []
    finally:
        sess.close()


def test_cannot_convert_lost_lead(admin_a):
    lead = admin_a.post(f"{V1}/leads", {"title": "لید مردود"}).json()
    r = admin_a.post(f"{V1}/leads/{lead['id']}/lose", {"lost_reason": "no_budget"})
    assert r.status_code == 200 and r.json()["status"] == "lost"
    r = admin_a.post(f"{V1}/leads/{lead['id']}/convert", {})
    assert r.status_code == 422


def test_illegal_status_transitions(admin_a):
    lead = admin_a.post(f"{V1}/leads", {"title": "L"}).json()
    r = admin_a.patch(f"{V1}/leads/{lead['id']}", {"status": "converted"})
    assert r.status_code == 422                      # must use /convert
    r = admin_a.patch(f"{V1}/leads/{lead['id']}", {"status": "unqualified"})
    assert r.status_code == 200
    r = admin_a.patch(f"{V1}/leads/{lead['id']}", {"status": "converted"})
    assert r.status_code == 422
