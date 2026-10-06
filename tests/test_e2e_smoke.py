"""Step 3 — real HTTP end-to-end flow."""
from __future__ import annotations

V1 = "/api/v1"


def test_full_flow(admin_a):
    # organization
    r = admin_a.post(f"{V1}/organizations", {"name": "تاکتاز CNC", "industry": "CNC",
                                             "source": "referral"})
    assert r.status_code == 201, r.text
    org = r.json()

    # contact
    r = admin_a.post(f"{V1}/contacts", {"first_name": "علی", "last_name": "رضایی",
                                        "organization_id": org["id"],
                                        "job_title": "مدیرعامل"})
    assert r.status_code == 201, r.text
    contact = r.json()

    # lead linked to both
    r = admin_a.post(f"{V1}/leads", {"title": "تاکتاز — مدیریار",
                                     "organization_id": org["id"],
                                     "contact_id": contact["id"],
                                     "source": "referral",
                                     "estimated_value": 500000000})
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["status"] == "new"
    assert lead["owner_id"] == "u-admin-a"

    # next action on the lead
    r = admin_a.post(f"{V1}/activities", {"type": "follow_up",
                                          "subject": "ارسال پروپوزال اولیه",
                                          "lead_id": lead["id"],
                                          "due_at": "2026-10-10T10:00:00Z"})
    assert r.status_code == 201, r.text
    na = r.json()
    assert na["status"] == "pending"

    # lead.next_activity_at synced deterministically
    r = admin_a.get(f"{V1}/leads/{lead['id']}")
    assert r.json()["next_activity_at"] == na["due_at"]

    # qualify then convert
    r = admin_a.patch(f"{V1}/leads/{lead['id']}", {"status": "qualified"})
    assert r.status_code == 200 and r.json()["status"] == "qualified"
    r = admin_a.post(f"{V1}/leads/{lead['id']}/convert",
                     {"value": 500000000, "contact_first_name": None})
    assert r.status_code == 200, r.text
    conv = r.json()
    opp = conv["opportunity"]
    assert opp["organization_id"] == org["id"]
    assert opp["lead_id"] == lead["id"]

    # activity on the opportunity + complete it
    r = admin_a.post(f"{V1}/activities", {"type": "demo", "subject": "دموی مدیریار",
                                          "opportunity_id": opp["id"]})
    assert r.status_code == 201
    aid = r.json()["id"]
    r = admin_a.post(f"{V1}/activities/{aid}/complete")
    assert r.status_code == 200 and r.json()["status"] == "completed"

    # customer 360
    r = admin_a.get(f"{V1}/organizations/{org['id']}/360")
    assert r.status_code == 200, r.text
    view = r.json()
    for section in ("identity", "contacts", "commercial", "relationship",
                    "timeline", "tasks", "notes", "tags", "events", "intelligence"):
        assert section in view

    # dashboard
    r = admin_a.get(f"{V1}/dashboard")
    assert r.status_code == 200
    assert r.json()["sales"]["total_leads"] == 1

    # search
    r = admin_a.get(f"{V1}/search", params={"q": "تاکتاز"})
    res = r.json()
    assert res["organizations"] and res["contacts"] and res["leads"]
    assert res["opportunities"]
