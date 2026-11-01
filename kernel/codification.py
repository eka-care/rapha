"""The codification seam: a heard phrase in, candidate codes out, and the
empty answer as the ordinary one.

What this module is for
-----------------------
A clinician says "sugar". Something has to turn that into a code a second
facility will read the same way. Multilingual concept ranking over twelve
Indian languages is the one piece of this product we cannot build and should
not try, which is why the coded data plan's authority table gives that row to
Eka's codification service. This module is the seam that row sits behind.

The rule the whole file exists to hold
--------------------------------------
**Codification proposes. It never decides.** Eka's own documentation for the
Medical Entity Codification endpoint says it, in the Scope and Limitations
section of /docs/models/medical-entity-codification, read 2026-10-31: it
"Provides candidate codes; clinical validation remains with the integrator",
and it is "Not a substitute for professional medical coding judgment". So:

- nothing here returns a value. It returns `Candidate`s, and a candidate is
  not an answer to anything until a person picks one;
- there is NO SCORE THRESHOLD in this file and there must not be one. A
  threshold is the mechanism by which a suggestion becomes a decision, and
  nobody has validated one. The candidates come back in the order the service
  ranked them and a person reads the list;
- `is_linked` is carried through and acted on by nothing. It is the service's
  own confidence that it found the single right match, which is worth showing
  beside a candidate and is not a licence to fill a field.

This is invariant I6's neighbour and it is the invariant the module before
this one found inverted in shipped code: the consultation mapping carried
`verification_status: {const: confirmed}`, so every diagnosis, including a
scribe's guess and a symptom the patient denied, was stored as confirmed.
That is fixed, and the way it comes back is a high score auto-selecting or a
verification status defaulting to confirmed when a candidate is accepted.
Neither is expressible from here: a `Candidate` has no path into a payload
except through a screen.

**Where this file disagrees with the plan it implements, and why.** The coded
data plan's invariant I4 says "A codifier that reports `linked` writes
`verification_status: confirmed`", and section 5 says a linked candidate above
a threshold is prefilled and "committed with the note". Both of those answer
the plan's own table row "Does it enter the record: a person, by a tick" with
the codifier instead, which the table's own rule forbids ("no row may be
answered by the party in another row"). They are also the exact sentences the
shipped `const: confirmed` defect implemented. This file follows the table and
not I4. The contradiction is reported rather than worked around, in the same
place the others are: see the architecture document's section 12.

What makes a candidate a candidate
----------------------------------
Four refusals, each with its own reason, applied in this order by `resolve()`.
A refused candidate is counted and named, never silently dropped, because "the
service found nothing" and "the service found four things this build cannot
code" are different sentences to put in front of a doctor.

  1. **No span.** The phrase a candidate was asked about must appear in the
     transcript, by `api/shaped.py`'s rule and for its reason: a code with no
     words behind it is unarguable afterwards. This is the same `_norm`
     comparison, not a looser one.
  2. **Not resolvable.** The code must come back from `Terminology.bound()`,
     which is the only constructor of a `Coding` in this product. An external
     service returning a code this build cannot resolve is refused, not
     stored. Today that refuses nearly everything, because three conditions
     and six medicines are coded, and that is the real operating condition
     rather than a temporary state to design around.
  3. **Wrong branch.** A SNOMED candidate carries its semantic tag, and the
     value set declares which tags its concepts carry. A `procedure` offered
     for a diagnosis is refused on the tag before anything looks at the code.
     This is a separate rule from 2 on purpose: with the local cache the two
     coincide for most codes, and with the NRCeS index behind the seam, where
     a value set is a whole branch, it will not.
  4. **Already seen.** The service returns the same concept under several term
     names (its own documentation says so: localised and transliterated
     variants of one concept). The first, highest ranked one is kept.

The empty answer
----------------
`suggest` returns a `Suggestions`, which IS a sequence, so `if not suggest(...)`
is the whole of handling the empty case. It also carries `refused`, a list of
sentences, so a caller that wants to explain the emptiness can. Returning an
object instead of a bare list would have made the empty path a thing a caller
has to remember to unwrap; this way forgetting is correct.

`NoCodification` is the default implementation and returns nothing, always.
Everything in this product must work against it, because it is what a health
centre with no line has, and because it is what the gate runs.

Layering. This file is in the kernel, so it may not open a socket: the
protocol, the refusals and the stub are here, and the one implementation that
speaks to a network lives in `care_phc/connectors/codification/eka.py`, the
way the patient directory's does. Pure: reads the local terminology cache and
nothing else.

Run: python3 -m kernel.codification
"""
from __future__ import annotations

import re
from typing import Optional, Protocol, Sequence

from kernel import terminology
from kernel.terminology import Coding, UnboundCoding

# Where a value set says which semantic tags its concepts carry. Read off the
# file rather than written here, for the reason every other clinical fact is:
# the kernel may know that codes have categories and may not know what any
# category is called.
SEMANTIC_TAGS = "semantic_tags"
SEMANTIC_TAG = "semantic_tag"

_SPACE = re.compile(r"\s+")


def _norm(text):
    """The same normalisation `api/shaped.py` compares spans with. Shared by
    copy and not by import, because that module is in the api layer and the
    kernel may not import it; the shape is three lines and the rule is one
    sentence, so a wrapper would hide more than it saves."""
    return _SPACE.sub(" ", str(text)).strip().lower()


class Candidate:
    """One suggested code, with everything a person needs to refuse it.

    Immutable, and it carries a `Coding` rather than a code and a system.
    That is the whole of why this class needs no gate of its own: a `Coding`
    is unconstructible without having passed a value set, so a `Candidate`
    cannot be made to carry a code nothing vouched for. The sentinel lives in
    `kernel/terminology.py` and one gate is enough.

      coding  the resolved code. Its display is the terminology's, never the
              service's `term_name`, so a service that disagrees with the
              value set cannot rename a concept on a doctor's screen.
      score   what the service reported, or None. `None` is the ordinary case
              for a medication candidate, where Eka's contract documents
              `score` as null and reports matching through its own breakdown
              instead. Carried and compared against nothing.
      linked  the service's own flag that it believes this is the single right
              match. Shown beside a candidate, never acted on.
      span    the words in the transcript this was asked about.
      term    what the service called it, kept only so a person can see what
              was matched. Never stored and never displayed as the code's name.
    """

    __slots__ = ("coding", "score", "linked", "span", "term")

    def __init__(self, coding: Coding, *, score=None, linked=False, span="", term=""):
        if not isinstance(coding, Coding):
            raise TypeError("a Candidate carries a Coding, which is the only "
                            "thing in this product that has been through a "
                            "value set")
        object.__setattr__(self, "coding", coding)
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "linked", bool(linked))
        object.__setattr__(self, "span", str(span))
        object.__setattr__(self, "term", str(term))

    def __setattr__(self, name, value):
        raise AttributeError("a Candidate is immutable")

    def __delattr__(self, name):
        raise AttributeError("a Candidate is immutable")

    def __eq__(self, other):
        return (isinstance(other, Candidate) and self.coding == other.coding
                and self.span == other.span)

    def __hash__(self):
        return hash((self.coding, self.span))

    def __repr__(self):
        return "Candidate(%r, score=%r, linked=%r)" % (
            self.coding.code, self.score, self.linked)

    def public(self):
        """The candidate as a renderer reads it. The code, the terminology's
        own display, and the two things that let a person judge it.

        There is no `value` key and there must not be one: a shape a form
        control could bind to directly is how a candidate becomes a value
        without anybody picking it."""
        return {"code": self.coding.code, "system": self.coding.system,
                "display": self.coding.display, "valueset": self.coding.valueset,
                "score": self.score, "linked": self.linked,
                "span": self.span, "term": self.term}


class Suggestions(tuple):
    """Ranked candidates, and why the rest are not here.

    A tuple subclass, so every caller that treats the answer as a sequence is
    right, and the empty answer needs no special handling at all. `refused`
    is beside it rather than inside it: a caller drawing a picker iterates the
    candidates, and a caller explaining an empty picker reads the sentences.
    """

    def __new__(cls, candidates=(), *, refused=(), asked="", reachable=True):
        self = super().__new__(cls, tuple(candidates))
        self.refused = tuple(refused)
        self.asked = str(asked)
        # False only when the service could not be ASKED. One that answered
        # and offered nothing is reachable, and the two are different
        # sentences for the same reason a directory lookup's are: "nobody
        # matched" and "I could not look" lead a clinician to different next
        # actions.
        self.reachable = bool(reachable)
        return self

    def __repr__(self):
        return "Suggestions(%d, refused=%d, reachable=%r)" % (
            len(self), len(self.refused), self.reachable)


class Codification(Protocol):
    """The seam. One method, the shape settled in the coded data plan 2.2.

    `text` is what was heard. `valueset` is the slug the question binds its
    answer to, which is what decides both which ontology is asked and which
    codes may come back. `context` carries the hints the service's accuracy
    depends on, which for a laboratory value is the unit and the specimen and
    for a medicine is the form; it is a dict and an implementation that wants
    none ignores it. `transcript` is what the span is checked against.
    """

    def suggest(self, text: str, valueset: str, *, context: Optional[dict] = None,
                transcript: str = "", span: str = "") -> Suggestions: ...


class NoCodification:
    """The implementation everything must work against: nothing, every time.

    Not a test double. This is what a primary health centre with no line runs,
    and it is the default wherever a codifier is optional, so the offline path
    is the path that gets exercised rather than a fallback nobody reaches.
    `reachable` is True, because a facility that has no codification
    configured is not a facility whose codification is down.
    """

    def suggest(self, text, valueset, *, context=None, transcript="", span=""):
        return Suggestions(asked=text)


def accepted_tags(valueset, terminology_=None):
    """The semantic tags this value set's own concepts carry, as a set.

    Empty when the value set declares none, and an empty set means the tag
    rule does not apply rather than that everything is refused. The FHIR
    status value sets and the UCUM units have no semantic tags and never will:
    they are not SNOMED and the concept of a semantic tag is SNOMED's.
    """
    t = terminology_ or terminology.LOCAL
    try:
        declared = t.tags(valueset)
    except AttributeError:
        declared = ()
    return {str(tag).strip().lower() for tag in declared or () if str(tag).strip()}


def resolve(results, valueset, *, transcript="", span="", terminology_=None,
            text=""):
    """Raw service results in, `Suggestions` out. The four refusals, in order.

    `results` is a sequence of dicts in the service's own ranked order, each
    with `code`, and optionally `term`, `score`, `linked` and `tag`. The
    translation from one service's wire format into that shape belongs to that
    service's connector; what is here is every rule that must hold whichever
    service is behind the seam, which is why it is in the kernel and not in
    the connector.

    The order of the results is preserved exactly. Nothing is re-sorted by
    score, because sorting by score is one line away from picking by score.
    """
    t = terminology_ or terminology.LOCAL
    tags = accepted_tags(valueset, t)
    heard = _norm(transcript)
    kept, refused, seen = [], [], set()

    if span and heard and _norm(span) not in heard:
        # One refusal for the whole batch: the words were not said, so no
        # candidate for them can be traced to anything.
        return Suggestions(refused=[
            "%r is not in the transcript, so nothing suggested for it can be "
            "traced to what was said" % span], asked=text or span)

    for raw in results or ():
        code = str((raw or {}).get("code") or "").strip()
        term = str((raw or {}).get("term") or "")
        if not code:
            refused.append("a candidate came back with no code")
            continue
        tag = str((raw or {}).get("tag") or "").strip().lower()
        if tags and tag not in tags:
            refused.append(
                "%s (%s) is a %s, and %s holds %s, so it is not a candidate "
                "for this question"
                % (code, term or "no name", tag or "concept of no stated kind",
                   valueset, " or ".join(sorted(tags))))
            continue
        try:
            coding = t.bound(valueset, code)
        except UnboundCoding:
            refused.append(
                "%s (%s) is not in %s, so this build cannot resolve it and it "
                "may not be offered" % (code, term or "no name", valueset))
            continue
        if coding.code in seen:
            continue        # the same concept under another of its names
        seen.add(coding.code)
        kept.append(Candidate(coding, score=(raw or {}).get("score"),
                              linked=(raw or {}).get("linked"),
                              span=span, term=term))
    return Suggestions(kept, refused=refused, asked=text or span)


def demo():
    import json
    import pathlib
    import re
    import sys
    import tempfile

    SLUG = "condition-code"

    # 1. Nothing found is the ordinary answer, and it is a sequence, so a
    #    caller that forgets to handle the empty case is still correct.
    empty = NoCodification().suggest("dengue", SLUG, transcript="dengue hai")
    assert not empty and len(empty) == 0 and list(empty) == [], empty
    assert empty.reachable and empty.refused == (), empty
    assert empty.asked == "dengue"

    # 2. A code this build can resolve comes back as a candidate, carrying the
    #    terminology's display and not the service's name for it.
    got = resolve([{"code": "44054006", "term": "DM2", "score": 0.98,
                    "linked": True, "tag": "disorder"}], SLUG,
                  transcript="patient has sugar", span="sugar")
    assert len(got) == 1, got
    one = got[0]
    assert one.coding.code == "44054006"
    assert one.coding.display == "Type 2 diabetes mellitus", one.coding.display
    assert one.term == "DM2" and one.span == "sugar"
    assert one.linked is True and one.score == 0.98
    assert one.public()["display"] == "Type 2 diabetes mellitus"
    assert "value" not in one.public(), \
        "a candidate must not have a shape a form control can bind to"

    # 3. A code this build cannot resolve is refused, and named in a sentence.
    #    This is the ordinary outcome for almost anything a clinician says.
    none = resolve([{"code": "38362002", "term": "Dengue", "score": 0.99,
                     "linked": True, "tag": "disorder"}], SLUG,
                   transcript="dengue hai", span="dengue")
    assert len(none) == 0, none
    assert len(none.refused) == 1 and "38362002" in none.refused[0], none.refused
    assert "cannot resolve" in none.refused[0], none.refused

    # 4. Wrong branch of the ontology. This needs a terminology that WOULD
    #    resolve the code, or the tag rule could be deleted and the
    #    unresolvable rule above would catch the case anyway and nothing would
    #    fail. A real CachedTerminology over a crafted file, because a fake
    #    object cannot be used here at all: `Coding` has one constructor and a
    #    stand-in class has no way to reach it, which is the gate working.
    with tempfile.TemporaryDirectory() as directory:
        (pathlib.Path(directory) / ("%s.json" % SLUG)).write_text(json.dumps({
            "slug": SLUG, "system": "http://snomed.info/sct",
            "semantic_tags": ["disorder", "finding"],
            "concepts": {"71388002": {"display": "Procedure",
                                      "semantic_tag": "procedure"}}}))
        wrong = terminology.CachedTerminology(path=directory)
        assert wrong.validate(SLUG, "71388002"), "the stand-in does hold it"
        branch = resolve([{"code": "71388002", "term": "Procedure",
                           "score": 0.9, "linked": True, "tag": "procedure"}],
                         SLUG, transcript="procedure done", span="procedure",
                         terminology_=wrong)
        assert len(branch) == 0, branch
        assert "is a procedure" in branch.refused[0], branch.refused
        # The same code, the same terminology, an accepted tag: kept. This is
        # what proves the refusal above was the tag rule and nothing else.
        right = resolve([{"code": "71388002", "term": "Procedure",
                          "tag": "disorder"}], SLUG, transcript="x", span="x",
                        terminology_=wrong)
        assert len(right) == 1, right

    # 5. A span that is not in the transcript takes the whole batch with it.
    #    api/shaped.py's rule, applied to a code instead of a value.
    lied = resolve([{"code": "44054006", "term": "DM2", "tag": "disorder"}],
                   SLUG, transcript="the patient has a fever",
                   span="type two diabetes")
    assert len(lied) == 0, lied
    assert "not in the transcript" in lied.refused[0], lied.refused

    # 6. One concept under several of its names is one candidate. Eka's own
    #    documentation says a concept comes back under localised and
    #    transliterated variants, so this is the documented shape and not a
    #    defensive guess.
    twice = resolve([{"code": "44054006", "term": "Type 2 diabetes", "tag": "disorder"},
                     {"code": "44054006", "term": "madhumeha", "tag": "disorder"},
                     {"code": "297142003", "term": "swollen foot", "tag": "finding"}],
                    SLUG, transcript="sugar and swollen foot", span="sugar")
    assert [c.coding.code for c in twice] == ["44054006", "297142003"], twice
    assert twice[0].term == "Type 2 diabetes", "the highest ranked name is kept"

    # 7. Rank order is the service's own, never re-sorted by score here.
    ranked = resolve([{"code": "297142003", "score": 0.4, "tag": "finding"},
                      {"code": "44054006", "score": 0.99, "tag": "disorder"}],
                     SLUG, transcript="x", span="x")
    assert [c.coding.code for c in ranked] == ["297142003", "44054006"], ranked

    # 8. A medication candidate's score is null in the real contract, and a
    #    null score is not a reason to refuse anything.
    med = resolve([{"code": "777067000", "term": "Dolo 650", "score": None,
                    "linked": True, "tag": "medicinal product"}],
                  "medication-code", transcript="dolo 650", span="Dolo 650")
    assert len(med) == 1 and med[0].score is None, med

    # 9. A candidate with no code at all, which is what a malformed response
    #    looks like from here.
    junk = resolve([{"term": "something", "tag": "disorder"}, {}], SLUG,
                   transcript="x", span="x")
    assert len(junk) == 0 and len(junk.refused) == 2, junk.refused

    # 10. The gate: a Candidate cannot be built around a Coding, and cannot be
    #     rewritten once built.
    try:
        Candidate("44054006", span="sugar")
    except TypeError:
        pass
    else:
        raise AssertionError("a Candidate was built from a bare code")
    try:
        one.coding = None
    except AttributeError:
        pass
    else:
        raise AssertionError("a Candidate was rewritten in place")

    # 11. The tags are declared, not coded: they come off the value set file.
    assert accepted_tags(SLUG) == {"disorder", "finding"}, accepted_tags(SLUG)
    assert accepted_tags("medication-code") == {"medicinal product"}
    assert accepted_tags("ucum-units") == set(), \
        "a value set with no semantic tags does not get the tag rule"
    # And a value set that declares none accepts a candidate of any kind,
    # because there is nothing to compare against and refusing everything
    # would be a rule inventing itself.
    untagged = resolve([{"code": "mm[Hg]", "term": "mmHg", "tag": "unit"}],
                       "ucum-units", transcript="140 mmHg", span="mmHg")
    assert len(untagged) == 1, untagged

    # 12. No threshold in this module, and no comparison of a score to
    #     anything. Asserted rather than remembered: the unvalidated threshold
    #     that got into shipped code got there by looking harmless.
    sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
    from engine_code import engine_code
    live = engine_code(pathlib.Path(__file__))
    assert live.strip(), "the live code was stripped to nothing"
    numbers = re.findall(r"\d+\.\d+", live)
    assert not numbers, "a number between 0 and 1 in the live code is a " \
                        "threshold nobody validated: %r" % numbers
    for shape in ("score >", "score <", "score ==", "max(", "min(",
                  "reverse=", "key=", "linked and", "if linked"):
        assert shape not in live, \
            "%r in the live code: a score and a linked flag are carried, " \
            "never compared and never acted on" % shape
    # `sorted` is allowed and used, on the tag names in a refusal sentence.
    # Ranked results are not sorted, which is a different claim and is what
    # check 7 above holds.
    assert "sorted(results" not in live and ".sort(" not in live, \
        "the service's ranking is the ranking"

    print("ok   kernel.codification")


if __name__ == "__main__":
    demo()
