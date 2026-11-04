"""Lint rules for the `calendar` view kind."""
from __future__ import annotations

import json
import pathlib

import yaml

from catalogue.build import parse
from kernel import declarations

ROOT = pathlib.Path(__file__).parents[2]
BUNDLE = ROOT / "bundles" / "phc"
CAT = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
MANIFEST = yaml.safe_load((BUNDLE / "bundle.yaml").read_text())


def _decls():
    return {fm["id"]: (dict(fm), body)
            for fm, body in (parse(p) for p in sorted(BUNDLE.glob("*.md")))}


def _lint(decls):
    return declarations.lint(MANIFEST, decls, CAT["operations"])


def test_the_shipped_bundle_lints_clean():
    assert _lint(_decls()) == []


def test_a_calendar_naming_an_episode_type_no_schedule_covers_is_refused():
    # Drawing an episode no schedule declares gives an empty screen with no
    # error anywhere: the silent failure the tasklist branch also prevents.
    decls = _decls()
    decls["phc.view.calendar"][0]["episodes"] = ["pregnancy", "toddlerhood"]
    bad = _lint(decls)
    assert any("phc.view.calendar" in b and "toddlerhood" in b for b in bad), bad
    assert not any("'pregnancy'" in b for b in bad)


def test_a_calendar_naming_no_episodes_is_refused():
    decls = _decls()
    decls["phc.view.calendar"][0]["episodes"] = []
    assert any("phc.view.calendar" in b and "no episodes" in b for b in _lint(decls))


def test_a_calendar_naming_an_unknown_workflow_is_refused():
    decls = _decls()
    decls["phc.view.calendar"][0]["workflow"] = "phc.wf.nonesuch"
    assert any("phc.view.calendar" in b and "phc.wf.nonesuch" in b for b in _lint(decls))


def test_the_shipped_calendar_declaration_compiles():
    view = CAT["views"]["phc.view.calendar"]
    assert view["kind"] == "calendar"
    assert view["episodes"] == ["pregnancy", "postnatal"]


def test_a_contact_carries_both_a_plain_name_and_the_programme_s():
    anc = CAT["schedules"]["phc.sched.antenatal"]["contacts"]
    assert [c["title"] for c in anc] == [
        "First check-up", "Second check-up", "Third check-up", "Fourth check-up"]
    assert [c["programme_title"] for c in anc] == [
        "First antenatal contact", "Second antenatal contact",
        "Third antenatal contact", "Fourth antenatal contact"]
    # The statutory code is a third thing and stays as it was.
    assert [c["reports_as"] for c in anc] == ["ANC1", "ANC2", "ANC3", "ANC4"]


def test_a_schedule_declaring_no_programme_name_still_compiles():
    decls = _decls()
    for c in decls["phc.sched.postnatal"][0]["contacts"]:
        c.pop("programme_title", None)
    assert _lint(decls) == []
    bundle = declarations.load("phc")
    from kernel.contracts import Contact
    assert Contact.__dataclass_fields__["programme_title"].default is None
    assert bundle.schedules["phc.sched.postnatal"].contacts


def test_the_subject_answer_carries_the_date_it_was_generated():
    import re
    from adapters.local.store import SqliteStore
    from kernel import spine
    b = declarations.load("phc")
    store = SqliteStore(":memory:")
    wf = b.workflow()
    store.write("patient", {"id": "p-x", "name": "X"}, thread="e-x")
    found = spine.of(b, store, wf, "p-x")
    assert found is not None
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", found["generated_at"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok   {fn.__name__}")
    print(f"\n{len(fns)} checks passed")
