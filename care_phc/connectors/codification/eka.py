"""Eka's Medical Entity Codification endpoint, behind kernel.codification.

The surface, read from the contract rather than guessed
------------------------------------------------------
The OpenAPI specification at
`/openapi/api-reference/health-ai/medical-entity-codification/med-link.yaml`
on developer.eka.care, read 2026-10-31, plus the ontology guides beside it:

    GET  /med-link/registry/        the live ontologies and their versions
    POST /med-link/nel/link         one entity
    POST /med-link/nel/link/batch   up to 5 entities, one ontology for all

Request: `{query, ontology, version, top_k, metadata, request_id}`. `top_k`
is 1 to 10, default 5. `metadata` is "strongly recommended for LOINC", where
a unit can change which code is linked, optional for medication, and ignored
by SNOMED CT and ICD-10-CM.

Response: `{request_id, query, query_breakdown, ontology, version,
index_name, model_version, results: [{term_id, term_name, score, is_linked,
metadata}]}`. Three facts from that contract shape this file:

- **`score` is documented as nullable, and null for every medication
  candidate**, where "matching is reported through `metadata.matching_breakdown`
  instead". So a null score is ordinary and is not a reason to refuse or to
  rank differently. `kernel/codification.py` carries it and compares it to
  nothing, which is why that is easy.
- **`term_id` is the ontology's code, and for the `medication` ontology the
  ontology is Eka's own.** A medication candidate comes back as `b-4117370658`,
  an Eka product id, not a SNOMED concept. This build's medicine value set is
  SNOMED, so **every medication candidate from this service is refused as
  unresolvable.** That is not a defect in either side; it is two different
  vocabularies, and the seam's job is to refuse rather than to store an id
  the record's reader cannot look up. Said plainly here because it means the
  medicine picker gets nothing from codification today. The route out is
  CDCI, Common Drug Codes for India, which the coded data plan already names
  as the right medication vocabulary for ABDM and which needs the MLDS
  licence this build does not hold.
- **SNOMED candidates carry `metadata.semantic_tag`**, documented as the
  concept's category: `finding`, `disorder`, `procedure`. That is what the
  wrong-branch refusal reads, against the tags the value set declares.

What Eka says this service is for, which is the whole design
-----------------------------------------------------------
From the Scope and Limitations of /docs/models/medical-entity-codification,
read 2026-10-31: it "Provides candidate codes; clinical validation remains
with the integrator", and is "Not a substitute for professional medical coding
judgment". This connector therefore returns candidates and nothing else. It
cannot write, cannot fill a field, and has no path to a payload.

Failure is not an exception here, and that is deliberate
--------------------------------------------------------
Unlike `care_phc/connectors/scribe/base.py`, which raises on a timeout so a
doctor is told "we do not know yet" rather than "nothing was heard", every
failure on this path becomes an EMPTY `Suggestions` with `reachable=False` and
a sentence. The asymmetry is the product: a scribe that fails leaves a doctor
with nothing but the form, so the difference matters; a codifier that fails
leaves a doctor with the picker, which is what they had anyway. Raising here
would mean every caller needs a try, and one caller forgetting it would turn a
bad line into a broken consultation. So the offline path is the return value.

Bounded on purpose. The timeout below is short, because this call sits between
a clinician and a list they could have scrolled instead.

UNVERIFIED AGAINST THE LIVE SERVICE. Not one request in this file has been
made against api.eka.care from this branch, by instruction: the gate must stay
offline and deterministic, and the credential is not this module's to spend.
What is checked is every translation either side of the socket, against
response bodies taken from the published contract's own examples. `check.py`
beside this file is that check, and it says which bodies came from where.
Treat a first live run as the verification step and record what came back
here, the way api/scribe.py records it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from kernel import codification

BASE = os.environ.get("EKA_CODIFICATION_BASE", "https://api.eka.care")
LINK = "/med-link/nel/link"
BATCH = "/med-link/nel/link/batch"
REGISTRY = "/med-link/registry/"

# Short, because a clinician is waiting and the alternative to this call is a
# list they can already scroll. Not a measured number: no request in this file
# has been made for real, so this is a ceiling on a guess rather than a
# tuning. Raise it only with a measurement.
TIMEOUT = 4

# How many candidates to ask for. The contract allows 1 to 10 and defaults to
# 5. Five is kept, because the person reads the list and a list nobody can
# scan is the same as no list.
TOP_K = 5

# Which ontology serves a value set, by the value set's own code system. The
# key is a system URI, which is the one thing a value set and an ontology
# agree on, so no clinical word and no value set slug appears here. The
# versions are the ones the contract documents; the docs also say to call
# `GET /med-link/registry/` to confirm the live values, which `registry()`
# below does and which nothing in the gate can.
ONTOLOGIES = {
    "http://snomed.info/sct": ("snomed", "20250401_extended"),
    "http://loinc.org": ("loinc", "v1.0"),
}


class EkaCodification:
    """kernel.codification.Codification over Eka's linking endpoint.

    `transport` is the seam inside the seam: a callable taking
    (method, url, headers, body) and returning (status, text). The default
    opens a socket; a check passes one that does not, so the whole of this
    file's request building and response reading is exercised without a
    credential and without a network. Same reason `kernel/terminology.py`
    takes a terminology: a check passes a stand-in instead of monkey patching
    a module global.
    """

    def __init__(self, *, token=None, base=BASE, transport=None,
                 terminology=None, top_k=TOP_K, timeout=TIMEOUT,
                 ontologies=None):
        self.token = token or os.environ.get("EKA_ACCESS_TOKEN") or ""
        self.base = base.rstrip("/")
        self.transport = transport or _urlopen
        self.terminology = terminology
        self.top_k = max(1, min(int(top_k), 10))
        self.timeout = timeout
        self.ontologies = dict(ontologies or ONTOLOGIES)

    # ------------------------------------------------------------ the seam
    def suggest(self, text, valueset, *, context=None, transcript="", span=""):
        """Candidates for one heard phrase, or an empty answer with a reason.

        Never raises. Every way this can fail ends as an empty `Suggestions`,
        and `reachable` says whether the service could be asked at all.
        """
        said = str(text or "").strip()
        if not said:
            return codification.Suggestions(asked=said)
        try:
            ontology, version = self._ontology(valueset)
        except KeyError as broke:
            return codification.Suggestions(asked=said, refused=[str(broke)])
        if not self.token:
            return codification.Suggestions(
                asked=said, reachable=False,
                refused=["no codification credential is configured, so nothing "
                         "was asked. Pick from the list."])
        body = {"query": said, "ontology": ontology, "version": version,
                "top_k": self.top_k}
        hints = _hints(context)
        if hints:
            body["metadata"] = hints
        try:
            answer = self._post(LINK, body)
        except _Unreachable as broke:
            return codification.Suggestions(asked=said, reachable=False,
                                            refused=[str(broke)])
        return codification.resolve(
            results(answer), valueset, transcript=transcript,
            span=span or said, text=said, terminology_=self.terminology)

    def registry(self):
        """The live ontologies and versions, for a design time check that the
        table above is still right. Not called at the point of care: a clinic
        that has to ask which version of SNOMED exists before it can offer a
        picker has made codification load bearing."""
        try:
            return self._get(REGISTRY).get("ontologies") or []
        except _Unreachable:
            return []

    # ------------------------------------------------------------ the socket
    def _ontology(self, valueset):
        system = _system(valueset, self.terminology)
        found = self.ontologies.get(system)
        if not found:
            raise KeyError(
                "no codification ontology is mapped to %s, so nothing was "
                "asked for %s" % (system, valueset))
        return found

    def _post(self, path, body):
        return self._request("POST", path, body=body)

    def _get(self, path):
        return self._request("GET", path)

    def _request(self, method, path, *, body=None):
        url = "%s%s" % (self.base, path)
        headers = {"Authorization": "Bearer %s" % self.token,
                   "Content-Type": "application/json",
                   "Accept": "application/json"}
        try:
            status, text = self.transport(
                method, url, headers,
                json.dumps(body).encode() if body is not None else None,
                self.timeout)
        except Exception as broke:
            # No line, DNS, a TLS failure, a socket timeout. The clinic keeps
            # going and the picker is what it had anyway. The message carries
            # no response body, because a body on this path echoes the
            # clinician's own words back into a log line.
            raise _Unreachable("the codification service could not be reached "
                               "(%s). Pick from the list."
                               % type(broke).__name__)
        if status != 200:
            # 422 is the contract's validation error and anything else is the
            # gateway. Both are "answered and gave us nothing usable", and
            # neither is a sentence with the service's own text in it.
            raise _Unreachable("the codification service answered %d, so "
                               "nothing was suggested. Pick from the list."
                               % status)
        try:
            found = json.loads(text or "{}")
        except ValueError:
            raise _Unreachable("the codification service answered with "
                               "something that is not JSON, so nothing was "
                               "suggested. Pick from the list.")
        if not isinstance(found, dict):
            raise _Unreachable("the codification service answered with "
                               "something that is not a result, so nothing "
                               "was suggested. Pick from the list.")
        return found


class _Unreachable(RuntimeError):
    """Module private: every failure becomes an empty answer before it
    leaves this file, so no caller ever sees this type."""


def results(answer):
    """One `NELResponse` turned into the shape `kernel.codification.resolve`
    takes. The whole of the wire format's vocabulary lives in this function.

    `term_id` is the code, `term_name` the service's own name for it,
    `is_linked` its confidence that this is the single right match, and the
    semantic tag comes out of the candidate's `metadata`, where SNOMED
    candidates carry it. A result that is not a dictionary is dropped here
    rather than refused by name: it is not a candidate, it is a parse failure.
    """
    out = []
    for raw in (answer or {}).get("results") or []:
        if not isinstance(raw, dict):
            continue
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        score = raw.get("score")
        out.append({
            "code": raw.get("term_id"),
            "term": raw.get("term_name") or "",
            "score": score if isinstance(score, (int, float)) else None,
            "linked": bool(raw.get("is_linked")),
            "tag": meta.get(codification.SEMANTIC_TAG) or "",
        })
    return out


def batched(answer):
    """One `NELBatchResponse` as a list of per query result lists, in request
    order. The contract guarantees one block per query in order; nothing here
    re-matches them by `query`, because the contract's own words are "in
    request order" and matching on the echoed text would silently mis-pair two
    rows of a prescription that say the same thing."""
    return [results(block) for block in (answer or {}).get("results") or []
            if isinstance(block, dict)]


def _hints(context):
    """The `metadata` hints, filtered to the keys the contract documents.

    A dictionary straight from a caller would put whatever the caller had into
    a request body, and what a caller has on this path is a consultation. So
    the keys are an allowlist and the values are strings.
    """
    allowed = ("unit", "value", "specimen", "form", "generic_name", "dose_unit")
    return {k: str(v) for k, v in (context or {}).items()
            if k in allowed and v not in (None, "")}


def _system(valueset, terminology=None):
    """The code system a value set is drawn from, read off the value set."""
    t = terminology or _local()
    try:
        return t.system(valueset)
    except AttributeError:
        pass
    # Every Terminology can answer this through its one constructor, by
    # binding any concept it holds: the system is on the Coding. Slower and
    # it needs no second method on the protocol.
    for code in t.concepts(valueset):
        return t.bound(valueset, code).system
    return ""


def _local():
    from kernel import terminology
    return terminology.LOCAL


def _urlopen(method, url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, method=method,
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return answer.status, answer.read().decode()
    except urllib.error.HTTPError as broke:
        # An HTTP status is an answer, so it comes back as one and the caller
        # decides. The body is never read: on this path it echoes the
        # clinician's own phrase.
        return broke.code, ""
