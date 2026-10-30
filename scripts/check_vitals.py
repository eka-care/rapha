"""Run: python3 scripts/check_vitals.py

One vertical slice, every layer, no socket.

A nurse records a blood pressure. The reading validates against the
questionnaire, the coding validates against the value set its question binds
to, the guard allows it, the audit row is written before the write executes,
the rows land in the adapter, and the thread projects to an ABDM
DocumentBundle whose Observation carries a LOINC code and a UCUM unit.

This is the proof of the architecture rather than an assertion of it: every
layer named in docs/superpowers/plans/2026-10-31-application-architecture.md
is on the path below, and each one is checked for the thing only it can get
wrong.

  declarations   the questionnaire binds a code, the atom maps it to columns
  terminology    a code outside its value set cannot be stored, as a type
  validate       a reading outside physiological range refuses the write
  guard          capability, precondition, surface, audit before execute
  kernel         the mapping fans one payload out to one row per reading
  adapter        flat FHIR shaped rows, countable by code
  projection     a FHIR R4 Observation with a LOINC code and a UCUM unit
  state          the flags the workflow derives from what was stored

Mutations this is built to fail under are listed at the bottom of the file.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                 # noqa: E402
from catalogue import guard, vocab                           # noqa: E402
from kernel import declarations, fhir, mapping, proposals, state, terminology  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
WF = BUNDLE.workflow()
VITALS = BUNDLE.operations["phc.op.vitals-record"]
REGISTER = BUNDLE.operations["phc.op.patient-register"]
NURSE = set(vocab.for_bundle("phc").roles["nurse"])
A_NURSE = "user:meena"
NOW = "2026-10-31T09:14:00+00:00"

# What the nurse keys. One high reading, so the flag path is exercised too.
READING = {"systolic": 186, "diastolic": 112, "pulse": 92, "spo2": 97,
           "weight": 61.5, "temperature": 37.1}


def fresh():
    """A store with one registered patient on one open thread."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="A01", actor=A_NURSE)
    decision = proposals.commit(
        store, BUNDLE, "phc.op.patient-register", thread=thread,
        payload={"name": "Sunita Devi", "age": 34, "sex": "female",
                 "phone": "9876500000", "village": "Yadiki", "category": "general"},
        caps=NURSE, actor=A_NURSE)
    assert decision, decision.reason
    return store, thread


# ---------------------------------------------------------------------------
# 1. Declarations. The question binds a concept and the atom says which
#    columns it becomes. Neither is code.
# ---------------------------------------------------------------------------

from catalogue import validate                                # noqa: E402

SCHEMA = validate.load(VITALS["input"])
QUESTIONS = {q["link_id"]: q for q in validate.walk(SCHEMA["questions"])}

assert set(QUESTIONS) == set(READING), sorted(QUESTIONS)
for link_id, q in QUESTIONS.items():
    assert q.get("code"), "%s binds no concept" % link_id
    assert (q["styling_metadata"]["phc"].get("unit")), "%s declares no unit" % link_id
ok("every vitals question binds a concept and declares a unit")

(record,) = VITALS["mapping"]
columns = set(record["fields"])
assert {"code", "code_system", "code_display", "unit", "unit_system"} <= columns, columns
assert record["fields"]["code"] == {"question": "code"}, record["fields"]["code"]
assert any("actor" in s for s in record["fields"].values()), "no author column"
ok("the atom maps each reading to a code, its system, its display and its unit")

# ---------------------------------------------------------------------------
# 2. Terminology. The binding is a type, and it is held by the one producer.
# ---------------------------------------------------------------------------

compiled = {q["link_id"]: q for q in record["per_question"]}
assert set(compiled) == set(READING), sorted(compiled)
for link_id, q in compiled.items():
    assert terminology.LOCAL.validate(terminology.CODE_BINDING, q["code"]), q
    assert terminology.LOCAL.validate(terminology.UNIT_BINDING, q["unit"]), q
    assert q["code_system"] == "http://loinc.org", q
    assert q["unit_system"] == "http://unitsofmeasure.org", q
    assert q["code_display"], q
ok("every compiled reading carries facts its value set vouched for")

# The compiled mapping travels: it is served on /operations and
# web/src/structured.ts reads it, so web/src/messages.check.ts json.dumps the
# whole of it. A coding object here would be a 500 on the thread panel.
import json                                                   # noqa: E402

assert json.dumps(BUNDLE.operations), "the compiled mapping is not plain JSON"
ok("the compiled mapping is plain JSON, because the renderer is served it")

try:
    terminology.Coding("http://loinc.org", "8480-6", "Systolic", "observation-code")
except terminology.UnboundCoding:
    ok("a coding cannot be built around the value set check")
else:
    raise AssertionError("a Coding was built without passing a value set")

try:
    terminology.LOCAL.bound(terminology.CODE_BINDING, "29463-7000")
except terminology.UnboundCoding:
    ok("a code outside the bound value set cannot become a coding at all")
else:
    raise AssertionError("a code outside the value set was bound")

# The write path, not only the build. A compiled context carrying a code the
# value set does not hold makes no row at all: the facts arrive as strings
# because they have to travel, a string carries no proof, so the proof is
# re-established where the row is made. This is where invariant I1 bites.
forged = dict(compiled["systolic"], code="9999-9")
try:
    mapping.records({"mapping": [dict(record, per_question=[forged])]},
                    {"systolic": 140}, actor=A_NURSE)
except terminology.UnboundCoding as exc:
    assert "9999-9" in str(exc), exc
    ok("the write path refuses a code its value set does not hold, not only the build")
else:
    raise AssertionError("an unvalidated code reached a row")

# A good code with a missing system is the dangerous one, because nothing
# about it looks wrong: the validate call above passes, the row is written,
# and it is written without the system that makes the code resolvable. So the
# check nulls the fact and keeps the code valid.
missing = dict(compiled["systolic"], code_system=None)
assert terminology.LOCAL.validate(terminology.CODE_BINDING, missing["code"]), \
    "this check proves nothing unless the code itself is still good"
try:
    mapping.records({"mapping": [dict(record, per_question=[missing])]},
                    {"systolic": 140}, actor=A_NURSE)
except terminology.UnboundCoding:
    ok("a coding column that would land null stops the write instead")
else:
    raise AssertionError("a coding column landed null")

# And the build refuses it too, so it never gets that far in practice.
bad = dict(QUESTIONS["systolic"], code="9999-9")
try:
    mapping._compile_record(
        {"resource": "observation", "per_question": ["systolic"],
         "fields": dict(record["fields"])}, {"systolic": bad})
except terminology.UnboundCoding as exc:
    assert "9999-9" in str(exc) and terminology.CODE_BINDING in str(exc), exc
    ok("a question declaring a code outside its value set fails the build, naming both")
else:
    raise AssertionError("a bad binding compiled")

# ---------------------------------------------------------------------------
# 3. The guard. Capability, precondition, range, and audit before execute.
# ---------------------------------------------------------------------------

store, thread = fresh()
flags = state.flags(store, thread, WF)
assert "registered" in flags and "vitals.recorded" not in flags, sorted(flags)
assert state.station(WF, flags) == "nurse", state.station(WF, flags)
ok("a registered patient with no readings stands at the nurse")

refused = proposals.commit(store, BUNDLE, "phc.op.vitals-record", thread=thread,
                           payload=dict(READING, systolic=400), caps=NURSE,
                           actor=A_NURSE)
assert not refused and "outside 70 to 250" in refused.reason, refused.reason
assert not store.select("observation", thread=thread, where={}, fields=["id"],
                        limit=5), "a refused reading wrote a row"
ok("a reading outside physiological range refuses the write: %s"
   % refused.reason.split(".")[0])

without = proposals.commit(store, BUNDLE, "phc.op.vitals-record", thread=thread,
                           payload=READING, caps={"patient.find"}, actor=A_NURSE)
assert not without and "vitals.record" in without.reason, without.reason
ok("an account without vitals.record is refused: %s" % without.reason)

machine, proposal = proposals.propose(
    store, BUNDLE, "phc.op.vitals-record", thread=thread, payload=READING,
    caps=NURSE, actor="device:cuff", surface=guard.MCP)
assert machine and machine.reason == "proposed" and proposal.status == "pending"
assert not store.select("observation", thread=thread, where={}, fields=["id"],
                        limit=5), "a proposal wrote a row"
ok("a reading from a machine surface is a proposal and writes nothing")

# The audit row is written BEFORE the write executes. The order is only
# observable when the write fails, which is the whole reason it matters: if
# the rows went first, a write that blew up half way would leave a thread
# with no record that anybody tried. So this hands the kernel a store whose
# write raises and asserts the audit line survives.


class Breaks:
    """A store that records everything and refuses to write a clinical row."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def write(self, *a, **kw):
        raise RuntimeError("the disk went away")


broken = Breaks(store)
try:
    proposals.commit(broken, BUNDLE, "phc.op.vitals-record", thread=thread,
                     payload=READING, caps=NURSE, actor=A_NURSE)
except RuntimeError:
    pass
else:
    raise AssertionError("a store that cannot write reported success")
tried = [r for r in store.audit(thread)
         if r.operation == "phc.op.vitals-record" and r.outcome == "allowed"]
assert len(tried) == 1, [r.outcome for r in store.audit(thread)]
assert not store.select("observation", thread=thread, where={}, fields=["id"],
                        limit=5), "a row survived a failed write"
ok("a write that fails still leaves its audit line: the audit goes first")

before = len(store.audit(thread))
allowed = proposals.commit(store, BUNDLE, "phc.op.vitals-record", thread=thread,
                           payload=READING, caps=NURSE, actor=A_NURSE)
assert allowed, allowed.reason
trail = store.audit(thread)
assert len(trail) == before + 1, trail
last = trail[-1]
assert last.operation == "phc.op.vitals-record" and last.outcome == "allowed"
assert last.actor == A_NURSE and last.surface == guard.RENDERED
assert last.payload == READING, last.payload
# The failed write above left an "allowed" line of its own, which is the
# point of it: what was attempted is on the record whether or not it landed.
assert [r.outcome.split(":")[0] for r in trail] == \
    ["allowed", "denied", "denied", "proposed", "allowed", "allowed"], \
    [r.outcome for r in trail]
ok("the audit trail is oldest first and holds both refusals and the machine's "
   "proposal, not only what worked")

# ---------------------------------------------------------------------------
# 4. The adapter. One row per reading, flat and countable by code.
# ---------------------------------------------------------------------------

rows = store.select("observation", thread=thread, where={"category": "vital-signs"},
                    fields=["code", "code_system", "code_display", "value", "unit",
                            "unit_system", "created_by"], limit=20)
assert len(rows) == len(READING), rows
by_code = {r["code"]: r for r in rows}
assert set(by_code) == {"8480-6", "8462-4", "8867-4", "59408-5", "29463-7", "8310-5"}, \
    sorted(by_code)
systolic = by_code["8480-6"]
assert systolic["value"] == "186" and systolic["unit"] == "mm[Hg]", systolic
assert systolic["code_system"] == "http://loinc.org", systolic
assert systolic["unit_system"] == "http://unitsofmeasure.org", systolic
assert systolic["code_display"] == "Systolic blood pressure", systolic
assert all(r["created_by"] == A_NURSE for r in rows), "a row with no author"
ok("six readings are six flat rows, each with its LOINC code, system and author")

assert store.count("observation", thread=thread, where={"code": "8480-6"}) == 1
assert store.count("observation", thread=None, where={"code": "8480-6"}) == 1
ok("a row is countable by its code, which is what a district count needs")

# ---------------------------------------------------------------------------
# 5. State. The flags the workflow derives, and the flag the reading raised.
# ---------------------------------------------------------------------------

flags = state.flags(store, thread, WF)
assert "vitals.recorded" in flags, sorted(flags)
assert "vitals.flagged" in flags, "186 over 112 is outside the critical band"
assert state.station(WF, flags) == "doctor", state.station(WF, flags)
ok("the readings move the thread to the doctor and raise vitals.flagged")

second = proposals.commit(store, BUNDLE, "phc.op.vitals-record", thread=thread,
                          payload=READING, caps=NURSE, actor=A_NURSE)
assert not second and "Already vitals recorded" in second.reason, second.reason
ok("recording them again is refused by the precondition: %s" % second.reason)

# ---------------------------------------------------------------------------
# 6. The projection. A FHIR R4 Observation with a LOINC code and a UCUM unit.
# ---------------------------------------------------------------------------

doc = fhir.document(store, thread, profile="WellnessRecord",
                    sections_wanted={"VitalSigns": [
                        ("observation", {"category": "vital-signs"})]},
                    now=NOW)
assert doc["type"] == "document" and doc["resourceType"] == "Bundle"
assert doc["meta"]["profile"] == [fhir.DOCUMENT_BUNDLE], doc["meta"]
kinds = [e["resource"]["resourceType"] for e in doc["entry"]]
assert kinds[0] == "Composition", kinds
assert kinds.count("Observation") == len(READING), kinds
assert "Patient" in kinds and "Encounter" in kinds and "Practitioner" in kinds, kinds
ok("the thread projects to a document bundle: %s"
   % ", ".join("%d %s" % (kinds.count(k), k) for k in sorted(set(kinds))))

comp = doc["entry"][0]["resource"]
assert comp["meta"]["profile"] == ["%s/WellnessRecord" % fhir.NRCES], comp["meta"]
assert doc["meta"].get("versionId"), "DocumentBundle requires Bundle.meta.versionId"
# Read from the profile table rather than typed here, so a profile that
# declares more required paths checks more of them. The tier 1 ABDM validator
# found two of these absent when this was first written: Composition.type and
# Bundle.meta.versionId. Both are now emitted and both are asserted.
required = fhir.PROFILES["WellnessRecord"]["required"]
assert len(required) >= 7, required
for path in required:
    assert comp.get(path), "Composition.%s is required and absent" % path
assert comp["type"].get("text"), comp["type"]
assert comp["subject"]["reference"].startswith("urn:uuid:")
(section,) = comp["section"]
assert section["title"] == "Vital signs" and len(section["entry"]) == len(READING)
ok("its Composition carries every element the NRCeS profile requires")

refs = {e["fullUrl"]: e["resource"] for e in doc["entry"]}
assert set(r["reference"] for r in section["entry"]) <= set(refs), "a dangling section entry"
assert comp["subject"]["reference"] in refs and comp["encounter"]["reference"] in refs
assert all(a["reference"] in refs for a in comp["author"]), comp["author"]
ok("every reference in the document resolves inside the document")

obs = next(e["resource"] for e in doc["entry"]
           if e["resource"]["resourceType"] == "Observation"
           and e["resource"]["code"]["coding"][0]["code"] == "8480-6")
assert obs["status"] == "final", obs
assert obs["code"]["coding"] == [{"system": "http://loinc.org", "code": "8480-6",
                                  "display": "Systolic blood pressure"}], obs["code"]
assert obs["valueQuantity"] == {"value": 186, "unit": "mm[Hg]",
                                "system": "http://unitsofmeasure.org",
                                "code": "mm[Hg]"}, obs["valueQuantity"]
assert isinstance(obs["valueQuantity"]["value"], int), "a FHIR decimal is not a string"
assert obs["category"][0]["coding"][0] == {"system": fhir.HL7_CATEGORY,
                                           "code": "vital-signs"}, obs["category"]
assert obs["subject"]["reference"] == comp["subject"]["reference"]
ok("the blood pressure is a LOINC coded Observation with a UCUM quantity")

again = fhir.document(store, thread, profile="WellnessRecord",
                      sections_wanted={"VitalSigns": [
                          ("observation", {"category": "vital-signs"})]},
                      now=NOW)
assert again == doc, "the same rows projected to a different document"
ok("the same rows project to the same document, so ABDM sees one visit once")

try:
    fhir.document(store, thread, profile="WellnessRecord",
                  sections_wanted={"ChiefComplaints": []}, now=NOW)
except KeyError as exc:
    assert "ChiefComplaints" in str(exc), exc
    ok("a section the profile does not declare is refused, not emitted")
else:
    raise AssertionError("an undeclared section was emitted")

empty, empty_thread = fresh()
try:
    fhir.document(empty, empty_thread, profile="WellnessRecord",
                  sections_wanted={"VitalSigns": [
                      ("observation", {"category": "vital-signs"})]}, now=NOW)
except KeyError as exc:
    assert "nothing to put in" in str(exc), exc
    ok("a visit with nothing recorded publishes no document rather than an empty one")
else:
    raise AssertionError("an empty document was published")

# ---------------------------------------------------------------------------
# 7. The rule the whole layering exists for: no clinical word in the engine.
# ---------------------------------------------------------------------------

# Derived from the declarations, so this grows when a bundle declares more:
# the same self-growing shape web/src/ui.check.ts uses for the renderer.
WORDS = sorted({q["code"] for q in QUESTIONS.values()}
               | {q["styling_metadata"]["phc"]["unit"] for q in QUESTIONS.values()}
               | set(QUESTIONS))
assert len(WORDS) >= 12, WORDS


def engine_code(path):
    """A module's live code: no comments, no docstrings, no self-test.

    Three exemptions, each for the reason scripts/check_khoj.py exempts
    itself. A comment or a docstring explaining a rule has to be able to name
    what breaking it would look like, which is why `if code == "..."` appears
    in kernel/fhir.py's docstring as the thing it must never contain. And a
    `demo()` has to name a concrete code and a concrete unit or it is not a
    test of anything.

    Comments and docstrings are removed with tokenize rather than by scanning
    for a `#`, so a `#` inside a string cannot blank out the rest of a live
    line. A docstring is a STRING token standing alone as a statement, which
    is the one shape a comment-like string takes. The self-test is everything
    from `def demo(`, and the marker is asserted by the caller so that
    renaming demo() cannot quietly exempt a module.
    """
    import io
    import tokenize

    text = path.read_text()
    marker = "\ndef demo("
    live = text.split(marker)[0] if marker in text else text
    # A string that STARTS a statement is a docstring; one that follows an
    # operator or a name is a value. So `previous` tracks every token,
    # trivia included, which is the whole distinction.
    STATEMENT_START = (tokenize.NEWLINE, tokenize.NL, tokenize.INDENT,
                       tokenize.DEDENT, tokenize.ENCODING)
    out, previous = [], tokenize.NEWLINE
    for tok in tokenize.generate_tokens(io.StringIO(live).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and previous in STATEMENT_START:
            previous = tok.type
            continue                      # a docstring, not a value
        previous = tok.type
        out.append(tok.string)
    return "\n".join(out)


for module in ("kernel/fhir.py", "kernel/mapping.py", "kernel/state.py",
               "kernel/proposals.py", "kernel/views.py", "catalogue/guard.py",
               "adapters/local/store.py"):
    path = ROOT / module
    live = engine_code(path)
    assert live.strip() and "\ndef\n" in live, module
    assert "\"\"\"" not in live, "%s: a docstring survived the strip" % module
    typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
    assert not typed, "%s types the clinical word(s) %r" % (module, typed)
ok("no engine module types a reading's name, its LOINC code or its unit")

print("ok   vitals slice: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# Mutations this is built to fail under. Each was run.
#
#   questionnaires/phc.schema.vitals-v1.json   change a question's code to one
#       the value set does not hold  ->  the build fails, naming code and set
#   terminology/observation-code.json          remove 8480-6
#       ->  the build fails before any check here runs
#   kernel/terminology.py                      let Coding be built without the
#       gate  ->  the two gate checks above fail
#   kernel/mapping.py                          return context.get(arg) for a
#       coding fact instead of reading the Coding
#       ->  the write path check fails and the rows lose their systems
#   kernel/fhir.py                             drop `system` from the quantity
#       ->  the UCUM assertion fails
#   kernel/fhir.py                             use uuid4 instead of uuid5
#       ->  the same-document check fails
#   kernel/proposals.py                        write before auditing
#       ->  the audit order check fails
#   catalogue/ops/phc.op.vitals-record.md      drop the code_system column
#       ->  the atom check fails, then the adapter and projection checks
# ---------------------------------------------------------------------------
