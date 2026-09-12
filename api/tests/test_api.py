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
    body = client.get("/api/views/phc.view.visit-summary?thread=enc-006").json()
    titles = [s["title"] for s in body["rows"]]
    assert titles[0] == "Visit" and "Audit trail" in titles
    prescription = [s for s in body["rows"] if s["title"] == "Prescription"][0]
    assert len(prescription["rows"]) == 2
    assert set(prescription["rows"][0]) == {"medication", "dosage_instruction", "status"}
    assert client.get("/api/views/phc.view.visit-summary").status_code == 400


def test_a_section_s_declared_resource_reaches_the_serialised_response():
    # The rail on the thread screen (web/src/loops.ts: records()) decides a
    # section is a document, not kernel structure, by reading its `resource`
    # off the JSON the API actually sends - not off the in-process ViewResult,
    # and not off the frontend's own mock, which hardcodes it. If `resource`
    # were ever dropped again on the way to JSON, every other check here would
    # stay green while the rail silently emptied for every real user.
    body = client.get("/api/views/phc.view.visit-summary?thread=enc-006").json()
    prescription = [s for s in body["rows"] if s["title"] == "Prescription"][0]
    assert prescription.get("resource") == "medication_request", \
        "a section that reads a resource must carry that resource in the response"
    visit = [s for s in body["rows"] if s["title"] == "Visit"][0]
    assert visit.get("resource") is None, \
        "a section that shows a kernel structure carries no resource"


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


# ---------------------------------------------------------------- the scribe
# The connector is faked at the SDK boundary, not at api/scribe's own, so what
# runs below is the real upload path: the real temporary file, the real
# deletion, the real reading of a response recorded live on 2026-09-11.

from api import scribe  # noqa: E402


class FakeV2RX:
    """Stands in for ekacare.v2rx. Records what it was handed and whether the
    file was still on disk when it was handed it."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.uploads = []
        self.asked = 0

    def upload(self, paths, txn_id=None, action=None, extra_data=None,
               output_format=None):
        with open(paths[0], "rb") as handle:
            self.uploads.append({"path": paths[0], "txn": txn_id, "action": action,
                                 "bytes": handle.read()})
        return {"txn_id": txn_id}

    def get_session_status(self, txn, action=None):
        self.asked += 1
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class FakeEka:
    def __init__(self, *answers):
        self.v2rx = FakeV2RX(answers)


def fake_scribe(*answers):
    scribe.SESSIONS.clear()
    scribe._client = FakeEka(*answers)
    return scribe._client


RUNNING = {"data": {"output": [], "template_results": {}}}
AUDIO = b"RIFFfake-consultation-audio"


def test_a_visit_without_capture_consent_is_never_recorded():
    fake = fake_scribe(scribe.SAMPLE)
    # enc-002 stands at the nurse and nobody asked it for consent.
    reply = client.post("/api/scribe/sessions?thread=enc-002", content=AUDIO,
                        headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 403
    assert "consent" in reply.json()["detail"].lower()
    assert "type the note" in reply.json()["detail"].lower(), \
        "a refusal says what to do instead, because declining is not a barrier to care"
    assert fake.v2rx.uploads == [], "not one byte left this machine"


def test_a_role_the_scribe_is_not_declared_for_is_refused():
    fake = fake_scribe(scribe.SAMPLE)
    reply = client.post("/api/scribe/sessions?thread=enc-003&role=pharmacist",
                        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 403
    assert fake.v2rx.uploads == []


def test_the_recording_reaches_the_service_and_the_file_does_not_outlive_it():
    fake = fake_scribe(RUNNING, scribe.SAMPLE)
    reply = client.post("/api/scribe/sessions?thread=enc-003", content=AUDIO,
                        headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["status"] == "running"
    assert "txn" not in body and "transaction_id" not in body, \
        "the handle on somebody's consultation audio is not the browser's"

    sent = fake.v2rx.uploads[0]
    assert sent["bytes"] == AUDIO
    assert sent["path"].endswith(".webm"), "the browser said webm, so the file is webm"
    assert not os.path.exists(sent["path"]), "the one copy is deleted in start()'s finally"
    assert not sent["path"].startswith(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "nothing under this repository ever held it"

    # The browser polls. The first answer is Eka's 202 with an empty output
    # list, which is not a failure and must not be drawn as one.
    waiting = client.get("/api/scribe/sessions/%s" % body["session"]).json()
    assert waiting["status"] == "running" and waiting["drafts"] == []
    got = client.get("/api/scribe/sessions/%s" % body["session"]).json()
    assert got["status"] == "ready", got
    values = {d["operation"]: d["values"] for d in got["drafts"]}
    assert values["phc.op.consult-document"]["assessment"]
    assert values["phc.op.rx-prescribe"]["medications"][0]["medication"] == "Amoxicillin 500 mg"
    every = {k: v for d in got["drafts"] for k, v in d["values"].items()}
    assert "temperature" not in every, "a recording never fills a number"
    for d in got["drafts"]:
        assert all(c < 0.9 for c in d["confidence"].values()), \
            "every drafted value arrives unconfirmed"


def test_withdrawal_stops_the_fetching_and_drops_the_draft():
    fake = fake_scribe(RUNNING)
    started = client.post("/api/scribe/sessions?thread=enc-003", content=AUDIO,
                          headers={"Content-Type": "audio/webm"}).json()
    asked = fake.v2rx.asked
    gone = client.delete("/api/scribe/sessions/%s" % started["session"]).json()
    assert gone["status"] == "withdrawn" and gone["drafts"] == []
    # The job may well finish at the service. Nothing here ever looks again.
    fake.v2rx.answers = [scribe.SAMPLE]
    after = client.get("/api/scribe/sessions/%s" % started["session"]).json()
    assert after["status"] == "withdrawn" and after["drafts"] == []
    assert fake.v2rx.asked == asked, "a withdrawn session is never fetched again"


def test_consent_withdrawn_while_the_job_runs_stops_the_poll_and_the_webhook():
    """E.3, on the server and not only in the browser.

    The Stop button is a DELETE and the test above covers it. This is the other
    half: the patient says stop, the doctor commits the withdrawal, and the
    recording that is still running at the service must not come back. Before
    this guard the next poll answered with the full draft.

    The withdrawal used to ride on the consultation form, which meant it could
    not be recorded without also writing a note. It is now its own operation
    with its own one question form, so this posts that instead.
    """
    fake = fake_scribe(RUNNING)
    started = client.post("/api/scribe/sessions?thread=enc-003", content=AUDIO,
                          headers={"Content-Type": "audio/webm"}).json()
    assert started["status"] == "running"

    stop = client.post("/api/operations/phc.op.capture-withdraw/commit?role=mo",
                       json={"thread": "enc-003", "confirmed": True,
                             "payload": {"capture_stop": True}})
    assert stop.status_code == 200, stop.text
    assert "capture.withdrawn" in stop.json()["thread"]["flags"]
    assert "capture.consented" not in stop.json()["thread"]["flags"]

    fake.v2rx.answers = [scribe.SAMPLE]          # the service finished anyway
    asked = fake.v2rx.asked
    after = client.get("/api/scribe/sessions/%s" % started["session"]).json()
    assert after["status"] == "withdrawn" and after["drafts"] == [], after
    assert fake.v2rx.asked == asked, "a withdrawn visit's job is never fetched"

    # The webhook is the same rule, because it is the same collect.
    txn = scribe.SESSIONS[started["session"]]["txn"]
    hook = client.post("/api/scribe/webhook", json={"payload": {"transaction_id": txn}}).json()
    assert hook == {"ok": True, "collected": False}, hook
    assert fake.v2rx.asked == asked, "nor by the webhook"

    # And a second recording cannot be started on that visit at all.
    again = client.post("/api/scribe/sessions?thread=enc-003", content=AUDIO,
                        headers={"Content-Type": "audio/webm"})
    assert again.status_code == 403, again.text


def test_the_webhook_only_collects_a_session_this_kernel_started():
    # The callback fires when the job is done, so the service answers with the
    # draft the first time it is asked.
    fake = fake_scribe(scribe.SAMPLE)
    started = client.post("/api/scribe/sessions?thread=enc-003", content=AUDIO,
                          headers={"Content-Type": "audio/webm"}).json()
    txn = scribe.SESSIONS[started["session"]]["txn"]

    stranger = client.post("/api/scribe/webhook",
                           json={"transaction_id": "somebody-elses-job"}).json()
    assert stranger == {"ok": True, "collected": False}
    assert fake.v2rx.asked == 0, "an unknown transaction id is not looked up anywhere"

    mine = client.post("/api/scribe/webhook", json={"payload": {"transaction_id": txn}}).json()
    assert mine == {"ok": True, "collected": True}
    assert client.get("/api/scribe/sessions/%s" % started["session"]).json()["status"] == "ready"


def test_a_session_id_nobody_started_is_a_404_that_says_so():
    fake_scribe(RUNNING)
    reply = client.get("/api/scribe/sessions/scr-invented")
    assert reply.status_code == 404
    assert "Nothing was kept" in reply.json()["detail"]


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            reset()
            fn()
            ran += 1
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   api: %d checks" % ran)
