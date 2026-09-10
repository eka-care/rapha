"""Run: python3 -m kernel.tests.test_contracts

The PHC bundle must say the same thing as the code it replaces. These checks
fail if the workflow drifts from care_phc/thread.py, a declaration names
something outside the vocabularies, or a voice instrument finds a way to
commit without a tap. No kernel, no database, no network.
"""
from __future__ import annotations

import json
import pathlib

import yaml

from care_phc.thread import LINE, STORED
from catalogue import validate, vocab
from catalogue.build import parse
from kernel import contracts as c

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
    listed = set(sum((MANIFEST[k] for k in ("workflows", "views", "instruments", "metrics")), []))
    assert listed == set(DECLS), f"manifest and files disagree: {listed ^ set(DECLS)}"
    assert set(MANIFEST["operations"]) == set(CAT["operations"]), "bundle must reference all 9 ops"
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
        assert inst.fallback in ("keypad", "form")
        for op in inst.operations:
            schema = validate.load(CAT["operations"][op]["input"])
            link_ids = {q["link_id"] for q in validate.walk(schema["questions"])}
            assert set(inst.fields) <= link_ids or not inst.fields, f"{iid}: unknown field"
            if inst.kind == "scribe":
                assert CAT["operations"][op]["instrument"] != "device", \
                    f"{iid}: scribe offered on a numeric station"
        if inst.kind == "constrained-voice":
            assert inst.grammar in c.VOICE_GRAMMARS


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


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
