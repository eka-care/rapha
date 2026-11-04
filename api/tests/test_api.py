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
    main.OVERRIDES.clear()

VITALS = {"systolic": 118, "diastolic": 76, "pulse": 80}


def test_the_queue_draws_the_declared_view_with_everyone_on_it():
    body = client.get("/api/queue").json()
    assert body["kind"] == "queue"
    assert len(body["rows"]) == 7
    assert sum(g["count"] for g in body["groups"]) == 7
    stations = {r["thread"]: r["station"] for r in body["rows"]}
    # The pregnancy stands at the nurse, like any other registered visit
    # whose vitals are not yet taken. Being followed is not a station.
    assert stations["enc-007"] == "doctor"
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
    # The sixth is the home visit step, skipped because she has not delivered.
    assert [s["status"] for s in body["line"]] == ["done", "now", "pending",
                                                   "skipped", "skipped",
                                                   "skipped"]
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
    # No capture flag of any kind survives the owner's removal of consent on
    # 4 November 2026. Asserted rather than dropped: a flag that came back
    # here would be a gate nothing honours, which looks like protection from
    # every other part of the product.
    assert not [f for f in flags if f.startswith("capture.")], flags


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
    assert twice.json()["detail"] == "Already registered."


def test_a_capability_the_role_lacks_hides_the_action_and_refuses_the_write():
    thread = client.get("/api/threads/enc-005?role=pharmacist").json()
    # Exact equality on purpose: an operation appearing here that nobody meant to
    # grant is exactly what this test is for. handover is present because six
    # roles hold that capability and actions() never filters on the caller's
    # station, so a note is writable from any desk. rx-prescribe is the absence
    # under test.
    # referral-raise joins them for the same reason and on the same
    # capability: a pharmacist who sees something that needs a hospital may
    # say so, and referring is no more the property of one desk than a note
    # is. If that is wrong it is wrong in bundle.yaml, which is where the
    # capability is granted, and not here.
    assert [op["id"] for op in thread["actions"]] == [
        "phc.op.pharmacy-dispense", "phc.op.handover", "phc.op.referral-raise"]
    denied = client.post("/api/operations/phc.op.rx-prescribe/commit?role=pharmacist",
                         json={"thread": "enc-005", "payload": {"medications": []}})
    assert denied.status_code == 422


def test_the_dashboard_evaluates_its_metrics_locally():
    body = client.get("/api/views/phc.view.facility-dashboard").json()
    assert body["kind"] == "dashboard"
    by_id = {row["metric"]: row for row in body["rows"]}
    # 7 since the pregnancy was seeded, and she has no ABHA number, so she
    # is a sixth patient and not a fourth linked one. The coverage falls
    # from 60% to 50% because of her, which is the metric doing its job.
    assert by_id["phc.metric.visits"]["numerator"] == 7
    coverage = by_id["phc.metric.abha-coverage"]
    assert coverage["unit"] == "percent" and 0 <= coverage["value"] <= 100
    assert coverage["denominator"] == 6, "six of the seven threads have a patient"
    assert coverage["numerator"] == 3 and coverage["value"] == 50.0
    assert client.get("/api/views/phc.view.facility-dashboard?role=lab").status_code == 403


def test_the_summary_view_is_the_thread_panel_declared():
    body = client.get("/api/views/phc.view.visit-summary?thread=enc-006").json()
    titles = [s["title"] for s in body["rows"]]
    assert titles[0] == "Visit" and "Audit trail" in titles
    prescription = [s for s in body["rows"] if s["title"] == "Prescription"][0]
    assert len(prescription["rows"]) == 1
    # The five answers a prescription line is made of, drawn as the displays
    # the value sets gave them rather than as the codes stored beside them.
    assert set(prescription["rows"][0]) == {
        "medication_display", "dose", "dose_unit", "frequency_display",
        "route_display", "duration", "duration_unit", "status"}
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
                              # A LOINC code, because the analyte question
                              # binds its answer to a value set and free text
                              # is refused before a row is built.
                              "payload": {"analyte": "718-7", "value": 9.4,
                                          "unit": "g/dL"}})
    assert reply.status_code == 200, reply.text
    assert reply.json()["awaiting"].startswith("clinician review")


# ---------------------------------------------------------- the agent's turn
#
# POST /api/khoj is the composer's endpoint: a sentence in, proposal cards
# out. The properties worth pinning are the same three as everywhere else, plus
# one that is new here, because this is the surface a model's words reach.

SAY = {"thread": "enc-002", "backend": "router"}   # backend pinned so the check
                                                   # never calls Anthropic


def test_an_utterance_proposes_and_the_card_carries_what_the_thread_must_draw():
    reply = client.post("/api/khoj",
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
    # 8 since 2026-11-01, not 7: recording is presumed, so the action that
    # stops it stands on every visit nobody refused and is offered here too.
    # 9 since 2026-11-04: background from elsewhere is seated at this bench,
    # BEHIND the reading -- which is what "1 of" still being the vitals is
    # checking. The count moves when the bundle adds an action; the position
    # moves only if the line changes its mind about what this bench is for.
    # 10 later the same day: STARTING a pregnancy is seated here too, behind
    # the reading for the same reason. Closing one is not counted, and that
    # is the preconditions working rather than an omission: this visit has
    # no open pregnancy, so there is nothing to close and the action is
    # absent rather than drawn and refused. 11 once referring arrived, for
    # the same reason a handover is offered at every desk.
    assert card["order"] == "the kernel lists it 1 of 10 at nurse", \
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
        reply = client.post("/api/khoj",
                            json=dict(SAY, utterance="bp is 140 over 90 and pulse 72"))
    finally:
        main.proposals.confirm, main.proposals.commit = keep
    assert reply.status_code == 200
    assert reply.json()["proposals"][0]["proposal_id"]
    # and the body cannot ask for one either: confirmed is not a parameter of
    # this route, so a sentence carrying it changes nothing.
    smuggled = client.post("/api/khoj",
                           json=dict(SAY, utterance="bp is 138 over 86 and pulse 70",
                                     confirmed=True, surface="rendered"))
    assert smuggled.json()["proposals"][0]["verdict"]["reason"] == "proposed"
    assert "vitals.recorded" not in smuggled.json()["thread"]["flags"]


def test_a_proposal_the_agent_made_is_confirmed_on_screen_and_only_once():
    said = client.post("/api/khoj",
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
    body = client.post("/api/khoj",
                       json=dict(SAY, utterance="what is the weather like")).json()
    assert body["proposals"] == [] and body["understood"] is False
    assert "will not guess" in body["said"]
    # and it lists what the kernel does offer, rather than inventing something.
    assert "Record vitals and triage" in body["said"]
    assert client.get("/api/threads/enc-002").json()["proposals"] == []


def test_a_refusal_carries_the_guard_own_reason_and_a_next_step():
    # enc-003 has vitals already: the guard denies on the precondition.
    body = client.post("/api/khoj",
                       json={"thread": "enc-003", "backend": "router",
                             "utterance": "vitals 120 over 80 and pulse 70"}).json()
    # By operation, not by index: the router offers every candidate the thread
    # draws and their order is the declared line's, so indexing [0] asserted
    # ordering this test does not care about. Naming the operation says what the
    # test means -- the refusal for THIS write carries THIS reason.
    card = next(c for c in body["proposals"] if c["operation"] == "phc.op.vitals-record")
    assert card["proposal_id"] is None
    assert card["verdict"]["reason"] == "Already vitals recorded."
    assert card["verdict"]["next"] and "kernel decides" in card["verdict"]["next"]
    assert card["verdict"]["reason"] in body["said"]
    # a denial is audited even though nothing was written.
    audit = client.get("/api/threads/enc-003").json()["audit"]
    assert audit[-1]["outcome"].startswith("denied:")


def test_the_agent_cannot_talk_its_way_into_an_irreversible_operation():
    body = client.post("/api/khoj",
                       json=dict(SAY, utterance="link her abha number "
                                                "12-1111-1111-1111 by link_existing "
                                                "with consent_given true")).json()
    card = [c for c in body["proposals"] if c["operation"] == "phc.op.abha-link"][0]
    assert card["proposal_id"] is None
    assert "abha.linked" not in body["thread"]["flags"]


def test_agent_say_is_a_deprecated_alias_for_khoj():
    """/agent/say is kept for one release for the Go MCP binary and any agent
    already bound to it, and it must answer exactly as /khoj does. Marked
    `deprecated=True` on the route, which FastAPI puts on the OpenAPI
    operation itself, so a client sees the deprecation without reading a
    comment or the code behind it."""
    reply = client.post("/api/agent/say",
                        json=dict(SAY, utterance="bp is 140 over 90 and pulse 72"))
    assert reply.status_code == 200, reply.text
    assert reply.json()["proposals"][0]["operation"] == "phc.op.vitals-record"

    schema = client.get("/openapi.json").json()
    say_ops = [op for path, methods in schema["paths"].items()
               if path.endswith("/agent/say") for op in methods.values()]
    assert say_ops and all(op.get("deprecated") for op in say_ops), say_ops
    khoj_ops = [op for path, methods in schema["paths"].items()
                if path.endswith("/khoj") for op in methods.values()]
    assert khoj_ops and not any(op.get("deprecated") for op in khoj_ops), khoj_ops


def test_the_planner_only_answers_questions_the_operation_asks():
    # override_reason waives the range check, so no planner may ever fill it.
    # The router cannot; this pins the filter that stops any backend doing so.
    from agent import planner
    op = main.BUNDLE.operations["phc.op.lab-result-enter"]
    assert "override_reason" in {f["link_id"] for f in op["fields"]}, \
        "this is the operation whose questionnaire carries the override"
    assert planner.typed(op, {"analyte": "718-7", "value": 9.4, "unit": "g/dL",
                              "override_reason": "the agent said so",
                              "invented": 1}) == {"analyte": "718-7",
                                                  "value": 9.4, "unit": "g/dL"}


# ---------------------------------------------------------------- the scribe
# The connector is faked at the SDK boundary, not at api/scribe's own, so what
# runs below is the real upload path: the real temporary file, the real
# deletion, the real reading of a response recorded live on 2026-09-11.
#
# Eka is asked for a transcript only now (api/scribe.py, Task 3): there is no
# more EMR-shaped answer to fake. A test that needs a draft fakes the
# transcript here and monkeypatches api.extract's extract() to say what was
# "heard" in it, same as api/scribe.py's own demo() does.

import base64  # noqa: E402
import importlib  # noqa: E402

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
    """The service, as far as this kernel can tell.

    It answers the template endpoints as well as the upload, because the
    shaped note replaced the second provider on 2026-11-01 and resolving a
    template is now part of starting a recording. The workspace starts empty,
    so the first recording of a form CREATES a template here, and the test
    below asserts the second one does not.
    """

    def __init__(self, *answers):
        self.v2rx = FakeV2RX(answers)
        self.templates, self.created, self.listed = {}, [], 0

    def request(self, method, endpoint, json=None, **kw):
        if method == "GET" and endpoint == "/voice/api/v1/template":
            self.listed += 1
            return {"items": [{"id": i, "title": t["title"], "desc": t["desc"],
                               "default": False}
                              for i, t in self.templates.items()]}
        if method == "POST" and endpoint == "/voice/api/v1/template":
            tid = "tpl-%d" % (len(self.templates) + 1)
            self.templates[tid] = dict(json or {})
            self.created.append(dict(json or {}))
            return {"msg": "ok", "template_id": tid}
        if method == "PATCH" and endpoint.startswith("/voice/api/v1/template/"):
            self.templates[endpoint.rsplit("/", 1)[1]].update(json or {})
            return {"msg": "ok"}
        raise AssertionError("the kernel called %s %s" % (method, endpoint))


def fake_scribe(*answers):
    scribe.SESSIONS.clear()
    scribe._templates.clear()
    scribe._client = FakeEka(*answers)
    return scribe._client


RUNNING = {"data": {"output": [], "template_results": {}}}
AUDIO = b"RIFFfake-consultation-audio"

# The note the service returns for the vitals template: a real table, read by
# the real parser. Nothing in these tests stubs the reading, because the
# reading is the part that replaced a model and it is worth exercising.
SHAPED = b"""\
| field | value | row | heard | sure |
|---|---|---|---|---|
| systolic | 140 | | BP is 140 | 0.95 |
"""

TRANSCRIPT = {"data": {"output": [
    {"template_id": "tpl-1", "status": "success",
     "value": base64.b64encode(SHAPED).decode()}],
    "template_results": {"transcript": [
        {"template_id": "transcript", "status": "success",
         "value": base64.b64encode(b"BP is 140 over 90").decode()}]}}}


def consented_thread():
    """enc-003, which stands at the doctor on the seeded day.

    The name is kept for one release. It used to mean "a visit whose capture
    consent stands"; there is no consent since 4 November 2026, so it now
    means only that this is the visit the recording tests record."""
    return "enc-003"


def test_no_visit_is_refused_a_recording_over_consent_any_more():
    """The owner removed consent in full on 4 November 2026.

    enc-004 is the visit that used to refuse: this asserted a 403 whose
    sentence said so, and that not one byte left the machine. The assertion
    is inverted rather than deleted, because a 403 reappearing here would
    mean a gate came back somewhere with nothing left in the product to
    lower it -- a recording refused forever, for a reason nobody can act
    on."""
    reset()
    fake = fake_scribe(TRANSCRIPT)
    reply = client.post("/api/scribe/sessions?thread=enc-004&role=mo"
                        "&operations=phc.op.consult-document", content=AUDIO,
                        headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 200, reply.text
    assert "consent" not in reply.text.lower(), reply.text
    assert reply.json()["status"] == "running", reply.text
    del fake


def test_a_visit_nobody_asked_is_recorded():
    """enc-002 stands at the nurse and nobody put any question to them.

    This was the half that changed on 2026-11-01, when consent became
    presumed; it is now simply the ordinary case, since there is no question
    to put."""
    reset()
    fake = fake_scribe(RUNNING, TRANSCRIPT)
    reply = client.post(
        "/api/scribe/sessions?thread=enc-002&operations=phc.op.vitals-record",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 200, reply.text
    assert len(fake.v2rx.uploads) == 1, fake.v2rx.uploads


def test_a_role_the_scribe_is_not_declared_for_is_refused():
    fake = fake_scribe(TRANSCRIPT)
    thread = consented_thread()
    reply = client.post(
        f"/api/scribe/sessions?thread={thread}&role=pharmacist&operations=phc.op.vitals-record",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert reply.status_code == 403
    assert fake.v2rx.uploads == []


def test_the_recording_reaches_the_service_and_the_file_does_not_outlive_it():
    reset()
    fake = fake_scribe(RUNNING, TRANSCRIPT)
    thread = consented_thread()
    reply = client.post(
        f"/api/scribe/sessions?thread={thread}&role=nurse&operations=phc.op.vitals-record",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
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
    waiting = client.get(f"/api/scribe/sessions/{body['session']}?role=nurse").json()
    assert waiting["status"] == "running" and waiting["drafts"] == []
    got = client.get(f"/api/scribe/sessions/{body['session']}?role=nurse").json()
    assert got["status"] == "ready", got
    values = {d["operation"]: d["values"] for d in got["drafts"]}
    assert values["phc.op.vitals-record"] == {"systolic": 140}
    for d in got["drafts"]:
        assert d["tick"] == ["systolic"], \
            "a number filled by a recording is ticked, not silently trusted"
        assert all(c <= 0.89 for c in d["confidence"].values()), \
            "confidence sent to the renderer is capped at 0.89"

    # The value came out of the service's own note, read by api/shaped.py's
    # parser. Nothing in this test stubbed that reading, and no second
    # provider was called: the fake client refuses any endpoint but the
    # template ones, so a model call anywhere would have raised here.
    assert len(fake.created) == 1, "one template, for the one form recorded"
    created = fake.created[0]
    assert created["title"] == "phc · phc.op.vitals-record", created
    assert "`systolic`" in created["desc"], \
        "the template is built from the questionnaire, not typed into the kernel"

    # A second recording of the same form reuses it. A template per
    # consultation would fill the workspace and cost a call every time.
    client.post(
        f"/api/scribe/sessions?thread={thread}&role=nurse&operations=phc.op.vitals-record",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert len(fake.created) == 1, "the template is made once, not once a recording"


def test_withdrawal_stops_the_fetching_and_drops_the_draft():
    fake = fake_scribe(RUNNING)
    thread = consented_thread()
    started = client.post(
        f"/api/scribe/sessions?thread={thread}&role=mo&operations=phc.op.consult-document",
        content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
    asked = fake.v2rx.asked
    gone = client.delete("/api/scribe/sessions/%s?role=mo" % started["session"]).json()
    assert gone["status"] == "withdrawn" and gone["drafts"] == []
    # The job may well finish at the service. Nothing here ever looks again.
    fake.v2rx.answers = [TRANSCRIPT]
    after = client.get("/api/scribe/sessions/%s?role=mo" % started["session"]).json()
    assert after["status"] == "withdrawn" and after["drafts"] == []
    assert fake.v2rx.asked == asked, "a withdrawn session is never fetched again"


def test_a_stopped_job_comes_back_through_neither_the_poll_nor_the_webhook():
    """Stopping a recording that is still running at the service.

    The test above covers the poll. This is the webhook, which is the other
    way a draft can arrive and is the same collect underneath: a job that
    finishes after somebody pressed Stop must not come back by either road.
    Before this guard the next poll answered with the full draft.

    Stopping used to be an operation of its own that lowered a capture
    consent gate, and withdrawing that consent also blocked every later
    recording on the visit. The owner removed consent in full on 4 November
    2026. Stopping one recording is now exactly that and nothing more, and
    the assertion that a second one was refused went with the gate -- it
    was the gate's property, not this route's.
    """
    fake = fake_scribe(RUNNING)
    thread = consented_thread()
    started = client.post(
        f"/api/scribe/sessions?thread={thread}&role=mo&operations=phc.op.consult-document",
        content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
    assert started["status"] == "running"

    stop = client.delete("/api/scribe/sessions/%s?role=mo" % started["session"])
    assert stop.status_code == 200, stop.text

    fake.v2rx.answers = [TRANSCRIPT]             # the service finished anyway
    asked = fake.v2rx.asked
    after = client.get("/api/scribe/sessions/%s?role=mo" % started["session"]).json()
    assert after["status"] == "withdrawn" and after["drafts"] == [], after
    assert fake.v2rx.asked == asked, "a withdrawn visit's job is never fetched"

    # The webhook is the same rule, because it is the same collect.
    txn = scribe.SESSIONS[started["session"]]["txn"]
    hook = client.post("/api/scribe/webhook", json={"payload": {"transaction_id": txn}}).json()
    assert hook == {"ok": True, "collected": False}, hook
    assert fake.v2rx.asked == asked, "nor by the webhook"

    # And a NEW recording on the same visit is an ordinary recording. This
    # asserted a 403 while consent existed, because withdrawing it stopped
    # capture for the rest of the visit. Stopping one recording no longer
    # says anything about the next.
    again = client.post(
        f"/api/scribe/sessions?thread={thread}&role=mo&operations=phc.op.consult-document",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert again.status_code == 200, again.text
    assert again.json()["session"] != started["session"], "the stopped session came back"


def test_the_webhook_only_collects_a_session_this_kernel_started():
    # The callback fires when the job is done, so the service answers with the
    # draft the first time it is asked.
    fake = fake_scribe(TRANSCRIPT)
    started = client.post(
        "/api/scribe/sessions?thread=enc-003&role=mo&operations=phc.op.consult-document",
        content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
    txn = scribe.SESSIONS[started["session"]]["txn"]

    stranger = client.post("/api/scribe/webhook",
                           json={"transaction_id": "somebody-elses-job"}).json()
    assert stranger == {"ok": True, "collected": False}
    assert fake.v2rx.asked == 0, "an unknown transaction id is not looked up anywhere"

    mine = client.post("/api/scribe/webhook", json={"payload": {"transaction_id": txn}}).json()
    assert mine == {"ok": True, "collected": True}
    assert client.get("/api/scribe/sessions/%s?role=mo" % started["session"]).json()["status"] == "ready"


def test_a_stopped_session_refuses_the_template_switch():
    """The extract route rebuilds drafts from a transcript, so it is a draft
    returning path like the poll and must refuse a stopped session like the
    poll. It read the consent gate until 4 November 2026; what it reads now
    is whether the session itself was withdrawn."""
    reset()
    fake_scribe(TRANSCRIPT)
    try:
        thread = consented_thread()
        started = client.post(
            f"/api/scribe/sessions?thread={thread}&role=mo&operations=phc.op.consult-document",
            content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
        ready = client.get(f"/api/scribe/sessions/{started['session']}?role=mo").json()
        assert ready["status"] == "ready", ready
        stop = client.delete("/api/scribe/sessions/%s?role=mo" % started["session"])
        assert stop.status_code == 200, stop.text
        switched = client.post(f"/api/scribe/sessions/{started['session']}/extract?role=mo",
                               json={"operations": ["phc.op.consult-document"]})
        assert switched.status_code == 403, switched.text
        assert "type the note" in switched.json()["detail"].lower()
        session = scribe.SESSIONS[started["session"]]
        assert session["status"] == "withdrawn" and session["transcript"] == "" \
            and session["drafts"] == [], session
    finally:
        reset()


def test_a_session_is_only_the_callers_who_started_it():
    fake_scribe(RUNNING)
    started = client.post(
        f"/api/scribe/sessions?thread={consented_thread()}&role=mo"
        "&operations=phc.op.consult-document",
        content=AUDIO, headers={"Content-Type": "audio/webm"}).json()
    sid = started["session"]
    other = {"X-PHC-Role": "mo", "X-PHC-Actor": "user:someone-else"}
    assert client.get(f"/api/scribe/sessions/{sid}", headers=other).status_code == 404
    assert client.delete(f"/api/scribe/sessions/{sid}", headers=other).status_code == 404
    assert client.post(f"/api/scribe/sessions/{sid}/extract", headers=other,
                       json={"operations": []}).status_code == 404
    assert scribe.SESSIONS[sid]["status"] == "running", "a stranger changed nothing"


def test_a_session_id_nobody_started_is_a_404_that_says_so():
    fake_scribe(RUNNING)
    reply = client.get("/api/scribe/sessions/scr-invented")
    assert reply.status_code == 404
    assert "Nothing was kept" in reply.json()["detail"]


def test_templates_are_the_stations_and_the_callers():
    body = client.get("/api/scribe/templates?station=doctor&role=mo").json()
    assert body["default"] == "phc.op.consult-document"
    # The doctor's five: the general consultation, the three templates that
    # narrow it, and the prescription. Order is the bundle's own, and the
    # three templates are generated from one `templates` declaration rather
    # than written here or anywhere else.
    assert [c["operation"] for c in body["choose"]] == \
        ["phc.op.consult-document", "phc.op.ncd-review",
         "phc.op.antenatal-visit", "phc.op.followup", "phc.op.rx-prescribe"]
    assert [c["title"] for c in body["choose"]][1:4] == \
        ["Review a long term condition", "Antenatal visit", "Follow up visit"], \
        "a template's title is the declaration's, not a renderer's"
    # NO LANGUAGE LIST. Nothing picks one: every recording goes up as every
    # language this facility supports and the service decides what it heard.
    # A consultation at a primary health centre is not in one language, and
    # asking somebody to predict their own before they speak cost them the
    # transcript when they guessed wrong.
    assert "languages" not in body, body
    assert set(scribe.LANGUAGES["auto"]) >= {"hi", "ta"}, scribe.LANGUAGES["auto"]
    nurse_as_pharmacist = client.get("/api/scribe/templates?station=nurse&role=pharmacist").json()
    assert nurse_as_pharmacist["choose"] == [], "no capability, no template"


ACTOR = {"X-PHC-Actor": "user:ward-1"}


def test_a_recording_fills_the_named_template_and_switches_without_rerecording():
    reset()
    fake = fake_scribe(TRANSCRIPT)
    thread = consented_thread()                  # the helper the consent test uses
    started = client.post(
        f"/api/scribe/sessions?thread={thread}&operations=phc.op.vitals-record"
        "&language=hinglish&role=nurse",
        content=AUDIO, headers=ACTOR | {"Content-Type": "audio/webm"}).json()
    ready = client.get(f"/api/scribe/sessions/{started['session']}?role=nurse",
                       headers=ACTOR).json()
    assert ready["status"] == "ready", ready
    assert ready["drafts"][0]["values"] == {"systolic": 140}
    assert ready["drafts"][0]["tick"] == ["systolic"]
    assert fake.v2rx.uploads[0]["bytes"] == AUDIO

    # One person at one desk, whose role changes: the session is the actor's.
    switched = client.post(f"/api/scribe/sessions/{started['session']}/extract?role=mo",
                           headers=ACTOR,
                           json={"operations": ["phc.op.consult-document"]}).json()
    assert switched["operations"] == ["phc.op.consult-document"]
    assert len(fake.v2rx.uploads) == 1, "switching never uploads again"

    refused = client.post(
        f"/api/scribe/sessions?thread={thread}&operations=phc.op.lab-order&role=mo",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert refused.status_code == 403, "not on the scribe's list"
    too_many = client.post(
        f"/api/scribe/sessions?thread={thread}&role=mo&operations="
        "phc.op.consult-document,phc.op.rx-prescribe,phc.op.vitals-record",
        content=AUDIO, headers={"Content-Type": "audio/webm"})
    assert too_many.status_code == 400


def test_roles_lists_presets_and_saves_a_deviation():
    got = client.get("/api/roles").json()
    # The nine in bundle.yaml are the presets, and they are the 70%.
    assert "frontdesk" in got["presets"] and "nurse" in got["presets"]
    assert "patient.register" in got["presets"]["frontdesk"]
    assert "vitals.record" not in got["presets"]["frontdesk"]

    # Enabling a function for a role is a capability grant and nothing else.
    body = {"capabilities": got["presets"]["frontdesk"] + ["vitals.record"]}
    saved = client.put("/api/roles/frontdesk", json=body).json()
    assert "vitals.record" in saved["capabilities"]

    # And the preset is untouched: a facility's own combination never edits
    # the shipped role.
    again = client.get("/api/roles").json()
    assert "vitals.record" not in again["presets"]["frontdesk"]

    # The grant took effect: the next request as that role carries it.
    assert "vitals.record" in client.get("/api/facility?role=frontdesk").json()["user"]["capabilities"]

    # And a saved deviation comes back on the read, not just the preset: an
    # editor that seeds from `presets` alone would show frontdesk exactly as
    # it shipped, and a later unrelated save would silently undo this grant.
    assert again["overrides"]["frontdesk"] == saved["capabilities"]


def test_removing_a_capability_from_a_preset_takes_and_stays_removed():
    # The bug this guards against was a revocation, not a grant: an admin
    # takes patient.register away from frontdesk, and it must actually be
    # gone -- from the saved override, from the live capability set, and
    # from what the next GET /roles reports -- while the preset keeps it, so
    # "Reset to preset" still means something.
    preset = client.get("/api/roles").json()["presets"]["frontdesk"]
    assert "patient.register" in preset, "the case is worthless if it was never held"

    narrowed = [c for c in preset if c != "patient.register"]
    saved = client.put("/api/roles/frontdesk", json={"capabilities": narrowed}).json()
    assert "patient.register" not in saved["capabilities"]

    again = client.get("/api/roles").json()
    assert "patient.register" not in again["overrides"]["frontdesk"]
    assert "patient.register" in again["presets"]["frontdesk"]

    # And the revocation actually took effect, not just got stored: the next
    # request as that role carries the narrower set.
    live = client.get("/api/facility?role=frontdesk").json()["user"]["capabilities"]
    assert "patient.register" not in live


def test_a_caller_without_facility_admin_cannot_edit_a_role():
    # frontdesk holds no facility.admin in any preset, so it is refused, not
    # silently ignored: the preset stays exactly as it was.
    denied = client.put("/api/roles/frontdesk?role=frontdesk", json={"capabilities": ["patient.find"]})
    assert denied.status_code == 403
    assert "frontdesk" not in main.OVERRIDES


def test_a_role_write_refuses_a_capability_the_bundle_does_not_declare():
    denied = client.put("/api/roles/frontdesk", json={"capabilities": ["not.a.capability"]})
    assert denied.status_code == 400
    assert "frontdesk" not in main.OVERRIDES


def test_the_register_lists_every_patient_and_counts_their_visits():
    """The top of the patients screen's hierarchy: a person, and how many
    times they have been. The visits themselves are NOT in this answer --
    `GET /subjects/{id}` is what opening a row asks for, so the list and the
    thread's own spine cannot disagree about somebody's history."""
    body = client.get("/api/patients?limit=50").json()
    assert body["total"] >= 1, body
    by_id = {p["id"]: p for p in body["patients"]}
    # enc-003 and enc-000 are the same person in the seed, which is the whole
    # reason this screen exists: two visits, one row.
    returning = by_id["seed-0003"]
    assert returning["visits"] == 2, returning
    assert returning["subject"]["name"] == "Ramesh Kumar"
    assert "id" not in returning["subject"], "the id is the row's, not a field on it"
    # Newest first, so whoever was here today is who somebody is looking for.
    stamps = [p["last"] for p in body["patients"] if p["last"]]
    assert stamps == sorted(stamps, reverse=True), stamps


def test_the_register_is_refused_without_the_capability_to_find_a_patient():
    """Every role this bundle ships holds `patient.find`, so the refusal can
    only be reached by asking as somebody who does not -- which is what the
    guard is for the day a bundle declares such a role."""
    import api.main as main
    role = "no-find"
    main.ROLES[role] = []
    try:
        assert client.get(f"/api/patients?role={role}").status_code == 403
        assert client.get(f"/api/subjects/seed-0003?role={role}").status_code == 403
    finally:
        del main.ROLES[role]


def test_no_subject_carries_the_kernels_own_bookkeeping():
    """`operation` is on every clinical row so that a correction can find the
    rows its own form wrote. It is OUR schema, not a fact about a patient,
    and it must not reach a screen.

    Both paths are held, because there are two and they are in different
    files: `ref_or_404` here builds one thread's subject, and the adapter's
    `threads()` builds a queue's. The first version of this dropped it in
    one of them, and the context rail went on printing a line reading
    "Operation: phc.op.patient-register" beside somebody's village.
    """
    one = client.get("/api/threads/enc-003").json()["subject"]
    assert one["name"], one
    assert "operation" not in one, one

    rows = client.get("/api/views/phc.view.station-queue").json()["rows"]
    assert rows, "the queue is empty, so this check proves nothing"
    for row in rows:
        assert "operation" not in (row.get("subject") or {}), row


if __name__ == "__main__":
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            reset()
            fn()
            ran += 1
            print("ok   %s" % name.replace("_", " ")[5:])
    print("ok   api: %d checks" % ran)
