"""Run: python3 scripts/check_codification.py

Codification, and the fact that it mostly finds nothing.

The module this checks exists to turn a spoken phrase into CANDIDATE codes a
person chooses from. Its own one line definition puts the emphasis in an
unusual place: *it must work when it returns none*. That is not modesty. Three
conditions and six medicines are coded in this build, so for almost everything
a clinician says, codification finds nothing resolvable. The empty answer is
the ordinary path and it is the one this file spends most of its length on.

What is proved here, in order:

  the whole consultation path, with the stub returning nothing, unchanged
  the five ways the answer is empty, each one its own case and its own sentence
  a candidate never becomes a value: it is not in `values`, it is not in
    `tick`, and the field it belongs to is still named as unfilled
  the designed fallback, end to end: a finding this build cannot code travels
    as narrative text and the note still reaches ABDM as a document

The fallback is the one that needed building rather than checking. The claim
has been written down twice, in `kernel/terminology.py` and in the
architecture document's ceilings, and it was not true: a narrative row had no
FHIR projection and every profile requires at least one section, so a
consultation whose findings could not be coded published nothing at all. The
probe that showed it is section 5 below, now inverted into the check that
would fail if it were removed.

The narrative-only bundle this produces was run through the ABDM catalogue's
tier one structural validator on 2026-10-31, against the pinned NRCeS
profiles (ndhm.in 6.5.0), and came back with no findings. That is a structural
check and not a certification: it does not validate terminology, and the
official HL7 validator has not been run on it. Both of those are stated here
rather than in a commit message, because a validator result nobody can find
is the same as none.
"""
from __future__ import annotations

import base64
import json
import pathlib
import socket
import sys

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from adapters.local.store import SqliteStore                       # noqa: E402
from api import fill                                               # noqa: E402
from care_phc.connectors.codification import eka                   # noqa: E402
from catalogue import validate, vocab                              # noqa: E402
from kernel import codification, declarations, fhir, proposals, terminology  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
CONSULT = BUNDLE.operations["phc.op.consult-document"]
SCHEMA = validate.load(CONSULT["input"])
CAPS = set(vocab.for_bundle("phc").roles["mo"]) \
    | set(vocab.for_bundle("phc").roles["frontdesk"]) \
    | set(vocab.for_bundle("phc").roles["nurse"])
A_DOCTOR = "user:ravi"
NOW = "2026-10-31T10:05:00+00:00"
CONDITION = "condition-code"

# What a doctor actually says, and the part of it this build cannot code.
# Dengue is endemic in India and is not in the condition list, which is the
# normal case rather than an awkward example.
SAID = ("Bukhaar teen din se. Chest clear, hydrated. Likely dengue fever, "
        "and her sugar is known. Paracetamol, review in three days.")


# ---------------------------------------------------------------------------
# 1. The stub. Everything must work when it answers nothing, which is what a
#    health centre with no line runs and what this gate runs.
# ---------------------------------------------------------------------------

NONE = codification.NoCodification()
answer = NONE.suggest("dengue fever", CONDITION, transcript=SAID,
                      span="dengue fever")
assert isinstance(answer, codification.Suggestions), answer
assert not answer and len(answer) == 0 and list(answer) == [], answer
assert answer.reachable, "no codifier configured is not a codifier that is down"
ok("the stub answers nothing, and the empty answer is a sequence, so a caller "
   "that forgets the empty case is still correct")

# The default everywhere it is optional is the stub, not the client. The
# offline path is the path, so it is the one that gets exercised.
assert fill.CODIFIER is NONE.__class__ or isinstance(fill.CODIFIER, codification.NoCodification), \
    fill.CODIFIER
ok("the default codifier on the fill path is the one that answers nothing")


# ---------------------------------------------------------------------------
# 2. The whole consultation path, with the stub. Nothing about a recording,
#    a draft, a commit or a document changes because codification found
#    nothing, which is the plan's own check for this step.
# ---------------------------------------------------------------------------

HEARD = {
    "history": {"value": "Bukhaar teen din se", "confidence": 0.9,
                "evidence": "Bukhaar teen din se"},
    "examination": {"value": "Chest clear, hydrated", "confidence": 0.9,
                    "evidence": "Chest clear, hydrated"},
    "assessment": {"value": "Likely dengue fever", "confidence": 0.8,
                   "evidence": "Likely dengue fever"},
    # The one finding this build CAN code, spoken the way it is spoken.
    "diagnosis[0].condition": {"value": "Type 2 diabetes mellitus",
                               "confidence": 0.7, "evidence": "her sugar is known"},
    "diagnosis[0].clinical_status": {"value": "Active", "confidence": 0.7,
                                     "evidence": "her sugar is known"},
    "diagnosis[0].verification_status": {"value": "Confirmed", "confidence": 0.7,
                                         "evidence": "her sugar is known"},
    # And the one it cannot. Heard, refused as a value, named rather than
    # guessed into the field.
    "diagnosis[1].condition": {"value": "dengue fever", "confidence": 0.8,
                               "evidence": "Likely dengue fever"},
}
import datetime                                                    # noqa: E402

TODAY = datetime.date(2026, 10, 31)
draft = fill.build_draft("phc.op.consult-document", SCHEMA, HEARD, SAID,
                         instrument="phc.inst.consult-scribe", today=TODAY)
assert draft["values"]["diagnosis"] == [
    {"condition": "44054006", "clinical_status": "active",
     "verification_status": "confirmed"}], draft["values"]
assert "dengue" not in json.dumps(draft["values"]["diagnosis"]).lower(), \
    "a phrase this build cannot code reached a coded field"
# It is in the narrative, which is where it belongs and is the fallback
# section 5 below publishes.
assert "dengue" in draft["values"]["assessment"].lower(), draft["values"]
assert "diagnosis[1].condition" in draft["unfilled"], draft["unfilled"]
ok("a spoken finding this build cannot code is named as unfilled, never "
   "stored as the nearest code and never stored as text")

# With the stub, there are no candidates at all and the draft is the draft it
# has always been. Asserted as an absent key, not an empty one: a key that is
# always there and always empty is how a renderer learns to ignore it.
assert "candidates" not in draft, draft.get("candidates")
ok("with the stub, the draft carries no candidates key at all")

# The tick is untouched. Every non text value of every row is still owed one.
assert sorted(draft["tick"]) == ["diagnosis[0].clinical_status",
                                 "diagnosis[0].condition",
                                 "diagnosis[0].verification_status"], draft["tick"]
ok("every coded value of every row is still owed its own tick")

# And the commit path. The payload a person confirms is what commits, through
# the ordinary validator and the ordinary guard.
store = SqliteStore(":memory:")
thread = store.open_thread(token="B01", actor=A_DOCTOR)
decision = proposals.commit(store, BUNDLE, "phc.op.patient-register",
                            thread=thread,
                            payload={"name": "Sunita Devi", "age": 34,
                                     "sex": "female", "phone": "9876500000",
                                     "village": "Yadiki", "category": "general"},
                            caps=CAPS, actor=A_DOCTOR)
assert decision, decision.reason
NOTE = dict({k: v["value"] for k, v in HEARD.items() if "[" not in k},
            diagnosis=draft["values"]["diagnosis"],
            plan="Paracetamol, review in three days.")
before = len(store.audit(thread))
decision = proposals.commit(store, BUNDLE, "phc.op.consult-document",
                            thread=thread, payload=NOTE, caps=CAPS,
                            actor=A_DOCTOR)
assert decision, decision.reason
assert len(store.audit(thread)) == before + 1
assert store.audit(thread)[-1].outcome == "allowed"
ok("the consultation commits with one coded diagnosis and one uncoded "
   "finding, and writes its audit line")


# ---------------------------------------------------------------------------
# 3. The five empty answers. One case each, because each is a different
#    sentence to put in front of a clinician, and a caller that cannot tell
#    them apart tells the clinician the wrong thing.
# ---------------------------------------------------------------------------

TOKEN = "not-a-credential-and-never-sent-anywhere"


class Service:
    """A stand-in transport. See care_phc/connectors/codification/check.py for
    where the bodies come from: the published contract's own examples, not a
    recording of a live call."""

    def __init__(self, answer):
        self.answer = answer

    def __call__(self, method, url, headers, body, timeout):
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def ask(answer, phrase="dengue fever", span="Likely dengue fever",
        valueset=CONDITION):
    client = eka.EkaCodification(token=TOKEN, transport=Service(answer),
                                 base="https://api.invalid")
    return client.suggest(phrase, valueset, transcript=SAID, span=span)


def nel(*results):
    return (200, json.dumps({
        "request_id": "r", "query": "dengue fever", "query_breakdown": None,
        "ontology": "snomed", "version": "20250401_extended",
        "index_name": "snomed_20250401_extended", "model_version": "m",
        "results": list(results)}))


def term(code, name, tag, score=0.9, linked=True):
    return {"term_id": code, "term_name": name, "score": score,
            "is_linked": linked, "metadata": {"semantic_tag": tag}}


# (a) It answered and found nothing.
found_nothing = ask(nel())
assert len(found_nothing) == 0 and found_nothing.reachable, found_nothing
assert found_nothing.refused == (), found_nothing.refused

# (b) It is down.
down = ask(ConnectionRefusedError("refused"))
assert len(down) == 0 and down.reachable is False, down
assert "could not be reached" in down.refused[0], down.refused

# (c) It is slow. The wait is bounded, because the alternative to this call is
#     a list the clinician could already have scrolled.
slow = ask(socket.timeout("timed out"))
assert len(slow) == 0 and slow.reachable is False, slow
assert eka.TIMEOUT <= 10, eka.TIMEOUT

# (d) It returned a code this build cannot resolve. Dengue is a real SNOMED
#     concept and a real diagnosis in India; this build still cannot store it,
#     and saying so is the whole point of the list's own banner.
unresolvable = ask(nel(term("38362002", "Dengue", "disorder", score=0.99)))
assert len(unresolvable) == 0, unresolvable
assert unresolvable.reachable is True, "the service answered; the gap is ours"
assert "38362002" in unresolvable.refused[0], unresolvable.refused

# (e) It returned a code from the wrong branch of the ontology.
wrong_branch = ask(nel(term("71388002", "Procedure", "procedure")))
assert len(wrong_branch) == 0, wrong_branch
assert "is a procedure" in wrong_branch.refused[0], wrong_branch.refused

# And the five are told apart. Two axes, and both are needed: whether the
# service could be asked, and whether anything it said survived.
shapes = {"found nothing": (found_nothing.reachable, bool(found_nothing.refused)),
          "down": (down.reachable, bool(down.refused)),
          "slow": (slow.reachable, bool(slow.refused)),
          "unresolvable": (unresolvable.reachable, bool(unresolvable.refused)),
          "wrong branch": (wrong_branch.reachable, bool(wrong_branch.refused))}
assert shapes["found nothing"] == (True, False), shapes
assert shapes["down"] == (False, True) and shapes["slow"] == (False, True), shapes
assert shapes["unresolvable"] == (True, True), shapes
assert shapes["wrong branch"] == (True, True), shapes
assert len({s for s in shapes.values()}) == 3, shapes
ok("five empty answers, each with its own sentence, and a caller can tell "
   "'nobody matched' from 'I could not look'")

# Every one of them is a sentence a clinician can act on, not a code.
for name, answer in (("found nothing", found_nothing), ("down", down),
                     ("slow", slow), ("unresolvable", unresolvable),
                     ("wrong branch", wrong_branch)):
    for line in answer.refused:
        assert line[0].isalnum() and len(line.split()) >= 6, (name, line)
ok("every refusal is a sentence, not an error code")


# ---------------------------------------------------------------------------
# 4. A candidate is not a value. The rule the whole seam exists for, checked
#    from the direction it would be broken: a service that is SURE.
# ---------------------------------------------------------------------------

sure = ask(nel(term("44054006", "Diabetes mellitus type 2", "disorder",
                    score=1.0, linked=True)),
           phrase="her sugar", span="her sugar is known")
assert len(sure) == 1 and sure[0].linked is True and sure[0].score == 1.0, sure
# It is still a candidate. There is no shape here a form control binds to, and
# no path from here into a payload.
shown = sure[0].public()
assert "value" not in shown and set(shown) == {
    "code", "system", "display", "valueset", "score", "linked", "span", "term"}, shown
ok("a candidate the service is certain of and scores 1.0 is still a "
   "candidate: it carries no value a field could take")

# Wired onto the fill path, a certain candidate changes no value and owes no
# tick. The field it belongs to is still unfilled.
class OneCandidate:
    def suggest(self, text, valueset, *, context=None, transcript="", span=""):
        return ask(nel(term("44054006", "Diabetes mellitus type 2", "disorder",
                            score=1.0)), phrase=text, span=span or text,
                   valueset=valueset)


offered = fill.build_draft("phc.op.consult-document", SCHEMA, HEARD, SAID,
                           instrument="phc.inst.consult-scribe", today=TODAY,
                           codifier=OneCandidate())
assert offered["values"] == draft["values"], \
    "a candidate changed a value, which is the defect this seam exists to prevent"
assert offered["tick"] == draft["tick"], "a candidate was owed a tick"
assert "diagnosis[1].condition" in offered["unfilled"], offered["unfilled"]
assert offered["candidates"]["diagnosis[1].condition"][0]["code"] == "44054006", \
    offered["candidates"]
assert offered["candidates"]["diagnosis[1].condition"][0]["linked"] is True
ok("a candidate rides beside the draft, under the id of a field that is still "
   "unfilled, and it moves no value and owes no tick")

# The candidate is offered for the words that were actually said, and the
# span it carries is the EVIDENCE the extractor kept, not the value it tried
# to make of it. Those differ here on purpose: the value heard was "dengue
# fever" and the words were "Likely dengue fever", and a candidate shown
# beside the wrong words is a candidate a doctor cannot check.
assert offered["candidates"]["diagnosis[1].condition"][0]["span"] == \
    HEARD["diagnosis[1].condition"]["evidence"], offered["candidates"]
assert offered["candidates"]["diagnosis[1].condition"][0]["span"] in SAID
ok("a candidate carries the words the extractor kept, and the transcript "
   "holds them")

# Nothing is offered for a field that filled, and nothing is offered for a
# field that binds no value set however badly it was heard: a narrative field
# has no codes to choose between.
assert set(offered["candidates"]) == {"diagnosis[1].condition"}, \
    offered["candidates"]

# And nothing is offered for a field that filled, because there is nothing to
# choose: the person already said something this build could code.
assert "diagnosis[0].condition" not in offered["candidates"], offered["candidates"]
ok("a field a recording filled is offered no candidates")


# ---------------------------------------------------------------------------
# 5. The designed fallback, end to end. An uncoded finding travels as
#    narrative text and the note still reaches ABDM.
# ---------------------------------------------------------------------------

# The note is on the thread as narrative, carrying the finding nothing coded.
notes = store.select("notes", thread=thread, where={}, fields=[], limit=5)
assert len(notes) == 1, notes
assert "dengue" in notes[0]["text"].lower(), notes[0]["text"]
ok("the finding this build cannot code is in the note, in the doctor's own "
   "words, attributed to the doctor")

# Where a row goes in a published document is the bundle's declaration, not
# this file's choice. It was typed here, and typed differently in
# scripts/check_verification.py, which is one visit filed two ways.
CONSULTATION = BUNDLE.documents["consultation"]
doc = fhir.document(store, thread, now=NOW, **CONSULTATION)
kinds = [e["resource"]["resourceType"] for e in doc["entry"]]
assert kinds[0] == "Composition", kinds
assert "DocumentReference" in kinds and "Condition" in kinds, kinds
(reference,) = [e["resource"] for e in doc["entry"]
                if e["resource"]["resourceType"] == "DocumentReference"]
attachment = reference["content"][0]["attachment"]
carried = base64.b64decode(attachment["data"]).decode("utf-8")
assert "dengue" in carried.lower(), carried
assert reference["meta"]["profile"] == [
    "https://nrces.in/ndhm/fhir/r4/StructureDefinition/DocumentReference"], reference
assert reference["status"] == "current" and reference["docStatus"] == "final"
assert attachment["contentType"] == "text/plain", attachment
# What kind of document it is comes from the profile, not from this file and
# not from the projection: the Composition's own type, which NRCeS fixes.
wanted = fhir.PROFILES["OPConsultRecord"]["type"]
assert reference["type"]["coding"] == [
    {"system": "http://snomed.info/sct", "code": wanted["code"],
     "display": wanted["text"]}], reference["type"]
assert attachment["title"] == wanted["text"], attachment
assert reference["subject"]["reference"] == doc["entry"][0]["resource"]["subject"]["reference"]
assert reference["author"], "a note published with no author"
ok("the note reaches ABDM: one DocumentReference whose attachment carries the "
   "uncoded finding verbatim, under the patient and the doctor")

# The Composition is still a valid one: every path the profile's digest makes
# required is filled, and the narrative has a section of its own.
composition = doc["entry"][0]["resource"]
for path in fhir.PROFILES["OPConsultRecord"]["required"]:
    assert composition.get(path), "Composition.%s is missing" % path
titles = [s["title"] for s in composition["section"]]
assert "Document Reference" in titles, titles
ok("the Composition fills every required path and gives the narrative its "
   "own declared section")

# The same note in a different document takes THAT document's type, and when
# the standard's code for it is not published anywhere we can read, it takes
# none rather than the nearest one. WellnessRecord is in exactly that state
# and kernel/fhir.py says so: a note filed under a wellness record is not a
# clinical consultation report, and typing it as one files it under a heading
# that reads as correct everywhere it is read.
assert fhir.PROFILES["WellnessRecord"]["type"]["code"] is None, \
    "this check needs a profile whose document type code is not published"
elsewhere = fhir.document(store, thread, profile="WellnessRecord",
                          sections_wanted={"DocumentReference": [("notes", {})]},
                          now=NOW)
(other,) = [e["resource"] for e in elsewhere["entry"]
            if e["resource"]["resourceType"] == "DocumentReference"]
assert "type" not in other, other
assert "title" not in other["content"][0]["attachment"], other
assert base64.b64decode(other["content"][0]["attachment"]["data"]).decode() == carried
ok("the same note in another document carries that document's type, and none "
   "at all where the standard's code is not published")

# The fallback with NOTHING coded, which is the case that was broken. A
# consultation whose every finding is uncoded used to publish no document at
# all, because an empty section is omitted and every profile requires one.
bare = SqliteStore(":memory:")
bare_thread = bare.open_thread(token="B02", actor=A_DOCTOR)
assert proposals.commit(bare, BUNDLE, "phc.op.patient-register",
                        thread=bare_thread,
                        payload={"name": "Lakshmi", "age": 41, "sex": "female",
                                 "phone": "9876500001", "village": "Yadiki",
                                 "category": "general"},
                        caps=CAPS, actor=A_DOCTOR)
assert proposals.commit(bare, BUNDLE, "phc.op.consult-document",
                        thread=bare_thread,
                        payload={"history": "Bukhaar teen din se.",
                                 "examination": "Chest clear.",
                                 "assessment": "Likely dengue fever.",
                                 "plan": "Review in three days."},
                        caps=CAPS, actor=A_DOCTOR)
assert bare.select("condition", thread=bare_thread, where={}, fields=[],
                   limit=5) == [], "this consultation coded nothing"
only_words = fhir.document(bare, bare_thread, now=NOW, **CONSULTATION)
kinds = [e["resource"]["resourceType"] for e in only_words["entry"]]
assert kinds.count("DocumentReference") == 1 and "Condition" not in kinds, kinds
assert len(only_words["entry"][0]["resource"]["section"]) == 1, \
    "an empty section was emitted beside the one with the note in it"
ok("a consultation that coded nothing at all still publishes a document, "
   "which is the fallback that was written down twice and did not exist")

# And a narrative row with nothing in it publishes nothing, rather than an
# empty attachment under a heading claiming there is a note.
empty = SqliteStore(":memory:")
empty_thread = empty.open_thread(token="B03", actor=A_DOCTOR)
assert proposals.commit(empty, BUNDLE, "phc.op.patient-register",
                        thread=empty_thread,
                        payload={"name": "Ram", "age": 50, "sex": "male",
                                 "phone": "9876500002", "village": "Yadiki",
                                 "category": "general"},
                        caps=CAPS, actor=A_DOCTOR)
empty.write("notes", {"text": "   ", "created_by": A_DOCTOR,
                      "created_date": NOW}, thread=empty_thread)
try:
    fhir.document(empty, empty_thread, now=NOW, **CONSULTATION)
except KeyError as broke:
    assert "nothing to put in" in str(broke), broke
    ok("an empty narrative row publishes nothing, rather than an attachment "
       "with no words under a heading saying there is a note")
else:
    raise AssertionError("an empty note was published as a document")


# ---------------------------------------------------------------------------
# 6. The rule the layering exists for, applied to this module: no engine
#    module types a clinical word, and the semantic tags are now among them.
# ---------------------------------------------------------------------------

CLINICAL = ("condition-code", "medication-code", "medication-route",
            "medication-frequency")
WORDS = sorted({code for slug in CLINICAL
                for code in terminology.LOCAL.concepts(slug)}
               | {c["display"] for slug in CLINICAL
                  for c in terminology.LOCAL.concepts(slug).values()}
               # New on this branch, and the reason the list is read rather
               # than typed: a semantic tag is a category of clinical concept,
               # so `if tag == "disorder"` in an engine module would be the
               # same defect as `if code == "44054006"` one layer down.
               | {tag for slug in CLINICAL
                  for tag in terminology.LOCAL.tags(slug)})
assert len(WORDS) >= 47, len(WORDS)
assert "disorder" in WORDS and "medicinal product" in WORDS, WORDS

ENGINE = ("kernel/codification.py", "kernel/terminology.py", "kernel/fhir.py",
          "kernel/mapping.py", "api/fill.py",
          "care_phc/connectors/codification/eka.py")
sys.path.insert(0, str(ROOT / "scripts"))
from engine_code import engine_code                                # noqa: E402

for name in ENGINE:
    live = engine_code(ROOT / name)
    assert live.strip() and "\ndef\n" in live, name
    typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
    assert not typed, "%s types the clinical word(s) %r" % (name, typed)
ok("no module on the codification path types a diagnosis, a drug or the name "
   "of a kind of clinical concept: %d words" % len(WORDS))

# And there is no threshold anywhere on the path. A float between 0 and 1 in
# any of these would be an unvalidated clinical threshold, which is how a
# suggestion becomes a decision.
for name in ("kernel/codification.py", "care_phc/connectors/codification/eka.py"):
    live = engine_code(ROOT / name)
    import re
    found = re.findall(r"\b0\.\d+\b", live)
    assert not found, "%s holds a threshold: %r" % (name, found)
ok("no score threshold on the codification path, in either module")

print("ok   codification: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run.
# ---------------------------------------------------------------------------
#
# - remove `document_reference` from fhir.PROJECTIONS: section 5 goes back to
#   what it was before this branch, which is a consultation that publishes
#   nothing, and the probe at the top of this file becomes the check again.
# - let an empty narrative row publish: a document is emitted with an
#   attachment of no words under a heading saying there is a note.
# - fill the candidate's code into the draft's values: section 4 fails on the
#   first assertion, which is the one the whole seam exists for.
# - add the candidate's id to the draft's tick list: a suggestion becomes a
#   value that a tick can confirm.
# - make `NoCodification.suggest` answer something: section 1 and section 2
#   both fail, because the offline path stops being the path.
# - give the stub `reachable=False`: a clinic with no codification configured
#   starts telling its clinicians the service is down.
# - take the semantic tags out of the engine word list: the rule stops
#   covering the words this branch added.
