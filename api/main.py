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

import os
from dataclasses import asdict

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from adapters.local.store import SqliteStore, seed
from catalogue import vocab
from kernel import declarations, proposals, state, views
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
ROLES[DEMO_ROLE] = sorted(set().union(*vocab.BUNDLES.values()))


def make_store():
    """A store, seeded on first use so the queue is never an empty screen."""
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
    return {"id": request.headers.get("X-PHC-Actor") or "user:%s" % role,
            "role": role, "capabilities": ROLES[role], "scopes": sorted(ROLES[role])}


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
    view = state.thread_view(store, ref_or_404(thread), WORKFLOW, BUNDLE.operations,
                             caps=set(user["capabilities"]))
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
