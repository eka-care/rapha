"""Run: python3 -m kernel.tests.test_contracts

The PHC bundle must say the same thing as the code it replaces. These checks
fail if the workflow drifts from care_phc/thread.py, a declaration names
something outside the vocabularies, or a voice instrument finds a way to
commit without a tap. No kernel, no database, no network.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib
from datetime import date

import yaml

from api import fill
from care_phc.thread import LINE, STORED
from catalogue import validate, vocab
from catalogue.build import parse
from kernel import contracts as c
from kernel import declarations

ROOT = pathlib.Path(__file__).parents[2]
BUNDLE = ROOT / "bundles" / "phc"
CAT = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
MANIFEST = yaml.safe_load((BUNDLE / "bundle.yaml").read_text())
DECLS = {fm["id"]: (fm, body) for fm, body in (parse(p) for p in sorted(BUNDLE.glob("*.md")))}


def _of(kind):
    return {k: v for k, (v, _) in DECLS.items() if v["type"] == kind}


def _resources(query):
    return {query["resource"]}


def test_manifest_lists_every_declaration_and_every_operation():
    # `schedules` is optional in a manifest -- bundles/lab declares none and
    # a required key would have made adding the type a change to every
    # bundle file -- so it is read with a default rather than indexed.
    listed = set(sum((MANIFEST[k] for k in ("workflows", "views", "instruments",
                                            "metrics")), []))
    listed |= set(MANIFEST.get("schedules") or [])
    assert listed == set(DECLS), f"manifest and files disagree: {listed ^ set(DECLS)}"
    # catalogue/ops is shared between bundles (bundles/lab references its own
    # lab.* atoms), so the PHC manifest owns the phc.* atoms and no others.
    assert set(MANIFEST["operations"]) <= set(CAT["operations"])
    assert set(MANIFEST["operations"]) == {o for o in CAT["operations"] if o.startswith("phc.")}, \
        "the phc bundle must reference every phc.* op"
    for path in BUNDLE.glob("*.md"):
        fm, body = parse(path)
        assert fm["id"] == path.stem and fm["type"] in c.DECLARATION_TYPES
        assert "## In plain words" in body
        assert "\u2014" not in path.read_text(), f"{path.name}: em dash"


def test_workflow_steps_equal_the_hard_coded_line():
    wf = c.Workflow(**{**_of("workflow")["phc.wf.outpatient"],
                       "steps": [c.Step(**s) for s in _of("workflow")["phc.wf.outpatient"]["steps"]],
                       "stored": []})
    assert [(s.station, s.done_when, s.applies_when) for s in wf.steps] == list(LINE)
    for step in wf.steps:
        assert step.station in vocab.STATIONS
        for op in step.operations:
            assert CAT["operations"][op]["station"] == step.station, f"{op} drawn at wrong station"


def test_workflow_states_cover_the_vocabulary_and_reference_only_earlier_flags():
    states = _of("workflow")["phc.wf.outpatient"]["states"]
    assert set(states) == vocab.STATES, f"uncovered: {vocab.STATES ^ set(states)}"
    assert {f for f, r in states.items() if r == {"stored": True}} == set(STORED)
    seen = []
    for flag, rule in states.items():
        _check_rule(rule, seen)
        seen.append(flag)


def _check_rule(rule, seen):
    (form, arg), = rule.items()
    assert form in ("stored", "exists", "gte", "all_of"), form
    if form == "exists":
        assert arg["resource"] in vocab.CARE_RESOURCES, arg
    elif form == "gte":
        assert all(q["resource"] in vocab.CARE_RESOURCES for q in arg) and len(arg) == 2
    elif form == "all_of":
        for item in arg:
            if isinstance(item, str):
                assert item.replace("not ", "", 1) in seen, f"{item} referenced before declared"
            else:
                _check_rule(item, seen)


def test_voice_and_scribe_instruments_read_back_and_commit_by_tap():
    for iid, fm in _of("instrument").items():
        inst = c.Instrument(**fm)
        assert inst.kind in c.INSTRUMENT_KINDS
        assert inst.readback == "required" and inst.commit == "tap", f"{iid} bypasses the tap"
        assert inst.fallback in ("keypad", "form", "text")
        for op in inst.operations:
            schema = validate.load(CAT["operations"][op]["input"])
            link_ids = {q["link_id"] for q in validate.walk(schema["questions"])}
            assert set(inst.fields) <= link_ids or not inst.fields, f"{iid}: unknown field"
        if inst.kind == "constrained-voice":
            assert inst.grammar in c.VOICE_GRAMMARS
    # A scribe used to be refused outright on a numeric station. It is now
    # offered there, behind a per field tick: see the test below, which is
    # where that property is checked.


# Free text and structured rows arrive unconfirmed but without a tick; groups
# and display items carry no value at all. Every other CARE type is a discrete
# value and must be ticked. Splitting the vocabulary three ways here means a
# new CARE question type fails this check until somebody decides which it is.
_UNTICKED = {"string", "text", "url", "structured"}
_STRUCTURAL = {"group", "display"}

# How many rows of a repeating group this check fills. Two and not one, on
# purpose: with one row, a draft that collapsed every row into the first would
# still pass, and collapsing rows is the failure a repeating group adds.
_ROWS = 2


def _say(field):
    """Something a person could plausibly have said into this field, by type.

    Deliberately total: an unhandled type raises rather than being skipped,
    because a silently skipped field is a field this check does not cover
    while still reading as coverage.
    """
    kind = field["type"]
    if kind == "integer":
        return "3"
    if kind == "decimal":
        return "3.5"
    if kind == "quantity":
        return "3"
    if kind == "boolean":
        return "yes"
    if kind in ("date", "dateTime"):
        return "2026-01-02"
    if kind == "time":
        return "09:30"
    if kind == "choice":
        assert field["options"], f"{field['link_id']}: a choice with no options"
        return field["options"][0]
    raise AssertionError(f"this check cannot speak a {kind}: teach it one")


def test_every_non_text_value_a_recording_fills_comes_back_owing_a_tick():
    """The replacement for "a scribe is never offered on a numeric station".

    That rule was reversed by decision 4 of
    docs/superpowers/specs/2026-09-16-scribe-design.md: a recording may fill a
    number, and the safety property moves to a per field tick. The clinical
    risk is unchanged. A misheard "one forty" for "one fourteen" is silent,
    plausible and unrecoverable, so no heard discrete value may reach the
    record without a person confirming that one value.

    Be clear about what was traded. The old rule was structural and lived
    here: the kernel would not let a scribe near a numeric form at all, so no
    renderer could get it wrong. The new rule is split in two. This check owns
    the half that is still structural and still kernel side:

      every non-text value a scribe instrument can fill is a type the draft
      builder puts in `tick`, so the draft that reaches the renderer always
      says which values are owed a confirmation.

    The other half, that Commit stays disabled until each owed value is
    ticked, is renderer side only (kernel/DECLARATIONS.md section 4 says so)
    and is checked in web/src/scribe/scribe.check.ts. The kernel cannot
    enforce it: the guard sees a payload of tapped values and has no way to
    tell which of them were heard rather than typed. A renderer that ignored
    `tick` would commit unconfirmed numbers and this check would not catch it.
    """
    assert set(validate.TYPES) == set(fill.TICK_TYPES) | _UNTICKED | _STRUCTURAL, \
        "a CARE question type is in neither the ticked nor the untickable set"
    assert not set(fill.TICK_TYPES) & _UNTICKED, "a type cannot be both"
    # Named, because the cheap way to defeat the rest of this check is to move
    # a type out of TICK_TYPES rather than to stop ticking it. These six are
    # the ones that are dangerous when misheard.
    assert {"integer", "decimal", "quantity", "date", "choice", "boolean"} \
        <= set(fill.TICK_TYPES), "a heard number, date, choice or yes/no is always owed a tick"

    seen = 0
    for iid, fm in _of("instrument").items():
        inst = c.Instrument(**fm)
        if inst.kind != "scribe":
            continue
        for op in inst.operations:
            schema = validate.load(CAT["operations"][op]["input"])
            fields = fill.flatten(schema)
            assert fields, f"{iid}: {op} has no answerable question"
            discrete = [f for f in fields if f["type"] not in _UNTICKED]
            for f in discrete:
                assert f["type"] in fill.TICK_TYPES, \
                    f"{iid}/{op}/{f['link_id']}: a {f['type']} is neither free text nor ticked"
            # Not just the type table: the draft the kernel actually builds for
            # this operation names every one of those fields in `tick`.
            # Addressed exactly as a recording would address them: a top
            # level question by its link_id, and a question inside a repeating
            # group once per row, by row. A repeating group multiplies this
            # rule rather than exempting anything from it, so every field of
            # every row is in `answers` and every one of them must come back
            # owed a tick of its own.
            answers = {}
            for f in discrete:
                said = {"value": _say(f), "confidence": 1.0, "evidence": "said so"}
                if f["row_of"]:
                    for row in range(_ROWS):
                        answers[fill.row_id(f["row_of"], row, f["link_id"])] = said
                else:
                    answers[f["link_id"]] = said
            if not answers:
                continue
            draft = fill.build_draft(op, schema, answers, "said so",
                                     instrument=iid, today=date(2026, 1, 2))
            assert draft, f"{iid}/{op}: nothing coerced, so this check proved nothing"
            # The values a draft carries are addressed one way at the top level
            # and another inside a row, so the comparison is against the ids
            # the draft itself owes a tick for, plus the rows it built.
            groups = {f["row_of"] for f in discrete if f["row_of"]}
            assert set(draft["values"]) == \
                {f["link_id"] for f in discrete if not f["row_of"]} | groups, \
                f"{iid}/{op}: {sorted(draft['values'])} is not what was said"
            for group in groups:
                assert len(draft["values"][group]) == _ROWS, \
                    f"{iid}/{op}/{group}: {_ROWS} rows were said and " \
                    f"{len(draft['values'][group])} came back; rows were collapsed"
            assert set(draft["tick"]) == set(answers), \
                f"{iid}/{op}: heard but not owed a tick: {set(answers) - set(draft['tick'])}"
            seen += len(answers)
    assert seen, "no scribe instrument fills a discrete value, so nothing was checked"


def test_views_and_metrics_name_only_declared_things():
    metrics = _of("metric")
    for mid, fm in metrics.items():
        m = c.Metric(**fm)
        assert m.unit in c.METRIC_UNITS and m.window in c.METRIC_WINDOWS
        allowed = vocab.CARE_RESOURCES | vocab.KERNEL_RESOURCES
        assert m.numerator["resource"] in allowed
        assert (m.denominator is None) == (m.unit == "count"), mid
        if m.denominator:
            assert m.denominator["resource"] in vocab.CARE_RESOURCES
    for vid, fm in _of("view").items():
        v = c.View(**{**fm, "sections": [c.Section(**s) for s in fm.get("sections", [])]})
        assert v.kind in c.VIEW_KINDS and v.capability in vocab.CAPABILITIES
        assert v.scope in c.VIEW_SCOPES and v.window in c.METRIC_WINDOWS
        if v.kind == "dashboard":
            assert set(v.metrics) <= set(metrics), vid
        else:
            assert v.workflow in _of("workflow"), vid
        for s in v.sections:
            assert (s.show is None) != (s.resource is None), f"{vid}: {s.title}"
            assert s.show in (None,) + c.SUMMARY_SHOW
            assert s.resource in (None,) or s.resource in vocab.CARE_RESOURCES
        assert set(v.badges) <= vocab.STATES


def test_api_shapes_are_plain_json():
    audit = c.AuditRecord.from_guard(
        {"operation": "phc.op.vitals-record", "actor": "u1", "surface": c.RENDERED,
         "payload": {"systolic": 140}, "outcome": "allowed"},
        id="a1", thread="enc-1", at="2026-09-10T10:00:00Z")
    tv = c.ThreadView(id="enc-1", workflow="phc.wf.outpatient", subject={"name": "L"},
                      flags=["registered"], station="nurse",
                      line=[c.StepStatus("reception", "registered", "done")],
                      actions=[], proposals=[], audit=[audit],
                      capabilities=sorted(vocab.CAPABILITIES), held=["vitals.record"])
    out = json.loads(json.dumps(tv.to_json()))
    assert out["audit"][0]["outcome"] == "allowed" and out["line"][0]["status"] == "done"
    assert "patient" not in out and "subject" in out, "the FE rename is part of the contract"
    assert c.Proposal("p1", "enc-1", "phc.op.rx-prescribe", {}, "svc", c.MCP,
                      "pending", "2026-09-10T10:00:00Z").status in c.PROPOSAL_STATUSES


def test_a_seeded_audit_line_answers_its_own_questionnaire():
    """A posted card draws its values from the audit payload, so a seed that
    names an operation and answers nothing is a receipt for something
    invisible, and one that answers a key the form does not ask renders a raw
    identifier at a clinician. Both are build failures.

    This is the check for the bug that shipped: the health centre's seed
    declared no audit at all, so every demo thread said "Nothing has been
    recorded on this visit yet" over three ticked steps of its own stepper.
    """
    ops = CAT["operations"]
    phc = declarations.load("phc")
    manifest = dataclasses.asdict(phc.manifest)
    voc = vocab.for_bundle("phc")

    # The provenance marks this bundle's own views declare. A seeded arrival
    # is closed against them, so the lint needs them the same way the build
    # does; passing none would make that half of it quietly vacuous.
    marks = {v.provenance["mark"] for v in phc.views.values() if v.provenance}
    assert marks, "this bundle declares a provenance mark to close the seed against"

    good = declarations._lint_seed(phc.seed, manifest, voc, ops, marks)
    assert good == [], good

    # And a demo day that invents its own word for how somebody arrived is a
    # build failure, not a thread that silently draws no mark.
    invented = [{"id": "enc-1", "arrival": "walked-in-through-the-window"}]
    assert declarations._lint_seed(invented, manifest, voc, ops, marks), \
        "an arrival no view declares has to fail the build"
    assert declarations._lint_seed(
        [{"id": "enc-1", "arrival": sorted(marks)[0]}], manifest, voc, ops, marks) == [], \
        "and a declared mark has to pass, or the rule is just refusing everything"

    typo = [{"id": "enc-1", "audit": [
        {"operation": "phc.op.vitals-record", "actor": "user:nurse",
         "payload": {"systolic": 120, "sistolic": 120}}]}]
    bad = declarations._lint_seed(typo, manifest, voc, ops)
    assert len(bad) == 1 and "sistolic" in bad[0], bad
    assert "phc.schema.vitals-v1 does not ask" in bad[0], bad

    # Every audit line in every bundle's seed says what was recorded, not only
    # that something was.
    for bundle_id in ("phc", "lab"):
        b = declarations.load(bundle_id)
        for t in b.seed:
            for entry in t.get("audit") or []:
                assert entry.get("payload"), (bundle_id, t["id"], entry["operation"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
