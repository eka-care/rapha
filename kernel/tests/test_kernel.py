"""Run: python3 -m kernel.tests.test_kernel

The kernel with no database and no network. The store is a dict; every rule
under test is a pure function of it. The checks that matter are the ones that
fail loudly if a safety property regresses: an action visible before its
precondition, an agent finding a path to an irreversible write, an out of
range value committed without a reason, a patient parked at a station nobody
sent them to, and a workflow declaration that has stopped driving the line.
"""
from __future__ import annotations

import dataclasses
import inspect
import json

from datetime import datetime, timezone

from care_phc.thread import Snapshot, derive
from care_phc.thread import station as coded_station
from catalogue import guard, vocab
from kernel import contracts as c
from kernel import declarations, proposals, state, views

BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
OPS = BUNDLE.operations
T = "enc-1"


class Fake:
    """A Store the tests can see through. Rows are dicts, tagged with a thread.

    `thread=None` on a read means facility wide, which is what a metric asks
    for. Nothing here enforces a rule; the kernel is what is under test.
    """

    def __init__(self, stored=(), threads=(), stored_by_thread=None):
        self.rows, self.props, self.log = {}, {}, []
        self.stored, self._threads = set(stored), list(threads)
        # Every existing caller shares one global `stored` set, which is fine
        # while every test works one thread at a time (T = "enc-1"). A
        # tasklist walks many threads at once and needs some of them to hold
        # a stored flag (capture.declined) that others do not, so this is an
        # additive per-thread override: unset for a thread, `stored_flags`
        # falls back to the global set exactly as before.
        self._stored_by_thread = {t: set(f) for t, f in (stored_by_thread or {}).items()}

    # test helpers
    def add(self, resource, n=1, thread=T, **fields):
        for _ in range(n):
            self.rows.setdefault(resource, []).append(dict(fields, _thread=thread))
        return self

    def _match(self, resource, thread, where):
        out = []
        for row in self.rows.get(resource, []):
            if thread is not None and row["_thread"] != thread:
                continue
            for field, cond in (where or {}).items():
                value = row.get(field)
                if cond == "*":
                    if value in (None, ""):
                        break
                elif isinstance(cond, dict):
                    if "gte" in cond and not (value is not None and value >= cond["gte"]):
                        break
                    if "lt" in cond and not (value is not None and value < cond["lt"]):
                        break
                elif value != cond:
                    break
            else:
                out.append(row)
        return out

    # Store protocol
    def count(self, resource, *, thread, where):
        return len(self._match(resource, thread, where))

    def select(self, resource, *, thread, where, fields, limit):
        return [{k: r.get(k) for k in fields}
                for r in self._match(resource, thread, where)[:limit]]

    def threads(self, *, workflow, scope):
        return list(self._threads)

    def stored_flags(self, thread):
        if thread in self._stored_by_thread:
            return frozenset(self._stored_by_thread[thread])
        return frozenset(self.stored)

    def write(self, resource, record, *, thread):
        self.add(resource, thread=thread, **record)
        return f"{resource}-{len(self.rows[resource])}"

    def raise_flag(self, thread, flag):
        self.stored.add(flag)

    def put_proposal(self, proposal):
        self.props[proposal.id] = proposal

    def proposals(self, thread, *, status=None):
        return [p for p in self.props.values()
                if p.thread == thread and (status is None or p.status == status)]

    def append_audit(self, record):
        self.log.append(record)

    def audit(self, thread):
        return [r for r in self.log if r.thread == thread]


def registered(**more):
    """A store holding a registered patient, plus whatever else is asked for."""
    s = Fake(**{k: v for k, v in more.items() if k in ("stored", "threads")})
    s.add("patient", abha_number=more.get("abha"))
    for res, n in more.get("rows", {}).items():
        s.add(res, n=n, **more.get("fields", {}).get(res, {}))
    return s


def consulted():
    return registered(rows={"observation": 2, "notes": 1},
                      fields={"observation": {"category": "vital-signs"}})


VITALS = {"systolic": 122, "diastolic": 78, "pulse": 74}
# One valid prescription row and one valid diagnosis row, and both must stay
# valid: a repeating group is validated per row now, so a half filled row is a
# denial for a reason that has nothing to do with the rule a check is about.
# Written out here rather than per test so that a new sub question breaks one
# line instead of eight. The codes are the value sets' own.
RX = {"medications": [{"drug": "774586009", "dose": 500, "dose_unit": "mg",
                       "route": "26643006", "frequency": "229798009",
                       "duration": 5, "duration_unit": "d"}]}
RX_EDITED = {"medications": [dict(RX["medications"][0], dose=250)]}
DX = [{"condition": "44054006", "clinical_status": "active",
       "verification_status": "confirmed"}]


# --------------------------------------------------------------------------
# the workflow declaration drives the line
# --------------------------------------------------------------------------

def test_the_declaration_and_not_a_constant_decides_the_line():
    s = consulted()
    known = state.flags(s, T, WF)
    assert state.station(WF, known) is None, "consulted with no orders is finished"

    # Reorder the declaration and the station follows it. Nothing else changed.
    swapped = dataclasses.replace(WF, steps=[WF.steps[1], WF.steps[0]] + list(WF.steps[2:]))
    fresh = state.flags(Fake(), T, WF)
    assert state.station(WF, fresh) == "reception"
    assert state.station(swapped, fresh) == "nurse", "the line came from a constant"

    # A step the declaration does not carry cannot be a station.
    without_lab = dataclasses.replace(WF, steps=[s for s in WF.steps if s.station != "lab"])
    ordered = consulted()
    ordered.add("service_request")
    assert state.station(WF, state.flags(ordered, T, WF)) == "lab"
    assert state.station(without_lab, state.flags(ordered, T, without_lab)) is None


def test_declared_states_reproduce_the_coded_derivation():
    """While care_phc/thread.py exists, the two must agree flag for flag."""
    cases = [
        dict(),
        dict(patient=1),
        dict(patient=1, abha="12-3456"),
        dict(patient=1, vitals=3, notes=1),
        dict(patient=1, vitals=1, notes=1, service_request=1, diagnostic_report=1),
        dict(patient=1, vitals=1, notes=1, service_request=1, diagnostic_report=1,
             final=True),
        dict(patient=1, notes=1, rx=3, dispense=2),
        dict(patient=1, notes=1, rx=3, dispense=3),
        dict(patient=1, booking=1, stored={"vitals.flagged", "rx.confirmed"}),
    ]
    for case in cases:
        s = Fake(stored=case.get("stored", ()))
        if case.get("patient"):
            s.add("patient", abha_number=case.get("abha"))
        s.add("observation", n=case.get("vitals", 0), category="vital-signs")
        s.add("notes", n=case.get("notes", 0))
        s.add("medication_request", n=case.get("rx", 0), status="active")
        s.add("medication_dispense", n=case.get("dispense", 0))
        s.add("service_request", n=case.get("service_request", 0))
        s.add("diagnostic_report", n=case.get("diagnostic_report", 0),
              status="final" if case.get("final") else "partial")
        s.add("token_booking", n=case.get("booking", 0), status="booked")

        snap = Snapshot(
            patient_exists=bool(case.get("patient")), abha_number=case.get("abha"),
            vitals_observations=case.get("vitals", 0), consult_notes=case.get("notes", 0),
            active_medication_requests=case.get("rx", 0), prescribed_lines=case.get("rx", 0),
            dispensed_lines=case.get("dispense", 0),
            service_requests=case.get("service_request", 0),
            diagnostic_reports=case.get("diagnostic_report", 0),
            final_diagnostic_reports=case.get("diagnostic_report", 0) if case.get("final") else 0,
            bookings=case.get("booking", 0), stored=frozenset(case.get("stored", ())))

        declared, coded = state.flags(s, T, WF), derive(snap)
        assert declared == coded, f"{case}: declared {sorted(declared)} coded {sorted(coded)}"
        assert state.station(WF, declared) == coded_station(coded), case


def test_station_skips_steps_the_patient_was_never_sent_to():
    s = consulted()
    assert state.station(WF, state.flags(s, T, WF)) is None
    s.add("medication_request", status="active")
    assert state.station(WF, state.flags(s, T, WF)) == "pharmacy", "never sent to the lab"
    statuses = {x.station: x.status for x in state.line(WF, state.flags(s, T, WF))}
    assert statuses == {"reception": "done", "nurse": "done", "doctor": "done",
                        "lab": "skipped", "pharmacy": "now"}


def test_only_the_declared_stored_flags_survive_derivation():
    s = registered(stored={"vitals.flagged", "rx.confirmed"})
    known = state.flags(s, T, WF)
    assert "vitals.flagged" in known
    assert "rx.confirmed" not in known, "a derived flag was accepted from storage"


# --------------------------------------------------------------------------
# visibility and the guard, through the kernel
# --------------------------------------------------------------------------

def test_dispense_invisible_until_rx_confirmed():
    caps = {"pharmacy.dispense", "patient.find"}
    s = consulted()
    assert [op["id"] for op in state.actions(WF, OPS, state.flags(s, T, WF), caps)] == []
    s.add("medication_request", n=2, status="active")
    assert "phc.op.pharmacy-dispense" in [
        op["id"] for op in state.actions(WF, OPS, state.flags(s, T, WF), caps)]
    s.add("medication_dispense", n=2)
    assert [op["id"] for op in state.actions(WF, OPS, state.flags(s, T, WF), caps)] == [], \
        "dispense still offered after a complete dispense"


def test_actions_lead_with_the_station_the_thread_is_at():
    s = registered()
    known = state.flags(s, T, WF)
    every_capability = {op["capability"] for op in OPS.values()}
    first = state.actions(WF, OPS, known, every_capability)[0]
    assert first["station"] == state.station(WF, known) == "nurse"
    assert first["id"] == "phc.op.vitals-record"


# --------------------------------------------------------------------------
# the write path
# --------------------------------------------------------------------------

def test_an_agent_can_never_commit_an_irreversible_write():
    s = registered()
    op = OPS["phc.op.abha-link"]
    assert op["irreversibility"] == "irreversible"
    payload = {"method": "link_existing", "abha_number": "12-3456", "consent_given": True}
    d, prop = proposals.propose(s, BUNDLE, "phc.op.abha-link", thread=T, payload=payload,
                                caps={"abha.link"}, actor="agent")
    assert not d and prop is None and "rendered surface" in d.reason
    assert s.rows.get("patient", [{}])[0].get("abha_number") is None, "the agent wrote"
    assert s.log[-1].outcome.startswith("denied:"), "the denial was not audited"
    # commit() takes no surface: there is no argument a machine could pass.
    assert "surface" not in inspect.signature(proposals.commit).parameters


def test_confirming_a_proposal_this_bundle_does_not_declare_is_a_refusal():
    """One SQLite file opened under a second bundle still holds the first
    bundle's pending rows, and the renderer draws them. Tapping one used to
    raise KeyError inside confirm() and answer 500. Nothing was written either
    way, but a crash is not a refusal and does not reach the audit."""
    s = registered()
    stranded = c.Proposal(
        id="prop-stranded", thread=T, operation="lab.op.result-verify",
        payload={"decision": "verified"}, proposed_by="agent", surface=guard.MCP,
        status="pending", created_at="2026-09-13T00:00:00Z", flags_raised=[])
    s.put_proposal(stranded)
    d, back = proposals.confirm(s, BUNDLE, stranded, caps={"result.verify"},
                                actor="user:demo", confirmed=True)
    assert not d and "not an operation this facility declares" in d.reason
    assert back.status == "pending", "a refusal must not decide the proposal"
    assert s.log[-1].outcome == "denied: not in this bundle"


def test_an_irreversible_write_needs_an_explicit_confirm_from_a_person():
    payload = {"method": "link_existing", "abha_number": "12-3456", "consent_given": True}
    s = registered()
    assert not proposals.commit(s, BUNDLE, "phc.op.abha-link", thread=T, payload=payload,
                                caps={"abha.link"}, actor="nurse", confirmed=False)
    assert proposals.commit(s, BUNDLE, "phc.op.abha-link", thread=T, payload=payload,
                            caps={"abha.link"}, actor="nurse", confirmed=True)
    assert "abha.linked" in state.flags(s, T, WF)


def test_out_of_range_blocks_and_an_override_needs_a_reason():
    s = registered()
    args = dict(thread=T, caps={"vitals.record"}, actor="nurse")
    bad = dict(VITALS, systolic=400)
    d = proposals.commit(s, BUNDLE, "phc.op.vitals-record", payload=bad, **args)
    assert not d and "outside 70 to 250" in d.reason
    assert "observation" not in s.rows, "an impossible value was written"

    d, prop = proposals.propose(s, BUNDLE, "phc.op.vitals-record", payload=bad, **args)
    assert not d and prop is None, "the machine surface accepted it"

    ok = dict(bad, override_reason="cuff reads high, repeated twice, referring")
    assert proposals.commit(s, BUNDLE, "phc.op.vitals-record", payload=ok, **args)
    assert s.rows["observation"][0]["value"] == 400, "the value as measured"
    # The reason is recorded on the audit line, which is where a reader looks
    # for why an impossible value was accepted. No resource has a column for
    # it. This used to assert it landed on the observation row, which was true
    # only of this dict fake: it was handed the raw payload, and the SQLite
    # adapter dropped the same key on the floor.
    assert s.audit(T)[-1].payload["override_reason"], "the reason was not recorded"


def test_a_critical_but_in_range_value_raises_a_stored_flag():
    s = registered()
    assert proposals.commit(s, BUNDLE, "phc.op.vitals-record", thread=T,
                            payload=dict(VITALS, systolic=190), caps={"vitals.record"},
                            actor="nurse")
    assert "vitals.flagged" in s.stored
    assert "vitals.flagged" in state.flags(s, T, WF)


def test_a_proposal_is_judged_again_at_confirm_and_not_when_it_was_made():
    s = consulted()
    payload = dict(RX)
    d, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T, payload=payload,
                                caps={"rx.prescribe"}, actor="agent")
    assert d and d.reason == "proposed" and prop.status == "pending"
    assert "medication_request" not in s.rows, "a proposal wrote"

    # Someone else prescribes first. The precondition 'not rx.confirmed' has gone.
    s.add("medication_request", status="active")
    d2, prop2 = proposals.confirm(s, BUNDLE, prop, caps={"rx.prescribe"}, actor="mo")
    assert not d2 and d2.reason == "Already rx confirmed.", d2.reason
    assert prop2.status == "pending" and len(s.rows["medication_request"]) == 1


def test_confirming_writes_once_and_leaves_both_payloads_on_the_record():
    s = consulted()
    proposed = dict(RX)
    edited = dict(RX_EDITED)
    _, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                                payload=proposed, caps={"rx.prescribe"}, actor="agent")
    d, done = proposals.confirm(s, BUNDLE, prop, caps={"rx.prescribe"}, actor="mo",
                                payload=edited)
    assert d and done.status == "confirmed" and done.decided_by == "mo"
    assert done.payload == proposed and done.final_payload == edited, \
        "what was proposed and what was committed must both survive"
    assert len(s.rows["medication_request"]) == 1
    assert [r.outcome for r in s.audit(T)] == ["proposed", "confirmed"]
    assert s.proposals(T, status="pending") == []


def test_a_confirmed_proposal_cannot_be_confirmed_twice():
    s = consulted()
    _, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                                payload=dict(RX),
                                caps={"rx.prescribe"}, actor="agent")
    _, done = proposals.confirm(s, BUNDLE, prop, caps={"rx.prescribe"}, actor="mo")
    d, _ = proposals.confirm(s, BUNDLE, done, caps={"rx.prescribe"}, actor="mo")
    assert not d and "already confirmed" in d.reason
    assert len(s.rows["medication_request"]) == 1, "a second write got through"


def test_rejecting_writes_nothing_and_stays_on_the_record():
    s = consulted()
    _, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                                payload=dict(RX),
                                caps={"rx.prescribe"}, actor="agent")
    done = proposals.reject(s, prop, actor="mo", reason="allergy on file")
    assert done.status == "rejected" and "medication_request" not in s.rows
    assert s.audit(T)[-1].outcome == "rejected: allergy on file"
    assert s.proposals(T, status="pending") == []


def test_a_capability_the_caller_lacks_is_denied_and_audited_on_both_surfaces():
    for surface, call in (("mcp", proposals.propose), ("rendered", proposals.commit)):
        s = consulted()
        out = call(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                   payload=dict(RX), caps={"vitals.record"},
                   actor="nurse")
        d = out[0] if isinstance(out, tuple) else out
        assert not d and "missing capability" in d.reason, surface
        assert s.audit(T)[-1].outcome.startswith("denied:"), surface


def test_a_draft_is_never_a_write():
    inst = BUNDLE.instruments["phc.inst.vitals-voice"]
    draft = proposals.draft(inst, "phc.op.vitals-record", {"systolic": 140},
                            confidence={"systolic": 0.62})
    assert isinstance(draft, c.Draft) and draft.values == {"systolic": 140}
    empty = proposals.draft(inst, "phc.op.vitals-record", {})
    assert empty.values == {}, "an empty draft means show the keypad"
    assert not hasattr(draft, "commit"), "a draft is data, not an action"


# --------------------------------------------------------------------------
# views and metrics
# --------------------------------------------------------------------------

def _refs(*ids):
    return [c.ThreadRef(id=i, workflow=WF.id, opened_at="2026-09-10T09:00:00Z",
                        subject={"name": i, "age": 30, "sex": "female",
                                 "village": "Kadur", "token": "A1"}) for i in ids]


def test_a_queue_groups_in_line_order_with_a_trailing_finished_group():
    s = Fake(threads=_refs("enc-1", "enc-2"))
    s.add("patient", thread="enc-1")
    s.add("patient", thread="enc-2")
    s.add("observation", thread="enc-2", category="vital-signs")
    s.add("notes", thread="enc-2")
    res = views.resolve(BUNDLE, "phc.view.station-queue", s)
    assert [g["key"] for g in res.groups] == ["reception", "nurse", "doctor",
                                              "lab", "pharmacy", None]
    assert [(g["key"], g["count"]) for g in res.groups if g["count"]] == [("nurse", 1),
                                                                         (None, 1)]
    row = next(r for r in res.rows if r.thread == "enc-1")
    # The declared columns, spelled out rather than read back off the
    # declaration: a test that asks the bundle what it declares and then
    # asserts the kernel returned that is true for every bundle and says
    # nothing. "category" joined this list when the queue gained its
    # programme filter, and "arrival" when it gained the mark that says
    # whether somebody registered themselves; those are the only reasons to
    # touch this line.
    assert set(row.subject) == {"name", "age", "sex", "village", "token",
                                "category", "arrival"}
    assert row.badges == {"abha.pending": "warn"}, "a declared badge did not fire"


def test_a_summary_draws_what_the_sections_declare():
    s = consulted()
    s.add("service_request", code="CBC", status="active")
    res = views.resolve(BUNDLE, "phc.view.visit-summary", s, thread=T,
                        caps={"patient.find", "rx.prescribe"})
    titles = [block["title"] for block in res.rows]
    assert titles[:2] == ["Visit", "Flags"]
    line_rows = res.rows[0]["rows"]
    assert [r["status"] for r in line_rows] == ["done", "done", "done", "now", "skipped"]
    investigations = next(b for b in res.rows if b["title"] == "Investigations")
    assert investigations["rows"] == [{"code": "CBC", "status": "active",
                                      "created_date": None}]


def test_a_metric_with_an_empty_denominator_is_zero_and_not_an_error():
    s = Fake()
    m = views.metric(s, BUNDLE.metrics["phc.metric.abha-coverage"])
    assert m.value == 0 and m.denominator == 0 and m.unit == "percent"

    s.add("patient", n=3, created_date="2026-09-10T09:00:00Z")
    s.add("patient", created_date="2026-09-10T09:00:00Z", abha_number="12-3456")
    m = views.metric(s, BUNDLE.metrics["phc.metric.abha-coverage"], window="all")
    assert (m.numerator, m.denominator, m.value) == (1, 4, 25.0)


def _inside(window):
    """A timestamp the given window contains, derived from the window itself.

    A literal date here is a time bomb. `2026-09-10T09:00:00Z` was inside the
    window on the day it was typed and outside it a month later, so this check
    started failing on a change nobody made. Deriving the stamp from
    `views.window_start` keeps the check about the windowing rule rather than
    about the month it was written in. Same reason
    `adapters/local/tests/test_store.py` derives its count from the declared
    seed instead of writing the number down.
    """
    start = datetime.strptime(views.window_start(window), "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert start < now, f"{window} starts in the future"
    return (start + (now - start) / 2).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_dashboard_evaluates_every_metric_locally():
    view = BUNDLE.views["phc.view.facility-dashboard"]
    at = _inside(view.window)
    s = Fake()
    s.add("encounter", n=2, created_date=at)
    s.add("thread_flag", flag="vitals.flagged", created_date=at)
    res = views.resolve(BUNDLE, "phc.view.facility-dashboard", s)
    by_id = {m.metric: m for m in res.rows}
    assert by_id["phc.metric.visits"].value == 2
    assert by_id["phc.metric.vitals-flagged-rate"].value == 50.0
    assert all(m.window == view.window for m in res.rows), "the view's window did not win"
    # Without this the line above is satisfied by a resolver that ignores the
    # view and reads each metric's own window: at least one metric on this
    # dashboard must declare a different one for the override to be exercised.
    assert any(BUNDLE.metrics[m.metric].window != view.window for m in res.rows), \
        "every metric here declares the view's own window, so nothing is overridden"


def test_a_tasklist_resolves_a_count_and_the_matching_threads_per_task():
    """Cross thread by construction: three threads share the workflow, one
    task's `where` picks out one of them, the other picks out all three, and
    the resolver must not confuse the two. A resolver that ignored `where`
    and returned every thread would pass a check that only asserts *some*
    rows come back; this asserts the exact set and the exact count."""
    s = Fake(threads=_refs("enc-1", "enc-2", "enc-3"))
    for t in ("enc-1", "enc-2", "enc-3"):
        s.add("patient", thread=t)
    s.add("service_request", thread="enc-2")
    s.add("service_request", thread="enc-3")
    s.add("diagnostic_report", thread="enc-3")

    res = views.resolve(BUNDLE, "phc.view.today-tasks", s)
    by_title = {r.title: r for r in res.rows}

    waiting = by_title["Waiting on a lab result"]
    assert (waiting.count, waiting.threads) == (1, ["enc-2"]), waiting
    assert waiting.operation == "phc.op.lab-result-enter"

    unasked = by_title["Consent never asked"]
    assert (unasked.count, sorted(unasked.threads)) == (3, ["enc-1", "enc-2", "enc-3"])
    assert unasked.operation is None, "a task with no declared operation is a worklist"


def test_a_tasklist_with_nothing_matching_is_a_real_zero_not_an_empty_result():
    """The other half of the mutation: a resolver that always returned no
    threads would still pass a check that only asserts *a* zero count
    somewhere. This pins a task that must be non-zero alongside one that
    must be exactly zero, on the same call."""
    s = Fake(threads=_refs("enc-1"))
    s.add("patient", thread="enc-1")
    s.add("service_request", thread="enc-1")
    s.add("diagnostic_report", thread="enc-1")   # lab.resulted: the task must be 0
    res = views.resolve(BUNDLE, "phc.view.today-tasks", s)
    by_title = {r.title: r for r in res.rows}
    assert by_title["Waiting on a lab result"].count == 0
    assert by_title["Consent never asked"].count == 1, "the other task on the same call is not zero"


def test_a_tasklist_not_clause_excludes_a_thread_that_has_declined():
    """'Consent never asked' names `not capture.declined` for a reason: a
    visit that said no is not a visit nobody asked. Without this test a
    resolver checking only the first member of `not` (here capture.consented)
    would let a declined thread straight back onto the row, which is the
    silent-half-match failure the spec calls out by name."""
    s = Fake(threads=_refs("enc-1", "enc-3"),
            stored_by_thread={"enc-3": {"capture.declined"}})
    s.add("patient", thread="enc-1")
    s.add("patient", thread="enc-3")
    res = views.resolve(BUNDLE, "phc.view.today-tasks", s)
    row = next(r for r in res.rows if r.title == "Consent never asked")
    assert row.threads == ["enc-1"], \
        "a thread that declined must be excluded, not counted as unasked"


def test_a_tasklist_not_clause_excludes_a_thread_that_has_consented():
    """The other half of the same `not` list: capture.consented is composed
    (all_of agreed, not declined, not withdrawn), so this also proves the
    tasklist reads a derived flag correctly and not only a stored one."""
    s = Fake(threads=_refs("enc-1", "enc-2"),
            stored_by_thread={"enc-2": {"capture.agreed"}})
    s.add("patient", thread="enc-1")
    s.add("patient", thread="enc-2")
    res = views.resolve(BUNDLE, "phc.view.today-tasks", s)
    row = next(r for r in res.rows if r.title == "Consent never asked")
    assert row.threads == ["enc-1"], \
        "a thread that already consented must be excluded, not counted as unasked"


def test_a_tasklist_requires_every_member_of_a_multi_flag_where():
    """The declared bundle's own tasks each name one `flag`, so this proves
    the `all(want)` side directly: a task naming two flags must require both,
    not just the first, the same property the two `not` tests above prove for
    exclusion."""
    s = Fake(threads=_refs("enc-1", "enc-2"))
    s.add("patient", thread="enc-1")                              # registered only
    s.add("patient", thread="enc-2")
    s.add("observation", thread="enc-2", category="vital-signs")  # + vitals.recorded
    task = c.Task(title="Registered and vitalled",
                 where={"flag": ["registered", "vitals.recorded"]})
    view = c.View(id="phc.view._fixture-multi-flag", kind="tasklist", title="", summary="",
                 capability="patient.find", workflow=WF.id, tasks=[task])
    bundle = dataclasses.replace(BUNDLE, views={view.id: view})
    res = views.resolve(bundle, view.id, s)
    row, = res.rows
    assert row.threads == ["enc-2"], \
        "a multi-member `flag` list must require every member, not just the first"


def test_the_laboratory_gets_the_tasklist_kind_free_and_names_no_phc_word():
    """Declared, not coded: the same kernel resolver runs a bundle that
    shares no vocabulary with the PHC. Nothing on the laboratory's tasklist
    may name a PHC word, which is the point of a bundle-closed vocabulary."""
    lab = declarations.load("lab")
    view = lab.views["lab.view.today-tasks"]
    blob = json.dumps(dataclasses.asdict(view)).lower()
    for word in ("phc", "patient", "vitals", "consult", "rx.", "pharmacy",
                "dispense", "abha", "capture."):
        assert word not in blob, f"'{word}' leaked into the laboratory's tasklist"

    s = Fake(threads=[c.ThreadRef(id="spec-1", workflow=lab.workflow().id,
                                  opened_at="2026-09-10T09:00:00Z", subject={})])
    s.add("specimen", thread="spec-1")
    res = views.resolve(lab, "lab.view.today-tasks", s)
    by_title = {r.title: r for r in res.rows}
    assert by_title["Collected, no result yet"].count == 1
    assert by_title["Entered, not yet verified"].count == 0


def test_lint_refuses_a_tasklist_naming_an_unknown_flag():
    bad = _lint_with("phc.view.today-tasks",
                     tasks=[{"title": "x", "where": {"flag": "lab.orderd"}}])
    assert any("unknown state" in b for b in bad), bad


def test_lint_refuses_a_tasklist_naming_an_unknown_operation():
    bad = _lint_with("phc.view.today-tasks",
                     tasks=[{"title": "x", "where": {"flag": "lab.ordered"},
                            "operation": "phc.op.nope"}])
    assert any("does not exist" in b for b in bad), bad


def test_a_window_excludes_what_is_older_than_it():
    s = Fake()
    s.add("encounter", created_date="2020-01-01T00:00:00Z")
    s.add("encounter", created_date="2999-01-01T00:00:00Z")
    m = views.metric(s, BUNDLE.metrics["phc.metric.visits"], window="day")
    assert m.numerator == 1, "the window did not bind"
    assert views.metric(s, BUNDLE.metrics["phc.metric.visits"], window="all").numerator == 2


# --------------------------------------------------------------------------
# lint: the declaration is where the rules are, so lint is a safety check
# --------------------------------------------------------------------------

def _lint_with(did, **changes):
    path = declarations.BUNDLES / "phc"
    from catalogue.build import parse
    import yaml
    manifest = yaml.safe_load((path / "bundle.yaml").read_text())
    decls = {fm["id"]: (fm, body) for fm, body in (parse(p) for p in sorted(path.glob("*.md")))}
    fm, body = decls[did]
    decls[did] = ({**fm, **changes}, body)
    return declarations.lint(manifest, decls, OPS)


def test_the_bundle_as_written_lints_clean():
    assert _lint_with("phc.wf.outpatient") == []


def test_lint_refuses_an_instrument_that_commits_without_a_tap():
    assert any("commit must be 'tap'" in b
               for b in _lint_with("phc.inst.vitals-voice", commit="auto"))
    assert any("readback must be 'required'" in b
               for b in _lint_with("phc.inst.vitals-voice", readback="optional"))


def test_lint_refuses_a_dangling_or_misspelt_reference():
    checks = [
        ("phc.wf.outpatient", dict(steps=[{"station": "nurse", "done_when": "registered",
                                           "operations": ["phc.op.nope"]}]),
         "does not exist"),
        ("phc.wf.outpatient", dict(states={"registered": {"exists": {"resource": "unicorn"}}}),
         "unknown resource"),
        ("phc.view.station-queue", dict(capability="patient.finnd"), "unknown capability"),
        ("phc.view.station-queue", dict(badges={"vitals.flaged": "crit"}), "unknown state"),
        ("phc.view.facility-dashboard", dict(metrics=["phc.metric.nope"]), "does not exist"),
        ("phc.metric.visits", dict(unit="furlongs"), "unit must be one of"),
        ("phc.inst.vitals-voice", dict(fields=["systolik"]), "not a question"),
    ]
    for did, change, expected in checks:
        bad = _lint_with(did, **change)
        assert any(expected in b for b in bad), f"{did} {change} linted clean"


def test_lint_refuses_states_that_do_not_cover_this_bundles_vocabulary():
    """Closure is per bundle: the states a workflow declares must be exactly
    the ones its own bundle.yaml lists. A flag from another facility's
    vocabulary is as much a failure as a missing one."""
    states = dict(declarations.load("phc").workflows["phc.wf.outpatient"].states)
    trimmed = {k: v for k, v in states.items() if k != "lab.critical"}
    assert any("cover this bundle's vocabulary" in b
               for b in _lint_with("phc.wf.outpatient", states=trimmed))
    borrowed = dict(states, **{"specimen.collected": {"stored": True}})
    assert any("unknown ['specimen.collected']" in b
               for b in _lint_with("phc.wf.outpatient", states=borrowed))


def test_lint_refuses_a_state_rule_that_looks_ahead():
    states = {"registered": {"all_of": ["abha.linked"]}}
    assert any("before it is declared" in b
               for b in _lint_with("phc.wf.outpatient",
                                   states={**states, **{k: v for k, v in
                                                        declarations.load("phc").workflows
                                                        ["phc.wf.outpatient"].states.items()
                                                        if k != "registered"}}))


def test_the_compiled_form_is_plain_json():
    import json
    blob = json.dumps(declarations.compile_json(BUNDLE), sort_keys=True)
    back = json.loads(blob)
    # The key set comes from the contract, not from a copy of it written here.
    # A sixth key (`scribe`) was added to the compiler and this literal said
    # five, so the check failed on a change that was correct.
    assert set(back) == set(c.BUNDLE_KEYS), set(back) ^ set(c.BUNDLE_KEYS)
    assert back["workflows"]["phc.wf.outpatient"]["steps"][0]["station"] == "reception"
    assert not set(c.BUNDLE_KEYS) & set(c.CATALOGUE_KEYS), \
        "a bundle key and a catalogue-wide key cannot share a name"
    assert set(back) <= set(c.compiled_keys())

    # The three keys a second engine answers GET /facility from. Asserted to
    # carry something rather than only to be present: emptying them left the
    # key set right, this test green, and the Go backend serving a centre that
    # withholds nothing whatever PHC_FACILITY said. scripts/check_go_parity.py
    # caught that, and it is skipped under SKIP_E2E, so the hole was real.
    plugins = back["plugins"]
    assert plugins, "catalogue.json carries no plugin declarations"
    for pid, decl in plugins.items():
        assert decl.get("title"), pid
        assert decl.get("capabilities"), pid
        for cap in decl["capabilities"]:
            assert cap in vocab.CAPABILITIES, (pid, cap)
    shapes = back["facilities"]
    assert shapes["default"] in shapes["declared"], shapes["default"]
    for fid, decl in shapes["declared"].items():
        assert decl.get("title"), fid
        assert set(decl.get("without") or []) <= set(plugins), fid
    # The loaded bundle's own words, which are NARROWER than the catalogue
    # wide union the four original keys carry.
    assert back["vocabulary"]["capabilities"] == sorted(vocab.CAPABILITIES)
    assert back["vocabulary"]["roles"] == {r: list(caps) for r, caps
                                           in dict(vocab.BUNDLES).items()}
    assert back["vocabulary"]["states"] == sorted(vocab.STATES)


def test_the_compiled_state_order_is_the_declared_one_and_not_the_sorted_one():
    """`state_order` was written and read and held by nothing.

    `kernel.declarations.compile_json` carries it because `write_catalogue`
    dumps with sort_keys=True, so a second engine reading `states` gets the
    flags alphabetically. The order is load bearing: `kernel.state._true`
    evaluates `all_of` against the flags already known, and
    `test_lint_refuses_a_state_rule_that_looks_ahead` pins that a rule may
    only reference an earlier one. Alphabetically `abha.pending` cannot see
    `registered`, and `capture.consented` cannot see `capture.declined` — so
    an engine deriving flags from the sorted dict serves a visit that is never
    pending an ABHA and is consented to ambient capture after the patient
    declined. That is a consent defect, which is why this is pinned and not
    left to the comment beside the emit.

    Nothing checked it before this. `care_phc_mcp/kstate` reads it, so a drift
    between the declaration and the carried list is a wrong answer in one
    engine and a right one in the other, with the gate green.
    """
    import json
    compiled = json.loads(json.dumps(declarations.compile_json(BUNDLE)))
    for wid, wf in BUNDLE.workflows.items():
        order = compiled["workflows"][wid]["state_order"]
        declared = list(wf.states)
        assert order == declared, (wid, order, declared)
        assert set(order) == set(compiled["workflows"][wid]["states"]), wid
        # The property the order exists to preserve, asserted against the
        # carried list rather than the source: every flag a rule leans on is
        # earlier in it. A rule that leans on nothing is the base case.
        position = {flag: i for i, flag in enumerate(order)}
        leaned_on = 0
        for i, flag in enumerate(order):
            for ref in _flags_a_rule_references(wf.states[flag]):
                assert ref in position, (wid, flag, ref)
                assert position[ref] < i, (
                    "%s: %r leans on %r, which the carried order puts later"
                    % (wid, flag, ref))
                leaned_on += 1
        # Without this the loop above is satisfied by an order whose rules
        # reference nothing at all, which is every order including the sorted
        # one.
        assert leaned_on, wid
        # And the sorted order must actually break it, or this check is about
        # nothing. phc declares `registered` before `abha.pending`; sorted,
        # it does not.
        if sorted(order) != order:
            assert any(position[ref] > sorted(order).index(flag) or
                       sorted(order).index(ref) > sorted(order).index(flag)
                       for flag in order
                       for ref in _flags_a_rule_references(wf.states[flag])), \
                "%s: sorting the flags breaks no rule, so the order is not " \
                "load bearing here and this check proves nothing" % wid


def _flags_a_rule_references(rule):
    """Every flag named inside one state rule, whatever clause holds it."""
    out = []
    for clause in ("all_of", "any_of", "none_of"):
        for ref in rule.get(clause) or ():
            out.append(ref[4:].strip() if str(ref).startswith("not ") else ref)
    return [r for r in out if isinstance(r, str)]


def test_the_file_on_disk_carries_every_key_the_contract_promises():
    """catalogue.json after `catalogue.build` then `kernel.declarations`. If
    this fails, one of the two compile steps has not been run."""
    import json
    on_disk = json.loads(
        (declarations.ROOT / "catalogue" / "catalogue.json").read_text())
    assert set(c.compiled_keys()) <= set(on_disk), (
        "run: python3 -m catalogue.build && python3 -m kernel.declarations")
    assert on_disk["workflows"]["phc.wf.outpatient"]["subject"] == "encounter"


def test_a_thread_view_is_the_shape_the_renderer_was_promised():
    import json
    s = consulted()
    proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                      payload=dict(RX),
                      caps={"rx.prescribe"}, actor="agent")
    ref = _refs(T)[0]
    view = state.thread_view(s, ref, WF, OPS, caps={"patient.find", "rx.prescribe"},
                             nudge="Prescription waiting on the doctor.")
    out = json.loads(json.dumps(view.to_json()))
    assert "patient" not in out and out["subject"]["name"] == T
    assert [step["status"] for step in out["line"]][:3] == ["done", "done", "done"]
    assert out["proposals"][0]["status"] == "pending"
    assert out["station"] is None and out["nudge"]
    assert set(out) == {f.name for f in dataclasses.fields(c.ThreadView)}


def test_an_operation_no_step_draws_is_neither_a_button_nor_a_write():
    """phc.op.household-visit is in the PHC manifest and in no PHC step: it
    stands at `community` and the outpatient line has no such station. It must
    not be drawn on a clinic thread, and it must not be writable onto one from
    any surface, or a household questionnaire lands on an encounter."""
    stray = "phc.op.household-visit"
    assert stray in OPS, "the fixture this asserts against has moved"
    assert not state.drawn_by(WF, stray)
    assert all(state.drawn_by(WF, op_id) for op_id in OPS if op_id != stray)

    s = registered()
    every = set(vocab.CAPABILITIES)
    drawn = [op["id"] for op in state.actions(WF, OPS, state.flags(s, T, WF), every)]
    assert stray not in drawn, drawn
    assert "phc.op.vitals-record" in drawn, drawn

    payload = {"visit_type": "routine", "consent_at_door": True,
               "narrative": "knocked, nothing clinical happened",
               "followup_needed": False}
    denied = proposals.commit(s, BUNDLE, stray, thread=T, payload=payload,
                              caps=every, actor="nurse", confirmed=True)
    assert not denied and "not a step of" in denied.reason, denied.reason
    denied, nothing = proposals.propose(s, BUNDLE, stray, thread=T, payload=payload,
                                        caps=every, actor="agent")
    assert not denied and nothing is None, denied.reason
    assert s.count("questionnaire_response", thread=T, where={}) == 0


def test_loop_closer_is_the_operation_that_emits_done_when():
    """A station's loop closes on the operation that satisfies its step.

    Derived, never declared: adding a `loop:` key to every bundle would be a
    second place to state what `done_when` and `emits` already say, and so a
    second place to be wrong.
    """
    assert state.loop_closer(WF, OPS, "reception") == "phc.op.patient-register"
    assert state.loop_closer(WF, OPS, "nurse") == "phc.op.vitals-record"
    # The doctor's step draws four operations and only one of them ends it.
    # rx-prescribe and lab-order live INSIDE the doctor's loop.
    assert state.loop_closer(WF, OPS, "doctor") == "phc.op.consult-document"
    assert state.loop_closer(WF, OPS, "nowhere") is None


def test_loop_closer_is_not_fooled_by_declaration_order():
    """Every real bundle happens to declare its emitter first in the step's
    operation list, so a `loop_closer` that just returned
    `step.operations[0]` would pass every check above without ever reading
    `done_when` or `emits`. This fixture puts the emitter second to catch
    exactly that shortcut."""
    step = c.Step(station="s", done_when="flag.done",
                 operations=["op.other", "op.emitter"])
    wf = c.Workflow(id="wf.fixture", title="", summary="", subject="thing",
                    steps=[step], states={}, stored=[])
    ops = {
        "op.other": {"id": "op.other", "emits": ["flag.other"]},
        "op.emitter": {"id": "op.emitter", "emits": ["flag.done"]},
    }
    assert state.loop_closer(wf, ops, "s") == "op.emitter"


def test_loop_opener_is_the_only_operation_that_needs_an_empty_thread():
    """`not registered` is the signature of an operation that starts a subject."""
    assert state.loop_opener(WF, OPS) == "phc.op.patient-register"


def test_loop_opener_is_not_fooled_by_declaration_order():
    """phc.op.patient-register is both the correct opener and literally the
    first operation of the first step, so a `loop_opener` that just returned
    `steps[0].operations[0]` would pass the check above without ever reading
    `preconditions`. This fixture puts the precondition-satisfying operation
    in the second step, behind an operation whose precondition an empty
    thread does not hold."""
    step1 = c.Step(station="a", done_when="flag.a", operations=["op.needs-flag"])
    step2 = c.Step(station="b", done_when="flag.b", operations=["op.opener"])
    wf = c.Workflow(id="wf.fixture", title="", summary="", subject="thing",
                    steps=[step1, step2], states={}, stored=[])
    ops = {
        "op.needs-flag": {"id": "op.needs-flag", "preconditions": ["flag.a"]},
        "op.opener": {"id": "op.opener", "preconditions": []},
    }
    assert state.loop_opener(wf, ops) == "op.opener"


def test_thread_view_carries_what_closes_this_station():
    store = Fake()
    ref = _refs(T)[0]
    caps = set(vocab.for_bundle("phc").roles["frontdesk"])
    view = state.thread_view(store, ref, WF, OPS, caps=caps)
    assert view.station == "reception"
    assert view.closes == "phc.op.patient-register"


def test_scribe_station_config_is_linted():
    from kernel import declarations
    bundle = declarations.load("phc")
    assert bundle.scribe["nurse"]["default"] == "phc.op.vitals-record"
    manifest_bad = {"scribe": {"nurse": {"default": "phc.op.nope", "choose": []}}}
    problems = declarations._lint_scribe(manifest_bad, bundle.instruments_raw)
    assert any("phc.op.nope" in p for p in problems), problems


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
