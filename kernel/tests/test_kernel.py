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

from care_phc.thread import Snapshot, derive
from care_phc.thread import station as coded_station
from catalogue import guard
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

    def __init__(self, stored=(), threads=()):
        self.rows, self.props, self.log = {}, {}, []
        self.stored, self._threads = set(stored), list(threads)

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
    assert s.rows["observation"][0]["override_reason"], "the reason was not recorded"


def test_a_critical_but_in_range_value_raises_a_stored_flag():
    s = registered()
    assert proposals.commit(s, BUNDLE, "phc.op.vitals-record", thread=T,
                            payload=dict(VITALS, systolic=190), caps={"vitals.record"},
                            actor="nurse")
    assert "vitals.flagged" in s.stored
    assert "vitals.flagged" in state.flags(s, T, WF)


def test_a_proposal_is_judged_again_at_confirm_and_not_when_it_was_made():
    s = consulted()
    payload = {"medications": [{"drug": "amoxicillin", "dose": "500mg"}]}
    d, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T, payload=payload,
                                caps={"rx.prescribe"}, actor="agent")
    assert d and d.reason == "proposed" and prop.status == "pending"
    assert "medication_request" not in s.rows, "a proposal wrote"

    # Someone else prescribes first. The precondition 'not rx.confirmed' has gone.
    s.add("medication_request", status="active")
    d2, prop2 = proposals.confirm(s, BUNDLE, prop, caps={"rx.prescribe"}, actor="mo")
    assert not d2 and "precondition not met" in d2.reason
    assert prop2.status == "pending" and len(s.rows["medication_request"]) == 1


def test_confirming_writes_once_and_leaves_both_payloads_on_the_record():
    s = consulted()
    proposed = {"medications": [{"drug": "amoxicillin", "dose": "500mg"}]}
    edited = {"medications": [{"drug": "amoxicillin", "dose": "250mg"}]}
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
                                payload={"medications": [{"drug": "x"}]},
                                caps={"rx.prescribe"}, actor="agent")
    _, done = proposals.confirm(s, BUNDLE, prop, caps={"rx.prescribe"}, actor="mo")
    d, _ = proposals.confirm(s, BUNDLE, done, caps={"rx.prescribe"}, actor="mo")
    assert not d and "already confirmed" in d.reason
    assert len(s.rows["medication_request"]) == 1, "a second write got through"


def test_rejecting_writes_nothing_and_stays_on_the_record():
    s = consulted()
    _, prop = proposals.propose(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                                payload={"medications": [{"drug": "x"}]},
                                caps={"rx.prescribe"}, actor="agent")
    done = proposals.reject(s, prop, actor="mo", reason="allergy on file")
    assert done.status == "rejected" and "medication_request" not in s.rows
    assert s.audit(T)[-1].outcome == "rejected: allergy on file"
    assert s.proposals(T, status="pending") == []


def test_a_capability_the_caller_lacks_is_denied_and_audited_on_both_surfaces():
    for surface, call in (("mcp", proposals.propose), ("rendered", proposals.commit)):
        s = consulted()
        out = call(s, BUNDLE, "phc.op.rx-prescribe", thread=T,
                   payload={"medications": [{"drug": "x"}]}, caps={"vitals.record"},
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
    assert set(row.subject) == {"name", "age", "sex", "village", "token"}
    assert row.badges == {"abha.pending": "warn"}, "a declared badge did not fire"


def test_a_summary_draws_what_the_sections_declare():
    s = consulted()
    s.add("service_request", code="CBC", status="active")
    res = views.resolve(BUNDLE, "phc.view.patient-summary", s, thread=T,
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


def test_a_dashboard_evaluates_every_metric_locally():
    s = Fake()
    s.add("encounter", n=2, created_date="2026-09-10T09:00:00Z")
    s.add("thread_flag", flag="vitals.flagged", created_date="2026-09-10T09:00:00Z")
    res = views.resolve(BUNDLE, "phc.view.facility-dashboard", s)
    by_id = {m.metric: m for m in res.rows}
    assert by_id["phc.metric.visits"].value == 2
    assert by_id["phc.metric.vitals-flagged-rate"].value == 50.0
    assert all(m.window == "week" for m in res.rows), "the view's window did not win"


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
    assert any("scribe may not be offered" in b
               for b in _lint_with("phc.inst.consult-scribe",
                                   operations=["phc.op.vitals-record"])), \
        "a scribe was allowed onto the numeric station"


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


def test_lint_refuses_states_that_do_not_cover_the_vocabulary():
    trimmed = dict(declarations.load("phc").workflows["phc.wf.outpatient"].states)
    trimmed.pop("lab.critical")
    assert any("cover the vocabulary" in b
               for b in _lint_with("phc.wf.outpatient", states=trimmed))


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
    assert set(back) == {"manifest", "workflows", "views", "instruments", "metrics"}
    assert back["workflows"]["phc.wf.outpatient"]["steps"][0]["station"] == "reception"
    assert set(back) <= set(c.compiled_keys())


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
                      payload={"medications": [{"drug": "x"}]},
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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
