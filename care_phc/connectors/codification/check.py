"""The Eka codification connector, against a stand-in service. No socket.

WHERE THE RESPONSE BODIES CAME FROM. Every body below is copied from the
published OpenAPI contract's own response examples, in
`/openapi/api-reference/health-ai/medical-entity-codification/med-link.yaml`
on developer.eka.care, read 2026-10-31. They are the vendor's examples of its
own wire format, which is the strongest shape available without spending a
credential. **They are not recordings of a live call.** No request in
`eka.py` has been made against api.eka.care from this branch, so what is
proved here is every translation either side of the socket and nothing about
what the service actually returns for an Indian primary health centre's words.
`api/scribe.py` records a real response and says so; this file deliberately
does not claim to.

The stand-in is a transport, not a fake Codification. That is the point: a
fake implementation of the seam would prove the seam's shape and skip all of
this file's request building, status handling and response reading, which is
where the bugs are. So the transport is replaced one layer lower and the real
client runs.

Run: python3 -m care_phc.connectors.codification.check
"""
from __future__ import annotations

import json

from care_phc.connectors.codification import eka
from kernel import codification

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


# --------------------------------------------------------------------------
# The stand-in.
# --------------------------------------------------------------------------

class Stub:
    """A transport that answers from a script instead of a socket.

    `answers` is a list of what to do per call, in order: a (status, text)
    pair to answer with, or an exception instance to raise. Raising is how a
    dead line, a DNS failure and a socket timeout all look from inside
    `eka.py`, which is why one stand-in covers all three.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent = []

    def __call__(self, method, url, headers, body, timeout):
        self.sent.append({"method": method, "url": url, "headers": headers,
                          "body": json.loads(body) if body else None,
                          "timeout": timeout})
        answer = self.answers.pop(0) if self.answers else (200, "{}")
        if isinstance(answer, BaseException):
            raise answer
        return answer


def body(*results):
    """A NELResponse with these candidate blocks, in the contract's shape."""
    return json.dumps({
        "request_id": "0e95448d-7e32-44c9-8586-c33315412330",
        "query": "x", "query_breakdown": None, "ontology": "snomed",
        "version": "20250401_extended", "index_name": "snomed_20250401_extended",
        "model_version": "c88b15811956d4fcb54da9ae6d14a733ac90e7a7",
        "results": list(results)})


# The contract's own SNOMED example, verbatim apart from the code, which is
# changed to one this build's value set holds. The original is 29857009,
# "Chest pain", which this build cannot resolve; that case is checked below
# under its own name rather than being the only case.
DIABETES = {"term_id": "44054006", "term_name": "Diabetes mellitus type 2",
            "score": 0.94, "is_linked": True,
            "metadata": {"semantic_tag": "disorder", "is_core": True,
                         "source": "snomed_ct_20250401_extended",
                         "language": "en", "script": "latin"}}
CHEST_PAIN = {"term_id": "29857009", "term_name": "Chest pain", "score": 1,
              "is_linked": True,
              "metadata": {"semantic_tag": "finding", "is_core": True,
                           "source": "snomed_ct_20250401_extended",
                           "language": "en", "script": "latin"}}
# The contract's medication example, verbatim. `score` is null and `term_id`
# is an Eka product id rather than a SNOMED concept.
DOLO = {"term_id": "b-4117370658", "term_name": "Dolo 650 Tablet",
        "score": None, "is_linked": True,
        "metadata": {"form_info": "tablet", "volume": "650",
                     "generic_name": "paracetamol + acetaminophen",
                     "generic_id": "g-3283555471",
                     "matching_breakdown": {"drug_detection_score": "1.0"}}}

TOKEN = "not-a-credential-and-never-sent-anywhere"
CONDITION = "condition-code"
MEDICINE = "medication-code"
SAID = "Patient has sugar since 2024 and a swollen foot."


def client(stub, **kw):
    return eka.EkaCodification(token=TOKEN, transport=stub,
                               base="https://api.invalid", **kw)


# --------------------------------------------------------------------------
# 1. The request. Built from the contract, with nothing of the clinic in it
#    that the contract does not ask for.
# --------------------------------------------------------------------------

stub = Stub((200, body(DIABETES)))
got = client(stub).suggest("sugar", CONDITION, transcript=SAID, span="sugar")
sent = stub.sent[0]
assert sent["method"] == "POST" and sent["url"].endswith("/med-link/nel/link"), sent
assert sent["body"] == {"query": "sugar", "ontology": "snomed",
                        "version": "20250401_extended", "top_k": 5}, sent["body"]
assert sent["headers"]["Authorization"] == "Bearer %s" % TOKEN
assert sent["timeout"] == eka.TIMEOUT
ok("one heard phrase becomes one documented request, with the ontology the "
   "value set's code system maps to")

assert len(got) == 1, got
assert got[0].coding.code == "44054006"
assert got[0].coding.display == "Type 2 diabetes mellitus", got[0].coding.display
assert got[0].term == "Diabetes mellitus type 2"
assert got[0].linked is True and got[0].score == 0.94
assert got[0].span == "sugar" and got.reachable
ok("a resolvable candidate comes back with the terminology's display, the "
   "service's own name beside it, and the words it came from")

# No metadata key at all when there is nothing to hint with, because the
# contract defaults it and sending an empty object says something different
# from sending nothing.
assert "metadata" not in sent["body"], sent["body"]
stub = Stub((200, body(DIABETES)))
client(stub).suggest("haemoglobin twelve", CONDITION, transcript="haemoglobin twelve",
                     span="haemoglobin twelve",
                     context={"unit": "g/dL", "specimen": "blood",
                              "mobile": "9876543210", "abha": "12-3456"})
assert stub.sent[0]["body"]["metadata"] == {"unit": "g/dL", "specimen": "blood"}, \
    stub.sent[0]["body"]
ok("the hints the contract documents are sent and nothing else is: a phone "
   "number handed in as context does not reach the wire")


# --------------------------------------------------------------------------
# 2. The empty answer, six ways. Each one is its own case, because each one
#    is a different sentence in front of a clinician.
# --------------------------------------------------------------------------

# (a) The service answered and found nothing.
stub = Stub((200, body()))
none = client(stub).suggest("dengue", CONDITION, transcript="dengue hai",
                            span="dengue")
assert len(none) == 0 and none.reachable and none.refused == (), none
ok("nothing found: an empty answer from a reachable service, with nothing to "
   "explain away")

# (b) The service is down. Any socket failure looks like this from here.
import socket                                                      # noqa: E402

for broke in (socket.gaierror("no such host"),
              ConnectionRefusedError("refused"),
              OSError("network is unreachable")):
    stub = Stub(broke)
    down = client(stub).suggest("sugar", CONDITION, transcript=SAID, span="sugar")
    assert len(down) == 0, down
    assert down.reachable is False, down
    assert "could not be reached" in down.refused[0], down.refused
    assert "Pick from the list" in down.refused[0], down.refused
ok("service down: no candidates, reachable is False, and the sentence tells "
   "the clinician what to do instead")

# (c) The service is slow. A timeout is a socket failure with a name, and it
#     must not be told apart from (b) by a caller: both mean "no suggestion".
stub = Stub(socket.timeout("timed out"))
slow = client(stub).suggest("sugar", CONDITION, transcript=SAID, span="sugar")
assert len(slow) == 0 and slow.reachable is False, slow
assert "could not be reached" in slow.refused[0], slow.refused
# And nothing waits longer than the ceiling, because a clinician is in front
# of a list they could have scrolled.
assert stub.sent[0]["timeout"] == eka.TIMEOUT and eka.TIMEOUT <= 10, eka.TIMEOUT
ok("service slow: the same empty answer, and the wait is bounded at %ds"
   % eka.TIMEOUT)

# (d) The service answered with a status, or with something that is not a
#     result. Answered is not reachable-and-useful.
for status, text in ((422, '{"detail": []}'), (500, ""), (200, "<html>not json"),
                     (200, "[]")):
    stub = Stub((status, text))
    bad = client(stub).suggest("sugar", CONDITION, transcript=SAID, span="sugar")
    assert len(bad) == 0, (status, bad)
    assert bad.reachable is False and bad.refused, (status, bad)
ok("a status, a non-JSON body and a body that is not a result all come back "
   "as the same empty answer rather than as an exception")

# (e) The service returned a code this build cannot resolve. This is the
#     ordinary case, not the exceptional one: three conditions are coded.
stub = Stub((200, body(CHEST_PAIN)))
unresolvable = client(stub).suggest("chest pain", CONDITION,
                                    transcript="chest pain since morning",
                                    span="chest pain")
assert len(unresolvable) == 0, unresolvable
assert unresolvable.reachable is True, "the service answered; it was us"
assert "29857009" in unresolvable.refused[0], unresolvable.refused
assert "cannot resolve" in unresolvable.refused[0], unresolvable.refused
ok("a code this build cannot resolve is refused by name, and the answer still "
   "says the service was reachable")

# (f) The service returned a candidate from the wrong branch of the ontology.
PROCEDURE = {"term_id": "71388002", "term_name": "Procedure",
             "score": 0.91, "is_linked": True,
             "metadata": {"semantic_tag": "procedure", "is_core": True}}
stub = Stub((200, body(PROCEDURE)))
branch = client(stub).suggest("procedure", CONDITION,
                              transcript="procedure done", span="procedure")
assert len(branch) == 0, branch
assert "is a procedure" in branch.refused[0], branch.refused
ok("a candidate from the wrong branch of the ontology is refused on its "
   "semantic tag, which the value set declares")


# --------------------------------------------------------------------------
# 3. The medicine picker gets nothing from this service, and the reason is
#    two vocabularies rather than a bug. Checked so the day it changes,
#    something says so.
# --------------------------------------------------------------------------

stub = Stub((200, body(DOLO)))
drug = client(stub).suggest("Dolo 650", MEDICINE, transcript="Dolo 650 twice a day",
                            span="Dolo 650",
                            context={"form": "tablet", "generic_name": "paracetamol"})
assert stub.sent[0]["body"]["metadata"] == {"form": "tablet",
                                            "generic_name": "paracetamol"}
assert len(drug) == 0, drug
assert "b-4117370658" in drug.refused[0], drug.refused
ok("a medication candidate is an Eka product id, not a SNOMED concept, so "
   "this build refuses it rather than storing an id nobody can look up")

# A null score is not what refused it: the same body against a value set whose
# system the ontology table does not map is refused before any request is made.
stub = Stub()
unmapped = eka.EkaCodification(token=TOKEN, transport=stub,
                               base="https://api.invalid").suggest(
    "active", "condition-clinical-status", transcript="it is active",
    span="active")
assert len(unmapped) == 0 and stub.sent == [], unmapped
assert "no codification ontology is mapped" in unmapped.refused[0], unmapped.refused
ok("a value set no ontology serves asks nothing at all, rather than asking "
   "the wrong index and refusing what comes back")

# Which value sets those are is not a guess: the table maps a code SYSTEM, so
# every SNOMED and LOINC backed value set is served and the FHIR status sets
# and the UCUM units are not. A clinical status is not a concept anybody
# dictates; it is an answer the doctor gives.
assert eka.ONTOLOGIES.keys() == {"http://snomed.info/sct", "http://loinc.org"}, \
    eka.ONTOLOGIES


# --------------------------------------------------------------------------
# 4. No credential, nothing asked. The developer and the clinic with no Eka
#    account get the same thing: a picker.
# --------------------------------------------------------------------------

stub = Stub()
bare = eka.EkaCodification(token="", transport=stub,
                           base="https://api.invalid").suggest(
    "sugar", CONDITION, transcript=SAID, span="sugar")
assert len(bare) == 0 and bare.reachable is False, bare
assert stub.sent == [], "a request was built with no credential"
assert "no codification credential" in bare.refused[0], bare.refused
ok("no credential: nothing is sent, and the empty answer says why")

# An empty phrase asks nothing either.
stub = Stub()
assert len(client(stub).suggest("   ", CONDITION, transcript=SAID)) == 0
assert stub.sent == [], "a request was built for nothing"
ok("an empty phrase asks nothing")


# --------------------------------------------------------------------------
# 5. The response reader, over the contract's own shapes.
# --------------------------------------------------------------------------

assert eka.results(json.loads(body(DIABETES, CHEST_PAIN))) == [
    {"code": "44054006", "term": "Diabetes mellitus type 2", "score": 0.94,
     "linked": True, "tag": "disorder"},
    {"code": "29857009", "term": "Chest pain", "score": 1, "linked": True,
     "tag": "finding"}], eka.results(json.loads(body(DIABETES, CHEST_PAIN)))
assert eka.results(json.loads(body(DOLO)))[0]["score"] is None, \
    "a medication candidate's score is null in the contract and stays null"
assert eka.results({}) == [] and eka.results(None) == []
assert eka.results({"results": ["not a dict", None, 7]}) == []
# A malformed candidate: a score that is not a number and a linked flag that
# is a string. Neither may reach a candidate in that shape, because a score
# that is a string compares with anything and a truthy string is not a
# service saying it is sure.
ODD = {"term_id": "44054006", "term_name": "DM2", "score": "0.94",
       "is_linked": "no", "metadata": {"semantic_tag": "disorder"}}
read = eka.results(json.loads(body(ODD)))[0]
assert read["score"] is None, read
assert read["linked"] is True and isinstance(read["linked"], bool), read
ok("a score that is not a number is read as unscored, and a linked flag is a "
   "boolean whatever arrived")
ok("the response reader takes the contract's shapes, including a null score, "
   "and drops what is not a candidate")

# The batch shape: one block per query, in request order, never re-matched on
# the echoed query text.
batch = {"results": [json.loads(body(DIABETES)), json.loads(body(CHEST_PAIN)),
                     "not a block"]}
assert [[r["code"] for r in block] for block in eka.batched(batch)] == \
    [["44054006"], ["29857009"]], eka.batched(batch)
ok("a batch answer is one result list per query in request order")

stub = Stub(socket.timeout("timed out"))
assert eka.EkaCodification(token=TOKEN, transport=stub,
                           base="https://api.invalid").registry() == [], \
    "the registry read is for design time and never raises at the clinic"
ok("the registry read answers empty rather than raising")


# --------------------------------------------------------------------------
# 6. It satisfies the seam, and it holds the seam's rule.
# --------------------------------------------------------------------------

made = client(Stub((200, body(DIABETES, DIABETES, CHEST_PAIN, PROCEDURE))))
mixed = made.suggest("sugar", CONDITION, transcript=SAID, span="sugar")
assert isinstance(mixed, codification.Suggestions), mixed
assert [c.coding.code for c in mixed] == ["44054006"], mixed
assert len(mixed.refused) == 2, mixed.refused
assert all(isinstance(c, codification.Candidate) for c in mixed)
ok("one answer carrying a candidate, a duplicate, an unresolvable code and a "
   "wrong branch yields one candidate and two named refusals")

# The span rule reaches across the socket: a phrase the transcript does not
# hold takes every candidate with it, however sure the service was.
sure = client(Stub((200, body(DIABETES))))
lied = sure.suggest("type two diabetes", CONDITION,
                    transcript="the patient has a fever",
                    span="type two diabetes")
assert len(lied) == 0 and "not in the transcript" in lied.refused[0], lied.refused
ok("a candidate for words the transcript does not hold is dropped, even when "
   "the service reported it linked")

print("ok   the codification connector: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run.
# ---------------------------------------------------------------------------
#
# - let a socket failure out of `_request` instead of raising `_Unreachable`:
#   the service-down case stops being an empty answer and becomes a traceback.
# - treat a non-200 status as a result: a 422 becomes zero candidates with
#   `reachable` True, which tells a clinician the service looked and found
#   nothing when it never looked.
# - read `score` without the numeric guard: a string score from a malformed
#   body reaches a candidate.
# - pass the whole `context` dict as `metadata`: a mobile number reaches the
#   request body.
# - ask the SNOMED index for a value set with no mapped ontology: a frequency
#   code is sent to a diagnosis index.
# - drop the `is_linked` cast: a truthy string becomes a linked candidate.
