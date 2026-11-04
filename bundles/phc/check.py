"""Run: python3 -m bundles.phc.check

THERE IS NO CONSENT TO AMBIENT CAPTURE, and this is what holds that true.

This file was 407 lines of end-to-end consent tests: consenting raised the
flag and offered the scribe, declining was visibly declined, neither leaked
to the next visit, and a withdrawal turned the gate off without writing a
clinical note. The owner removed the whole mechanism on 4 November 2026.

It is not deleted with the feature, and that is deliberate. A test suite for
something that no longer exists has nothing left to assert about it -- but a
half-removed gate is worse than either having one or not having one, because
a flag that still exists somewhere and that nothing honours looks exactly
like protection from the outside. So the suite was replaced, not dropped,
and what it holds now is that the removal stayed complete: no flag, no
question, no operation, no instrument gate, in either bundle, on either
engine's own copy of the declarations.

What was taken out, for whoever has to put it back:

    capture.agreed     a question on the registration form
    capture.declined   its own answer on the same form, a first class no
    capture.withdrawn  phc.op.capture-withdraw, one question, its own action
    capture.consented  composed: neither declined nor withdrawn
    phc.inst.consent-speak      the line a clerk read to the patient
    requires: capture.consented on phc.inst.consult-scribe

bundles/phc/phc.wf.outpatient.md carries the same list in prose, next to
what it cost.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PASSED = 0


def ok(msg: str) -> None:
    global PASSED
    PASSED += 1
    print("ok   " + msg)


# The compiled catalogue, which is what both engines actually read. Checking
# the source atoms instead would miss a flag that survived into the build.
CATALOGUES = {
    "catalogue/catalogue.json": json.loads((ROOT / "catalogue" / "catalogue.json").read_text()),
    "care_phc_mcp/catalogue.json": json.loads(
        (ROOT / "care_phc_mcp" / "catalogue.json").read_text()),
}


def check_no_workflow_declares_a_capture_state():
    """The gate itself. A state nothing composes and nothing lowers is the
    hole this product already had once, in the other direction."""
    for where, cat in CATALOGUES.items():
        for wf_id, wf in (cat.get("workflows") or {}).items():
            strays = sorted(f for f in (wf.get("states") or {}) if f.startswith("capture."))
            assert not strays, f"{where} {wf_id} still declares {strays}"
            stored = sorted(f for f in (wf.get("stored") or ()) if f.startswith("capture."))
            assert not stored, f"{where} {wf_id} still stores {stored}"
    ok("no workflow in either engine's catalogue declares a capture state")


def check_no_operation_emits_or_requires_one():
    """phc.op.capture-withdraw was the only way to lower the gate. An
    operation that emitted a capture flag with nothing reading it would be a
    button that claims to stop a recording and does not."""
    for where, cat in CATALOGUES.items():
        for op_id, op in (cat.get("operations") or {}).items():
            assert "capture-withdraw" not in op_id, f"{where} still carries {op_id}"
            bad = sorted(f for f in (op.get("emits") or ()) if f.startswith("capture."))
            assert not bad, f"{where} {op_id} emits {bad}"
            pre = sorted(f for f in (op.get("preconditions") or ()) if f.startswith("capture."))
            assert not pre, f"{where} {op_id} is gated on {pre}"
    ok("no operation emits a capture flag or is gated on one")


def check_no_instrument_requires_one():
    """`requires:` is the renderer's own gate and it still works; what is
    gone is this bundle's use of it. A scribe that still required a flag
    nothing raises would be a microphone permanently off."""
    for where, cat in CATALOGUES.items():
        for inst_id, inst in (cat.get("instruments") or {}).items():
            needs = inst.get("requires")
            assert not (needs or "").startswith("capture."), \
                f"{where} {inst_id} still requires {needs}"
    ok("no instrument is gated on a capture flag, so no microphone is "
       "permanently off")


def check_no_form_still_asks():
    """A question that raises a flag nothing declares is refused by the
    build, so this is belt and braces -- but it is the half a reader
    actually sees, and a clerk being asked for consent nothing records is
    the worst of both."""
    forms = sorted((ROOT / "questionnaires").glob("*.json"))
    assert forms, "no questionnaires found, so this check proves nothing"
    for path in forms:
        schema = json.loads(path.read_text())

        def walk(questions):
            for q in questions:
                yield q
                yield from walk(q.get("questions") or [])

        for q in walk(schema.get("questions") or []):
            assert not q["link_id"].startswith("capture"), \
                f"{path.name} still asks {q['link_id']}"
            raises = ((q.get("styling_metadata") or {}).get("phc") or {}).get("flags") or ""
            assert not raises.startswith("capture."), \
                f"{path.name}:{q['link_id']} still raises {raises}"
    ok(f"none of the {len(forms)} forms asks for consent or raises a capture flag")


def check_the_seeded_day_carries_none():
    """The demo day had one visit that agreed and one that declined, and
    both were read off the queue. A seed is a declaration like any other."""
    seed = (ROOT / "bundles" / "phc" / "seed.yaml").read_text()
    assert "capture" not in seed, "bundles/phc/seed.yaml still seeds a capture flag"
    ok("the seeded day carries no capture flag on any visit")


def check_the_laboratory_never_had_one_and_still_does_not():
    """The lab bundle does no ambient capture and never declared any of
    this. Kept because it is the check that would catch consent coming back
    in the wrong place: a flag reintroduced for the health centre and
    copied across."""
    for path in sorted((ROOT / "bundles" / "lab").glob("*.md")):
        assert "capture" not in path.read_text(), path
    ok("the laboratory bundle carries no capture flag, no scribe gate and "
       "no consent question")


def check_the_kernel_enforces_nothing_about_consent():
    """The trust boundary. The renderer's gate was always a courtesy; this
    was the check that mattered, and now it is the check that there is
    nothing left to check."""
    api = (ROOT / "api" / "main.py").read_text()
    assert 'CONSENT = "capture.consented"' not in api, \
        "api/main.py still defines the consent flag"
    assert "capture.consented" not in api, \
        "api/main.py still reads the consent flag somewhere"
    ok("the kernel's upload route refuses a recording for capability alone")


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("check_"):
            fn()
    print(f"\n{PASSED} checks: consent is gone, and gone from both engines")
