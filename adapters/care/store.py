"""Adapter 1: kernel.contracts.Store over CARE's REST API.

What is in here and what is not
-------------------------------
No field name. Every one lives in adapters/care/map.py with the mark saying
how it was established, so this file is the machinery: the thread join, the
query grammar to query parameter push down, pagination, and the write bodies.
Read map.py first; this is the boring half.

The thread join, which is this adapter's only cleverness
--------------------------------------------------------
A thread is an encounter, exactly as in adapters/local. CARE's clinical
endpoints are patient scoped (/patient/{p}/observation/) or facility scoped
(/facility/{f}/service_request/), so almost every read needs the encounter's
patient id and facility id first. One GET /api/v1/encounter/{id}/ answers both
and is cached per store instance. No declaration ever states this and none can.

Three honest limits, each with its ceiling named
------------------------------------------------
1. CARE filters what it filters. `{"category": "vital-signs"}` on an
   observation has no query parameter (map.py says why), so those rows are
   fetched and filtered here. count() over such a query pages the whole list.
   ponytail: fine for a PHC's day; if a query ever spans thousands of rows,
   the fix is a count endpoint in CARE, not a cleverer loop here.
2. Six of the Store methods are not CARE's at all. (Ten, not nine: the
   contract's own prose says nine and its Protocol declares ten. Reported,
   not patched; kernel/ is frozen. adapters/care/tests/test_store.py asserts
   the real list.) CARE has no proposal
   queue, no arbitrary per encounter flag, and its audit is its own trail and
   not this one. stored_flags, raise_flag, put_proposal, proposals,
   append_audit and audit are delegated to an injected sidecar store, which by
   default is adapters.local.SqliteStore. That is not a shortcut: those
   records are the kernel's, so a deployment against CARE still has to keep
   them somewhere, and the somewhere already exists and is already tested.
3. Several writes are refused rather than guessed. An observation cannot be
   POSTed to CARE at all; a dispense needs product and location ids a PHC
   payload does not carry. map.py carries the reason and write() raises it.

Verified against a real CARE response?
--------------------------------------
The transport, the pagination envelope and the error shape are: they were read
off https://careapi.ohc.network on 2026-09-11. Every method's FIELD NAMES
carry their own mark in map.py. No method has been run end to end against an
authenticated CARE, because that needs a token and a facility this repo does
not have; per method status is on each method's docstring, and the
`# UNVERIFIED` comments in here are literal.

Python 3.9. Depends on stdlib only.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from adapters.care.map import KERNEL_RECORDS, NO_CARE_RESOURCE, RESOURCES
from kernel.contracts import ThreadRef

PAGE = 100          # rows per request when this adapter has to page
TIMEOUT = 30


class CareError(RuntimeError):
    """A CARE response that was not a success. Carries the status and body so
    a caller sees CARE's own words, which are usually the useful part:
    {"detail": "Authentication credentials were not provided."} is LIVE."""

    def __init__(self, status, body, method="", path=""):
        self.status, self.body = status, body
        super().__init__("CARE %s %s -> %s %s" % (method, path, status, body))


def http_transport(base_url, token, prefix="Bearer"):
    """The default transport: urllib, one call, no session, no dependency.

    A transport is `(method, path, params, body) -> (status, decoded)`. It is
    a plain callable so every check in tests/ runs with no network, which is
    the same property adapters/local has by being a file.

    VERIFIED: the Authorization schemes are the running instance's own
    securitySchemes (tokenAuth wants the prefix "Token", jwtAuth "Bearer"),
    and a 403 with {"detail": ...} was seen live.
    """
    base = base_url.rstrip("/")

    def call(method, path, params=None, body=None):
        url = base + path
        if params:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Authorization", "%s %s" % (prefix, token))
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
                return response.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"detail": raw.decode("utf-8", "replace")}

    return call


class CareStore:
    """kernel.contracts.Store over CARE.

    facility is the CARE facility external id every facility scoped path
    needs; geo_organization is the id PatientCreateSpec requires (SCHEMA) and
    has no clinical meaning to this kernel. abha_config is the patient
    identifier config id that holds an ABHA in this deployment. All three are
    deployment facts, so they are arguments and not constants: a missing one
    makes the affected call raise with the reason, never guess.
    """

    def __init__(self, base_url=None, token=None, *, prefix="Bearer",
                 facility=None, geo_organization=None, abha_config=None,
                 transport=None, sidecar=None):
        if transport is None:
            if not base_url:
                raise ValueError("CareStore needs a base_url or a transport")
            transport = http_transport(base_url, token, prefix)
        self.call = transport
        self.facility = facility
        self.geo_organization = geo_organization
        self.abha_config = abha_config
        self._sidecar = sidecar
        self._context = {}          # thread id -> {"patient", "facility", ...}

    # ------------------------------------------------------------ plumbing

    @property
    def sidecar(self):
        """Where the kernel's own records live. Imported lazily so that
        adapters/care does not depend on adapters/local at import time; the
        default exists so a CareStore is usable without wiring two things."""
        if self._sidecar is None:
            from adapters.local.store import SqliteStore
            self._sidecar = SqliteStore(":memory:")
        return self._sidecar

    def unreachable(self):
        """None if this CARE answers, else one plain sentence saying why not.

        Two probes, and both failure branches are LIVE against
        careapi.ohc.network on 2026-09-11. GET /api/v1/govt/organization/ is
        the one path that instance answers without credentials, so it
        separates "nothing there" from "CARE there, credentials wrong". GET
        /api/v1/facility/ needs a token, and a bad one comes back 401
        {"detail": "Invalid Token, please relogin to continue"}, which is the
        message this returns. UNVERIFIED: the success branch of the second
        probe. No correct token has ever been presented from this repository,
        so "CARE answered 200 to an authenticated read" is a thing this code
        has never seen happen.
        """
        try:
            status, body = self.call("GET", "/api/v1/govt/organization/",
                                     {"limit": 1}, None)
        except Exception as exc:            # URLError, socket.timeout, bad DNS
            return "Nothing answered: %s" % exc
        if status >= 500:
            return "It answered %s, which is CARE failing, not refusing." % status
        if status >= 400:
            return ("It answered %s to a request that needs no credentials, so "
                    "this is probably not a CARE: %s" % (status, body))
        status, body = self.call("GET", "/api/v1/facility/", {"limit": 1}, None)
        if status in (401, 403):
            return "CARE is there and refused CARE_TOKEN: %s" % body
        return None

    def _get(self, path, params=None):
        status, body = self.call("GET", path, params, None)
        if status >= 400:
            raise CareError(status, body, "GET", path)
        return body

    def _post(self, path, body):
        status, out = self.call("POST", path, None, body)
        if status >= 400:
            raise CareError(status, out, "POST", path)
        return out

    def _put(self, path, body):
        status, out = self.call("PUT", path, None, body)
        if status >= 400:
            raise CareError(status, out, "PUT", path)
        return out

    def context(self, thread):
        """The encounter's patient and facility ids, cached.

        One GET per thread per process. VERIFIED shape: EncounterRetrieveSpec
        has `patient` and `facility` (SCHEMA); that each is keyed `id` is
        INFERRED, because the schema types both as a bare object.
        """
        if thread not in self._context:
            row = self._get("/api/v1/encounter/%s/" % thread)
            self._context[thread] = {
                "thread": thread,
                "patient": (row.get("patient") or {}).get("id"),
                "facility": (row.get("facility") or {}).get("id") or self.facility,
                "encounter": row,
            }
        return self._context[thread]

    def _path(self, resource, thread, extra=None):
        spec = RESOURCES[resource]
        context = dict(self.context(thread) if thread else {})
        context.setdefault("facility", self.facility)
        context.update(extra or {})
        try:
            return spec.path.format(**context)
        except KeyError as exc:
            raise CareError(0, "%s needs %s in the path and the thread does not "
                               "supply it" % (resource, exc), "GET", spec.path)

    def _split(self, resource, thread, where):
        """(query parameters CARE can answer, conditions left for this file).

        The push down is per field and declared: a field with a `param` can be
        filtered by equality on the server, one with `range_params` can take
        gte and lt. Everything else comes back and is filtered after
        projection, which is the honest cost of CARE's filter set.
        """
        spec = RESOURCES[resource]
        params, residue = {}, {}
        if thread is not None and spec.thread_param:
            params[spec.thread_param] = thread
        for name, cond in (where or {}).items():
            field = spec.fields.get(name)
            if field is None:
                raise ValueError("%s has no field %r in adapters/care/map.py"
                                 % (resource, name))
            if isinstance(cond, dict):
                pushed = {op: v for op, v in cond.items() if op in field.range_params}
                for op, value in pushed.items():
                    params[field.range_params[op]] = value
                left = {op: v for op, v in cond.items() if op not in pushed}
                if left:
                    residue[name] = left
            elif cond == "*":
                residue[name] = cond
            elif field.param:
                params[field.param] = field.send(cond)
            else:
                residue[name] = cond
        return params, residue

    @staticmethod
    def _matches(row, residue):
        for name, cond in residue.items():
            value = row.get(name)
            if cond == "*":
                if value is None or value == "":
                    return False
            elif isinstance(cond, dict):
                for op, other in cond.items():
                    got, want = str(value), str(other)
                    if op == "gte" and not got >= want:
                        return False
                    if op == "lt" and not got < want:
                        return False
                    if op == "gt" and not got > want:
                        return False
                    if op == "lte" and not got <= want:
                        return False
            elif str(value) != str(cond):
                return False
        return True

    def _project(self, resource, row):
        """A CARE row as the query grammar's field names, values translated
        back into the declarations' vocabulary."""
        spec = RESOURCES[resource]
        return {name: field.read(row) for name, field in spec.fields.items()}

    def _rows(self, resource, thread, where, cap=None):
        """Projected, filtered rows. Pages until CARE runs out or cap is met.

        The envelope is {count, results}: `next` is in the schema but the one
        live response available does not carry it, so it is never followed.
        """
        params, residue = self._split(resource, thread, where)
        path = self._path(resource, thread)
        out, offset = [], 0
        while True:
            page = self._get(path, dict(params, limit=PAGE, offset=offset)) or {}
            results = page.get("results") or []
            for row in results:
                projected = self._project(resource, row)
                if self._matches(projected, residue):
                    out.append(projected)
                    if cap is not None and len(out) >= cap:
                        return out, page.get("count")
            offset += len(results)
            if not results or offset >= (page.get("count") or 0):
                return out, page.get("count")

    # --------------------------------------------------------------- reads

    def count(self, resource, *, thread, where):
        """UNVERIFIED end to end; field names per map.py.

        When CARE can answer the whole query, this is one request and reads
        the envelope's `count` (LIVE). When it cannot, it pages and counts
        here, which is the declared ceiling in this module's docstring.
        """
        self._refuse_unreadable(resource)
        if resource == "patient" and thread is not None:
            # The thread join: a thread has the one patient its encounter
            # points at, or none. Same special case as adapters/local.
            patient = self.context(thread)["patient"]
            if not patient:
                return 0
            row = self._project("patient", self._patient(thread))
            return 1 if self._matches(row, (where or {})) else 0
        if resource == "encounter" and thread is not None:
            row = self._project("encounter", self.context(thread)["encounter"])
            return 1 if self._matches(row, (where or {})) else 0
        params, residue = self._split(resource, thread, where)
        if not residue:
            page = self._get(self._path(resource, thread),
                             dict(params, limit=1)) or {}
            return page.get("count") or 0
        rows, _ = self._rows(resource, thread, where)
        return len(rows)

    def select(self, resource, *, thread, where, fields, limit=50):
        """UNVERIFIED end to end; field names per map.py."""
        self._refuse_unreadable(resource)
        spec = RESOURCES[resource]
        for name in fields:
            if name not in spec.fields:
                raise ValueError("%s has no field %r in adapters/care/map.py"
                                 % (resource, name))
        if resource == "patient" and thread is not None:
            rows = ([self._project("patient", self._patient(thread))]
                    if self.context(thread)["patient"] else [])
            rows = [r for r in rows if self._matches(r, where or {})]
        elif resource == "encounter" and thread is not None:
            rows = [self._project("encounter", self.context(thread)["encounter"])]
            rows = [r for r in rows if self._matches(r, where or {})]
        else:
            rows, _ = self._rows(resource, thread, where, cap=int(limit))
        rows = rows[:int(limit)]
        if not fields:
            return rows
        return [{f: r.get(f) for f in fields} for r in rows]

    def threads(self, *, workflow, scope="today"):
        """UNVERIFIED end to end.

        VERIFIED (SCHEMA): /api/v1/encounter/ takes facility, status,
        created_date_after and ordering, and EncounterListSpec embeds the
        patient object, so a queue is one request and not one per row.

        INFERRED: that `ordering` accepts "-created_date", and the meaning of
        scope "open". CARE's status filter takes a value, not a negation, so
        "not completed" is asked for as the two statuses a PHC's open visit
        can be in. A CARE deployment using `planned` or `on_hold` would need
        that list widened; it is here and not in map.py because it is a
        question about this kernel's word "open", not about CARE's field.
        """
        from adapters.local.store import _start_of      # one dating rule, shared

        params = {"facility": self.facility, "limit": PAGE,
                  "ordering": "-created_date"}
        if scope == "today":
            params["created_date_after"] = _start_of("day")[:10]
        elif scope == "open":
            params["status"] = "in_progress"       # INFERRED, see docstring
        page = self._get("/api/v1/encounter/", params) or {}
        out = []
        for row in page.get("results") or []:
            subject = self._project("encounter", row)
            subject["encounter"] = subject.pop("id", None)
            patient = row.get("patient") or {}
            if patient:
                subject.update({k: v for k, v in
                                self._project("patient", patient).items()
                                if v is not None})
            out.append(ThreadRef(id=row.get("id"), workflow=workflow,
                                 subject=subject,
                                 opened_at=row.get("created_date") or ""))
        return out

    def _patient(self, thread):
        """The thread's patient. No request of its own: EncounterRetrieveSpec
        serialises its patient with PatientRetrieveSpec (SOURCE), so the one
        GET the thread join already made carries the whole person, including
        instance_identifiers. Those are absent from PatientListSpec (SCHEMA),
        so a list could never have answered abha_number anyway.

        The retrieve is kept as a fallback for the shape the list spec would
        give, in case a deployment serialises less than this one does.

        abha_number is synthesised here because CARE has no such field. Which
        identifier config is the ABHA is deployment data; with none configured
        the key is absent rather than guessed at.
        """
        context = self.context(thread)
        row = dict((context["encounter"] or {}).get("patient") or {})
        if self.abha_config and "instance_identifiers" not in row:
            row = dict(self._get("/api/v1/patient/%s/" % context["patient"]) or {})
        if self.abha_config:
            for identifier in row.get("instance_identifiers") or []:
                config = identifier.get("config") or {}
                if self.abha_config in (config.get("id"), config):
                    row["abha_number"] = identifier.get("value")
        return row

    def _refuse_unreadable(self, resource):
        if resource in KERNEL_RECORDS:
            raise ValueError(
                "%s is one of the kernel's own records; CARE keeps none of "
                "them and CareStore serves them from its sidecar, not from a "
                "query. Use stored_flags, proposals or audit." % resource)
        if resource in NO_CARE_RESOURCE:
            raise ValueError("%s: %s" % (resource, NO_CARE_RESOURCE[resource]))
        if resource not in RESOURCES:
            raise ValueError("no CARE endpoint mapped for resource %r" % resource)
        if resource == "specimen":
            raise ValueError("specimen: %s" % RESOURCES["specimen"].note)

    # -------------------------------------------------------------- writes

    def write(self, resource, record, *, thread):
        """One row as the operation's declared mapping produced it, into CARE.

        UNVERIFIED: no write in this adapter has been run against a CARE
        instance, and none was run against the public ones on purpose. The
        bodies are assembled from the POST request schemas the running
        instance publishes, and every required field the kernel's mapping does
        not produce is a `write_defaults` entry in map.py with its own mark.

        A resource CARE cannot create raises with the reason from map.py. That
        is the deliberate half: the failure of care_phc/queries.py was that a
        guess looked exactly like a fact.
        """
        spec = RESOURCES.get(resource)
        if spec is None:
            reason = NO_CARE_RESOURCE.get(resource)
            raise ValueError("%s: %s" % (resource, reason) if reason else
                             "no CARE endpoint mapped for resource %r" % resource)
        if spec.write is None:
            raise NotImplementedError("%s: %s" % (resource, spec.write_reason))
        record = dict(record)
        record.pop("created_by", None)      # CARE stamps the authenticated user
        record.pop("created_date", None)
        unknown = sorted(set(record) - set(spec.write)
                         - set(spec.write_side) - {"id"})
        if unknown:
            # Same rule as adapters/local: a mapped column with nowhere to go
            # is refused, never dropped.
            raise ValueError("%s has no CARE field for %s in adapters/care/map.py"
                             % (resource, ", ".join(unknown)))
        mapped = {}
        for column, target in spec.write.items():
            if column not in record or record[column] in (None, ""):
                continue
            _put_path(mapped, target, spec.fields[column].send(record[column]))
        return getattr(self, "_write_" + resource)(mapped, record, thread)

    def _write_patient(self, mapped, record, thread):
        body = dict(RESOURCES["patient"].write_defaults, **mapped)
        """POST /api/v1/patient/ then attach to the encounter, or PUT when the
        thread already has one (linking an ABHA updates the person registered
        earlier, exactly as in adapters/local).

        geo_organization is required (SCHEMA) and means nothing to this
        kernel, so an unconfigured one refuses rather than posting a body CARE
        will reject with a validation error nobody reads.
        """
        existing = self.context(thread)["patient"]
        if existing:
            patient = existing
            if body:
                self._put("/api/v1/patient/%s/" % patient, body)
        else:
            if not self.geo_organization:
                raise ValueError(
                    "creating a patient needs geo_organization, which "
                    "PatientCreateSpec requires and this kernel has no word "
                    "for. Pass it to CareStore.")
            body["geo_organization"] = self.geo_organization
            patient = (self._post("/api/v1/patient/", body) or {}).get("id")
            encounter = dict(self.context(thread)["encounter"])
            self._put("/api/v1/encounter/%s/" % thread,
                      {"patient": patient, "status": encounter.get("status"),
                       "priority": encounter.get("priority"),
                       "encounter_class": encounter.get("encounter_class"),
                       "facility": self.context(thread)["facility"]})
            self._context.pop(thread, None)
        if record.get("abha_number"):
            if not self.abha_config:
                raise ValueError(
                    "linking an ABHA needs abha_config, the patient identifier "
                    "config id that holds it in this deployment. CARE has no "
                    "abha_number field; POST update_identifier takes "
                    "{config, value} (SCHEMA).")
            self._post("/api/v1/patient/%s/update_identifier/" % patient,
                       {"config": self.abha_config,
                        "value": record["abha_number"]})
        return patient

    def _write_encounter(self, mapped, record, thread):
        """PUT the encounter. The thread IS this row, so it is never created
        here: open_thread() below makes one, and write_defaults belong to a
        create and must not overwrite a live encounter's own status.

        CARE's update is a PUT over a spec with five required fields (SCHEMA),
        so the unchanged ones are carried over from the encounter as it
        stands. INFERRED: that PUT is a full replace and not a merge; PATCH
        exists on the same path and would be the smaller call if it is.
        """
        current = dict(self.context(thread)["encounter"])
        merged = {"status": current.get("status"),
                  "priority": current.get("priority"),
                  "encounter_class": current.get("encounter_class"),
                  "external_identifier": current.get("external_identifier"),
                  "patient": (current.get("patient") or {}).get("id"),
                  "facility": self.context(thread)["facility"]}
        merged.update(mapped)
        self._put("/api/v1/encounter/%s/" % thread, merged)
        self._context.pop(thread, None)
        return thread

    def _write_condition(self, mapped, record, thread):
        body = dict(RESOURCES["condition"].write_defaults, **mapped)
        body["encounter"] = thread
        return (self._post(self._path("condition", thread), body) or {}).get("id")

    def _write_notes(self, mapped, record, thread):
        """A note needs a NoteThread first: CARE nests messages under one, and
        care_phc/queries.py's `encounter.notes` does not exist."""
        context = self.context(thread)
        path = "/api/v1/patient/%s/thread/" % context["patient"]
        page = self._get(path, {"encounter": thread, "limit": 1}) or {}
        results = page.get("results") or []
        note_thread = (results[0].get("id") if results else
                       (self._post(path, {"title": "Consultation",
                                          "encounter": thread}) or {}).get("id"))
        return (self._post(self._path("notes", thread,
                                      {"note_thread": note_thread}), mapped)
                or {}).get("id")

    def _write_medication_request(self, mapped, record, thread):
        body = dict(RESOURCES["medication_request"].write_defaults, **mapped)
        from datetime import datetime, timezone
        body["encounter"] = thread
        body.setdefault("authored_on",
                        datetime.now(timezone.utc).isoformat(timespec="seconds"))
        # medication is a Coding: the display carries the human string the
        # payload had, and code is required on a Coding (SCHEMA). Without a
        # coded medicine there is nothing honest to put in `code`.
        medication = (body.get("medication") or {}).get("display")
        if medication:
            body["medication"] = {"code": medication, "display": medication}
        return (self._post(self._path("medication_request", thread), body)
                or {}).get("id")

    def _write_service_request(self, mapped, record, thread):
        body = dict(RESOURCES["service_request"].write_defaults, **mapped)
        body["encounter"] = thread
        code = (body.get("code") or {}).get("code")
        if code:
            body["code"] = {"code": code, "display": code}
            body.setdefault("title", code)
        return (self._post(self._path("service_request", thread), body)
                or {}).get("id")

    def _write_diagnostic_report(self, mapped, record, thread):
        body = dict(RESOURCES["diagnostic_report"].write_defaults, **mapped)
        """service_request is required on POST (SCHEMA): a report answers an
        order. The most recent active order on the thread is used, and with
        none the write is refused rather than orphaned."""
        orders, _ = self._rows("service_request", thread, {}, cap=None)
        if not orders:
            raise ValueError(
                "a diagnostic report must point at a service_request "
                "(required, SCHEMA) and this thread has no order to answer.")
        body["service_request"] = orders[-1]["id"]
        code = (body.get("code") or {}).get("code")
        if code:
            body["code"] = {"code": code, "display": code}
        return (self._post(self._path("diagnostic_report", thread), body)
                or {}).get("id")

    def open_thread(self, *, token=None, actor=None, patient=None):
        """Start a visit. Not one of the nine: the Store protocol has no way
        to say "open a thread", the same gap adapters/local reports.

        UNVERIFIED. EncounterCreateSpec requires status, priority, patient,
        facility and encounter_class (SCHEMA), and `patient` being required is
        the difference from adapters/local, where a walk in opens an encounter
        with no person on it yet. A CARE thread cannot exist before its
        patient does, so the PHC's "register at reception" step has to create
        the person first. That is a real ordering constraint on the bundle,
        not something to paper over here.
        """
        if not patient:
            raise ValueError(
                "CARE requires a patient on an encounter (EncounterCreateSpec, "
                "SCHEMA), so a thread cannot be opened before the person "
                "exists. adapters/local allows it; CARE does not.")
        body = {"patient": patient, "facility": self.facility,
                "status": "in_progress", "priority": "routine",
                "encounter_class": "amb"}
        if token:
            body["external_identifier"] = token
        return (self._post("/api/v1/encounter/", body) or {}).get("id")

    # ------------------------------- the kernel's own records, via sidecar
    # CARE keeps none of these. Delegated verbatim; see map.KERNEL_RECORDS
    # and this module's docstring for why that is the answer and not a dodge.

    def stored_flags(self, thread):
        return self.sidecar.stored_flags(thread)

    def raise_flag(self, thread, flag, *, actor=None):
        return self.sidecar.raise_flag(thread, flag, actor=actor)

    def put_proposal(self, proposal):
        return self.sidecar.put_proposal(proposal)

    def proposal(self, proposal_id):
        return self.sidecar.proposal(proposal_id)

    def proposals(self, thread, *, status=None):
        return self.sidecar.proposals(thread, status=status)

    def append_audit(self, record):
        return self.sidecar.append_audit(record)

    def audit(self, thread):
        return self.sidecar.audit(thread)


def _put_path(body, dotted, value):
    """Set a dotted target in a request body, making the containers on the way.

    A numeric segment means a list, because some of CARE's required fields are
    arrays of one: dosage_instruction is `[{...}]` (SCHEMA), and writing
    {"dosage_instruction": {"0": {...}}} would be silently wrong.
    """
    parts = dotted.split(".")
    for part, nxt in zip(parts[:-1], parts[1:]):
        if nxt.isdigit():
            body = body.setdefault(part, [])
            while len(body) <= int(nxt):
                body.append({})
        elif part.isdigit():
            body = body[int(part)]
        else:
            body = body.setdefault(part, {})
    last = parts[-1]
    if last.isdigit():
        while len(body) <= int(last):
            body.append(None)
        body[int(last)] = value
    else:
        body[last] = value


# --------------------------------------------------------------------------
# Opening one from the environment. This is the only place that knows which
# environment variables name a CARE, and it is here rather than in api/ so
# that the probe below can use CARE's own paths.
# --------------------------------------------------------------------------

class CareUnreachable(RuntimeError):
    """There is no CARE to talk to, and the caller should be told in a
    sentence rather than a traceback. Raised before the kernel starts, never
    during a request."""


def open_care(env=None, db=None):
    """A CareStore from CARE_* in the environment, proven to answer.

    The kernel's own records (proposals, flags, audit) are not CARE's, so the
    sidecar is the same SQLite file adapter 0 would have used. Everything
    clinical goes over the network.
    """
    env = os.environ if env is None else env
    base, token = env.get("CARE_BASE_URL"), env.get("CARE_TOKEN")
    if not base or not token:
        missing = " and ".join(n for n, v in (("CARE_BASE_URL", base),
                                              ("CARE_TOKEN", token)) if not v)
        raise CareUnreachable(
            "PHC_STORE=care needs %s, and nothing set it.\n" % missing +
            "There is no CARE in this repository. Either point it at one:\n"
            "  CARE_BASE_URL=https://careapi.ohc.network CARE_TOKEN=... "
            "PHC_STORE=care sh api/run.sh\n"
            "or run on the SQLite adapter, which needs nothing: sh api/run.sh")
    from adapters.local.store import SqliteStore
    store = CareStore(
        base,
        token,
        prefix=env.get("CARE_AUTH_PREFIX", "Bearer"),
        facility=env.get("CARE_FACILITY"),
        geo_organization=env.get("CARE_GEO_ORGANIZATION"),
        abha_config=env.get("CARE_ABHA_CONFIG"),
        sidecar=SqliteStore(db or env.get("PHC_DB", "phc.sqlite3")),
    )
    reason = store.unreachable()
    if reason:
        raise CareUnreachable(
            "Cannot use CARE at %s.\n%s\n"
            "Fix that, or run on the SQLite adapter instead: sh api/run.sh"
            % (base, reason))
    return store
