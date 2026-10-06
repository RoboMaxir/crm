"""Step 5 — Opportunity math, stages, win/loss/reopen, aging reset."""
from __future__ import annotations

V1 = "/api/v1"


def _org(api, name="پتروپارس"):
    return api.post(f"{V1}/organizations", {"name": name}).json()


def _stages(api):
    pipes = api.get(f"{V1}/pipelines").json()["items"]
    assert pipes, "default pipeline must exist after first opp creation"
    pid = pipes[0]["id"]
    st = api.get(f"{V1}/pipelines/{pid}/stages").json()["items"]
    return {s["name"]: s for s in st}


def test_weighted_value_formula(admin_a):
    org = _org(admin_a)
    r = admin_a.post(f"{V1}/opportunities", {"name": "قرارداد نگهداری",
                                             "organization_id": org["id"],
                                             "value": 120_000_000,
                                             "probability": 35})
    assert r.status_code == 201, r.text
    opp = r.json()
    # weighted_value = value * probability / 100  => 120M * 35% = 42M
    assert opp["weighted_value"] == 42_000_000

    # update probability -> recomputed deterministically
    r = admin_a.patch(f"{V1}/opportunities/{opp['id']}", {"probability": 50})
    assert r.json()["weighted_value"] == 60_000_000
    # update value -> recomputed
    r = admin_a.patch(f"{V1}/opportunities/{opp['id']}", {"value": 200_000_000})
    assert r.json()["weighted_value"] == 100_000_000
    # rounding rule documented: round(value*prob/100)
    r = admin_a.patch(f"{V1}/opportunities/{opp['id']}", {"probability": 33})
    assert r.json()["weighted_value"] == round(200_000_000 * 33 / 100) == 66_000_000


def test_stage_change_win_loss_reopen_and_aging_reset(admin_a):
    org = _org(admin_a)
    stages = None
    # create default pipeline explicitly (ensure-default requires create perm)
    r = admin_a.post(f"{V1}/pipelines/ensure-default", {})
    assert r.status_code == 200
    stages = _stages(admin_a)
    assert set(stages) >= {"New", "Proposal", "Negotiation", "Won", "Lost"}

    r = admin_a.post(f"{V1}/opportunities", {"name": "ERP فاز دو",
                                             "organization_id": org["id"],
                                             "value": 500_000_000})
    opp = r.json()
    assert opp["stage_name"] == "New" and opp["probability"] == 10
    aging0 = opp["stage_entered_at"]

    # move to Proposal (60%)
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/move-stage",
                     {"stage_id": stages["Proposal"]["id"]})
    assert r.status_code == 200
    opp2 = r.json()
    assert opp2["stage_id"] == stages["Proposal"]["id"]
    assert opp2["probability"] == 60                      # stage probability applied
    assert opp2["weighted_value"] == 300_000_000
    assert opp2["status"] == "open" and opp2["closed_at"] is None

    # explicit probability override on a move
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/move-stage",
                     {"stage_id": stages["Negotiation"]["id"], "probability": 75})
    assert r.json()["probability"] == 75
    assert r.json()["weighted_value"] == 375_000_000

    # WIN: probability snaps to 100, status/closed_at set, weighted=value
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/move-stage",
                     {"stage_id": stages["Won"]["id"]})
    won = r.json()
    assert won["status"] == "won" and won["probability"] == 100
    assert won["weighted_value"] == 500_000_000 and won["closed_at"]

    # closed deals cannot be modified
    r = admin_a.patch(f"{V1}/opportunities/{opp['id']}", {"value": 1})
    assert r.status_code == 409

    # REOPEN back to an open stage: aging basis resets, closed cleared
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/reopen",
                     {"stage_id": stages["Discovery"]["id"]})
    assert r.status_code == 200
    reopened = r.json()
    assert reopened["status"] == "open" and reopened["closed_at"] is None
    assert reopened["probability"] == 25                  # stage probability re-applied
    assert reopened["weighted_value"] == 125_000_000
    assert reopened["stage_entered_at"] >= aging0         # aging reset on transition
    assert reopened["days_in_stage"] == 0

    # reopen into a terminal stage is rejected
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/reopen",
                     {"stage_id": stages["Won"]["id"]})
    assert r.status_code == 422

    # LOSS: probability 0, lost_reason defaulted, weighted 0
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/move-stage",
                     {"stage_id": stages["Lost"]["id"], "lost_reason": "price"})
    lost = r.json()
    assert lost["status"] == "lost" and lost["probability"] == 0
    assert lost["weighted_value"] == 0 and lost["lost_reason"] == "price"


def test_cross_pipeline_stage_rejected(admin_a):
    admin_a.post(f"{V1}/pipelines/ensure-default", {})
    stages = _stages(admin_a)
    r = admin_a.post(f"{V1}/pipelines", {"name": "Partner", "stages": [
        {"name": "Intro", "probability": 20}, {"name": "Done", "is_won": True}]})
    assert r.status_code == 201, r.text   # admin has manage
    other_stage = r.json()["stages"][0]
    org = _org(admin_a, "پارس انرژی")
    opp = admin_a.post(f"{V1}/opportunities", {"name": "O", "organization_id": org["id"]}).json()
    r = admin_a.post(f"{V1}/opportunities/{opp['id']}/move-stage",
                     {"stage_id": other_stage["id"]})
    assert r.status_code == 422           # different pipeline
