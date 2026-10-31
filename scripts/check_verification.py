"""Run: python3 scripts/check_verification.py

How sure anybody was, stored and published on every coded thing.

Why this file exists
--------------------
A code reaches this product three ways: a person picks it from a list, a
codifier suggests it and a person accepts it, or it arrives inside a bundle
somebody else's model produced. Those carry different amounts of certainty,
and the record leaves this building under a patient's ABHA number to
clinicians who cannot ask us what it meant. So certainty has to be a stored,
projected field rather than an assumption, and it has to be on every resource
this build emits rather than only on a diagnosis, which is where the module
before this one left it.

What is proved here, in order:

  1. every literal an operation can store into a FHIR `code` element is a code
     of the published list R4 binds that element to
  2. no projection chooses a clinical certainty for itself, and the one that
     chooses a status chooses the DOCUMENT's
  3. invariant I6, resource by resource, including where it is not kept
  4. the four honest cases, each on its own: a refuted finding, an unconfirmed
     guess, a historical finding, and a family history finding
  5. nothing here can write `confirmed`

Where I6 is NOT kept, and why. Stated here rather than in a commit message,
because an invariant with an unwritten exception is an invariant nobody can
rely on.

  Condition        KEPT. `verificationStatus` is a required clinician answer
                   bound to FHIR's own published list, and `clinicalStatus`
                   plus an onset carry the historical case.
  Observation      NOT KEPT, and not keepable. R4's Observation has no
                   verificationStatus, no clinicalStatus and no negation
                   element. A negated, hypothetical, family or historical
                   finding is a Condition in FHIR's own model, so the honest
                   behaviour is to refuse an Observation row that carries a
                   certainty rather than publish it without one. Section 3
                   below is that refusal.
  MedicationRequest
                   NOT APPLICABLE, and nothing was invented to make it look
                   applicable. A medicine is not a finding. R4 carries a
                   request's certainty in `intent`, which distinguishes a
                   `proposal`, a suggestion from someone with no authority to
                   make it happen, from an `order`, a demand and an
                   authorisation. That element is already stored. R4's own
                   negation for a request is `doNotPerform`, which this build
                   does not write because no form asks the question; naming it
                   here is not the same as having it.
  DocumentReference
                   NOT APPLICABLE. A narrative attachment asserts nothing
                   coded: the doubt is in the clinician's own words, which is
                   the whole reason the fallback publishes the words.
  FamilyMemberHistory
                   ABSENT. A family history finding cannot be recorded by this
                   build at all, and section 4 proves that it is refused
                   rather than stored as the patient's own condition. The
                   reasons are in section 4.

The three provenance routes, and why only one of them is in the record
----------------------------------------------------------------------
Asked for; not built; the reasoning and the tripwire are in section 6.

Validated, and what that does and does not mean
-----------------------------------------------
Two of the documents this file builds were run through the ABDM catalogue's
tier one structural validator on 2026-10-31, against the pinned NRCeS
profiles (ndhm.in 6.5.0), and both came back with no findings:

  the OPConsultRecord of section 4, carrying one refuted, one unconfirmed and
    one resolved Condition;
  the WellnessRecord `scripts/check_lab.py` builds, whose Observation now
    carries `status: preliminary` where it used to carry `final`.

That is structural. It does not validate terminology, and the official HL7
validator has not been run on either. Both are said here rather than in a
commit message, because a validator result nobody can find is the same as
none.
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.local.store import TABLES, SqliteStore            # noqa: E402
from catalogue import validate, vocab                           # noqa: E402
from engine_code import engine_code                             # noqa: E402
from kernel import declarations, fhir, proposals, terminology    # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLES = ("phc", "lab")
NOW = "2026-10-31T10:05:00+00:00"
A_DOCTOR = "user:ravi"


# ---------------------------------------------------------------------------
# 1. A status literal is a code, and a code is checked.
#
#    A FHIR `code` element is a bare token from a fixed list with no system
#    beside it, so none of the three binding forms in kernel/terminology.py
#    reaches one: a mapping's `{const: active}` is a literal somebody typed.
#    kernel/fhir.STATUS_BINDING says which stored column is copied into which
#    element, and this is what holds each literal against the cached list.
# ---------------------------------------------------------------------------

def declared_literals():
    """Every value an operation can store into a bound status column.

    `{const: x}` gives one value. `{answer: q}` gives whatever the question's
    own choices are, which is why the answer form is read as the set of its
    declared options rather than passed over: `lab.op.result-verify` stores
    `{answer: decision}` into a report's status, and if that column were ever
    bound, `verified` and `rejected` would both have to be R4 codes.
    """
    out = []
    for bundle_id in BUNDLES:
        bundle = declarations.load(bundle_id)
        for op_id, op in sorted(bundle.operations.items()):
            # `mapping` on a compiled operation IS the record list, and
            # `fields` beside it is the FORM's questions. Read from the
            # compiled form rather than from the atom, because the compiled
            # form is what every surface is served.
            records = op.get("mapping") or []
            schema = None
            for record in records:
                resource = record.get("resource")
                for column, source in (record.get("fields") or {}).items():
                    slug = fhir.STATUS_BINDING.get((resource, column))
                    if not slug:
                        continue
                    kind, arg = next(iter(source.items()))
                    if kind == "const":
                        out.append((op_id, resource, column, slug, str(arg)))
                    elif kind == "answer":
                        if schema is None:
                            schema = validate.load(op["input"])
                        for value in _options(schema, arg):
                            out.append((op_id, resource, column, slug, value))
                    else:
                        raise AssertionError(
                            "%s stores %s.%s from %r, which this check cannot "
                            "read. A bound status column takes a const or an "
                            "answer; anything else has to be read here before "
                            "it can be held against the list."
                            % (op_id, resource, column, kind))
    return out


def _options(schema, link_id):
    for question in _walk(schema.get("questions") or []):
        if question["link_id"] != link_id:
            continue
        return [str(o.get("value")) for o in question.get("answer_option") or []]
    raise AssertionError("no question %r on %s" % (link_id, schema["slug"]))


def _walk(questions):
    for q in questions:
        yield q
        for inner in _walk(q.get("questions") or []):
            yield inner


LITERALS = declared_literals()
assert LITERALS, "no operation stores anything into a bound status column, " \
                 "which would mean the binding table is dead"
for op_id, resource, column, slug, value in LITERALS:
    assert terminology.LOCAL.validate(slug, value), \
        "%s stores %r into %s.%s, and %r is not a code of %s. R4 would " \
        "reject it and nothing before this line was looking." \
        % (op_id, value, resource, column, value, slug)
ok("every status literal %d operations store is a code of the published list "
   "R4 binds that element to" % len({l[0] for l in LITERALS}))

# The systems are not interchangeable and were read off the server's own
# expansion rather than written from the pattern the others follow.
assert terminology.LOCAL.concepts("observation-status") and \
    json.loads((ROOT / "terminology" / "observation-status.json").read_text())["system"] \
    == "http://hl7.org/fhir/observation-status"
assert json.loads((ROOT / "terminology" / "medicationrequest-intent.json").read_text())["system"] \
    == "http://hl7.org/fhir/CodeSystem/medicationrequest-intent"
ok("the two status code systems are in different namespaces, and each cached "
   "file carries the one the server returned")

# And the value a laboratory result is actually stored with is R4's own word
# for a value that has been recorded and not yet verified.
LAB = [l for l in LITERALS if l[1] == "observation" and l[3] == "observation-status"]
assert {l[4] for l in LAB} == {"preliminary", "final"}, LAB
assert {l[4] for l in LAB if "result-enter" in l[0]} == {"preliminary"}, LAB
assert {l[4] for l in LAB if "vitals-record" in l[0]} == {"final"}, LAB
ok("a keyed laboratory value is stored preliminary and a nurse's vital sign "
   "final, and the projection copies whichever it finds")


# ---------------------------------------------------------------------------
# 2. No projection chooses a clinical certainty.
#
#    The rule, and the line it draws: a status describing the DOCUMENT this
#    file is building is this file's own fact, because it is building it, now,
#    finished. A status describing somebody else's clinical value is the row's,
#    because this file did not measure it. `observation()` broke that line for
#    as long as it existed.
# ---------------------------------------------------------------------------

# The FHIR elements a projection may still write a literal into, because each
# describes the document rather than the thing it reports. Both are on the
# narrative attachment: `status` is a DocumentReference's availability
# (current, superseded, entered-in-error) and `docStatus` is the document's
# own state.
DOCUMENT_LEVEL = {("notes", "status"), ("notes", "docStatus")}

# Which element names are a status at all. `intent` is here because R4 carries
# a request's certainty there and nowhere else.
STATUS_ELEMENTS = ("status", "docStatus", "intent")

PROJECTED = dict(fhir.PROJECTIONS, encounter=fhir.encounter)
TREE = ast.parse((ROOT / "kernel" / "fhir.py").read_text())
BODIES = {node.name: node for node in ast.walk(TREE)
          if isinstance(node, ast.FunctionDef)}


def _is_status(name):
    return name in STATUS_ELEMENTS or name.endswith("Status") \
        or name.endswith("status")


def written(function):
    """Every FHIR element this function writes a status into, and how.

    Read off the syntax tree rather than off the text, and that is not a
    stylistic choice. This was first written against the stripped live code
    from scripts/engine_code.py, and it caught nothing: that stripper removes
    a string that begins a statement, which in a dict written over several
    lines is every KEY. So `"status": "final"` came through as `: "final"` and
    the rule was comparing a pattern that could not occur. Found by mutation,
    which is the only reason it is not still true.
    """
    out = []
    for node in ast.walk(BODIES[function.__name__]):
        if isinstance(node, ast.Dict):
            pairs = zip(node.keys, node.values)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Subscript):
            pairs = [(node.targets[0].slice, node.value)]
        else:
            continue
        for key, value in pairs:
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            if not _is_status(key.value):
                continue
            out.append((key.value, value))
    return out


def reads(function):
    """Every row column this function reads: `row.get("x")` and `row["x"]`."""
    out = set()
    for node in ast.walk(BODIES[function.__name__]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "get" \
                and isinstance(node.func.value, ast.Name) \
                and node.func.value.id == "row" and node.args \
                and isinstance(node.args[0], ast.Constant):
            out.add(node.args[0].value)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) \
                and node.value.id == "row" \
                and isinstance(node.slice, ast.Constant):
            out.add(node.slice.value)
    return {c for c in out if isinstance(c, str)}


def fallbacks(node):
    """Every string literal in an expression that is not a call argument.

    The distinction matters: in `row.get("status") or "unknown"`, `"status"` is
    the name of a column and `"unknown"` is a value this file chose when the
    column is empty. Only the second is a fallback, so the walk stops at a
    call and at a subscript rather than reaching into either: `row["intent"]`
    names a column too.
    """
    if isinstance(node, (ast.Call, ast.Subscript)):
        return []
    if isinstance(node, ast.Constant):
        return [node.value] if isinstance(node.value, str) else []
    out = []
    for child in ast.iter_child_nodes(node):
        out += fallbacks(child)
    return out


seen = 0
for resource, project in sorted(PROJECTED.items()):
    for element, value in written(project):
        seen += 1
        if isinstance(value, ast.Constant):
            assert (resource, element) in DOCUMENT_LEVEL, \
                "%s() writes %s = %r as a literal. A status describing " \
                "somebody else's clinical value is the row's; only a status " \
                "describing this document is this file's." \
                % (project.__name__, element, value.value)
            continue
        if (resource, element) in fhir.CODED_STATUS:
            # A CodeableConcept status, which is an ANSWER a clinician gave
            # and was resolved against a value set at write time by the one
            # validating constructor of a Coding. The evidence is the code
            # system column beside the code: a coding with no system is not
            # storable, so a `_system` sibling means the answer went through
            # kernel/terminology.py rather than being typed.
            column = fhir.CODED_STATUS[(resource, element)]
            assert column in TABLES[resource], (resource, column)
            assert "%s_system" % column in TABLES[resource], \
                "%s.%s carries no code system column, so nothing proves its " \
                "code came out of a value set" % (resource, column)
            continue
        # Not a literal and not a coded answer, so it is a bare FHIR code
        # copied from the row, and the column has to be bound or translated.
        assert (resource, element) in fhir.STATUS_BINDING \
            or (resource, element) in fhir.TRANSLATED_STATUS, \
            "%s() fills %s from the row with no value set bound to it, so " \
            "nothing checks what it holds." % (project.__name__, element)
        # And any literal INSIDE that expression is a fallback the projection
        # chose, so it is held against the same list.
        slug = fhir.STATUS_BINDING.get((resource, element))
        if slug:
            for literal in fallbacks(value):
                assert terminology.LOCAL.validate(slug, literal), \
                    "%s() falls back to %r for %s, which is not a code of %s" \
                    % (project.__name__, literal, element, slug)
assert seen >= 5, seen
ok("none of the %d status elements the %d projections write is a clinical "
   "literal, and every one filled from a row is bound to a published list"
   % (seen, len(PROJECTED)))

# The other direction: a status column a projection READS must be bound too,
# so a new column cannot be copied into FHIR without a list behind it.
for resource, project in sorted(PROJECTED.items()):
    for column in sorted(reads(project)):
        if not _is_status(column) and column != "intent":
            continue
        if (resource, "%sStatus" % column.split("_")[0]) in fhir.CODED_STATUS:
            continue        # a coded answer; checked above by its system column
        assert (resource, column) in fhir.STATUS_BINDING \
            or (resource, column) in fhir.TRANSLATED_STATUS, \
            "%s() reads %s.%s with no value set bound to it. Add it to " \
            "STATUS_BINDING, or to TRANSLATED_STATUS if the projection " \
            "translates it rather than copying it." \
            % (project.__name__, resource, column)
ok("every status column a projection reads is either bound to a published "
   "list or declared as one the projection translates")

# Every column the binding table names is a real column of a real table, so a
# renamed column cannot leave a binding pointing at nothing.
for (resource, column) in sorted(fhir.STATUS_BINDING) + sorted(fhir.TRANSLATED_STATUS):
    assert resource in TABLES, resource
    assert column in TABLES[resource], "%s has no column %r" % (resource, column)
    if (resource, column) in fhir.STATUS_BINDING:
        assert fhir.STATUS_BINDING[(resource, column)] in terminology.LOCAL.cached()
ok("every bound status column exists on its table and names a cached list")


# ---------------------------------------------------------------------------
# 3. I6 on an Observation: not kept, not keepable, and refused rather than
#    quietly dropped.
# ---------------------------------------------------------------------------

VITAL = {"id": "o1", "category": "vital-signs", "code": "8480-6",
         "code_system": fhir.LOINC, "value": "140", "unit": "mm[Hg]",
         "unit_system": fhir.UCUM, "status": "final"}

obs = fhir.observation(VITAL, subject="urn:uuid:p", encounter="urn:uuid:e")
assert obs["status"] == "final", obs
assert "verificationStatus" not in obs and "clinicalStatus" not in obs, obs

try:
    fhir.observation(dict(VITAL, status=""), subject="urn:uuid:p",
                     encounter="urn:uuid:e")
except KeyError:
    pass
else:
    raise AssertionError("an observation with no status was given one at the "
                         "projection, which is where the defect was")
ok("an observation row with no status is refused: R4 requires the element and "
   "the projection may not decide how settled a measurement is")

try:
    fhir.observation(dict(VITAL, verification_status="refuted"),
                     subject="urn:uuid:p", encounter="urn:uuid:e")
except KeyError as refusal:
    assert "drop the doubt and keep the value" in str(refusal), refusal
else:
    raise AssertionError(
        "a refuted finding was published as an Observation, which drops the "
        "doubt and keeps the value. That is invariant I6 inverted.")
ok("an observation carrying a certainty is refused, because R4's Observation "
   "has nowhere to put it and a finding whose certainty matters is a Condition")

# And the table has no such column, so the refusal above is a guard against a
# future row rather than a dead branch over a column that exists.
assert "verification_status" not in TABLES["observation"], TABLES["observation"]
assert "verification_status" in TABLES["condition"], TABLES["condition"]
ok("certainty is a column on a condition and not on an observation, which is "
   "where R4 puts it and where it stays")


# ---------------------------------------------------------------------------
# 4. The four honest cases, each on its own, end to end.
# ---------------------------------------------------------------------------

BUNDLE = declarations.load("phc")
CAPS = set(vocab.for_bundle("phc").roles["mo"]) \
    | set(vocab.for_bundle("phc").roles["frontdesk"]) \
    | set(vocab.for_bundle("phc").roles["nurse"])

# Three rows, three different amounts of certainty, one consultation. Every
# code is one the value set already holds: nothing here is recalled.
DIAGNOSES = [
    # The patient denied it. Recorded, and not asserted.
    {"condition": "297142003", "clinical_status": "active",
     "verification_status": "refuted"},
    # A guess, and it says so.
    {"condition": "44054006", "clinical_status": "active",
     "verification_status": "unconfirmed"},
    # Over and done with, with the date it started.
    {"condition": "46635009", "clinical_status": "resolved",
     "verification_status": "confirmed", "onset": "2019-04-01"},
]

store = SqliteStore(":memory:")
thread = store.open_thread(token="C01", actor=A_DOCTOR)
assert proposals.commit(store, BUNDLE, "phc.op.patient-register", thread=thread,
                        payload={"name": "Sunita Devi", "age": 34,
                                 "sex": "female", "phone": "9876500000",
                                 "village": "Yadiki", "category": "general"},
                        caps=CAPS, actor=A_DOCTOR)
decision = proposals.commit(
    store, BUNDLE, "phc.op.consult-document", thread=thread,
    payload={"assessment": "Three findings, three different certainties.",
             "diagnosis": DIAGNOSES}, caps=CAPS, actor=A_DOCTOR)
assert decision, decision.reason

# The placement is the bundle's declaration. It was typed here, and typed
# differently in scripts/check_codification.py: a diagnosis went under Chief
# complaints in one and the note under Medical History, which is one visit
# filed two ways by two files that both looked right.
doc = fhir.document(store, thread, now=NOW, **BUNDLE.documents["consultation"])
BY_CODE = {e["resource"]["code"]["coding"][0]["code"]: e["resource"]
           for e in doc["entry"] if e["resource"]["resourceType"] == "Condition"}
assert len(BY_CODE) == 3, sorted(BY_CODE)

VER = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
CLIN = "http://terminology.hl7.org/CodeSystem/condition-clinical"


def status_of(resource, element, system):
    coding = resource[element]["coding"]
    assert len(coding) == 1 and coding[0]["system"] == system, coding
    return coding[0]["code"]


# (a) A refuted finding. Published, with the denial on it.
denied = BY_CODE["297142003"]
assert status_of(denied, "verificationStatus", VER) == "refuted", denied
assert denied["code"]["coding"][0]["system"] == fhir.SNOMED, denied
assert "refuted" in json.dumps(denied), denied
ok("a finding the patient denied is published as a Condition with "
   "verificationStatus refuted: recorded, and not asserted")

# (b) An unconfirmed guess. Not dropped, and not promoted.
guess = BY_CODE["44054006"]
assert status_of(guess, "verificationStatus", VER) == "unconfirmed", guess
ok("a guess is published as unconfirmed, so a clinician reading the record in "
   "another facility is told it is a guess")

# (c) A historical finding. Resolved, with the date it started.
past = BY_CODE["46635009"]
assert status_of(past, "clinicalStatus", CLIN) == "resolved", past
assert status_of(past, "verificationStatus", VER) == "confirmed", past
assert past["onsetDateTime"] == "2019-04-01", past
ok("a past illness is published as resolved with its onset, which is how a "
   "historical finding travels without reading as a current one")

# The three are told apart in the published document, which is the only place
# it matters: a reader who cannot tell them apart has three diagnoses.
assert len({status_of(c, "verificationStatus", VER) for c in BY_CODE.values()}) == 3
ok("the three certainties are three different codes in one document, not one "
   "code and two that round to it")

# (d) A family history finding. There is nowhere for it to go, and the build
#     refuses it rather than storing it as the patient's own.
#
#     Three reasons, each checked, because any one of them alone would look
#     like an oversight to fix rather than a wall:
#
#     - FHIR's own home for it is FamilyMemberHistory, which carries the
#       relationship. Condition has no element naming a family member, so a
#       family history stored as a Condition is a condition OF THE PATIENT.
#     - the OPConsultRecord profile does declare a FamilyHistory section, and
#       NRCeS publishes no code for that slice and no example populating it,
#       so kernel/fhir.py declares it nowhere and `document()` refuses it.
#     - no "family history of" concept is in the condition value set, so one
#       could not be coded even if there were a section for it.
assert "FamilyMemberHistory" not in fhir.RESOURCE_TYPE.values(), fhir.RESOURCE_TYPE
assert "family_member_history" not in TABLES, sorted(TABLES)
try:
    fhir.document(store, thread, profile="OPConsultRecord",
                  sections_wanted={"FamilyHistory": [("condition", {})]},
                  now=NOW)
except KeyError as refusal:
    assert "FamilyHistory" in str(refusal), refusal
else:
    raise AssertionError(
        "a family history section was published, and every resource this "
        "build can put in one asserts the finding of the PATIENT")
FAMILY = [code for code, concept in terminology.LOCAL.concepts("condition-code").items()
          if "family" in (concept.get("display") or "").lower()
          or "family" in (concept.get("fully_specified_name") or "").lower()]
assert FAMILY == [], FAMILY
ok("a family history finding has nowhere to go and is refused on all three: "
   "no resource, no section, no concept. It is never stored as the patient's")


# ---------------------------------------------------------------------------
# 5. Nothing here writes `confirmed`.
#
#    The machine never confirms. That is the owner's position and it is also
#    the only reason the three sections above mean anything: a `refuted` that
#    something downstream can promote is not a refusal.
# ---------------------------------------------------------------------------

# Every code of the verification list, so the rule is held against the whole
# of what a certainty can be rather than against the one word that is
# dangerous today.
CERTAINTIES = sorted(terminology.LOCAL.concepts("condition-verification-status"))
assert "confirmed" in CERTAINTIES and "refuted" in CERTAINTIES, CERTAINTIES

# The modules that turn an answer into a row and a row into a resource. The
# kernel's proposal layer is deliberately NOT here, and the reason is a word
# collision that has to be named or this rule reads as weaker than it is:
# `confirmed` is also the status of a PROPOSAL, which is the kernel's own tick
# vocabulary and a different code system with the same spelling
# (kernel/proposals.py, adapters/local/store.py). Banning the word there would
# ban the tick. So the rule is held over every module on the path from an
# answer to a published resource, which is where a certainty could be
# manufactured, and the adapter's one occurrence is pinned below instead.
ENGINE = ("kernel/fhir.py", "kernel/mapping.py", "kernel/codification.py",
          "kernel/terminology.py", "api/fill.py", "api/extract.py",
          "catalogue/validate.py")
for name in ENGINE:
    live = engine_code(ROOT / name)
    assert live.strip() and "\ndef\n" in live, name
    typed = [c for c in CERTAINTIES
             if '"%s"' % c in live or "'%s'" % c in live]
    assert not typed, \
        "%s types the certainty %r. A machine that can name a verification " \
        "status is a machine that can write one." % (name, typed)
ok("none of the %d modules between an answer and a published resource types "
   "any of the %d verification statuses: a machine cannot name one, so it "
   "cannot write one" % (len(ENGINE), len(CERTAINTIES)))

# The adapter's one `confirmed`, pinned to the proposal outcome it belongs to.
# This is what fails if the word ever appears there as a clinical value.
STORE = engine_code(ROOT / "adapters" / "local" / "store.py")
assert STORE.count('"confirmed"') == 1, STORE.count('"confirmed"')
assert 'outcome' in STORE[STORE.find('"confirmed"') - 200:STORE.find('"confirmed"')], \
    "the adapter's one `confirmed` is the audit outcome of a proposal. A " \
    "second one, or one not beside `outcome`, is a clinical certainty the " \
    "adapter typed."
for other in [c for c in CERTAINTIES if c != "confirmed"]:
    assert '"%s"' % other not in STORE and "'%s'" % other not in STORE, other
ok("the adapter's only verification word is the one `confirmed` that is a "
   "proposal's own outcome, and it sits beside `outcome` where it belongs")

# And the questionnaire asks for it, rather than any mapping supplying it.
CONSULT = BUNDLE.operations["phc.op.consult-document"]
SCHEMA = validate.load(CONSULT["input"])
(group,) = [g for g in SCHEMA["questions"] if g["link_id"] == "diagnosis"]
(question,) = [q for q in group["questions"]
               if q["link_id"] == "verification_status"]
assert question["required"] is True, question
assert question["answer_value_set"] == "condition-verification-status", question
for record in CONSULT["mapping"]:
    for column, source in (record.get("fields") or {}).items():
        if "verification" in column or "clinical" in column:
            assert "const" not in source, \
                "%s is supplied by the mapping rather than answered: %r" \
                % (column, source)
ok("how sure the clinician is, is a required answer on the form and is "
   "supplied by no mapping")


# ---------------------------------------------------------------------------
# 6. The three provenance routes: what FHIR offers, and why the record carries
#    one of them.
#
#    REFUSED, with the reason checked rather than asserted.
#
#    What R4 offers. Nothing on Condition, Observation or MedicationRequest
#    can say that a machine produced the content and a person validated it:
#    `Condition.recorder` and `Condition.asserter` reference a person,
#    `Observation.performer` references a person or an organisation, and
#    `MedicationRequest.reported[x]` means secondhand rather than machine
#    made. The standard's answer is the `Provenance` resource, whose
#    `agent.who` may reference a Device and whose `agent.type` is bound to the
#    published value set http://hl7.org/fhir/ValueSet/provenance-agent-type
#    (`author`, `verifier`, `assembler` among 13 codes, expanded from
#    tx.fhir.org on 2026-10-31). The three routes are then: one Practitioner
#    agent typed `author`; a Device agent typed `author` beside a Practitioner
#    agent typed `verifier`; and the same pair plus a `Provenance.entity` with
#    role `source` naming the incoming bundle. No extension is needed for any
#    of it.
#
#    Why it is not built. Two of the three routes cannot happen in this
#    build, so a column for them would have one reachable value and two that
#    nothing could ever write. Both tripwires below fail the day that changes,
#    and each names what then has to arrive with it.
# ---------------------------------------------------------------------------

# Route 2, a person accepting a suggestion, needs a candidate drawn on a
# screen. web/src/scribe/scribe.check.ts owns that assertion from the
# renderer's side; this is the same wall from the kernel's, so that a Python
# gate run without node still reports it.
DRAWS = sorted(p.name for p in (ROOT / "web" / "src" / "scribe").glob("*.ts")
               if "candidates" in p.read_text() and not p.name.endswith(".check.ts"))
assert DRAWS == ["session.ts"], DRAWS
assert "candidates?" in (ROOT / "web" / "src" / "scribe" / "session.ts").read_text(), \
    "the candidates key is declared as optional and read by nothing"

# Route 3, a bundle arriving, needs Eka asked for one. It is asked for the
# transcript only, which is also where the plan and the code disagree: the
# plan's decision 4 says "both the bundle and the transcript".
SCRIBE = engine_code(ROOT / "api" / "scribe.py")
for shape in ("fhir", "Bundle", "emr_json", "entity"):
    assert shape not in SCRIBE, \
        "api/scribe.py mentions %r in live code. If Eka's bundle is now read, " \
        "a code arriving in it did not come from a person picking it, and the " \
        "record has to say so: see section 6 for the Provenance shape." % shape
ok("neither route that would need a provenance field is reachable: no "
   "candidate is drawn for a person to accept, and Eka is asked for the "
   "transcript only. Both are tripwires, not conclusions")


print("ok   verification: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run: the mutation was applied, the file was
# re-read to confirm it landed, the check was run and FAILED, the mutation was
# reverted, and the check was run again and PASSED.
# ---------------------------------------------------------------------------
#
# - put `"status": "final"` back as a literal in `observation()`: section 2
#   names the function and the element. THIS ONE EXPOSED A HOLE IN SECTION 2
#   ITSELF, which is the only reason section 2 reads the syntax tree rather
#   than the text. The first version scanned the stripped live code from
#   scripts/engine_code.py with a regular expression, and the mutation was
#   MISSED: that stripper drops a string that begins a statement, which in a
#   dict written over several lines is every key, so `"status": "final"`
#   reached the regex as `: "final"` and the pattern could not occur. The
#   assertion was comparing a shape that does not exist in its own input.
# - drop the no-status refusal from `observation()` and default to `final`
#   instead: section 3 fails.
# - drop the verification-status refusal from `observation()`: section 3 fails
#   with the sentence about dropping the doubt and keeping the value.
# - change `lab.op.result-enter` to store `status: {const: verified}`: section 1
#   fails, because `verified` is not a code of observation-status.
# - add `("diagnostic_report", "status")` to STATUS_BINDING: section 1 then
#   reads `lab.op.result-verify`'s `{answer: decision}` and fails on
#   `verified`, which is not an R4 DiagnosticReport status. That is a real
#   latent defect and it is reported rather than fixed: see the report.
# - remove `status` from the observation table: section 2's column check fails.
# - declare a FamilyHistory section in kernel/fhir.PROFILES: section 4 fails.
# - make `verification_status` a `{const: confirmed}` in the consultation
#   mapping: section 5 fails twice, on the typed certainty and on the mapping.
# - add a FHIR bundle template to api/scribe.py's request: section 6 fails.
#
# 9 of 9 caught. No assertion was deleted. The one hole a mutation exposed was
# in section 2, described above, and it is fixed rather than noted.
