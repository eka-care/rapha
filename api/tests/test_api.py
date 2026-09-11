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
    # and the second attempt wrote nothing. Counted for this operation, not for
    # the thread: the seed declares its own audit trail, so enc-002 already
    # carries a confirmed registration before this test does anything.
    assert client.get("/api/threads/enc-002").json()["subject"]["name"] == "Kamala Devi"
    assert len([a for a in client.get("/api/threads/enc-002").json()["audit"]
                if a["outcome"] == "confirmed"
                and a["operation"] == "phc.op.vitals-record"]) == 1


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


# ---------------------------------------------------------- the agent's turn
#
# POST /api/agent/say is the composer's endpoint: a sentence in, proposal cards
# out. The properties worth pinning are the same three as everywhere else, plus
# one that is new here, because this is the surface a model's words reach.

SAY = {"thread": "enc-002", "backend": "router"}   # backend pinned so the check
                                                   # never calls Anthropic


def test_an_utterance_proposes_and_the_card_carries_what_the_thread_must_draw():
    reply = client.post("/api/agent/say",
                        json=dict(SAY, utterance="bp is 140 over 90 and pulse 72",
                                  confidence={"systolic": 0.82, "pulse": 0.91}))
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["backend"] == "router" and body["understood"]
    card = body["proposals"][0]
    assert card["operation"] == "phc.op.vitals-record"
    assert card["payload"] == {"systolic": 140, "diastolic": 90, "pulse": 72}
    # per field, and only for fields that ended up in the payload.
    assert card["confidence"] == {"systolic": 0.82, "pulse": 0.91}
    assert card["verdict"] == {"allowed": True, "reason": "proposed", "next": ""}
    assert card["order"] == "the kernel lists it 1 of 3 at nurse", \
        "ordering is read from kernel actions(), never decided by the agent"
    assert card["offered_here"] is True

    # A proposal and not a write: the flag is still down and the station has
    # not moved, and the thread that came back says so without a second read.
    assert "vitals.recorded" not in body["thread"]["flags"]
    assert body["thread"]["station"] == "nurse"
    assert card["proposal_id"] in [p["id"] for p in body["thread"]["proposals"]]


def test_the_agent_endpoint_has_no_path_to_a_write():
    """Proved by removing the floor: both write verbs explode for the turn."""
    def boom(*a, **kw):
        raise AssertionError("the agent endpoint reached a write verb")

    keep = main.proposals.confirm, main.proposals.commit
    main.proposals.confirm, main.proposals.commit = boom, boom
    try:
        reply = client.post("/api/agent/say",
                            json=dict(SAY, utterance="bp is 140 over 90 and pulse 72"))
    finally:
        main.proposals.confirm, main.proposals.commit = keep
    assert reply.status_code == 200
    assert reply.json()["proposals"][0]["proposal_id"]
    # and the body cannot ask for one either: confirmed is not a parameter of
    # this route, so a sentence carrying it changes nothing.
    smuggled = client.post("/api/agent/say",
                           json=dict(SAY, utterance="bp is 138 over 86 and pulse 70",
                                     confirmed=True, surface="rendered"))
    assert smuggled.json()["proposals"][0]["verdict"]["reason"] == "proposed"
    assert "vitals.recorded" not in smuggled.json()["thread"]["flags"]


def test_a_proposal_the_agent_made_is_confirmed_on_screen_and_only_once():
    said = client.post("/api/agent/say",
                       json=dict(SAY, utterance="bp is 140 over 90 and pulse 72")).json()
    proposal_id = said["proposals"][0]["proposal_id"]
    confirm = client.post("/api/proposals/%s/confirm" % proposal_id,
                          json={"confirmed": True})
    assert confirm.status_code == 200
    assert "vitals.recorded" in confirm.json()["thread"]["flags"]
    again = client.post("/api/proposals/%s/confirm" % proposal_id,
                        json={"confirmed": True})
    assert again.status_code == 409, "a proposal is confirmed once, whoever made it"
    # both halves are in the audit trail: the agent proposed, a person confirmed.
    audit = client.get("/api/threads/enc-002").json()["audit"]
    proposed = [a for a in audit if a["outcome"] == "proposed"][-1]
    assert proposed["actor"].startswith("agent:")
    assert [a for a in audit if a["outcome"] == "confirmed"][-1]["actor"] == "user:demo"


def test_an_utterance_it_cannot_map_says_so_instead_of_guessing():
    body = client.post("/api/agent/say",
                       json=dict(SAY, utterance="what is the weather like")).json()
    assert body["proposals"] == [] and body["understood"] is False
    assert "will not guess" in body["said"]
    # and it lists what the kernel does offer, rather than inventing something.
    assert "Record vitals and triage" in body["said"]
    assert client.get("/api/threads/enc-002").json()["proposals"] == []


def test_a_refusal_carries_the_guard_own_reason_and_a_next_step():
    # enc-003 has vitals already: the guard denies on the precondition.
    body = client.post("/api/agent/say",
                       json={"thread": "enc-003", "backend": "router",
                             "utterance": "vitals 120 over 80 and pulse 70"}).json()
    card = body["proposals"][0]
    assert card["proposal_id"] is None
    assert card["verdict"]["reason"] == "precondition not met: not vitals.recorded"
    assert card["verdict"]["next"] and "kernel decides" in card["verdict"]["next"]
    assert card["verdict"]["reason"] in body["said"]
    # a denial is audited even though nothing was written.
    audit = client.get("/api/threads/enc-003").json()["audit"]
    assert audit[-1]["outcome"].startswith("denied:")


def test_the_agent_cannot_talk_its_way_into_an_irreversible_operation():
    body = client.post("/api/agent/say",
                       json=dict(SAY, utterance="link her abha number "
                                                "12-1111-1111-1111 by link_existing "
                                                "with consent_given true")).json()
    card = [c for c in body["proposals"] if c["operation"] == "phc.op.abha-link"][0]
    assert card["proposal_id"] is None
    assert "abha.linked" not in body["thread"]["flags"]


def test_the_planner_only_answers_questions_the_operation_asks():
    # override_reason waives the range check, so no planner may ever fill it.
    # The router cannot; this pins the filter that stops any backend doing so.
    from agent import planner
    op = main.BUNDLE.operations["phc.op.lab-result-enter"]
    assert "override_reason" in {f["link_id"] for f in op["fields"]}, \
        "this is the operation whose questionnaire carries the override"
    assert planner.typed(op, {"analyte": "Haemoglobin", "value": 9.4, "unit": "g/dL",
                              "override_reason": "the agent said so",
                              "invented": 1}) == {"analyte": "Haemoglobin",
                                                  "value": 9.4, "unit": "g/dL"}



if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            reset()
            fn()
            ran += 1
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   api: %d checks" % ran)
