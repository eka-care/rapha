"""Run: python3 -m api.tests.test_api

The service end to end against a throwaway in memory store. What is worth pinning
down here is the write path and nothing else: a proposal is not a write, a
confirm is a second guard pass, and a proposal is confirmed exactly once.
"""
import os

# In memory, seeded fresh before every check below, so no check can depend on
# what the one before it wrote.
os.environ["PHC_DB"] = ":memory:"

from fastapi.testclient import TestClient  # noqa: E402

from api import main  # noqa: E402

client = TestClient(main.app)


def reset():
    main.store = main.make_store()

VITALS = {"systolic": 118, "diastolic": 76, "pulse": 80}


def test_the_queue_draws_the_declared_view_with_everyone_on_it():
    body = client.get("/api/queue").json()
    assert body["kind"] == "queue"
    assert len(body["rows"]) == 6
    assert sum(g["count"] for g in body["groups"]) == 6
    stations = {r["thread"]: r["station"] for r in body["rows"]}
    assert stations["enc-001"] == "reception", "a walk in is not registered yet"
    assert stations["enc-002"] == "nurse"
    assert stations["enc-003"] == "doctor"
    assert stations["enc-004"] == "lab"
    assert stations["enc-005"] == "pharmacy"
    assert stations["enc-006"] is None, "a finished line stands nowhere"
    flagged = [r for r in body["rows"] if r["thread"] == "enc-003"][0]
    assert flagged["badges"] == {"vitals.flagged": "crit"}


def test_a_thread_returns_flags_station_line_and_actions():
    body = client.get("/api/threads/enc-002").json()
    assert body["flags"] == ["abha.pending", "registered"]
    assert body["station"] == "nurse"
    assert [s["status"] for s in body["line"]] == ["done", "now", "pending",
                                                   "skipped", "skipped"]
    drawn = [op["id"] for op in body["actions"]]
    assert "phc.op.vitals-record" in drawn
    assert "phc.op.pharmacy-dispense" not in drawn, \
        "an action whose precondition is unmet is absent, not greyed out"
    assert drawn[0] == "phc.op.vitals-record", "this station sorts first"


def test_an_invalid_payload_never_becomes_a_proposal():
    before = len(client.get("/api/threads/enc-002").json()["proposals"])
    reply = client.post("/api/operations/phc.op.vitals-record/propose",
                        json={"thread": "enc-002", "payload": {"systolic": 118}})
    assert reply.status_code == 422
    assert "required" in reply.json()["detail"]
    out_of_range = client.post(
        "/api/operations/phc.op.vitals-record/propose",
        json={"thread": "enc-002", "payload": dict(VITALS, systolic=400)})
    assert out_of_range.status_code == 422
    assert "outside 70 to 250" in out_of_range.json()["detail"]
    assert len(client.get("/api/threads/enc-002").json()["proposals"]) == before


def test_an_agent_cannot_propose_an_irreversible_operation():
    reply = client.post("/api/operations/phc.op.abha-link/propose",
                        json={"thread": "enc-002",
                              "payload": {"method": "link_existing",
                                          "abha_number": "12-1111-1111-1111",
                                          "consent_given": True}})
    assert reply.status_code == 422
    assert "rendered surface" in reply.json()["detail"]


def test_a_proposal_is_not_a_write_and_is_confirmed_exactly_once():
    reply = client.post("/api/operations/phc.op.vitals-record/propose",
                        json={"thread": "enc-002", "payload": VITALS})
    assert reply.status_code == 200
    proposal_id = reply.json()["proposal_id"]
    assert reply.json()["status"] == "proposed"

    # nothing was written: the nurse's station is still the nurse's station.
    thread = client.get("/api/threads/enc-002").json()
    assert "vitals.recorded" not in thread["flags"]
    assert thread["station"] == "nurse"
    assert [p["id"] for p in thread["proposals"]] == [proposal_id]

    confirm = client.post("/api/proposals/%s/confirm" % proposal_id,
                          json={"confirmed": True})
    assert confirm.status_code == 200
    after = confirm.json()["thread"]
    assert "vitals.recorded" in after["flags"]
    assert after["station"] == "doctor"
    assert after["proposals"] == []

    again = client.post("/api/proposals/%s/confirm" % proposal_id,
                        json={"confirmed": True})
    assert again.status_code == 409, "a proposal is confirmed once"
    assert "already confirmed" in again.json()["detail"]
    # and the second attempt wrote nothing.
    assert client.get("/api/threads/enc-002").json()["subject"]["name"] == "Kamala Devi"
    assert len([a for a in client.get("/api/threads/enc-002").json()["audit"]
                if a["outcome"] == "confirmed"]) == 1


def test_confirm_refuses_anything_that_did_not_come_through_propose():
    reply = client.post("/api/proposals/prop-invented/confirm", json={"confirmed": True})
    assert reply.status_code == 404
    assert "propose issued" in reply.json()["detail"]


def test_an_irreversible_commit_needs_the_explicit_confirm():
    body = {"thread": "enc-002", "payload": {"method": "link_existing",
                                             "abha_number": "12-2222-2222-2222",
                                             "consent_given": True}}
    denied = client.post("/api/operations/phc.op.abha-link/commit", json=body)
    assert denied.status_code == 422
    assert "explicit confirm" in denied.json()["detail"]

    ok = client.post("/api/operations/phc.op.abha-link/commit",
                     json=dict(body, confirmed=True))
    assert ok.status_code == 200
    flags = ok.json()["thread"]["flags"]
    assert "abha.linked" in flags and "abha.pending" not in flags
    # capture.consented is declared stored and nothing raises it yet: the
    # kernel raises the flags validate.flags() returns, which are the critical
    # thresholds, and a consent question is not one. Asserted as it is, so the
    # gap cannot be forgotten quietly.
    assert "capture.consented" not in flags


def test_a_walk_in_can_be_registered_and_the_line_moves():
    payload = {"name": "Devi Prasad", "age": 41, "sex": "male",
               "phone": "9800000099", "village": "Sonpur"}
    reply = client.post("/api/operations/phc.op.patient-register/commit",
                        json={"thread": "enc-001", "payload": payload})
    assert reply.status_code == 200
    thread = reply.json()["thread"]
    assert thread["subject"]["name"] == "Devi Prasad"
    assert thread["station"] == "nurse"
    assert thread["flags"] == ["abha.pending", "registered"]
    # registering twice is refused by the precondition, not by a database error.
    twice = client.post("/api/operations/phc.op.patient-register/commit",
                        json={"thread": "enc-001", "payload": payload})
    assert twice.status_code == 422
    assert "precondition" in twice.json()["detail"]


def test_a_capability_the_role_lacks_hides_the_action_and_refuses_the_write():
    thread = client.get("/api/threads/enc-005?role=pharmacist").json()
    assert [op["id"] for op in thread["actions"]] == ["phc.op.pharmacy-dispense"]
    denied = client.post("/api/operations/phc.op.rx-prescribe/commit?role=pharmacist",
                         json={"thread": "enc-005", "payload": {"medications": []}})
    assert denied.status_code == 422


def test_the_dashboard_evaluates_its_metrics_locally():
    body = client.get("/api/views/phc.view.facility-dashboard").json()
    assert body["kind"] == "dashboard"
    by_id = {row["metric"]: row for row in body["rows"]}
    assert by_id["phc.metric.visits"]["numerator"] == 6
    coverage = by_id["phc.metric.abha-coverage"]
    assert coverage["unit"] == "percent" and 0 <= coverage["value"] <= 100
    assert coverage["denominator"] == 5, "five of the six threads have a patient"
    assert coverage["numerator"] == 3 and coverage["value"] == 60.0
    assert client.get("/api/views/phc.view.facility-dashboard?role=lab").status_code == 403


def test_the_summary_view_is_the_thread_panel_declared():
    body = client.get("/api/views/phc.view.patient-summary?thread=enc-006").json()
    titles = [s["title"] for s in body["rows"]]
    assert titles[0] == "Visit" and "Audit trail" in titles
    prescription = [s for s in body["rows"] if s["title"] == "Prescription"][0]
    assert len(prescription["rows"]) == 2
    assert set(prescription["rows"][0]) == {"medication", "dosage_instruction", "status"}
    assert client.get("/api/views/phc.view.patient-summary").status_code == 400


def test_the_mcp_facing_routes_did_not_move():
    assert client.get("/api/v1/phc/whoami/").status_code == 200
    assert "patient.find" in client.get("/api/v1/phc/whoami/").json()["capabilities"]
    reply = client.post("/api/v1/phc/operations/phc.op.lab-result-enter/propose/",
                        json={"patient": "enc-004",
                              "payload": {"analyte": "Haemoglobin", "value": 9.4,
                                          "unit": "g/dL"}})
    assert reply.status_code == 200, reply.text
    assert reply.json()["awaiting"].startswith("clinician review")


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            reset()
            fn()
            ran += 1
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   api: %d checks" % ran)
