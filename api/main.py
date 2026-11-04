"""The HTTP service. The kernel with a socket on it, and nothing else.

Every route here is a shell. The decision is kernel/proposals.py, which is
catalogue.guard.evaluate; the thread is kernel/state.py; a queue, a summary and
a dashboard are kernel/views.py; the rows are adapters/local. This module
parses a request, checks the caller's capability to open a view, and turns a
Decision into a status code. There is no clinical logic in it and there must
never be any: an endpoint that knows what a vital sign is has taken work away
from a declaration.

The one rule this file preserves by having no code of its own
--------------------------------------------------------------
The guard is the only write path. Two routes reach the store, and both call
kernel.proposals, which hard codes the rendered surface:

  POST /api/operations/{op}/commit    a person tapped commit
  POST /api/proposals/{id}/confirm    a person accepted a machine's proposal

propose() writes a proposal and an audit line and no clinical row. confirm()
refuses an id propose never issued (404) and a proposal that is not pending
(409), so a double tap, a retry or a replayed request cannot write twice.

Voice never appears here, which is the point: an instrument produces a Draft
in the renderer, a person reads it back on screen and taps, and the tap
arrives as an ordinary commit through the same validator as the keypad.

Run: api/run.sh   (uvicorn api.main:app --port 8000)
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from adapters.local.store import SqliteStore, seed
from agent import turn
from api import fill, notes, outbox, paper, scribe, vault
from catalogue import validate, vocab
from kernel import (declarations, directory, plugins, queues, spine, proposals,
                    state, terminology, tokens, views)
from kernel.contracts import DirectoryError, ThreadRef

BUNDLE = declarations.load(os.environ.get("PHC_BUNDLE", "phc"))
WORKFLOW = BUNDLE.workflow()
DB = os.environ.get("PHC_DB", "phc.sqlite3")

# A sub-centre nurse who is also the pharmacist and runs the lab is the normal
# case and not an edge case (addendum SSC), so the demo account holds the
# union. Pass ?role=nurse or X-PHC-Role to narrow it and watch actions vanish.
#
# The union is over every declared role, not a hand written five. Naming five
# quietly withheld lab.result.validate and visit.household, which meant the
# renderer (which has no role switch) got a 403 on any view declaring them:
# the lab bundle's own dashboard was unreachable from the only account the
# browser can be.
DEMO_ROLE = "demo"
ROLES = dict(vocab.BUNDLES)
# Every declared capability, not just the ones a preset happens to carry:
# "Every capability (demo)" is the label the sidebar already puts on this
# role, and facility.admin (needed to reach the endpoints below) sits in no
# preset on purpose, so the union of presets alone would leave the demo
# account unable to open its own role editor.
#
# demo is deliberately a superuser sandbox and not one more preset: it is the
# account this kernel hands out with no login at all, so it is safe only
# because there is no authentication yet. facility.admin sits in no preset on
# purpose (it names no operation and neither _decide nor guard.evaluate ever
# reads it, so on its own it unlocks no kernel write path, only /roles below),
# but a capability added here in the future lands in demo's hands too without
# anyone deciding that on purpose. The day a caller can be someone in
# particular, this line is the one to narrow first.
ROLES[DEMO_ROLE] = sorted(vocab.CAPABILITIES)

# A facility's own combination, saved away from the shipped presets in
# ROLES/BUNDLE.roles. Never mutate a preset: bundle.yaml ships as CARE
# is_system=True roles and a facility's deviation is its own is_system=False
# row, which sync_permissions_roles deliberately never touches.
#
# ponytail: in-process overrides, one facility per kernel. Persist to the
# store (a CARE-backed role, or a row beside phc.sqlite3) when a second
# facility shares this process.
OVERRIDES: dict[str, list[str]] = {}

# The examples the scribe screen shows, when a centre has changed them from
# what bundle.yaml ships. Same shape and same honesty as OVERRIDES above:
# in-process, one facility per kernel, lost on restart, and to be persisted
# beside phc.sqlite3 when a second facility shares this process. It is
# written down rather than hidden because a centre that edits its own
# prompts and finds them gone on Monday will not edit them again.
#
# {station: [{"field": ..., "say": ...}]}. A station absent here uses the
# bundle's own, which is the only reason a fresh kernel shows anything.
NUDGES: dict[str, list[dict]] = {}


# Which system of record. There is one: `local`, the SQLite file this
# repository ships with. The CARE adapter was deleted because patients now live
# in Eka's directory, so it had no remaining job and was not in the default
# path. PHC_STORE is still read, and still refuses a value it cannot serve,
# because the seam it names is the thing of value: the kernel only ever sees
# kernel.contracts.Store, so a second adapter is a new file and no edit here.
# The FHIR shaped resource names it mapped onto (patient, encounter,
# observation, medication_dispense, inventory_item) are kept in
# catalogue/vocab.py. Removing the adapter was not removing the model.
STORE = os.environ.get("PHC_STORE", "local")


def make_store():
    """A store, seeded on first use so the queue is never an empty screen."""
    if STORE != "local":
        raise SystemExit(
            "\nPHC_STORE=%r is not an adapter. There is one: local.\n" % STORE)
    store = SqliteStore(DB)
    if not store.db.execute("SELECT 1 FROM encounter").fetchone():
        seed(store)
    return store


store = make_store()
router = APIRouter()


# ------------------------------------------------------------------ helpers

def caller(request: Request) -> dict:
    """Who is asking. There is no authentication tonight, and pretending
    otherwise would be worse than saying so: the role comes from a header or a
    query parameter and the service is meant for localhost."""
    role = (request.headers.get("X-PHC-Role")
            or request.query_params.get("role") or DEMO_ROLE)
    if role not in ROLES:
        raise HTTPException(400, "no such role %r" % role)
    # The one subtraction. A plugin this facility does not run is a capability
    # the caller does not hold, and it is taken away here, before anything
    # reads the set: the guard, `visible()`, the quick action row, /whoami and
    # therefore the MCP tool list, and every view's own capability gate. There
    # is no render time hide to implement and nothing to forget.
    caps = plugins.effective(OVERRIDES.get(role, ROLES[role]), BUNDLE.withheld)
    return {"id": request.headers.get("X-PHC-Actor") or "user:%s" % role,
            "role": role, "capabilities": caps, "scopes": sorted(caps)}


def operation_or_404(op_id: str) -> dict:
    if op_id not in BUNDLE.operations:
        raise HTTPException(404, "unknown operation %r" % op_id)
    return BUNDLE.operations[op_id]


def ref_or_404(thread: str) -> ThreadRef:
    """The thread, with the subject fields a view or a panel may show."""
    rows = store.select("encounter", thread=thread, where={}, fields=[], limit=1)
    if not rows:
        raise HTTPException(404, "no such thread %r" % thread)
    subject = {"encounter": thread, "token": rows[0].get("token"),
               "status": rows[0].get("status"), "arrival": rows[0].get("arrival")}
    patient = store.select("patient", thread=thread, where={}, fields=[], limit=1)
    if patient:
        # WITHOUT `operation`, for the reason adapters/local/store.threads
        # gives at the other place a subject is built: it is which form
        # opened the row, so a correction can find it, and it is not a fact
        # about the person. It reached the context rail as a line reading
        # "Operation: phc.op.patient-register" beside somebody's village,
        # which is our schema printed at a clinician. api/tests/test_api.py
        # holds both paths to it.
        subject.update({k: v for k, v in patient[0].items() if k != "operation"})
    return ThreadRef(id=thread, workflow=WORKFLOW.id, subject=subject,
                     opened_at=rows[0].get("created_date") or "")


def panel(thread: str, user: dict) -> dict:
    # The caller's id, not just their capabilities: an action whose
    # precondition names an actor ("not actor of lab.op.result-enter") is then
    # ABSENT for the person it excludes rather than drawn and refused on the
    # tap. Invisible before its precondition, never greyed out.
    view = state.thread_view(store, ref_or_404(thread), WORKFLOW, BUNDLE.operations,
                             caps=set(user["capabilities"]), actor=user["id"])
    return dict(view.to_json(), nudge=_nudge(view))


def _nudge(view):
    """One line of wayfinding. The renderer may ignore it."""
    if view.station is None:
        return "Line complete."
    here = [op for op in view.actions if op["station"] == view.station]
    if not here:
        return "Waiting at %s. Nobody with your capabilities can act here." % view.station
    return "%s: %s" % (view.station, here[0]["title"])


def thread_of(body: dict) -> str:
    """The MCP server sends `patient`, the renderer sends `thread`. Both mean
    the id of the thread, which for this workflow is an encounter."""
    thread = body.get("thread") or body.get("encounter") or body.get("patient")
    if not thread:
        raise HTTPException(400, "body needs a thread id")
    ref_or_404(thread)
    return thread


def allowed_or_422(decision):
    if not decision:
        # The guard's reason is the useful thing to hand back, to a person and
        # to an agent alike.
        raise HTTPException(422, decision.reason)
    return decision


# -------------------------------------------------------------------- reads

@router.get("/facility")
def facility(request: Request):
    """The bundle this kernel loaded, its views, and who the caller is."""
    user = caller(request)
    return {"bundle": dict(asdict(BUNDLE.manifest), workflow=WORKFLOW.id),
            # Which shape of this facility is running, and what it withholds.
            # The caller's own narrowed set is in `user`; these two say why it
            # is narrower than `capabilities` below, which stays the whole of
            # what the bundle declares.
            "facility": BUNDLE.facility,
            "withheld": dict(sorted(BUNDLE.withheld.items())),
            # The same fact in the bundle's own words, so a screen can say
            # which thing this centre does not run rather than printing a
            # plugin id at a clinician. The role editor reads it: a switch for
            # a withheld capability is disabled with this title in the
            # sentence, instead of being offered and then refused by the guard.
            "without": dict(BUNDLE.without),
            "capabilities": sorted(vocab.CAPABILITIES),
            "views": [{"id": v.id, "kind": v.kind, "title": v.title,
                       "capability": v.capability} for v in BUNDLE.views.values()],
            # Who covers which habitation at THIS centre, as its own
            # declaration wrote it. Facility configuration, not a patient's
            # record: it says which sub-centre, ANM and ASHA a village has,
            # and a centre that declares none sends none.
            "catchment": ((BUNDLE.facilities.get("declared") or {})
                          .get(BUNDLE.facility) or {}).get("catchment"),
            "roles": sorted(ROLES), "user": user}


@router.get("/roles")
def roles_route(request: Request):
    """The shipped presets, a facility's own deviations, and who is asking.

    Presets are bundle.yaml's `roles:` (vocab.BUNDLES), read only here. A
    facility's own combination is saved separately, in OVERRIDES, which is
    what CARE's sync_permissions_roles deliberately does not touch either.
    Both come back: an editor that seeds only from `presets` shows a role
    exactly as it shipped even after a facility has deliberately moved away
    from it, and the next unrelated save silently restores what was removed."""
    return {"presets": dict(vocab.BUNDLES), "overrides": dict(OVERRIDES),
            "current": caller(request)["role"]}


@router.put("/roles/{role}")
def set_role(role: str, body: dict, request: Request):
    user = caller(request)
    if "facility.admin" not in user["capabilities"]:
        raise HTTPException(403, "missing capability facility.admin")
    if role not in ROLES:
        raise HTTPException(404, "no such role %r" % role)
    caps = sorted(set(body.get("capabilities") or []))
    unknown = [c for c in caps if c not in vocab.CAPABILITIES]
    if unknown:
        raise HTTPException(400, "not capabilities of this bundle: %s" % unknown)
    OVERRIDES[role] = caps          # facility role, never the preset
    return {"role": role, "capabilities": caps}


@router.put("/scribe/nudges/{station}")
def set_nudges(station: str, body: dict, request: Request):
    """A centre's own examples for one station's recording screen.

    Guarded on `facility.admin` like the role editor, and for the same
    reason: this is a change to how the centre works, not to one visit.

    It stores SENTENCES and nothing else. Nothing here can name an
    operation, a capability or a flag, so the worst a bad edit can do is
    put unhelpful words on a screen -- which is why it needs no lint
    beyond the two fields being there.
    """
    user = caller(request)
    if "facility.admin" not in user["capabilities"]:
        raise HTTPException(403, "missing capability facility.admin")
    if station not in BUNDLE.scribe:
        raise HTTPException(404, "no such station %r" % station)
    given = body.get("nudges")
    if not isinstance(given, list):
        raise HTTPException(400, "nudges must be a list")
    cleaned = []
    for n in given:
        field = str((n or {}).get("field") or "").strip()
        say = str((n or {}).get("say") or "").strip()
        if not field or not say:
            raise HTTPException(400, "each example needs a field and a sentence")
        cleaned.append({"field": field[:40], "say": say[:200]})
    NUDGES[station] = cleaned
    return {"station": station, "nudges": cleaned}


@router.get("/whoami")
def whoami(request: Request):
    """What the MCP server reads to build its tool list. Shape is frozen."""
    return {"capabilities": caller(request)["capabilities"]}


@router.get("/catalogue")
@router.get("/operations")
def catalogue():
    """The compiled catalogue: the operations, and the four declaration types
    that join them."""
    compiled = dict(declarations.compile_json(BUNDLE),
                    capabilities=sorted(vocab.CAPABILITIES), bundles=vocab.BUNDLES,
                    states=sorted(vocab.STATES), operations=BUNDLE.operations)
    # A centre's own examples replace the bundle's, station by station, so
    # editing the doctor's prompts leaves the nurse's as they shipped.
    if NUDGES:
        scribe_cfg = {k: dict(v) for k, v in (compiled.get("scribe") or {}).items()}
        for station, nudges in NUDGES.items():
            if station in scribe_cfg:
                scribe_cfg[station]["nudges"] = nudges
        compiled["scribe"] = scribe_cfg
    return compiled


@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, request: Request):
    return panel(thread_id, caller(request))


@router.get("/subjects/{subject_id}")
def get_subject(subject_id: str, request: Request):
    """The spine: one subject, and every visit it has had.

    A thread is one encounter, which is the right unit for the guard and the
    wrong one for a person. What joins encounters is declared by the workflow
    (`spine:`), never assumed here, so a bundle that declares none gets a 404
    rather than a screen built on a guess.

    Read only, and scoped by the same capability that opens a thread: this
    returns clinical state across visits, so it is not more public than one.
    """
    user = caller(request)
    workflow = WORKFLOW
    if not spine.declared(workflow):
        raise HTTPException(404, "this bundle declares no spine")
    if "patient.find" not in set(user["capabilities"]):
        raise HTTPException(403, "missing capability patient.find")
    found = spine.of(BUNDLE, store, workflow, subject_id)
    if not found:
        raise HTTPException(404, "unknown subject %r" % subject_id)
    return found


@router.get("/patients")
def patients_route(request: Request, limit: int = 200):
    """This centre's own register: every patient it holds, newest first.

    The patients screen is a hierarchy -- a person, and the visits they have
    had -- and this is the top of it. The visits are NOT here: a register of
    two thousand people would carry every encounter any of them ever had to
    draw a list, so a row says how many and when the last one was, and
    `GET /subjects/{id}` is what opening one asks for. That is the same
    endpoint the thread's own spine uses, so the two cannot disagree about
    somebody's history.

    Guarded on `patient.find`, like the spine and for the same reason: this
    answers "who has this centre seen", which is more than any one visit
    shows and is not a more public question than one patient's record.

    A SCAN, and honest about it, exactly as kernel/directory.cached is: the
    query grammar has equality and presence and no ordering, so the rows are
    read and sorted here. Right for a health centre's own register, which is
    thousands of rows at the outside, and wrong for a district. The fix when
    it matters is in the grammar, in one place.
    """
    user = caller(request)
    if "patient.find" not in set(user["capabilities"]):
        raise HTTPException(403, "missing capability patient.find")
    spine_resource = spine.declared(WORKFLOW)
    if not spine_resource:
        raise HTTPException(404, "this bundle declares no spine")

    rows = store.select(spine_resource, thread=None, where={}, fields=(), limit=5000)
    visits = {}
    for enc in store.select("encounter", thread=None, where={}, fields=(), limit=5000):
        who = enc.get("patient")
        if not who:
            continue
        seen = visits.setdefault(who, {"visits": 0, "last": ""})
        seen["visits"] += 1
        seen["last"] = max(seen["last"], str(enc.get("created_date") or ""))

    out = []
    for row in rows:
        counted = visits.get(row.get("id")) or {"visits": 0, "last": ""}
        out.append({"id": row.get("id"),
                    "subject": {k: v for k, v in dict(row).items() if k != "id"},
                    **counted})
    # Whoever was here most recently is who somebody is looking for.
    out.sort(key=lambda r: (r["last"], str(r["subject"].get("created_date") or "")),
             reverse=True)
    return {"patients": out[:max(1, min(int(limit), 500))], "total": len(out)}


def declared_provenance() -> dict:
    """What this facility's queue says about where an arrival came from.

    Read off the queue view rather than written down here, so the word that
    marks a self registered arrival is the declaration's and this module does
    not carry a facility's vocabulary. A bundle that declares no provenance
    has no self registration surface, which is the honest answer for a centre
    with no poster on the wall.
    """
    for view in BUNDLE.views.values():
        if view.kind == "queue" and view.workflow == WORKFLOW.id and view.provenance:
            return dict(view.provenance)
    return {}


@router.post("/threads")
def open_thread(request: Request, body: dict = Body(default={})):
    """Open an empty visit, so reception has something to register against.

    This writes an encounter row and no clinical fact whatsoever: an empty
    thread asserts nothing about a person. Every fact still goes through the
    guard, which is why opening one is not an operation in the catalogue.

    The number is ISSUED HERE and is not the caller's to choose. A token in
    the body is ignored, and that is the point: a number a client picks is a
    number nothing else knew it had given out, and two clients each picking
    their own is how one waiting room ends up with two people called seven.
    The sequence rule is kernel/tokens.py.

    An arrival through this route carries no provenance mark. The desk is the
    ordinary way in and the mark is for the other one, so the absence is the
    answer rather than a word this module would have to know. Nothing here
    names how anybody arrived.
    """
    user = caller(request)
    thread = store.open_thread(token=tokens.issue(store, workflow=WORKFLOW.id),
                               actor=user["id"])
    return panel(thread, user)


@router.post("/arrivals")
def self_registered_arrival(body: dict = Body(default={})):
    """A patient who scanned the poster by the door, and the number they get.

    The poster carries this facility's id and a counter id, so the scan
    happens at the counter and THE SCAN IS THE ARRIVAL. The number is issued
    at that moment, out of the same sequence the desk draws from, and it is
    returned on this response: that is how it reaches the patient's own
    application, which is the only screen this person is going to look at.

    No capability and no staff caller, deliberately. Nobody at the desk is
    involved in this route, which is the whole value of it, so there is no
    staff identity to read. What it writes is an encounter row with a number
    and a provenance, no clinical fact and no name, exactly as the desk's own
    route does, so the guard is still the only path to a fact about a person.

    What it answers is the number and nothing else. An unauthenticated caller
    does not get a clinical panel: this is the one route on this server with
    no capability in front of it, and what it can read back has to be the
    thing it was given rather than everything the thread knows.

    NOT the ABDM share callback. The profile this patient consented to send
    arrives by that callback, which this build does not have, because real
    ABDM calls are out of scope while ABHA is on staging. This is the arrival
    half: the number exists and is on the sequence before any profile lands,
    which is the right order, because a person is in the room either way.
    """
    provenance = declared_provenance()
    if not provenance:
        raise HTTPException(404, "this facility declares no self registration")
    counter = str(body.get("counter") or "").strip()
    if not counter:
        raise HTTPException(400, "a scan carries the counter it happened at")
    number = tokens.issue(store, workflow=WORKFLOW.id)
    thread = store.open_thread(token=number, arrival=provenance["mark"],
                               actor="poster:%s" % counter)
    return {"thread": thread, "token": number}


# ---------------------------------------------------- the patient directory
# Settled 2026-10-31: Eka's directory is the source of truth for patient
# identity. One seam (kernel.contracts.PatientDirectory), one vendor behind it,
# and a degraded path that is the designed path rather than a fallback.


def make_directory():
    """The directory this process talks to, or the kernel's absent one.

    No credential is not an error. A developer with no Eka account, and a
    health centre whose line is down, get the same thing: the local register
    answers searches, a registration commits, and nothing is published until
    there is a directory to publish to. That is the whole offline design and
    it is reached by the ordinary path, not by a flag.
    """
    if os.environ.get("PHC_DIRECTORY", "eka") == "absent":
        return directory.AbsentDirectory()
    try:
        from care_phc.connectors.directory.eka import EkaDirectory

        return EkaDirectory()
    except DirectoryError:
        return directory.AbsentDirectory()


DIRECTORY = make_directory()


@router.get("/patients/search")
def patient_search(request: Request, q: str = "", limit: int = 10):
    """Who might this be: the local register, then the directory.

    Always 200. A directory that could not be asked is reported in the body
    (`reachable: false` and a reason) beside whatever the local register
    found, and never as an error status: a clerk looking for a patient who is
    in today's line must not be shown a failure about a directory they were
    not relying on. That is the degradation this product is designed around
    and it is tested with no socket in scripts/check_directory.py.
    """
    caller(request)                     # capability-free read, but 400 on a bad role
    found = directory.resolve(store, DIRECTORY, q, limit=max(1, min(int(limit), 50)))
    return {
        "query": found.query,
        "local": found.local,
        "suggestions": [asdict(s) for s in found.suggestions],
        "reachable": found.reachable,
        "reason": found.reason,
        # What a suggestion is for. Said on the wire so the renderer cannot
        # invent a different answer: these are values for the register form,
        # and committing them is an ordinary guarded write.
        "commits_through": "phc.op.patient-register",
    }


@router.get("/patients/pending")
def patient_pending(request: Request, limit: int = 200):
    """Patients this facility registered that the directory has not seen.

    A query over rows we already keep rather than a queue, so it cannot
    disagree with the records it is about. See kernel/directory.pending.
    """
    caller(request)
    rows = directory.pending(store, limit=max(1, min(int(limit), 500)))
    return {"pending": rows, "count": len(rows)}


@router.post("/patients/publish")
def patient_publish(request: Request, body: dict = Body(default={})):
    """Publish what is pending. Needs facility.admin.

    Not a clinical write and not an operation in the catalogue: it records the
    identifier a registry minted for a person already registered here, on a
    row that already exists. Behind facility.admin because it is the only verb
    here that sends a patient's details off this machine.
    """
    user = caller(request)
    if "facility.admin" not in user["capabilities"]:
        raise HTTPException(403, "publishing to the patient directory needs "
                                 "facility.admin")
    report = directory.publish_pending(
        store, DIRECTORY, at=proposals.now(),
        limit=max(1, min(int(body.get("limit") or 50), 200)))
    return {"published": report.published, "failed": report.failed,
            "reachable": report.reachable, "count": report.count}


@router.get("/questionnaires")
def questionnaires(request: Request):
    """Every form this bundle's operations ask, by the slug an operation names.

    Until this route existed the renderer read questionnaires/*.json through a
    build time glob, which made the forms the one part of the screen that was
    not served by the kernel: a facility could not change a form without a
    rebuild of the browser bundle, and src/declarations.ts said so in its own
    docstring.

    Not narrowed by the caller's capabilities, on purpose. A form is a
    bundle's declaration and not a facility's choice, and the renderer labels
    an OLD audit row with the questionnaire of whatever operation wrote it, so
    a narrowed list would quietly lose the labels on a card a colleague left
    behind. What a facility narrows is which operations it offers, which is
    already subtracted once in caller() and reaches the screen as
    thread.actions. The guard is the enforcement; this is only the words on a
    label.
    """
    caller(request)
    out = {}
    for op in BUNDLE.operations.values():
        slug = op.get("input")
        if slug and slug not in out:
            out[slug] = validate.load(slug)
    return {"questionnaires": out}


@router.get("/valuesets/{slug}")
def valueset(slug: str, request: Request, q: str = "", limit: int = 50):
    """Expand a value set, for a picker.

    A question that binds its answer to a value set has no `answer_option`
    list, by design: the codes live in the value set and duplicating them into
    the questionnaire would be the same list twice. So something has to offer
    them, and this is it. Without this route the third binding form would be a
    column nothing could fill from a screen.

    Local and offline like everything else on this path: it reads the cache in
    terminology/, which is the only implementation behind the seam and the
    reason a health centre on a bad line can still pick an analyte.
    """
    caller(request)
    try:
        found = terminology.LOCAL.expand(slug, q, max(1, min(int(limit), 200)))
    except terminology.UnboundCoding as broke:
        raise HTTPException(404, str(broke))
    concepts = terminology.LOCAL.concepts(slug)
    return {
        "valueset": slug,
        "query": q,
        # `value` and `display` are the names a choice control already reads,
        # so a picker needs no new shape. The extras are what a coded answer
        # needs beside the code: the system it is from, and for an analyte the
        # unit it is reported in, which is what makes the unit field
        # answerable without a second lookup.
        "concepts": [dict({"value": c.code, "display": c.display,
                           "system": c.system},
                          **{k: v for k, v in (concepts.get(c.code) or {}).items()
                             if k in ("unit", "unit_system")})
                     for c in found],
    }


@router.get("/queue")
def queue(request: Request, view: str = None):
    """The declared queue. `view` defaults to the bundle's first queue view."""
    if view is None:
        queues = sorted(v.id for v in BUNDLE.views.values() if v.kind == "queue")
        if not queues:
            raise HTTPException(404, "this bundle declares no queue view")
        view = queues[0]
    return get_view(view, request)


@router.get("/views/{view_id}")
def get_view(view_id: str, request: Request, thread: str = None):
    user = caller(request)
    declaration = BUNDLE.views.get(view_id)
    if not declaration:
        raise HTTPException(404, "unknown view %r" % view_id)
    if declaration.capability not in set(user["capabilities"]):
        raise HTTPException(403, "missing capability %s" % declaration.capability)
    try:
        result = views.resolve(BUNDLE, view_id, store, thread=thread,
                               caps=set(user["capabilities"]))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result.to_json()


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: str):
    return asdict(proposal_or_404(proposal_id))


def proposal_or_404(proposal_id: str):
    found = store.proposal(proposal_id)
    if not found:
        raise HTTPException(404, "no such proposal %r: confirm only accepts an id "
                                 "that propose issued" % proposal_id)
    return found


# ------------------------------------------------------------------- writes

@router.post("/operations/{op_id}/propose")
def propose(op_id: str, request: Request, body: dict = Body(default={})):
    """Guard steps 1 to 4 on the machine surface, then a proposal. No write.

    An irreversible operation is denied here by design: guard step 4 refuses
    it on any surface but rendered, before it looks at a confirmed flag at
    all. An agent cannot propose an ABHA link, and it should not be able to.
    """
    user, _ = caller(request), operation_or_404(op_id)
    decision, proposal = proposals.propose(
        store, BUNDLE, op_id, thread=thread_of(body), payload=body.get("payload") or {},
        caps=set(user["capabilities"]), scopes=set(user["scopes"]), actor=user["id"])
    allowed_or_422(decision)
    return {"proposal_id": proposal.id, "status": decision.reason, "operation": op_id,
            "awaiting": "clinician review on the rendered surface",
            "flags_raised": proposal.flags_raised, "proposal": asdict(proposal)}


@router.post("/operations/{op_id}/commit")
def commit(op_id: str, request: Request, body: dict = Body(default={})):
    """A person tapped commit on the rendered surface. Body: thread, payload,
    confirmed.

    This is also where a voice or scribe draft lands, once it has been read
    back on screen and tapped. By the time it arrives it is indistinguishable
    from typing, and that is exactly the safety property: there is no route by
    which a recognised value reaches the store without a person seeing it.
    """
    user, _ = caller(request), operation_or_404(op_id)
    thread = thread_of(body)
    decision = proposals.commit(
        store, BUNDLE, op_id, thread=thread, payload=body.get("payload") or {},
        caps=set(user["capabilities"]), scopes=set(user["scopes"]), actor=user["id"],
        confirmed=bool(body.get("confirmed")))
    allowed_or_422(decision)
    return {"committed": op_id, "thread": panel(thread, user)}


@router.post("/operations/{op_id}/amend")
def amend(op_id: str, request: Request, body: dict = Body(default={})):
    """A person corrected something already recorded. Body: thread, payload.

    Not a second commit, and the difference matters: this REPLACES the rows
    the same operation wrote on this visit instead of adding a second,
    contradictory set. It refuses once the visit is over, because a record
    that has already been published is corrected by publishing again, not by
    editing underneath. kernel/proposals.amend holds both rules.
    """
    user, _ = caller(request), operation_or_404(op_id)
    thread = thread_of(body)
    decision = proposals.amend(
        store, BUNDLE, op_id, thread=thread, payload=body.get("payload") or {},
        caps=set(user["capabilities"]), scopes=set(user["scopes"]), actor=user["id"],
        confirmed=bool(body.get("confirmed")))
    allowed_or_422(decision)
    return {"amended": op_id, "thread": panel(thread, user)}


@router.post("/proposals/{proposal_id}/confirm")
def confirm(proposal_id: str, request: Request, body: dict = Body(default={})):
    """Accept a proposal. Rendered surface only, and once only.

    Three refusals, in order: an id propose never issued (404); a proposal
    that is not pending (409, so a replayed request cannot write twice); and
    whatever the guard says now (422), evaluated again against the state as it
    is at this moment and the payload as the person edited it.
    """
    user = caller(request)
    proposal = proposal_or_404(proposal_id)
    if proposal.status != "pending":
        raise HTTPException(409, "proposal %s is already %s; a proposal is confirmed "
                                 "once" % (proposal_id, proposal.status))
    decision, decided = proposals.confirm(
        store, BUNDLE, proposal, caps=set(user["capabilities"]),
        scopes=set(user["scopes"]), actor=user["id"], payload=body.get("payload"),
        confirmed=bool(body.get("confirmed")))
    allowed_or_422(decision)
    return {"proposal": asdict(decided), "thread": panel(proposal.thread, user)}


@router.post("/khoj")
def khoj(request: Request, body: dict = Body(default={})):
    """Khoj: a sentence in, proposals out. Body: thread, utterance, confidence, backend.

    This is the composer's endpoint, and it is a propose-only surface. It calls
    agent.turn, which calls the planner in agent/ and then this module's own
    propose path: kernel.proposals.propose, which takes no confirmed argument
    and runs the guard on guard.MCP. So the worst an utterance can do is put a
    card in front of a person. There is no branch here that reaches confirm or
    commit, and api/tests/test_api.py proves it by making both explode for the
    duration of a turn.

    `confidence` is the per-field map when the utterance was dictated (the
    scribe path emits link_id -> 0..1). Nothing on this side
    recognises anything, so a typed utterance carries no confidences rather
    than a fabricated one.

    `backend` pins the planner for a check; left out it is the llm when
    ANTHROPIC_API_KEY is set and the deterministic router otherwise.
    """
    user = caller(request)
    thread = thread_of(body)
    actor = "agent:%s" % user["id"]

    def propose_one(op_id, payload):
        """(proposal_id | None, the guard's reason, flags raised, precondition kind)."""
        if op_id not in BUNDLE.operations:
            return None, "unknown operation %r" % op_id, [], ""
        decision, proposal = proposals.propose(
            store, BUNDLE, op_id, thread=thread, payload=payload,
            caps=set(user["capabilities"]), scopes=set(user["scopes"]), actor=actor)
        return ((proposal.id if proposal else None), decision.reason,
                proposal.flags_raised if proposal else [], decision.kind)

    answer = turn.take(
        str(body.get("utterance") or ""),
        catalogue=catalogue(),  # the same declarations every other caller plans against
        view=panel(thread, user), propose=propose_one,
        confidence=body.get("confidence") or {}, which=body.get("backend"))
    # The thread as it stands after the turn, so the renderer draws the new
    # pending cards without a second read. Still pending: see every verdict.
    return dict(answer, thread=panel(thread, user))


@router.post("/agent/say", deprecated=True)
def say(request: Request, body: dict = Body(default={})):
    """Deprecated alias for POST /khoj, same body and same answer.

    Kept for one release: the Go MCP binary and any agent already bound to
    the old path may still call it. `deprecated=True` puts the flag on the
    OpenAPI operation itself, so a client sees it without reading a comment.
    Do not add anything here beyond this delegation; the one propose path is
    `khoj()` above, and this route has no logic of its own to drift out of
    step with it.
    """
    return khoj(request, body)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: str, request: Request, body: dict = Body(default={})):
    user = caller(request)
    proposal = proposal_or_404(proposal_id)
    if proposal.status != "pending":
        raise HTTPException(409, "proposal %s is already %s" % (proposal_id,
                                                                proposal.status))
    decided = proposals.reject(store, proposal, actor=user["id"],
                               reason=str(body.get("reason") or ""))
    return {"proposal": asdict(decided), "thread": panel(proposal.thread, user)}


# --------------------------------------------------------------- the ABHA SDK
# Eka ships a real ABHA web SDK. The renderer mounts it; this route is the only
# thing that tells the renderer WHICH one. Nothing here is a credential.
#
# Two things learned by reading the loaded bundle rather than the reference:
#
#   - The SDK's `clientId` is not an API client id. It is a platform name the
#     SDK branches on ("www-eka", "androidp", "patient-app-ios", "androiddoc",
#     "doctor-app-ios", "doctor-ipad-ios", "doc-web", "ext"), and anything else
#     falls through to its "phr" default. So EKA_CLIENT_ID does not belong in
#     it and is not sent here: the secret half of that pair is this process's
#     and stays this process's.
#   - The staging package hardcodes its own environment (`setEnv({env: "DEV"})`
#     inside initAbhaApp), so which package is loaded IS which environment. It
#     defaults to staging, because a production ABHA journey sends real one time
#     passwords to real phones and creates permanent national health accounts,
#     and a demo must not do that by accident. ABHA_ENV=production is the
#     deliberate opt in.

ABHA_PACKAGES = {"staging": "@eka-care/abha-stg", "production": "@eka-care/abha"}

# The theme handed to initAbhaApp, so Eka's journey sits inside our modal
# instead of beside it. Read off the staging bundle on 2026-09-11 rather than
# off the reference, and the bundle disagrees with the reference twice:
#
#   - There are FOUR token groups, not three. `content` (primary, secondary,
#     muted, success, enabled) is the group that carries every text colour and
#     it is absent from the documented shape.
#   - `qrCodeColors` is read off `theme`, not off `data`.
#
# generateThemeCSS interpolates each value straight into a declaration
# (`#<container> .<class>{<prop>: <value> !important}`), so `var(--x)` is legal
# there, and unlike a hex it follows the app's own light and dark toggle
# without re-initialising the journey. These are web/src/theme.css's tokens.
#
# Two traps in the map, both real:
#   - `surface.base` also paints `pds2-text-content-enabled`, which would set
#     text to the colour of the card under it. `content.enabled` maps to the
#     same class and is written after it, so it is what wins. Never drop it.
#   - `qrCodeColors` goes to a <canvas>, where `var(--x)` is not a colour. Those
#     two stay literal, and stay light: a QR code is read by a phone camera and
#     not by a theme.
ABHA_THEME = {
    "surface": {
        "base": "var(--surface)",
        "subtle": "var(--gray-100)",
        "muted": "var(--gray-200)",
        "strong": "var(--gray-300)",
        "success": "var(--success-bg)",
        "danger": "var(--destructive-bg)",
        "neutral": "var(--gray-100)",
        "abhaCard": "var(--abdm-bg)",
    },
    "content": {
        "primary": "var(--ink)",
        "secondary": "var(--ink-2)",
        "muted": "var(--ink-3)",
        "success": "var(--success)",
        "enabled": "var(--ink)",
    },
    "semantic": {
        "success": "var(--success)",
        "warning": "var(--warning)",
        "error": "var(--destructive)",
    },
    "primary": {"brand": "var(--abha-brand)"},
    "qrCodeColors": {"fgColor": "#1A1714", "bgColor": "#FFFFFF"},
}


@router.get("/abha/config")
def abha_config():
    """Which ABHA SDK the browser should load, and how to address it."""
    env = (os.environ.get("ABHA_ENV") or "staging").strip().lower()
    if env not in ABHA_PACKAGES:
        raise HTTPException(
            500, "ABHA_ENV=%r is not an environment. It is staging or production." % env)
    package = ABHA_PACKAGES[env]
    base = "https://unpkg.com/%s/dist/sdk/abha" % package
    theme = os.environ.get("ABHA_THEME")
    return {
        "environment": env,
        "package": package,
        "script": "%s/js/abha.js" % base,
        "css": "%s/css/abha.css" % base,
        # A platform name, not a secret. "ext" is the SDK's own name for an
        # external clinical surface, which is what this renderer is.
        "client_id": os.environ.get("ABHA_CLIENT_ID") or "ext",
        # Passed to the SDK's generateThemeCSS. ABHA_THEME overrides it whole.
        "theme": json.loads(theme) if theme else ABHA_THEME,
        # The facility's HIP id, when this deployment has one. The SDK sends it
        # as an X-Hip-Id header. None here is honest: this repository has no
        # onboarded bridge, and the journey says so rather than pretending.
        "hip_id": os.environ.get("ABHA_HIP_ID") or None,
    }


# ------------------------------------------------------------------ the scribe
# Audio in, a draft out. The draft is kernel.contracts.Draft's shape and it is
# not a write: api/scribe.py has no Store, these routes hand it none, and a
# value still arrives in the renderer's editable fields to be tapped. The
# ordinary commit route is the only way any of it reaches a row.

# NO CONSENT GATE. The owner removed it in full on 4 November 2026: the
# flags, the question on the registration form, the operation that withdrew
# it and the instrument that read the sentence out. A recording is refused
# here for one reason only, which is that the caller does not hold the
# capability to fill what they named. See bundles/phc/phc.wf.outpatient.md
# for what was taken out and what it would take to put back.


# Notes a recording had written are kept beside the visit, so the next person
# to open it reads one note with everybody's part in it. See api/notes.py.
scribe.KEEP = lambda **kw: notes.keep(DB, **kw)


def scribe_allowed(user):
    """{operation_id: {"schema": questionnaire}} a recording may fill for this caller:
    on a scribe instrument's list, and within the caller's capabilities."""
    caps = set(user["capabilities"])
    out, instrument = {}, ""
    for decl in BUNDLE.instruments.values():
        if decl.kind != "scribe" or decl.commit != "tap" or decl.readback != "required":
            continue
        instrument = instrument or decl.id
        for op_id in decl.operations:
            op = BUNDLE.operations.get(op_id)
            if op and op["capability"] in caps:
                out[op_id] = {"schema": validate.load(op["input"])}
    return out, instrument


def scribe_pick(user, names):
    """The operations a recording will fill this time: named by the caller, at
    most two, and each one this caller may fill. A refill picks again from the
    transcript already held; a start picks before a byte leaves this machine."""
    allowed, instrument = scribe_allowed(user)
    wanted = [n for n in (names or []) if n]
    if not wanted or len(wanted) > 2:
        raise HTTPException(400, "Name one or two templates to fill.")
    missing = [n for n in wanted if n not in allowed]
    if missing:
        raise HTTPException(403, "A recording may not fill %s for you. Type the note."
                            % ", ".join(missing))
    return {n: allowed[n] for n in wanted}, instrument


def note_default(title):
    """{id, title} of the library template a station declares, or None."""
    want = str(title or "").strip().lower()
    if not want:
        return None
    try:
        for item in scribe.library():
            if item["title"].strip().lower() == want:
                return {"id": item["id"], "title": item["title"]}
    except scribe.ScribeError:
        pass
    return None


@router.get("/scribe/notes")
def scribe_notes(request: Request, thread: str = ""):
    """The notes this visit has had written, one per template, each with a
    section per recording under the name of whoever made it. Words to read:
    this lists, and writes nothing."""
    caller(request)
    return {"notes": notes.for_thread(DB, thread_of({"thread": thread}))}


@router.get("/scribe/templates")
def scribe_templates(request: Request, station: str = ""):
    """What a recording may fill at this station, for this caller: the
    station's own default and switcher from `BUNDLE.scribe`, narrowed to
    what this person's capabilities allow."""
    user = caller(request)
    allowed, _ = scribe_allowed(user)
    cfg = BUNDLE.scribe.get(station) or {}
    choose = [o for o in cfg.get("choose") or [] if o in allowed]
    default = cfg.get("default") if cfg.get("default") in choose else None
    return {"default": default,
            "choose": [{"operation": o, "title": BUNDLE.operations[o]["title"]} for o in choose],
            # The note this station is written up in unless somebody says
            # otherwise: the bundle names it by title and Eka's library says
            # which template that is. Absent when the station declares none,
            # when the library has no such template, or when Eka cannot be
            # reached -- a recording does not need one.
            "note": note_default(cfg.get("note")),
            # No language list. Nothing picks one: every recording goes up
            # as `auto`, which is every language this facility supports, and
            # the service decides what it heard. See api/scribe.LANGUAGES.
            }


@router.get("/scribe/library")
async def scribe_library(request: Request):
    """Eka's own note templates for this workspace, for the screen to offer
    beside the forms a recording fills. Read only: this lists, it makes
    nothing, and the ones this kernel files for itself are left out."""
    caller(request)
    try:
        return {"items": await run_in_threadpool(scribe.library)}
    except scribe.ScribeError as broke:
        raise HTTPException(503, str(broke))


def collect_if_consent_stands(session):
    """Collect a draft. Named for a gate that no longer exists.

    The name is kept for one release because a poll and a webhook both call
    it; there is nothing left for it to decide. The browser's Stop button is
    still the DELETE route, and it still withdraws.
    """
    return scribe.collect(session)


def scribe_or_404(session_id, request):
    """The caller's own session, or a 404.

    Every browser facing session route comes through here, so none of them
    can forget the rule. A session belongs to the actor who started it: its
    transcript is somebody's consultation, kept for a day, and another desk
    asking for it by id gets the same 404 as an id nobody started, so an id
    is not a way to learn that a recording exists.

    It used to re-read the visit's consent and withdraw the session when it
    had been turned off. There is no consent to read now.
    """
    scribe.expire()
    session = scribe.SESSIONS.get(session_id)
    if not session or session["actor"] != caller(request)["id"]:
        raise HTTPException(404, "no such scribe session %r. Nothing was kept."
                            % session_id)
    return session


@router.post("/scribe/sessions")
async def scribe_start(request: Request, thread: str = None, format: str = None,
                       operations: str = "", language: str = "auto",
                       library: str = ""):
    """The browser posts one recording here, as the raw body.

    Three refusals before a byte leaves this machine, in this order: the
    named templates, the language, and a connector that can be reached. There
    were four, and the first was the visit's own consent to being recorded;
    the owner removed that in full on 4 November 2026.

    The audio is bytes in this process and one temporary file in scribe.start,
    deleted in its `finally`. It is never written under this repository, never
    logged, and the transaction id that identifies it at the service is not
    returned to the browser.

    WHEN THE LINE IS DOWN THE RECORDING IS HELD RATHER THAN LOST, which is new
    on 2026-11-01 and is the gap kernel/queues.py named: this route used to
    answer 503 and drop the only copy of a consultation in a `finally`, so an
    outage cost the recording and not just the transcript. The bytes now go to
    the spool, outside the repository and owner readable only, and the outbox
    sends them when the line is back.

    THE CLINICIAN IS STILL TOLD NOTHING WAS TRANSCRIBED. Holding it is not
    succeeding: the answer is still a refusal, with a sentence saying the
    recording is kept, that it will be sent, and that the note has to be typed
    now. A route that returned success because something was queued would be
    the "reported as sent when it was not" failure wearing a friendlier face.
    """
    user = caller(request)
    thread_id = thread_of({"thread": thread})
    if language not in scribe.LANGUAGES:
        raise HTTPException(400, "Unknown language %r." % language)
    # NO FORM CHOSEN IS A TRANSCRIPT. Choosing a template is not mandatory:
    # a recording with neither a form nor a note is still a recording, and
    # what it produces is the words.
    if any(n.strip() for n in operations.split(",")):
        picked, instrument = scribe_pick(user, operations.split(","))
    else:
        picked, instrument = {}, ""
    # Library templates asked for beside the forms: a note in Eka's own shape
    # (a SOAP note, a discharge summary) written from the same recording.
    try:
        wanted = await run_in_threadpool(
            scribe.library_pick, [i for i in library.split(",") if i][:2])
    except scribe.ScribeError as broke:
        raise HTTPException(400, str(broke))
    audio = await request.body()
    suffix = _suffix(format or request.headers.get("content-type"))
    # The template that shapes each of these forms, resolved BEFORE the audio
    # goes up, because the upload has to name them. Resolving is a listing and
    # at most one create against the workspace, and it is cached for the life
    # of the process: it is not a call per consultation.
    try:
        shapes = await run_in_threadpool(scribe_shapes, picked)
    except scribe.ScribeError as broke:
        raise HTTPException(503, hold_or_say(
            audio, thread_id, user, picked, suffix, str(broke)))
    try:
        txn = await run_in_threadpool(
            scribe.start, audio, suffix=suffix,
            languages=scribe.LANGUAGES[language],
            templates=list(shapes.values()) + list(wanted))
    except scribe.ScribeError as broke:
        raise HTTPException(503, hold_or_say(
            audio, thread_id, user, picked, suffix, str(broke)))
    session = scribe.begin(thread_id, user["id"], txn, picked,
                           instrument=instrument, templates=shapes, want=wanted)
    return scribe.public(session)


def scribe_shapes(picked):
    """{operation: template_id} for the forms this recording will fill."""
    return {op_id: scribe.shaped_template(op_id, fill.flatten(spec["schema"]))
            for op_id, spec in sorted(picked.items())}


def hold_or_say(audio, thread_id, user, picked, suffix, why):
    """Keep the recording if we can, and say which of the two happened.

    The sentence is the whole value of this function. "We kept it and will send
    it" and "it is gone" are different things to a doctor deciding whether to
    re-record a consultation the patient is still sitting through, and
    answering the same words either way is what makes a queue untrustworthy.

    Holding can itself fail, and then it says so rather than implying a copy
    exists. A plugin this centre does not run, a full disk, or no outbox at
    all: in every one of those the answer is that there is no recording.
    """
    first = sorted(picked)[0] if picked else ""
    operation = (BUNDLE.operations or {}).get(first) or {}
    try:
        OUTBOX.hold(audio, thread=thread_id, actor=user["id"],
                    operation=first, capability=operation.get("capability", ""),
                    suffix=suffix)
    except Exception as broke:                       # noqa: BLE001
        return ("%s The recording could not be kept either (%s), so there is no "
                "copy of it. Type the note."
                % (why, queues.scrubbed(str(broke))))
    return ("%s The recording is kept and will be sent when the line is back. "
            "Nothing has been transcribed yet, so type the note now: it is the "
            "record either way." % why)


def _suffix(content_type):
    """The extension the service will recognise, from what the browser said it
    recorded. Chrome gives audio/webm, Safari audio/mp4. An unknown type is
    sent as .webm rather than guessed at more cleverly than that."""
    kind = str(content_type or "").split(";")[0].strip().lower()
    return {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
            "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
            "audio/wave": ".wav"}.get(kind, ".webm")


def paper_allowed(user, operation):
    """The document instrument that may fill this operation for this caller.

    Three things have to hold, and they are the same three the recording
    route checks: a declared instrument of kind `document` names the
    operation, its readback and commit are the fixed ones, and the caller
    holds the operation's own capability. A caller who could not commit the
    form may not have a machine fill it either -- otherwise the read is a way
    to put values in front of somebody who is not allowed to put them there.
    """
    caps = set(user["capabilities"])
    for decl in BUNDLE.instruments.values():
        if decl.kind != "document" or decl.commit != "tap" or decl.readback != "required":
            continue
        if operation not in decl.operations:
            continue
        op = BUNDLE.operations.get(operation)
        if not op:
            continue
        if op["capability"] not in caps:
            raise HTTPException(403, "You cannot %s at this centre." % op["title"].lower())
        return decl
    return None


@router.post("/paper")
async def paper_read(request: Request, body: dict = Body(default={})):
    """What the service read off a document the browser already uploaded.

    The picture does not come through here. The browser uploads it with
    @eka-care/medical-records-ts-sdk -- the SDK the claims portal uses --
    which sends it to the presigned bucket the service hands back, and posts
    the document id here. So a ten megabyte photograph never travels through
    this process, and the credential never travels to the browser: the SDK is
    pointed at this kernel and `/mr/api/v1/...` below attaches it.

    The answer is a Draft or nothing, and never a write. This route has no
    Store, calls nothing that does, and the values it returns reach the
    record only the way every other drafted value does: drawn in editable
    fields, checked by a person, committed by a tap.

    `{"draft": null}` is a success. Attaching the paper is what somebody
    asked for and the browser already did it; a reading is a convenience on
    top, and a handwritten camp note that reads as nothing is the normal
    case rather than the broken one.

    The document stays on the patient's record. It is theirs, it was filed
    under their own Eka oid, and it follows them.
    """
    user = caller(request)
    operation = str(body.get("operation") or "")
    decl = paper_allowed(user, operation)
    if not decl:
        raise HTTPException(400, "Nothing here reads a document into %r." % operation)
    document = str(body.get("document_id") or "")
    patient = str(body.get("patient") or "") or None
    try:
        read = await run_in_threadpool(paper.describe, document, patient=patient)
    except paper.PaperError as broke:
        raise HTTPException(503, str(broke))
    draft = paper.parse(read, operation=operation, instrument=decl.id,
                        fills=decl.fills) if read else None
    # NOTHING READ IS AN ORDINARY ANSWER, not a refusal. The document is
    # already on the patient's record -- the browser's own SDK put it there
    # before this route was called -- and whether a machine could also read
    # it is a convenience. This used to answer 422, which told a clerk their
    # upload had failed when it had not.
    return {"draft": draft}


@router.get("/scribe/sessions/{session_id}")
async def scribe_status(session_id: str, request: Request):
    """Whether the draft is ready. The browser polls this; the webhook below
    only shortens the wait. Either way the answer is the same object.

    Consent is re-read here and not only at the start, because E.3's withdrawal
    is mid visit by definition: a patient who says stop while the job is still
    running has withdrawn, and the flag that says so is raised on a form this
    route knows nothing about. Whoever turns it off, the next poll is the last
    one and it returns no draft. The browser's own Stop button takes the DELETE
    below; this is the same rule for the half of the world that is not the
    browser.
    """
    session = await run_in_threadpool(collect_if_consent_stands,
                                      scribe_or_404(session_id, request))
    return scribe.public(session)


@router.delete("/scribe/sessions/{session_id}")
def scribe_withdraw(session_id: str, request: Request):
    """Withdrawal, mid visit. Nothing further is fetched and any draft already
    held is dropped. Records already confirmed stand, because they are rows and
    this never touched them."""
    return scribe.public(scribe.withdraw(scribe_or_404(session_id, request)))


@router.post("/scribe/sessions/{session_id}/extract")
async def scribe_extract(session_id: str, request: Request):
    """The template switch. Rebuilds drafts from the transcript this kernel
    already holds; nothing is uploaded and nothing is recorded again.

    A withdrawn session is refused outright rather than answered with an empty
    draft, because a switch the doctor asked for that silently came back empty
    would read as "nothing in the recording", which is not what happened."""
    user = caller(request)
    session = scribe_or_404(session_id, request)
    if session["status"] == "withdrawn":
        raise HTTPException(403, "This recording was stopped, so nothing from it "
                                 "is kept. Type the note: the record is the same "
                                 "either way.")
    if session["status"] != "ready":
        raise HTTPException(409, "There is no transcript to fill from yet.")
    body = await request.json()
    picked, _ = scribe_pick(user, body.get("operations") or [])
    return scribe.public(await run_in_threadpool(scribe.refill, session, picked))


@router.post("/scribe/sessions/{session_id}/note")
async def scribe_note(session_id: str, request: Request, template: str = ""):
    """Have this recording written up in one of Eka's library templates.

    Nothing is uploaded: the service keeps the transcript for the session and
    shapes it again. The note comes back as text on the session, held for the
    day with it, and it is words for somebody to read -- this route writes no
    record, and no value in a note reaches one without a person typing it into
    a form of their own.
    """
    caller(request)
    session = scribe_or_404(session_id, request)
    if session["status"] == "withdrawn":
        raise HTTPException(403, "This recording was stopped, so nothing from it "
                                 "is kept. Type the note.")
    if session["status"] != "ready":
        raise HTTPException(409, "There is no transcript to write a note from yet.")
    try:
        picked = await run_in_threadpool(scribe.library_pick, [template])
    except scribe.ScribeError as broke:
        raise HTTPException(400, str(broke))
    if not picked:
        raise HTTPException(400, "Name one template to write the note in.")
    text = await run_in_threadpool(scribe.note, session, template, picked[template])
    if not text:
        raise HTTPException(503, "The scribe service has not written that note yet. "
                                 "Try again in a moment, or type the note.")
    return scribe.public(session)


@router.post("/scribe/webhook")
def scribe_webhook(body: dict = Body(default={})):
    """Eka's `v2rx.completed` callback.

    The body is data, not instruction: the only thing read out of it is the
    transaction id, and the only thing that happens is the same collect the
    poll above does, for a session this kernel started itself. A call naming a
    transaction nobody here started does nothing at all.

    Unauthenticated, because the sender is not this browser and there is no
    authentication in this demo at all. It is also unreached: nothing outside
    this machine can call localhost, so this has never taken a live delivery.
    """
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    txn = str((payload or {}).get("transaction_id") or "")
    session = scribe.by_txn(txn) if txn else None
    if not session:
        return {"ok": True, "collected": False}
    collect_if_consent_stands(session)
    return {"ok": True, "collected": session["status"] == "ready"}


# ---------------------------------------------------------------------- app

# The outbox, and the thread that sweeps it. Started at import, with the
# process, because a retention ceiling that waits for a first request is off at
# a clinic nobody is using yet, and audio from yesterday is exactly what is
# sitting there. api/outbox.py argues the schedule and the order of a pass.
OUTBOX = outbox.start(store, BUNDLE, senders=outbox.live_senders())

app = FastAPI(title="care-phc kernel", version=BUNDLE.manifest.version)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# Two prefixes, one router: /api is what the renderer calls, /api/v1/phc is
# what the MCP server already calls, and those paths do not move.
app.include_router(router, prefix="/api")
app.include_router(router, prefix="/api/v1/phc")


@app.api_route("/mr/api/v1/{rest:path}",
               methods=["GET", "POST", "PATCH", "DELETE"])
async def medical_records(rest: str, request: Request):
    """The medical records seam the browser's own SDK talks to.

    NOT UNDER /api, and deliberately. These are the service's own paths,
    spelled the service's way, because the thing calling them is
    @eka-care/medical-records-ts-sdk with its `baseUrl` pointed here. A
    kernel route would mean a fork of the SDK, and a fork of the SDK is the
    thing the owner asked not to have: they wanted the claims portal's
    implementation, and this is it, with the credential kept on this side.

    api/vault.py decides what may be forwarded. It is a short list of
    prefixes and one identifier segment, because a proxy that forwards
    anything is a hole in a kernel that is otherwise careful about what
    leaves it.
    """
    caller(request)                       # a signed-in role, like every route
    path = "/mr/api/v1/" + rest
    body = await request.body()
    try:
        status, out, headers = await run_in_threadpool(
            vault.forward, request.method, path,
            request.url.query, body, dict(request.headers))
    except vault.VaultError as broke:
        raise HTTPException(503, str(broke))
    if status == 401:
        # The facility's token went stale. One retry with a fresh one, which
        # is what the SDK's own onUnauthorized would do if it held the token.
        vault.forget()
        try:
            status, out, headers = await run_in_threadpool(
                vault.forward, request.method, path,
                request.url.query, body, dict(request.headers))
        except vault.VaultError as broke:
            raise HTTPException(503, str(broke))
    return Response(content=out, status_code=status,
                    media_type=headers.get("content-type"))


@app.middleware("http")
async def either_spelling(request: Request, call_next):
    """kernel/contracts.py ROUTES spells every path with a trailing slash and
    the routes above are declared without one. Rather than pick a winner and
    break one of the two clients, both spellings hit the same handler here.

    Without this the trailing slash form is a 307, which costs the browser a
    second CORS preflight per write and makes a plain curl return nothing at
    all unless the caller remembered -L."""
    path = request.scope["path"]
    if len(path) > 1 and path.endswith("/"):
        request.scope["path"] = path.rstrip("/")
    return await call_next(request)


@app.get("/")
def index():
    return {"service": "care-phc kernel", "bundle": BUNDLE.manifest.id,
            "routes": sorted({r.path for r in app.routes})}
