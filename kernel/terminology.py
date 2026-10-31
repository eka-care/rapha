"""The terminology seam, and the one value type that can only exist validated.

Why this exists
---------------
Every clinical fact this product records has to mean the same thing in another
facility. That means a code, from a code system, out of a value set. Four
parties have a claim on that and only one of them may answer each question;
the table is in docs/superpowers/plans/2026-10-30-coded-data-symbiosis.md
section 1. This module answers exactly one line of it: *does that code
actually exist in the value set this question binds to*.

The invariant, and how it is held
---------------------------------
  I1. A stored coding is in the value set its question binds to. Enforced as
      a type at the write path, not as a lint.

`Coding` is that type. It has one constructor, `Terminology.bound()`, and the
constructor consults `validate()` before it hands anything back. A `Coding`
therefore cannot exist without having passed the value set it names, because
`Coding(...)` called from anywhere else raises `UnboundCoding`: the gate is a
module private sentinel this file never exports and never puts in a field.

That is the difference between this and CARE's version of the same idea.
CARE's `ValueSetBoundCoding[slug]` (care/emr/utils/valueset_coding_type.py,
23 lines, and the best idea in that codebase) is a pydantic after-validator
manufactured per slug, so the binding is the field declaration and there is no
write path around it. We take that design. What we do not take is how it is
tested: care/utils/tests/base.py:19 replaces `validate_valueset` with the
identity function for the whole suite, with a comment admitting they could not
find a better way, so the guarantee is never exercised in CI. Here the
terminology is a constructor argument, so a check passes a fake instead of
monkey patching a module global, and kernel/tests/test_terminology.py exercises
the real local one.

Why it is hosted locally, and why that is a feature
---------------------------------------------------
Decided, plan section 2.1. There is no hosted terminology server to point at:
SNOMED CT is free to use in India and still needs an Affiliate License from
MLDS, so nothing on the near path may depend on it. More to the point, a
primary health centre on a bad line needs `validate` to work with no network.
So the offline path is the only path rather than a fallback nobody tests, and
CARE's failure mode is designed out rather than handled: care/emr/fhir/client.py
has no try/except and a 10 second cache TTL, so a terminology server that is
down turns a correct code into a 500, and one that answers oddly turns it into
a 400 telling the clinician their correct code is invalid. Neither can happen
here, because there is no socket on this path at all.

What is consulted when
----------------------
`bound()` is called at BUILD time, by kernel/mapping.py, once per question per
build, not once per write. The local cache is the authority and it does not
change between builds, so validating per write would buy nothing and cost a
file read on the hot path. CARE pays six database reads and six HTTP round
trips for a MedicationRequest with six bound fields; we pay none.

Honest limits
-------------
- One code system per cached value set. A real FHIR value set composes several
  includes. This is enough for a value set that is a branch of one ontology,
  which is every binding the PHC bundle has, and it is what the local index
  from the NRCeS release files replaces (plan step 1, implementation 2).
- `expand` is a substring match over what is cached. It cannot answer over a
  full SNOMED branch of a hundred thousand concepts, so diagnosis picking is
  limited to cached codes until a real server is behind the seam. That is a
  degraded mode and the doctor's fallback is narrative text, which still
  reaches ABDM. Stated again in the architecture document's ceilings.
- A mapping record may still put a literal in a code column with
  `{const: ...}`. The kernel cannot refuse that without knowing which of an
  adapter's columns hold a coding, which the layering forbids
  (kernel/DECLARATIONS.md: "Column names are not linted here, because the
  kernel must not know an adapter's schema"). What stops it is that it is
  written in the atom and the atom is reviewed. The fix, when there is a
  second adapter, is a `coding:` column kind declared on the resource.

Pure: reads files, touches no database and no network. Python 3.9.
Run: python3 -m kernel.terminology
"""
from __future__ import annotations

import functools
import json
import pathlib
from typing import Optional, Protocol, Sequence

from catalogue import validate

ROOT = pathlib.Path(__file__).parents[1]
CACHE = ROOT / "terminology"

# The two bindings the PHC bundle has, and the whole of what a question may
# bind to today. These are not a facility's words and never become one: LOINC
# and UCUM are nobody's choice, so they sit here beside the kernel's grammar
# rather than in bundles/<id>/bundle.yaml. The two forms are CARE's, and they
# are the right two because there are two kinds of question (plan section 4):
#
#   a question's own `code`, when the question IS the concept. Systolic blood
#   pressure is always LOINC 8480-6.
#   a question's `unit`, when it carries a quantity.
#
# A question's `answer_value_set`, for when the ANSWER carries the concept.
# Implemented 2026-10-31, because something finally binds an answer: a
# laboratory result's analyte is a slot and the concept is whichever test the
# technician ran, exactly as a diagnosis is a slot and "type 2 diabetes" is
# the concept. Until then this was deliberately absent, on the rule that an
# unused binding is a promise with no check behind it; the checks arrived with
# the use, in scripts/check_lab.py.
#
# The slug is per question and not a constant, because the whole point of this
# form is that different questions bind different value sets. So there is no
# ANSWER_BINDING beside the two below: `answer_value_set` is read off the
# question, and `answer_coding()` is what resolves it.
CODE_BINDING = "observation-code"
UNIT_BINDING = "ucum-units"

# Where a question says which value set its ANSWER is drawn from. The FHIR
# questionnaire field name, verbatim, because CARE has it too
# (care/emr/resources/questionnaire/spec.py:145) and this is the one place the
# two models should not diverge. CARE's is a bare string checked only for
# existence, with enforcement re-implemented by hand twice in its response
# validator; ours resolves through the same single constructor every other
# coding goes through.
ANSWER_VALUE_SET = "answer_value_set"

# And where a question says its answer must be the unit that another answer's
# concept is reported in. Declared in styling_metadata.phc beside `range_from`,
# which has lived there as a renderer hint with nothing enforcing it; this one
# is enforced. A laboratory value and its unit are one thing or they are two
# strings that can disagree, and a haemoglobin of 12 mg/dL is storable today.
UNIT_OF = "unit_of"


class UnboundCoding(ValueError):
    """A coding that no value set vouches for, or one built around the gate.

    Both are the same failure from the record's point of view: a code nobody
    checked, travelling under a patient's ABHA number to a clinician who
    cannot ask us what it meant.
    """


# The gate. Held by this module and handed to nothing: `bound()` below is the
# only caller that can pass it, so `Coding(...)` from any other file raises.
# A sentinel rather than a name convention, because a leading underscore is a
# request and this is a rule.
_VALIDATED = object()


class Coding:
    """One code from one code system, vouched for by one value set.

    Construct with `Terminology.bound()`. Immutable: the attributes are the
    identity of a clinical fact and nothing may rewrite one in place.
    """

    __slots__ = ("system", "code", "display", "valueset")

    def __init__(self, system, code, display, valueset, gate=None):
        if gate is not _VALIDATED:
            raise UnboundCoding(
                "a Coding is built by Terminology.bound(), which validates it "
                "against a value set first. Building one directly would store "
                "a code nobody checked.")
        for name, value in (("system", system), ("code", code),
                            ("display", display), ("valueset", valueset)):
            object.__setattr__(self, name, value)

    def __setattr__(self, name, value):
        raise AttributeError("a Coding is immutable")

    def __delattr__(self, name):
        raise AttributeError("a Coding is immutable")

    def __eq__(self, other):
        return (isinstance(other, Coding) and self.system == other.system
                and self.code == other.code and self.valueset == other.valueset)

    def __hash__(self):
        return hash((self.system, self.code, self.valueset))

    def __repr__(self):
        return "Coding(%r, %r, valueset=%r)" % (self.system, self.code, self.valueset)

    def to_fhir(self):
        """This coding as a FHIR R4 Coding element.

        `system` is always present, unlike CARE's (care/emr/resources/common/
        coding.py makes it optional while `code` is required). A code without a
        system is meaningless in FHIR R4 and unexportable to ABDM, so it cannot
        be absent here: the value set carries it and every Coding came from one.
        """
        out = {"system": self.system, "code": self.code}
        if self.display:
            out["display"] = self.display
        return out


class Terminology(Protocol):
    """The seam. Two methods, in the spirit of kernel.contracts.Store: small
    enough that a local file and a real terminology server both satisfy it.

    `validate` is on the write path and must work with no network.
    `expand` is for a picker and may be poorer offline than online.
    """

    def validate(self, valueset: str, code: str) -> bool: ...

    def concepts(self, valueset: str) -> dict: ...
    # The cached concepts by code, for the facts a Coding has no field for.

    def expand(self, valueset: str, query: str, count: int) -> Sequence[Coding]: ...

    def bound(self, valueset: str, code: str) -> Coding: ...


class CachedTerminology:
    """Implementation 1: the local cache in terminology/<slug>.json.

    Read only and generated. Nothing in the product writes a value set, which
    is the answer to "who may edit one": nobody, here. The file carries its own
    provenance per concept, because a code whose source nobody wrote down is a
    code nobody can re-check.
    """

    def __init__(self, path=CACHE):
        self.path = pathlib.Path(path)

    @functools.lru_cache(maxsize=None)
    def _load(self, valueset):
        f = self.path / ("%s.json" % valueset)
        if not f.exists():
            raise UnboundCoding(
                "no value set '%s' is cached in %s. A question may not bind to "
                "a value set this facility cannot check offline."
                % (valueset, self.path))
        blob = json.loads(f.read_text())
        for key in ("slug", "system", "concepts"):
            if key not in blob:
                raise UnboundCoding("%s: a cached value set needs '%s'" % (f.name, key))
        if blob["slug"] != valueset:
            raise UnboundCoding("%s: declares slug '%s'" % (f.name, blob["slug"]))
        return blob

    def validate(self, valueset, code):
        return str(code) in self._load(valueset)["concepts"]

    def bound(self, valueset, code):
        """The only constructor of a Coding. Validates, then builds.

        The display comes from the cache and never from the caller, so a
        display that disagrees with the terminology is not expressible. That is
        CARE's free text `Coding.display` problem removed rather than handled.
        """
        blob = self._load(valueset)
        concept = blob["concepts"].get(str(code))
        if concept is None:
            raise UnboundCoding(
                "'%s' is not in value set '%s', so it may not be stored against "
                "a question bound to it" % (code, valueset))
        return Coding(blob["system"], str(code), concept.get("display") or "",
                      valueset, _VALIDATED)

    def concepts(self, valueset):
        """The cached concepts behind a value set, by code. Read only: a copy,
        so a caller cannot edit the cache through it."""
        return {k: dict(v) for k, v in self._load(valueset)["concepts"].items()}

    def expand(self, valueset, query="", count=20):
        blob = self._load(valueset)
        want = str(query or "").strip().lower()
        out = []
        for code, concept in sorted(blob["concepts"].items()):
            display = concept.get("display") or ""
            if want and want not in display.lower() and want not in code.lower():
                continue
            out.append(Coding(blob["system"], code, display, valueset, _VALIDATED))
            if len(out) >= count:
                break
        return out

    def cached(self):
        """Every value set slug on disk. For a check, not for the product."""
        return sorted(p.stem for p in self.path.glob("*.json"))


LOCAL = CachedTerminology()


def question_codings(question, terminology: Optional[Terminology] = None):
    """The bound codings one questionnaire question declares, by fact name.

    Two facts, both optional, and an absent one is absent rather than empty:
    a question that binds nothing gets nothing, and a mapping source that
    reads a fact nothing declared fails lint rather than writing a null.

      code   the question's own concept, bound to CODE_BINDING. Declared as a
             bare code, not a triple: the system comes from the value set and
             the display comes from the cache, so neither can be retyped
             wrongly. CARE declares all three per field and its displays are
             free text as a result.
      unit   the quantity's unit, bound to UNIT_BINDING. Read from
             styling_metadata.phc.unit, which is where it already lives, next
             to the range that validates it. Not moved and not duplicated:
             the symbol a UCUM value set holds is the same symbol the renderer
             prints and the voice grammar matches, so there is one declaration
             and the binding is new, not the data.

    Raises UnboundCoding, which is a build failure, for a declared code or
    unit that its value set does not hold.
    """
    t = terminology or LOCAL
    out = {}
    code = question.get("code")
    if code not in (None, ""):
        out["code"] = t.bound(CODE_BINDING, code)
    unit = ((question.get("styling_metadata") or {}).get("phc") or {}).get("unit")
    if unit not in (None, ""):
        out["unit"] = t.bound(UNIT_BINDING, unit)
    return out


def answer_binding(question):
    """The value set this question's ANSWER is drawn from, or None."""
    slug = (question or {}).get(ANSWER_VALUE_SET)
    return str(slug).strip() or None if slug not in (None, "") else None


def unit_of(question):
    """The link_id whose concept decides this question's unit, or None."""
    phc = ((question or {}).get("styling_metadata") or {}).get("phc") or {}
    link_id = phc.get(UNIT_OF)
    return str(link_id).strip() or None if link_id not in (None, "") else None


def answer_coding(question, answer, terminology: Optional[Terminology] = None):
    """The coding an answer names, through the question's own value set.

    The third binding form, resolved at WRITE time rather than build time,
    because the answer is not known until somebody answers. Everything else
    about it is identical to the other two: one constructor, which validates
    before it returns, so an answer the value set does not hold cannot become
    a coding and therefore cannot become a row.

    Raises UnboundCoding for a question that binds nothing (a caller asking
    for a coding where no binding was declared is a mapping bug, not an empty
    answer), and for an answer outside the value set.
    """
    slug = answer_binding(question)
    if not slug:
        raise UnboundCoding(
            "question %r declares no %s, so its answer carries no concept"
            % ((question or {}).get("link_id"), ANSWER_VALUE_SET))
    if answer in (None, ""):
        raise UnboundCoding(
            "question %r was not answered, so there is no concept to store"
            % question.get("link_id"))
    return (terminology or LOCAL).bound(slug, answer)


def concept(valueset, code, terminology: Optional[Terminology] = None):
    """The raw cached concept behind a code, for the facts a Coding has no
    field for. Today that is one fact: the unit LOINC reports an analyte in.

    Deliberately not on `Coding`. A Coding is the four things FHIR's Coding
    element has, and an expected unit is a fact ABOUT the concept rather than
    part of it, so putting it on the dataclass would make every coding in the
    product carry a field only lab analytes have.
    """
    t = terminology or LOCAL
    if not t.validate(valueset, code):
        raise UnboundCoding("%r is not in value set %r" % (code, valueset))
    return dict(t.concepts(valueset).get(str(code)) or {})


def answer_problems(schema, payload, terminology: Optional[Terminology] = None):
    """Terminology failures in a payload, as sentences, or an empty list.

    This is guard step 1's terminology half. It is composed into the validator
    by kernel/proposals.validator rather than living in
    catalogue/validate.py, because the catalogue layer may not import the
    kernel and the value sets are the kernel's. The split is the honest one:
    the schema rules are the catalogue's (required, types, choices, range) and
    the terminology rules are the kernel's, and there is still exactly one
    validator per operation that every surface uses.

    Being on step 1 rather than at the write matters for the person: a
    technician who picks the wrong unit is told before anything is written,
    in a sentence, instead of getting a traceback from a row builder.

    Two rules:

      every answer bound to a value set is a code that value set holds;
      an answer declared `unit_of` another is the unit that other answer's
      concept is reported in.

    The second is why a laboratory value and its unit are one checked thing
    rather than two strings. A haemoglobin of 12 is a normal haemoglobin in
    g/dL and a nonsense one in mg/dL, and nothing in the payload said which
    until now.
    """
    t = terminology or LOCAL
    problems = []
    # A repeating group's answer is a list of rows, and each row is a payload
    # over that group's own sub questions. So the rules below run once per row
    # with the row as the payload, and the row number is in the sentence.
    #
    # This is where a repeating group multiplies the risk rather than adding
    # to it: one unbound code used to be one bad row, and now one unbound code
    # is one bad row out of five on a prescription a pharmacist reads.
    for link_id, group in validate.row_groups(schema).items():
        rows = payload.get(link_id)
        if not isinstance(rows, list):
            continue
        questions = validate.row_questions(group)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            problems += ["%s[%d].%s" % (link_id, index, line)
                         for line in _problems(questions, row, t)]
    inside = set()
    for group in validate.row_groups(schema).values():
        inside |= set(validate.row_questions(group))
    questions = {q["link_id"]: q for q in _walk(schema.get("questions") or [])
                 if q["link_id"] not in inside}
    return problems + _problems(questions, payload, t)


def _problems(questions, payload, t):
    """The two terminology rules over one flat set of answers.

    One flat set, which is either the payload or one row of a repeating group:
    the rules are identical and a row is a payload over fewer questions, so
    there is one implementation and a row cannot be checked less than the form.
    """
    problems = []
    for link_id, question in questions.items():
        answer = payload.get(link_id)
        slug = answer_binding(question)
        if slug and answer not in (None, ""):
            if not t.validate(slug, answer):
                problems.append("%s is %r, which is not a code in %s"
                                % (link_id, answer, slug))
                continue
        other = unit_of(question)
        if not other:
            continue
        if other not in questions:
            problems.append("%s declares %s '%s', which is not a question on "
                            "this form" % (link_id, UNIT_OF, other))
            continue
        peer_slug = answer_binding(questions[other])
        peer_answer = payload.get(other)
        if not peer_slug or peer_answer in (None, "") or answer in (None, ""):
            continue
        if not t.validate(peer_slug, peer_answer):
            continue        # the peer's own failure is already reported above
        wanted = concept(peer_slug, peer_answer, t).get("unit")
        if not wanted:
            # A concept with no unit recorded cannot decide one. Reported
            # rather than passed over: a rule that silently stops applying is
            # worse than one that is absent.
            problems.append("%s is reported with no unit in %s, so %s cannot "
                            "be checked against it" % (peer_answer, peer_slug, link_id))
            continue
        if str(answer) != str(wanted):
            problems.append(
                "%s is %r, and %s is reported in %r. Correct the unit, or "
                "pick the analyte that is measured in %r."
                % (link_id, answer, peer_answer, wanted, answer))
    return problems


def _walk(questions):
    for q in questions:
        yield q
        for inner in _walk(q.get("questions") or []):
            yield inner


def demo():
    t = LOCAL
    assert CODE_BINDING in t.cached(), t.cached()
    assert UNIT_BINDING in t.cached(), t.cached()

    bp = t.bound(CODE_BINDING, "8480-6")
    assert bp.system == "http://loinc.org", bp
    assert bp.code == "8480-6" and bp.display, bp
    assert bp.valueset == CODE_BINDING
    assert bp.to_fhir() == {"system": "http://loinc.org", "code": "8480-6",
                            "display": bp.display}, bp.to_fhir()

    mmhg = t.bound(UNIT_BINDING, "mm[Hg]")
    assert mmhg.system == "http://unitsofmeasure.org", mmhg

    try:
        Coding("http://loinc.org", "8480-6", "Systolic", CODE_BINDING)
    except UnboundCoding:
        pass
    else:
        raise AssertionError("a Coding was built without passing a value set")

    try:
        t.bound(CODE_BINDING, "9999-9")
    except UnboundCoding:
        pass
    else:
        raise AssertionError("a code outside the value set was bound")

    try:
        t.bound("no-such-valueset", "x")
    except UnboundCoding:
        pass
    else:
        raise AssertionError("an uncached value set answered")

    try:
        bp.code = "8462-4"
    except AttributeError:
        pass
    else:
        raise AssertionError("a Coding was rewritten in place")

    assert not t.validate(CODE_BINDING, "9999-9")
    assert t.validate(CODE_BINDING, "8480-6")
    found = t.expand(CODE_BINDING, "systolic", 5)
    assert [c.code for c in found] == ["8480-6"], found
    print("ok   kernel.terminology")


if __name__ == "__main__":
    demo()
