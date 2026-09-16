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

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from adapters.local.store import SqliteStore, seed
from agent import turn
from api import scribe
from catalogue import validate, vocab
from kernel import declarations, spine, proposals, state, views
from kernel.contracts import ThreadRef

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


# Which system of record. `local` is the SQLite file this repository ships
# with and is the only one that has been run end to end; `care` is adapters/
# care over CARE's REST API, which needs a CARE and credentials that are not
# in here. The choice is configuration because the kernel only ever sees
# kernel.contracts.Store, so nothing below this function changes with it.
STORE = os.environ.get("PHC_STORE", "local")


def make_store():
    """A store, seeded on first use so the queue is never an empty screen.

    A CARE that cannot be reached is a normal thing to get wrong here, so it
    exits with a sentence instead of a connection traceback out of urllib.
    """
    if STORE == "care":
        from adapters.care.store import CareUnreachable, open_care
        try:
            return open_care(db=DB)
        except CareUnreachable as exc:
            raise SystemExit("\n%s\n" % exc)
    if STORE != "local":
        raise SystemExit(
            "\nPHC_STORE=%r is not an adapter. It is local or care.\n" % STORE)
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
    caps = OVERRIDES.get(role, ROLES[role])
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
               "status": rows[0].get("status")}
    patient = store.select("patient", thread=thread, where={}, fields=[], limit=1)
    if patient:
        subject.update(patient[0])
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
            "capabilities": sorted(vocab.CAPABILITIES),
            "views": [{"id": v.id, "kind": v.kind, "title": v.title,
                       "capability": v.capability} for v in BUNDLE.views.values()],
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


@router.get("/whoami")
def whoami(request: Request):
    """What the MCP server reads to build its tool list. Shape is frozen."""
    return {"capabilities": caller(request)["capabilities"]}


@router.get("/catalogue")
@router.get("/operations")
def catalogue():
    """The compiled catalogue: the operations, and the four declaration types
    that join them."""
    return dict(declarations.compile_json(BUNDLE),
                capabilities=sorted(vocab.CAPABILITIES), bundles=vocab.BUNDLES,
                states=sorted(vocab.STATES), operations=BUNDLE.operations)


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


@router.post("/threads")
def open_thread(request: Request, body: dict = Body(default={})):
    """Open an empty visit, so reception has something to register against.

    This writes an encounter row and no clinical fact whatsoever: an empty
    thread asserts nothing about a person. Every fact still goes through the
    guard, which is why opening one is not an operation in the catalogue.
    """
    user = caller(request)
    thread = store.open_thread(token=body.get("token"), actor=user["id"])
    return panel(thread, user)


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

    `confidence` is the recogniser's per-field map when the utterance was
    dictated (packages/voice emits link_id -> 0..1). Nothing on this side
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

CONSENT = "capture.consented"


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


@router.get("/scribe/templates")
def scribe_templates(request: Request, station: str = ""):
    """What a recording may fill at this station, for this caller: the
    station's own default and switcher from `BUNDLE.scribe`, narrowed to what
    this person's capabilities allow, plus the languages a recording may be
    made in."""
    user = caller(request)
    allowed, _ = scribe_allowed(user)
    cfg = BUNDLE.scribe.get(station) or {}
    choose = [o for o in cfg.get("choose") or [] if o in allowed]
    default = cfg.get("default") if cfg.get("default") in choose else None
    return {"default": default,
            "choose": [{"operation": o, "title": BUNDLE.operations[o]["title"]} for o in choose],
            "languages": list(scribe.LANGUAGES)}


def collect_if_consent_stands(session):
    """Collect a draft only while the visit still consents to being recorded.

    Every path that could bring a draft back goes through here, because E.3's
    withdrawal is mid visit by definition and the flag that records it is
    raised on a form neither of those paths knows about. Whoever turns the
    consent off, the next collect is a withdrawal instead and the job's result
    is never read. The browser's Stop button is the DELETE route and does not
    need this; a poll and a webhook do.
    """
    if CONSENT not in set(state.flags(store, session["thread"], WORKFLOW)):
        return scribe.withdraw(session)
    return scribe.collect(session)


def scribe_or_404(session_id):
    scribe.expire()
    session = scribe.SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "no such scribe session %r. Nothing was kept."
                            % session_id)
    return session


@router.post("/scribe/sessions")
async def scribe_start(request: Request, thread: str = None, format: str = None,
                       operations: str = "", language: str = "en-IN"):
    """The browser posts one recording here, as the raw body.

    Four refusals before a byte leaves this machine, in this order: consent,
    the named templates, the language, and a connector that can be reached.
    Addendum E.3 is the first of them: a visit without `capture.consented` is
    not recorded, and the answer says so in words a receptionist could read to
    the patient.

    The audio is bytes in this process and one temporary file in scribe.start,
    deleted in its `finally`. It is never written under this repository, never
    logged, and the transaction id that identifies it at the service is not
    returned to the browser.
    """
    user = caller(request)
    thread_id = thread_of({"thread": thread})
    if CONSENT not in set(state.flags(store, thread_id, WORKFLOW)):
        raise HTTPException(403, "Capture consent is not recorded on this visit, so "
                                 "nothing may be recorded. Ask, record the consent, "
                                 "or type the note: the record is the same either way.")
    if language not in scribe.LANGUAGES:
        raise HTTPException(400, "Unknown language %r." % language)
    picked, instrument = scribe_pick(user, operations.split(","))
    audio = await request.body()
    try:
        txn = await run_in_threadpool(
            scribe.start, audio, suffix=_suffix(format or request.headers.get("content-type")),
            languages=scribe.LANGUAGES[language])
    except scribe.ScribeError as broke:
        raise HTTPException(503, str(broke))
    session = scribe.begin(thread_id, user["id"], txn, picked, instrument=instrument)
    return scribe.public(session)


def _suffix(content_type):
    """The extension the service will recognise, from what the browser said it
    recorded. Chrome gives audio/webm, Safari audio/mp4. An unknown type is
    sent as .webm rather than guessed at more cleverly than that."""
    kind = str(content_type or "").split(";")[0].strip().lower()
    return {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".mp4",
            "audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
            "audio/wave": ".wav"}.get(kind, ".webm")


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
    caller(request)
    session = await run_in_threadpool(collect_if_consent_stands, scribe_or_404(session_id))
    return scribe.public(session)


@router.delete("/scribe/sessions/{session_id}")
def scribe_withdraw(session_id: str, request: Request):
    """Withdrawal, mid visit. Nothing further is fetched and any draft already
    held is dropped. Records already confirmed stand, because they are rows and
    this never touched them."""
    caller(request)
    return scribe.public(scribe.withdraw(scribe_or_404(session_id)))


@router.post("/scribe/sessions/{session_id}/extract")
async def scribe_extract(session_id: str, request: Request):
    """The template switch. Rebuilds drafts from the transcript this kernel
    already holds; nothing is uploaded and nothing is recorded again."""
    user = caller(request)
    session = scribe_or_404(session_id)
    if session["status"] != "ready":
        raise HTTPException(409, "There is no transcript to fill from yet.")
    body = await request.json()
    picked, _ = scribe_pick(user, body.get("operations") or [])
    return scribe.public(await run_in_threadpool(scribe.refill, session, picked))


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

app = FastAPI(title="care-phc kernel", version=BUNDLE.manifest.version)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
# Two prefixes, one router: /api is what the renderer calls, /api/v1/phc is
# what the MCP server already calls, and those paths do not move.
app.include_router(router, prefix="/api")
app.include_router(router, prefix="/api/v1/phc")


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
