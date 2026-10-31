"""Run: python3 scripts/check_templates.py

The doctor's three templates, and the properties that make them templates
rather than three more hand written forms.

What is proved here, in order:

  a template is a narrowing of ONE operation and nothing else about it moves.
    Its capability, station, instrument, preconditions, irreversibility,
    emits and surfaces are the base's own, read off the compiled catalogue
  the questions on a template's form are the base's question objects, so a
    binding, a unit, a range and a help sentence cannot be retyped and cannot
    disagree
  a template declares no clinical content, and there is nowhere in the
    declaration to put any
  the generated form and the generated atom are what the declaration says,
    and a hand edit to either fails
  every template publishes through the ONE `documents` declaration, into the
    same profile and the same section slices as the general consultation
  the narrative fallback is intact: the antenatal template codes nothing and
    its whole consultation reaches the document as text
  the tick cannot be weakened. A template narrows the FORM, so a question it
    does not ask produces no value, owes no tick and leaves nothing hidden
    for a renderer to commit unread
  the lint refuses eleven ways, each one a template that would look right
  no engine module types a clinical word, kernel/templates.py included

What this does NOT prove, and cannot
------------------------------------
That any of the three narrowings is clinically correct. Which questions an
NCD review or an antenatal visit should ask is a clinical and product
decision that has not been made: `terminology/condition-code.json` holds
three concepts, says it is not a diagnosis list, and awaits a named clinical
officer. Two of the three templates carry a NEEDS SIGN-OFF sentence for that
reason and this check asserts the sentence is there, which is a check about
honesty and not about medicine.

Pure: in memory stores, no socket, no network. Python 3.9.
"""
from __future__ import annotations

import base64
import copy
import datetime
import json
import pathlib
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                       # noqa: E402
from catalogue.build import parse as parse_atom                    # noqa: E402
from api import fill                                               # noqa: E402
from catalogue import validate, vocab                              # noqa: E402
from kernel import (declarations, fhir, mapping, proposals, templates,  # noqa: E402
                    terminology)

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
MANIFEST = yaml.safe_load((ROOT / "bundles" / "phc" / "bundle.yaml").read_text())
DECLARED = templates.declared(MANIFEST)
OPS = BUNDLE.operations
# The whole catalogue, which is what kernel/declarations.py hands the lint:
# catalogue/ops is shared between bundles, so "not in the catalogue" and "this
# bundle does not load it" are two different failures and need both lists.
ALL_OPS = json.loads(
    (ROOT / "catalogue" / "catalogue.json").read_text())["operations"]
CAPS = set(vocab.for_bundle("phc").roles["mo"]) \
    | set(vocab.for_bundle("phc").roles["frontdesk"])
A_DOCTOR = "user:ravi"
NOW = "2026-10-31T10:05:00+00:00"
BASE = "phc.op.consult-document"

assert sorted(DECLARED) == ["phc.op.antenatal-visit", "phc.op.followup",
                            "phc.op.ncd-review"], sorted(DECLARED)


# ---------------------------------------------------------------------------
# 1. A template is a narrowing of one operation, and nothing else moves.
# ---------------------------------------------------------------------------

# Every one of these is an answer to "who may do this, where, when, and from
# which surface". A template that could change any of them would be a way to
# widen a capability by declaring a form, which is the whole reason the
# narrowing is the only thing a template says.
INHERITS = ("capability", "station", "instrument", "preconditions",
            "irreversibility", "emits", "surfaces", "kind", "presents",
            "scope_qualifier")
for tid, decl in sorted(DECLARED.items()):
    base, made = OPS[decl["of"]], OPS[tid]
    for key in INHERITS:
        assert made[key] == base[key], (tid, key, made[key], base[key])
assert OPS[BASE]["capability"] == "encounter.document"
assert OPS[BASE]["station"] == "doctor"
ok("each template inherits every fact about who may do it, where and from "
   "which surface: %d facts, times %d templates, all the base's own"
   % (len(INHERITS), len(DECLARED)))

# And it is reachable: loaded, fillable by a recording, drawn at its station.
SCRIBE = {oid for inst in BUNDLE.instruments_raw if inst.get("kind") == "scribe"
          for oid in inst.get("operations") or []}
STEP = {oid for step in BUNDLE.workflow().steps if step.station == "doctor"
        for oid in step.operations}
for tid in DECLARED:
    assert tid in BUNDLE.manifest.operations, tid
    assert tid in SCRIBE, tid
    assert tid in STEP, tid
assert [c for c in BUNDLE.scribe["doctor"]["choose"]] == \
    [BASE, "phc.op.ncd-review", "phc.op.antenatal-visit", "phc.op.followup",
     "phc.op.rx-prescribe"], BUNDLE.scribe["doctor"]
ok("and it is reachable: loaded by the bundle, on the scribe's list, drawn at "
   "the doctor's step, and offered by the station's own switcher")


# ---------------------------------------------------------------------------
# 2. The questions are the base's own objects, not copies.
# ---------------------------------------------------------------------------

BASE_SCHEMA = validate.load(OPS[BASE]["input"])
BASE_BY = {q["link_id"]: q for q in BASE_SCHEMA["questions"]}
for tid, decl in sorted(DECLARED.items()):
    schema = validate.load(OPS[tid]["input"])
    asked = [q["link_id"] for q in schema["questions"]]
    assert asked == list(decl["asks"]), (tid, asked)
    assert set(asked) <= set(BASE_BY), (tid, set(asked) - set(BASE_BY))
    for q in schema["questions"]:
        want = dict(BASE_BY[q["link_id"]])
        if q["link_id"] in (decl.get("require") or []):
            want["required"] = True
        assert q == want, (tid, q["link_id"], q, want)
    assert validate._phc(schema)["operation"] == tid, schema
ok("every question on a template's form is the base's own question object, "
   "required flag aside: a binding, a unit, a range and a help sentence "
   "cannot be retyped and so cannot disagree")

# A required answer is the base's or the template's, never less than the
# base's for a question it still asks.
for tid, decl in sorted(DECLARED.items()):
    for q in validate.load(OPS[tid]["input"])["questions"]:
        if BASE_BY[q["link_id"]].get("required"):
            assert q.get("required"), (tid, q["link_id"])
ok("a question the base requires stays required on every template that asks "
   "it: narrowing drops a question, it never relaxes one")


# ---------------------------------------------------------------------------
# 3. A template declares no clinical content, and has nowhere to put any.
# ---------------------------------------------------------------------------

# Everything a code, a value set, a unit, a range or a threshold could travel
# in. A declaration carrying any of them would be clinical content declared in
# a bundle by somebody who is not a clinician, which is forbidden by every
# brief on this branch and by the banners on the two seeded value sets.
CLINICAL_KEYS = ("answer_value_set", "answer_option", "unit", "range",
                 "critical", "flags", "code", "system", "writes", "mapping",
                 "input", "capability", "station", "emits", "surfaces")
for tid, decl in sorted(DECLARED.items()):
    assert set(decl) <= set(templates.KEYS), set(decl) - set(templates.KEYS)
    for key in CLINICAL_KEYS:
        assert key not in decl, (tid, key)
    for link_id in list(decl["asks"]) + list(decl.get("require") or []):
        assert link_id in BASE_BY, (tid, link_id)
ok("a template declaration holds %d keys and not one of them can carry a "
   "code, a value set, a unit, a range or a threshold" % len(templates.KEYS))

# The value sets a template's form binds to are the base's, and every one is
# cached, so a bound choice has options to draw rather than an empty dropdown.
SLUGS = set()
for tid in DECLARED:
    for q in validate.walk(validate.load(OPS[tid]["input"])["questions"]):
        slug = terminology.answer_binding(q)
        if slug:
            SLUGS.add(slug)
            assert terminology.LOCAL.concepts(slug), slug
assert SLUGS == {"condition-code", "condition-clinical-status",
                 "condition-verification-status"}, sorted(SLUGS)
ok("every value set a template's form binds to is the base's and is cached "
   "offline: %s" % ", ".join(sorted(SLUGS)))

# The two narrowings that are product choices say so where a clinician reads
# them. The antenatal one says what it is instead: a fact about the
# vocabulary, and that it codes nothing.
for tid in ("phc.op.ncd-review", "phc.op.followup"):
    assert "NEEDS SIGN-OFF" in DECLARED[tid]["sign_off"], tid
    assert "NEEDS SIGN-OFF" in (ROOT / "catalogue" / "ops" / ("%s.md" % tid)).read_text()
# Squashed, because a YAML block scalar keeps the author's line breaks and a
# sentence is not a line.
antenatal = " ".join(DECLARED["phc.op.antenatal-visit"]["sign_off"].split())
assert "codes NOTHING" in antenatal and "signed off" in antenatal, antenatal
ok("a narrowing nobody clinical signed off says so on the atom a clinician "
   "reads, and the one that codes nothing says that instead")


# ---------------------------------------------------------------------------
# 4. Generated, so it cannot drift.
# ---------------------------------------------------------------------------

assert templates.drift(MANIFEST) == [], templates.drift(MANIFEST)
GENERATED = templates.generate(MANIFEST)
assert len(GENERATED) == 2 * len(DECLARED), sorted(p.name for p in GENERATED)
for path in GENERATED:
    assert "GENERATED FILE" in path.read_text() or path.suffix == ".json", path
ok("the %d generated files are what the `templates` declaration says, and "
   "every generated atom says it is generated" % len(GENERATED))

# A hand edit to a generated file fails, which is what makes "it cannot drift"
# a check rather than a hope. Done in a copy of the two directories so this
# check never writes into the repository it is checking.
with tempfile.TemporaryDirectory() as tmp:
    ops_dir, schemas_dir = pathlib.Path(tmp) / "ops", pathlib.Path(tmp) / "q"
    ops_dir.mkdir()
    schemas_dir.mkdir()
    for src in (ROOT / "catalogue" / "ops").glob("*.md"):
        (ops_dir / src.name).write_text(src.read_text())
    for src in (ROOT / "questionnaires").glob("*.json"):
        (schemas_dir / src.name).write_text(src.read_text())
    assert templates.drift(MANIFEST, ops_dir, schemas_dir) == []
    edited = ops_dir / "phc.op.followup.md"
    edited.write_text(edited.read_text().replace("Follow up visit",
                                                 "Follow-up visit"))
    bad = templates.drift(MANIFEST, ops_dir, schemas_dir)
    assert len(bad) == 1 and "phc.op.followup.md" in bad[0], bad
    assert "do not edit it" in bad[0].lower(), bad
    edited.unlink()
    assert any("not generated" in line for line in
               templates.drift(MANIFEST, ops_dir, schemas_dir))
ok("a hand edit to a generated atom is refused, and so is a declared "
   "template whose files were never generated")

# The narrowing itself is NOT compiled into catalogue.json, for the reason
# `documents` is not: the renderer draws a template's form by `input` like any
# other form and must never learn that it is a narrowing of something else.
CAT = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
assert "templates" not in CAT, sorted(CAT)
for tid in DECLARED:
    assert tid in CAT["operations"], tid
    assert "asks" not in CAT["operations"][tid], tid
ok("the narrowing stays out of catalogue.json: the renderer gets three "
   "ordinary operations with three ordinary forms and learns nothing else")


# ---------------------------------------------------------------------------
# 5. The same document path as the general consultation.
# ---------------------------------------------------------------------------

CONSULT = BUNDLE.documents["consultation"]
NARRATIVE = {"history": "Bukhaar teen din se, khaana kam.",
             "examination": "Chest clear. No pedal oedema.",
             "assessment": "Fever, likely viral. Dengue not excluded.",
             "plan": "Paracetamol SOS, review in 48 hours."}
CODED = [{"condition": "44054006", "clinical_status": "active",
          "verification_status": "unconfirmed"}]


def visit(token, op, payload):
    """One patient, one visit, through the guard with a person's tap on it."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token=token, actor=A_DOCTOR)
    for oid, body in (("phc.op.patient-register",
                       {"name": "Sunita Devi", "age": 34, "sex": "female",
                        "phone": "9876500000", "village": "Yadiki",
                        "category": "general"}),
                      (op, payload)):
        decision = proposals.commit(store, BUNDLE, oid, thread=thread,
                                    payload=body, caps=CAPS, actor=A_DOCTOR)
        assert decision, (oid, decision.reason)
    return store, thread


def published(store, thread):
    return fhir.document(store, thread, now=NOW, **CONSULT)


def sections(doc):
    return {s["title"]: s for s in doc["entry"][0]["resource"]["section"]}


def kinds(doc, kind):
    return [e["resource"] for e in doc["entry"]
            if e["resource"]["resourceType"] == kind]


def attached(doc):
    (reference,) = kinds(doc, "DocumentReference")
    return base64.b64decode(
        reference["content"][0]["attachment"]["data"]).decode()


# The general consultation, as the thing the three are held against.
store, thread = visit("T00", BASE, dict(NARRATIVE, diagnosis=CODED))
general = published(store, thread)
assert set(sections(general)) == {"Chief complaints", "Document Reference"}, \
    sorted(sections(general))

# NCD review: the same five questions, the examination required. Same profile,
# same two slices, same codes, by the same one declaration.
store, thread = visit("T01", "phc.op.ncd-review", dict(NARRATIVE, diagnosis=CODED))
review = published(store, thread)
assert review["entry"][0]["resource"]["meta"]["profile"] == \
    general["entry"][0]["resource"]["meta"]["profile"]
assert set(sections(review)) == set(sections(general)), sorted(sections(review))
for title, section in sections(review).items():
    assert section["code"] == sections(general)[title]["code"], title
(condition,) = kinds(review, "Condition")
assert condition["code"]["coding"][0]["code"] == "44054006", condition
ok("the NCD review publishes the same profile, under the same section slices "
   "with the same codes, as the general consultation: one declaration, not a "
   "second placement")

# Follow up: no examination on the form, so the note carries four paragraphs
# rather than five, and the coded diagnosis still files under Chief complaints.
store, thread = visit("T02", "phc.op.followup",
                      {k: v for k, v in dict(NARRATIVE, diagnosis=CODED).items()
                       if k != "examination"})
follow = published(store, thread)
assert set(sections(follow)) == set(sections(general)), sorted(sections(follow))
assert "Examination" not in attached(follow), attached(follow)
assert "History" in attached(follow) and "Plan" in attached(follow)
assert kinds(follow, "Condition"), follow
ok("the follow up files its coded condition under the same heading, and its "
   "note carries the four paragraphs its form asked for and no empty fifth")

# A payload answering a question the template does not ask is refused by the
# ordinary validator, so a narrowed form is narrowed at the write path too and
# not only on a screen.
refused = proposals.commit(
    SqliteStore(":memory:"), BUNDLE, "phc.op.antenatal-visit",
    thread=None, payload=dict(NARRATIVE, diagnosis=CODED), caps=CAPS,
    actor=A_DOCTOR)
assert not refused, refused
assert "diagnosis" in refused.reason, refused.reason
ok("an answer to a question a template does not ask is refused at the write "
   "path by the ordinary validator, not merely hidden by a renderer")


# ---------------------------------------------------------------------------
# 6. The narrative fallback, intact and proved rather than asserted.
# ---------------------------------------------------------------------------

store, thread = visit("T03", "phc.op.antenatal-visit", dict(NARRATIVE))
antenatal_doc = published(store, thread)
assert set(sections(antenatal_doc)) == {"Document Reference"}, \
    sorted(sections(antenatal_doc))
assert not kinds(antenatal_doc, "Condition"), antenatal_doc
carried = attached(antenatal_doc)
for paragraph in NARRATIVE.values():
    assert paragraph in carried, (paragraph, carried)
assert store.select("condition", thread=thread, where={}, fields=[], limit=5) == []
ok("the antenatal template codes nothing, publishes no Condition, and carries "
   "all four of its paragraphs into the document as text: the fallback the "
   "DocumentReference exists for")

# And it is the operation's own mapping that does it, narrowed from the base's
# rather than written again: the note record's sources are the base's list
# minus the questions the template does not ask.
BASE_NOTE, = [r for r in OPS[BASE]["mapping"] if r["resource"] == "notes"]
for tid, decl in sorted(DECLARED.items()):
    note, = [r for r in OPS[tid]["mapping"] if r["resource"] == "notes"]
    assert note["fields"]["text"]["note"] == \
        [k for k in BASE_NOTE["fields"]["text"]["note"] if k in decl["asks"]], tid
    assert note["fields"]["created_by"] == BASE_NOTE["fields"]["created_by"], tid
ok("each template's note is the base's own note source narrowed to the "
   "questions it asks, so the narrative path is inherited and never retyped")

# The resources a template writes follow from the narrowing, so a template
# that drops the diagnosis group writes no condition rather than writing an
# empty one.
assert OPS["phc.op.antenatal-visit"]["writes"] == ["encounter", "notes"]
assert OPS["phc.op.ncd-review"]["writes"] == ["encounter", "notes", "condition"]
assert OPS["phc.op.followup"]["writes"] == ["encounter", "notes", "condition"]
ok("what a template writes follows from what it asks: the one that drops the "
   "diagnosis rows declares no condition rather than an empty one")


# ---------------------------------------------------------------------------
# 7. The tick cannot be weakened.
# ---------------------------------------------------------------------------

TODAY = datetime.date(2026, 10, 31)
HEARD = {"history": "fever three days",
         "diagnosis[0].condition": "Type 2 diabetes mellitus",
         "diagnosis[0].clinical_status": "active",
         "diagnosis[0].verification_status": "unconfirmed",
         "diagnosis[0].onset": "15 August"}


def draft_for(op_id, heard):
    answers = {k: {"value": v, "confidence": 0.8, "evidence": str(v)}
               for k, v in heard.items()}
    return fill.build_draft(op_id, validate.load(OPS[op_id]["input"]), answers,
                            "a recording", instrument="phc.inst.consult-scribe",
                            today=TODAY)

# On a template that asks the diagnosis rows, every non text value of the row
# is owed its own tick, exactly as on the general consultation. One tick per
# question would commit three values nobody read.
for tid in (BASE, "phc.op.ncd-review", "phc.op.followup"):
    draft = draft_for(tid, HEARD)
    assert sorted(draft["tick"]) == [
        "diagnosis[0].clinical_status", "diagnosis[0].condition",
        "diagnosis[0].onset", "diagnosis[0].verification_status"], (tid, draft["tick"])
    assert "history" not in draft["tick"], tid
ok("a recording into a template owes a tick for every non text value of every "
   "row, the same four as the general consultation, and none for the text")

# And on the template that does NOT ask them, the heard diagnosis produces no
# value at all. This is the property that makes narrowing safe: a template
# narrows the FORM, so there is no hidden field holding an untickable value.
# A renderer hiding a field would have left the value in the payload.
narrowed = draft_for("phc.op.antenatal-visit", HEARD)
assert narrowed["values"] == {"history": "fever three days"}, narrowed["values"]
assert narrowed["tick"] == [], narrowed
assert set(narrowed["unfilled"]) == set(HEARD) - {"history"}, narrowed["unfilled"]
flat = {f["link_id"] for f in fill.flatten(validate.load(
    OPS["phc.op.antenatal-visit"]["input"]))}
assert "condition" not in flat and "onset" not in flat, flat
ok("a question a template does not ask is absent from its form, so a "
   "recording fills no value for it, owes no tick for it, and leaves nothing "
   "hidden for a tap to commit unread")


# ---------------------------------------------------------------------------
# 8. What the lint refuses.
# ---------------------------------------------------------------------------

# The bundle directory's own declarations, the way kernel/declarations.py
# reads them, so the lint can be asked about a scribe instrument and a
# workflow that have been bent.
DECLS = {}
for _path in sorted((ROOT / "bundles" / "phc").glob("*.md")):
    _fm, _body = parse_atom(_path)
    DECLS[_fm["id"]] = (_fm, _body)


def refuses(change, fragment, *, where="phc.op.followup"):
    """Mutate the manifest, lint it, and assert the named failure appears."""
    bent = copy.deepcopy(MANIFEST)
    change(bent)
    bad = templates.lint(bent, ALL_OPS, DECLS)
    assert any(fragment in line for line in bad), (fragment, bad)
    return bad


def tpl(bent, key, value, where="phc.op.followup"):
    bent["templates"][where][key] = value


refuses(lambda m: tpl(m, "asks", ["history", "bp"]),
        "asks 'bp', which phc.schema.consult-v1 does not ask")
refuses(lambda m: tpl(m, "require", ["examination"]),
        "requires 'examination', which it does not ask")
refuses(lambda m: tpl(m, "asks", ["history", "history", "assessment", "plan"]),
        "asks 'history' twice")
# An empty `asks` is a form with no questions, and it is reported as a
# missing key rather than by a branch of its own: `asks` is required and an
# empty list is falsy, so a second branch for it could never run.
refuses(lambda m: tpl(m, "asks", []), "missing asks")
# A narrowing that records nothing. Not reachable from the consultation,
# whose encounter record is all literals and so is kept whatever is asked, so
# this one narrows the ABHA link instead: its only record reads
# `abha_number`, and a narrowing that does not ask for it leaves the
# operation with nothing to write.
def nothing_recorded(bent):
    bent["templates"]["phc.op.followup"] = dict(
        bent["templates"]["phc.op.followup"],
        of="phc.op.abha-link", asks=["method"], require=[])


refuses(nothing_recorded, "its narrowing leaves no mapping record")
refuses(lambda m: tpl(m, "of", "phc.op.ncd-review"),
        "which is itself a template")
refuses(lambda m: tpl(m, "of", "lab.op.result-verify"),
        "which this bundle does not load")
refuses(lambda m: tpl(m, "of", "phc.op.nope"), "which is not in the catalogue")
refuses(lambda m: tpl(m, "plain", None), "missing plain")
refuses(lambda m: tpl(m, "colour", "blue"), "unknown key 'colour'")
refuses(lambda m: m["operations"].remove("phc.op.followup"),
        "is not in bundle.yaml operations")
ok("the lint refuses ten ways: a question that does not exist, a requirement "
   "off the form, a duplicate, an empty form, a narrowing that records "
   "nothing, a narrowing of a narrowing, an operation this bundle does not "
   "load, one that does not exist, a missing word a clinician reads, an "
   "unknown key, and a template generated but never loaded")

# A template claiming a station or a capability nobody declared. The station
# and the capability are the base's own, so the way a template claims one it
# does not have is by being drawn where nothing offers it: no scribe
# instrument that may fill it, or no step of the workflow that lists it at
# the station it inherits.
bent = copy.deepcopy(MANIFEST)
decls = dict(DECLS)
inst = copy.deepcopy(DECLS["phc.inst.consult-scribe"][0])
inst["operations"] = [o for o in inst["operations"] if o != "phc.op.followup"]
decls["phc.inst.consult-scribe"] = (inst, DECLS["phc.inst.consult-scribe"][1])
bad = templates.lint(bent, ALL_OPS, decls)
assert any("no scribe instrument lists it" in line for line in bad), bad

decls = dict(DECLS)
wf = copy.deepcopy(DECLS["phc.wf.outpatient"][0])
wf["steps"] = [dict(s, operations=[o for o in s["operations"]
                                   if o != "phc.op.followup"])
               for s in wf["steps"]]
decls["phc.wf.outpatient"] = (wf, DECLS["phc.wf.outpatient"][1])
bad = templates.lint(bent, ALL_OPS, decls)
assert any("the workflow does not offer it at 'doctor'" in line for line in bad), bad
ok("and it refuses a template claiming a station or a capability nothing "
   "declared: one no scribe instrument may fill, and one the workflow does "
   "not offer at the station it inherits")

# And the gate RUNS all of it. Everything above asks templates.lint() directly,
# which proves the rule and not the wiring: deleting the one call in
# kernel/declarations.py left every check above passing. So this loads a bent
# bundle through declarations.load(), the way check.sh does, and asserts the
# bundle refuses to load at all. Found by mutation.
with tempfile.TemporaryDirectory() as tmp:
    home = pathlib.Path(tmp) / "bundles"
    (home / "phc").mkdir(parents=True)
    for src in (ROOT / "bundles" / "phc").iterdir():
        if src.is_file():
            (home / "phc" / src.name).write_text(src.read_text())
    bent = copy.deepcopy(MANIFEST)
    bent["templates"]["phc.op.followup"]["asks"] = ["history", "bp"]
    (home / "phc" / "bundle.yaml").write_text(yaml.safe_dump(bent, sort_keys=False))
    was = declarations.BUNDLES
    try:
        declarations.BUNDLES = home
        try:
            declarations.load("phc")
            raise AssertionError("a bent template declaration loaded")
        except declarations.DeclarationError as exc:
            assert "asks 'bp'" in str(exc), str(exc)
    finally:
        declarations.BUNDLES = was
assert declarations.load("phc").manifest.id == "phc", "the real bundle still loads"
ok("the gate runs the template lint rather than only owning it: a bent "
   "declaration makes kernel/declarations.py refuse to load the bundle")


# A required answer that goes nowhere is NOT a rule this module owns, and the
# reason is worth the paragraph: kernel/mapping.py already refuses an
# operation with a required question that no record stores and that nobody
# declared they were dropping, and it runs over a generated atom and its
# generated form exactly as over a hand written one. A second copy of that
# rule in kernel/templates.py could not be made to fail, because narrowing
# removes a question rather than orphaning it, so it was deleted. What is
# worth proving is that the rule REACHES a template, which is this.
fm, _ = parse_atom(ROOT / "catalogue" / "ops" / "phc.op.followup.md")
compiled, failures = mapping.compile_records(fm, validate.load(fm["input"]))
assert compiled and not failures, failures
orphaned = copy.deepcopy(fm)
orphaned["mapping"]["records"] = [r for r in orphaned["mapping"]["records"]
                                  if r["resource"] != "notes"]
orphaned["writes"] = [w for w in orphaned["writes"] if w != "notes"]
_, failures = mapping.compile_records(orphaned, validate.load(fm["input"]))
assert any("'assessment' is required and goes nowhere" in line
           for line in failures), failures
ok("a generated template's atom is held to the same mapping rule as a hand "
   "written one: a required answer with no record to go into is refused in "
   "kernel/mapping.py, which is the one place that rule lives")

# A binding to a value set that does not exist. The bindings are the base's,
# so this is reached by asking the lint about a form whose question binds to
# an uncached slug, which is what it would be if somebody bound one.
with tempfile.TemporaryDirectory() as tmp:
    schema = copy.deepcopy(BASE_SCHEMA)
    group, = [q for q in schema["questions"] if q["link_id"] == "diagnosis"]
    group["questions"][0]["answer_value_set"] = "obstetric-code"
    bent = copy.deepcopy(MANIFEST)
    atom = (ROOT / "catalogue" / "ops" / ("%s.md" % BASE)).read_text()
    ops_dir = pathlib.Path(tmp) / "ops"
    ops_dir.mkdir()
    (ops_dir / ("%s.md" % BASE)).write_text(
        atom.replace("input: phc.schema.consult-v1",
                     "input: phc.schema.bent-consult-v1"))
    bent_schema = ROOT / "questionnaires" / "phc.schema.bent-consult-v1.json"
    try:
        bent_schema.write_text(json.dumps(schema, indent=2) + "\n")
        bad = templates.lint(bent, ALL_OPS, DECLS, ops_dir)
        assert any("binds its answer to value set 'obstetric-code'" in line
                   for line in bad), bad
        assert any("may not bind to a value set this facility cannot check "
                   "offline" in line for line in bad), bad
    finally:
        bent_schema.unlink(missing_ok=True)
ok("and it refuses a template whose form binds an answer to a value set this "
   "facility cannot check offline, which would draw an empty dropdown")


# ---------------------------------------------------------------------------
# 9. No engine module types a clinical word.
# ---------------------------------------------------------------------------

# `condition-code` only, and the reason is the one scripts/engine_code.py
# gives for its own exemptions. The clinical and verification status value
# sets are ordinary English words (active, resolved, confirmed, refuted), and
# "active" is also the status a CARE questionnaire carries, which this module
# copies from the base form. A check that failed on that would be renamed
# into silence within a week. What is left is every word that could only be
# in this file because somebody typed a diagnosis into the generator.
CLINICAL = ("condition-code",)
WORDS = sorted({code for slug in CLINICAL
                for code in terminology.LOCAL.concepts(slug)}
               | {c["display"] for slug in CLINICAL
                  for c in terminology.LOCAL.concepts(slug).values()})
assert len(WORDS) >= 6, len(WORDS)
sys.path.insert(0, str(ROOT / "scripts"))
from engine_code import engine_code                              # noqa: E402

live = engine_code(ROOT / "kernel" / "templates.py")
assert live.strip() and "\ndef\n" in live, "the stripper found no code"
typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
assert not typed, "kernel/templates.py types the clinical word(s) %r" % typed
# And no clinical question's own link_id either. The generator copies question
# objects by name from the base form, so a link_id it typed would be a
# question it had opinions about.
for link_id in sorted(BASE_BY):
    assert '"%s"' % link_id not in live and "'%s'" % link_id not in live, link_id
ok("the generator types no diagnosis and not one of the consultation's own "
   "question names: %d words and %d link ids" % (len(WORDS), len(BASE_BY)))

# ---------------------------------------------------------------------------
# 10. The gate runs every check there is.
# ---------------------------------------------------------------------------
#
# Found by mutation, and the hole was not this module's alone: deleting the
# line that runs this file from scripts/check.sh left the gate green with 549
# oks, and nothing anywhere said a check had gone missing. The same was true
# of all ten check scripts. One assertion closes it for nine of them.
#
# The tenth is this file, and that is a limit rather than an oversight: an
# assertion cannot notice that the file holding it was not run. Any one place
# this lived would have the same hole about itself. It lives here because
# this is the mutation that found it.
GATE = (ROOT / "scripts" / "check.sh").read_text()
SCRIPTS = sorted(p.name for p in (ROOT / "scripts").glob("check_*.py"))
MISSING = [name for name in SCRIPTS if name not in GATE]
assert not MISSING, "scripts/check.sh does not run %r, so those checks are " \
                    "written and never run" % MISSING
ok("every one of the %d check scripts in scripts/ is named in scripts/check.sh, "
   "so a check cannot be dropped from the gate in silence, this file aside"
   % len(SCRIPTS))

print("ok   the doctor's templates: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run, and the check that failed first is
# named, because a mutation that breaks parsing fails everything for the
# wrong reason.
# ---------------------------------------------------------------------------
#
# - have `narrow` keep a record whose answer the form no longer asks: the
#   antenatal template declares `writes: [encounter, notes, condition]` and
#   the build fails in kernel/mapping.py, because `per_row: diagnosis` names
#   a question its form does not have.
# - have `narrow` keep a note's full link list instead of narrowing it: the
#   follow up's note sources `examination`, which its form does not ask, and
#   section 6's "each template's note is the base's own note source narrowed"
#   fails.
# - have `questionnaire` rebuild a question instead of copying the base's:
#   section 2's "every question is the base's own question object" fails on
#   the first help sentence that differs.
# - drop the `required` override: section 2's second check fails, because the
#   NCD review's examination comes back optional.
# - have `drift` compare nothing: section 4's hand edit check fails.
# - have `atom` take the station from the declaration rather than the base:
#   there is nowhere in the declaration to put one, which is the point, and
#   section 3's CLINICAL_KEYS check is what would fail if somebody added one.
