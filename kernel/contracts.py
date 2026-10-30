"""The contracts every layer codes against. Nothing here does anything.

Why this file exists
--------------------
The product is a runtime where clinical capability is declared, not coded. A
declaration is a markdown atom with YAML frontmatter (the format already used
by catalogue/ops/*.md), linted by catalogue/build.py and compiled into
catalogue.json. This module states the shape of those compiled entries, the
shape of the records the kernel keeps, the shape of what the API returns, and
the small Store protocol an adapter must satisfy. Four agents build against it
tonight without talking to each other, so the ambiguity budget is zero: where
a choice existed, one was made and the reason is written next to it.

Reuse, not rewrite
------------------
- Decision is catalogue.guard.Decision, re-exported. The guard is not changed.
- AuditRecord wraps the dict catalogue.guard.evaluate() already builds.
- Operation is exactly the compiled entry catalogue/build.py already writes,
  which care_phc_mcp/catalogue.go already reads. New keys only get added.
- The station and state vocabularies stay in catalogue/vocab.py.
- The thread JSON keeps the field names the renderer's types.ts uses, with
  two renames called out on ThreadView. That was care_phc_fe/src/types.ts when
  this was written; it is web/src/types.ts now, and care_phc_fe is deleted.

The five declaration types
--------------------------
capability   what a person may do            (catalogue/vocab.py, unchanged)
operation    a typed action                  (catalogue/ops/*.md, unchanged)
workflow     the order operations happen in, and how each state flag is
             derived from the store. Generalises care_phc/thread.py LINE
             and derive().
view         a queue, summary or dashboard, declared as a query over state,
             resources and metrics. The renderer draws it; it has no
             screen-specific code.
instrument   how a value is captured: form, device, constrained-voice,
             scribe. Declared per field or question type, never per screen.
metric       a certified count or ratio, evaluated locally.

The safety property this must preserve
--------------------------------------
Voice is an input instrument and never a commit path. Nothing an instrument
produces reaches the store directly: it produces a Draft, the renderer shows
the Draft on screen in editable fields, a person taps commit, and the tapped
values go through catalogue.guard.evaluate() on the rendered surface with the
same validator every other surface uses. The MCP surface proposes and there is
no confirm verb. Both facts are already enforced in code; the contracts here
add no path around them, and Instrument.commit can only be "tap".

Python 3.9. Type hints are strings under `from __future__ import annotations`
and are never evaluated at runtime; do not add typing.get_type_hints() calls.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence

from catalogue.guard import MCP, RENDERED, Decision  # noqa: F401  re-exported

# --------------------------------------------------------------------------
# Closed vocabularies for the new declaration types. These join, not replace,
# the ones in catalogue/vocab.py. Lint rejects anything outside them.
# --------------------------------------------------------------------------

DECLARATION_TYPES = ("operation", "workflow", "view", "instrument", "metric")
VIEW_KINDS = ("queue", "summary", "dashboard", "tasklist")
VIEW_SCOPES = ("today", "open", "all")
SUMMARY_SHOW = ("line", "actions", "proposals", "audit", "flags")
INSTRUMENT_KINDS = ("form", "device", "constrained-voice", "scribe", "spoken-prompt")
VOICE_GRAMMARS = ("number", "choice", "date", "free")
METRIC_UNITS = ("count", "percent", "ratio")
METRIC_WINDOWS = ("day", "week", "month", "all")
PROPOSAL_STATUSES = ("pending", "confirmed", "rejected", "expired")
STEP_STATUSES = ("done", "now", "pending", "skipped")

# The query grammar. One shape, used by state rules, views and metrics, so
# an adapter implements Store.count and Store.select once.
#
#   Query = {"resource": <vocab.CARE_RESOURCES>, "where": {field: Cond}}
#   Cond  = literal            equality
#         | "*"                field present and not null
#         | {"gte": v}         v is a literal, or "window.start" in a metric
#         | {"lt": v}
#
# Field names are the CARE emr model field names (care/emr/models/*.py).
# Adapter 0 (SQLite) stores them verbatim. Adapter 1 (CARE REST) maps them.
# Everything else about joining a resource to a thread is the adapter's
# knowledge: a declaration never says how a patient relates to an encounter.
Query = Mapping[str, Any]  # resource may also be a vocab.KERNEL_RESOURCES name, in metrics only

# State rules, evaluated in declaration order. A rule may reference a flag
# declared above it, by name or "not name". Forms:
#
#   {"stored": true}                       the store holds this flag directly
#   {"exists": Query}                      count(Query) > 0
#   {"gte": [Query, Query]}                count(a) >= count(b) and count(b) > 0
#   {"all_of": [flag | "not flag" | rule]} every item true
#
# Anything a bundle cannot say in these four forms is a reason to extend the
# grammar in one place, not a reason for an adapter to grow a special case.
StateRule = Mapping[str, Any]


# --------------------------------------------------------------------------
# Compiled declarations: the shape of catalogue.json entries.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Field:
    """One question of an operation's questionnaire, as compiled today."""
    link_id: str
    type: str
    text: str
    required: bool
    options: Optional[list] = None


@dataclass(frozen=True)
class Operation:
    """catalogue.json["operations"][id]. Identical to what build.py writes now
    and catalogue.go reads. Do not add keys here without adding them there."""
    id: str
    kind: str                       # vocab.KINDS
    short: str
    title: str
    summary: str
    capability: str                 # vocab.CAPABILITIES
    station: str                    # vocab.STATIONS
    instrument: str                 # vocab.INSTRUMENTS; the default instrument
    preconditions: list             # flags, optionally "not " prefixed
    irreversibility: str            # vocab.IRREVERSIBILITY
    input: str                      # questionnaire id
    writes: list                    # vocab.CARE_RESOURCES
    emits: list                     # vocab.STATES
    surfaces: list                  # always [rendered, mcp]; lint enforces
    verified: str
    tool: str                       # MCP tool name; writes are propose_*
    description: str
    fields: list                    # of Field
    scope_qualifier: Optional[str] = None
    type: str = "operation"


@dataclass(frozen=True)
class Step:
    """One station on a workflow line. Replaces one tuple of thread.LINE."""
    station: str                    # vocab.STATIONS
    done_when: str                  # a flag; the step is finished once true
    applies_when: Optional[str] = None  # a flag; step is skipped while false
    operations: list = field(default_factory=list)  # op ids drawn here, ordered


@dataclass(frozen=True)
class Workflow:
    """catalogue.json["workflows"][id].

    `states` is what makes thread state declared instead of coded: it is the
    rule per flag that care_phc/thread.py derive() hard-codes today. The
    kernel evaluates the rules against Store.count in declaration order.
    `stored` lists the flags the store holds because no resource can answer
    them (today: capture.consented, vitals.flagged, lab.critical)."""
    id: str
    title: str
    summary: str
    subject: str                    # the resource a thread is about: encounter
    steps: list                     # of Step, in line order
    states: dict                    # flag -> StateRule, ordered
    stored: list                    # flags with {"stored": true}
    type: str = "workflow"
    # The field on `subject` naming what continues across threads: a health
    # centre's patient, a laboratory's own. Optional, because a bundle whose
    # threads genuinely do not join up should say so by declaring nothing
    # rather than by pointing at a field that means something else. See
    # kernel/spine.py.
    spine: Optional[str] = None


@dataclass(frozen=True)
class Section:
    """One block of a summary view. Exactly one of `show` or `resource`."""
    title: str
    show: Optional[str] = None      # SUMMARY_SHOW
    resource: Optional[str] = None  # vocab.CARE_RESOURCES
    where: dict = field(default_factory=dict)
    fields: list = field(default_factory=list)


@dataclass(frozen=True)
class Task:
    """One row of a tasklist view: a predicate over a workflow's threads and
    an optional verb. `where` is {"flag": str | [str], "not": str | [str]}:
    every named flag must be held, every "not" flag must be absent.
    `operation` is optional: with one the row is actionable from itself;
    without one it is a worklist, a count and a list with nothing to tap."""
    title: str
    where: dict
    operation: Optional[str] = None


@dataclass(frozen=True)
class View:
    """catalogue.json["views"][id]. One dataclass for four kinds, because
    the renderer keys on `kind` and the unused fields stay empty. Four
    classes would need four renderer entry points and four API shapes."""
    id: str
    kind: str                       # VIEW_KINDS
    title: str
    summary: str
    capability: str                 # who may open it
    workflow: Optional[str] = None  # queue, summary and tasklist: which thread kind
    # queue
    scope: str = "today"            # VIEW_SCOPES
    group_by: Optional[str] = None  # "station" or a flag; None is one list
    columns: list = field(default_factory=list)   # subject fields to show
    badges: dict = field(default_factory=dict)    # flag -> warn | crit | ok | mute
    # summary
    sections: list = field(default_factory=list)  # of Section
    # dashboard
    metrics: list = field(default_factory=list)   # metric ids
    window: str = "day"             # METRIC_WINDOWS
    # tasklist
    tasks: list = field(default_factory=list)     # of Task
    # colour law (Vernier): a queue's declared wait limits, in minutes. Both
    # optional; a bundle that declares neither renders pure monochrome. See
    # QueueRow.entered_at and the renderer's colourRule.
    target_minutes: Optional[int] = None
    escalate_minutes: Optional[int] = None        # defaults to 2x target when unset
    type: str = "view"


@dataclass(frozen=True)
class Instrument:
    """catalogue.json["instruments"][id].

    An instrument is an accelerator on top of an operation's default form. It
    never changes what is valid, only how a value arrives. The three fields at
    the bottom are fixed for voice and scribe and lint refuses other values:
    the parsed value is read back on screen, a tap commits, and the fallback
    is the keypad. That is the ambient-speech rule from the product spec,
    made unwritable rather than remembered."""
    id: str
    kind: str                       # INSTRUMENT_KINDS
    title: str
    summary: str
    operations: list                # op ids this applies to
    fields: list = field(default_factory=list)   # link_ids; empty means all
    types: list = field(default_factory=list)    # question types; empty means all
    grammar: Optional[str] = None   # VOICE_GRAMMARS, constrained-voice only
    readback: str = "required"      # always "required"
    commit: str = "tap"             # always "tap"
    fallback: str = "keypad"        # keypad | form | text
    says: Optional[str] = None      # spoken-prompt only: the exact line spoken
    spoken: bool = True             # spoken-prompt only: a facility's off switch
    # A thread flag this instrument may not run without. The scribe's atom
    # said "only where capture.consented is set" in English and the renderer
    # hard-coded that flag, which meant a bundle whose consent flag is spelled
    # differently got no gate at all. One of this bundle's own states, or None.
    requires: Optional[str] = None
    type: str = "instrument"


@dataclass(frozen=True)
class Metric:
    """catalogue.json["metrics"][id]. Evaluated locally, never exported.
    `denominator` is None for a plain count."""
    id: str
    title: str
    summary: str
    unit: str                       # METRIC_UNITS
    numerator: dict                 # Query; may use {"gte": "window.start"}
    window: str                     # METRIC_WINDOWS
    denominator: Optional[dict] = None
    certified_by: Optional[str] = None
    type: str = "metric"


# Khoj is the one ask-and-search surface, the same word in the renderer, the
# API route, an MCP tool, and here. It is not a sixth declaration type: it
# does not vary per bundle and nothing about it is linted, so it is a
# constant on the manifest every bundle already carries, not an atom of its
# own. care_phc_mcp/catalogue.go reads manifest.khoj.tool for the tool name it
# registers, and manifest.khoj.description word for word as that tool's
# description, so this is the one place an agent reading the compiled
# catalogue learns the word without being told.
KHOJ = {
    "tool": "khoj",
    "endpoint": "/api/v1/phc/khoj",
    "description": (
        "Searches, answers, and proposes. It never commits: every write it "
        "returns is a proposal for a clinician to review and confirm on "
        "screen, exactly like every other write tool here."
    ),
}


@dataclass(frozen=True)
class Manifest:
    """catalogue.json["manifest"]: which declarations this build loaded, from
    bundles/<id>/bundle.yaml. Named manifest and not bundle because
    catalogue.json["bundles"] already means role bundles (capability sets)
    and catalogue.go reads it under that name."""
    id: str
    version: str
    title: str
    operations: list
    workflows: list
    views: list
    instruments: list
    metrics: list
    khoj: dict = field(default_factory=lambda: dict(KHOJ))


# --------------------------------------------------------------------------
# Kernel records. What the kernel writes and reads back.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AuditRecord:
    """One line of the audit trail. The five fields the guard fills in are
    the guard's dict verbatim; the kernel adds where and when."""
    id: str
    thread: str
    operation: str
    actor: Optional[str]
    surface: str                    # RENDERED | MCP
    payload: dict
    outcome: str                    # allowed | proposed | denied: <reason> | confirmed | rejected
    at: str                         # ISO 8601, UTC
    proposal: Optional[str] = None  # proposal id when outcome came from one

    @classmethod
    def from_guard(cls, audit: Mapping[str, Any], *, id: str, thread: str,
                   at: str, proposal: Optional[str] = None) -> "AuditRecord":
        return cls(id=id, thread=thread, at=at, proposal=proposal,
                   operation=audit["operation"], actor=audit.get("actor"),
                   surface=audit["surface"], payload=dict(audit.get("payload") or {}),
                   outcome=audit["outcome"])


@dataclass(frozen=True)
class Proposal:
    """A write that a machine, or an instrument, wants and a person has not yet
    accepted. Confirmation is a second guard pass on the rendered surface with
    the payload as it stands after the person edited it; the original payload
    stays here so the audit shows what was proposed versus what was committed.
    The kernel never turns a proposal into a write on its own."""
    id: str
    thread: str
    operation: str
    payload: dict
    proposed_by: Optional[str]
    surface: str                    # MCP, or RENDERED for an instrument draft
    status: str                     # PROPOSAL_STATUSES
    created_at: str
    flags_raised: list = field(default_factory=list)
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    final_payload: Optional[dict] = None   # set on confirm


@dataclass(frozen=True)
class Draft:
    """What an instrument hands the renderer. Not a write, not a proposal: a
    set of values to put in editable fields. `values` are keyed by link_id.
    `confidence` is per link_id, 0 to 1, and the renderer must highlight any
    field below 0.9 for re-reading. A Draft with no values is the fail-closed
    outcome and means: show the keypad. `evidence` is per link_id, the
    words the value was taken from, shown beside it for the readback."""
    instrument: str
    operation: str
    values: dict
    confidence: dict = field(default_factory=dict)
    transcript: Optional[str] = None
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ThreadRef:
    """Enough to list a thread without deriving its state."""
    id: str                         # the subject resource id
    workflow: str
    subject: dict                   # subject fields the views may show
    opened_at: str


# --------------------------------------------------------------------------
# The Store protocol: what the kernel needs from a system of record.
# --------------------------------------------------------------------------

class Store(Protocol):
    """Adapter interface. Deliberately small: nine methods, and a SQLite file
    and a CARE REST client can both satisfy every one.

    Every read is scoped to a thread. How a resource joins to the thread's
    subject (patient via encounter, dispense via encounter) is the adapter's
    business and is not expressible in a declaration; that keeps the
    declarations portable and the adapters honest about their schema.

    Nothing here commits a proposal. The kernel confirms by evaluating the
    guard again and then calling write(); the store only stores.
    """

    # reads that feed state derivation, views and metrics
    def count(self, resource: str, *, thread: Optional[str], where: Query) -> int: ...

    def select(self, resource: str, *, thread: Optional[str], where: Query,
               fields: Sequence[str], limit: int) -> list: ...

    def threads(self, *, workflow: str, scope: str) -> list: ...
    # -> list[ThreadRef]. scope is a VIEW_SCOPES value.

    def stored_flags(self, thread: str) -> frozenset: ...

    # writes, one per resource kind, by name
    def write(self, resource: str, record: Mapping[str, Any], *, thread: str) -> str: ...
    # -> the new record's id. Called once per entry in Operation.writes.

    def raise_flag(self, thread: str, flag: str) -> None: ...
    # only for flags the workflow lists under `stored`; the kernel checks.

    # proposals and audit
    def put_proposal(self, proposal: Proposal) -> None: ...
    # insert or replace by proposal.id

    def proposals(self, thread: str, *, status: Optional[str] = None) -> list: ...

    def append_audit(self, record: AuditRecord) -> None: ...

    def audit(self, thread: str) -> list: ...


# --------------------------------------------------------------------------
# API shapes. Stable JSON: these are what the renderer and the MCP server
# read. Field names are frozen; add, never rename.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class StepStatus:
    station: str
    label: str                      # the step's done_when flag, for the renderer's wording
    status: str                     # STEP_STATUSES


@dataclass(frozen=True)
class ThreadView:
    """GET /api/v1/phc/threads/{id}/

    Same fields the renderer's Thread type has (care_phc_fe/src/types.ts when
    this was written, web/src/types.ts now), with two changes the
    frontend agent owns tonight: `patient` is now `subject`, because a thread
    can be about an encounter, a household or anything the workflow names;
    and `line` is returned instead of the frontend's hard-coded LINE constant,
    so the panel draws whatever the workflow declares. `team` is not returned;
    it is the distinct actors in `audit` and the renderer derives it.
    """
    id: str
    workflow: str
    subject: dict
    flags: list                     # sorted
    station: Optional[str]          # None once the line is complete
    line: list                      # of StepStatus, in workflow order
    actions: list                   # of Operation, ordered by thread.actions() rules
    proposals: list                 # of Proposal with status pending
    audit: list                     # of AuditRecord, oldest first
    capabilities: list              # every capability
    held: list                      # the caller's
    nudge: str = ""
    closes: Optional[str] = None    # loop_closer for `station`; None once complete

    def to_json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QueueRow:
    thread: str
    subject: dict                   # only View.columns
    station: Optional[str]
    flags: list
    badges: dict                    # flag -> style, only the flags present
    opened_at: str
    # colour law (Vernier): when this row entered its current station, if the
    # store tracks it. elapsed = now - (entered_at ?? opened_at). Optional and
    # unpopulated today; adding a value here is a later group's work.
    entered_at: Optional[str] = None


@dataclass(frozen=True)
class TaskRow:
    """One resolved row of a tasklist: a title, a count, the matching
    threads, and the verb if the declaration named one. Copy rule: a title
    and a count, no prose, so this carries nothing else to render."""
    title: str
    count: int
    threads: list                   # thread ids
    operation: Optional[str] = None


@dataclass(frozen=True)
class MetricValue:
    metric: str
    value: float
    numerator: int
    denominator: Optional[int]
    unit: str
    window: str
    window_start: str


@dataclass(frozen=True)
class ViewResult:
    """GET /api/v1/phc/views/{id}/            queue and dashboard
       GET /api/v1/phc/views/{id}/?thread=x   summary

    `rows` is by kind: QueueRow for a queue, {title, resource, rows} per
    Section for a summary (`resource` is the section's declared resource, or
    None for one that shows a kernel structure), MetricValue for a dashboard,
    TaskRow for a tasklist. `groups` is set only when the view declares
    group_by: a list of {key, count} in line order."""
    view: str
    kind: str
    rows: list
    generated_at: str
    groups: list = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


# Routes. The MCP server already calls the first three; they do not move.
ROUTES = {
    "whoami": "GET  /api/v1/phc/whoami/",
    "read": "POST /api/v1/phc/operations/{op}/",
    "propose": "POST /api/v1/phc/operations/{op}/propose/",
    "commit": "POST /api/v1/phc/operations/{op}/commit/",     # rendered only; body {thread, payload, confirmed}
    "confirm": "POST /api/v1/phc/proposals/{id}/confirm/",    # rendered only; body {payload, confirmed}
    "reject": "POST /api/v1/phc/proposals/{id}/reject/",
    "thread": "GET  /api/v1/phc/threads/{id}/",
    "subject": "GET  /api/v1/phc/subjects/{id}/",   # the spine: one subject, every visit
    "view": "GET  /api/v1/phc/views/{id}/",
    "catalogue": "GET  /api/v1/phc/catalogue/",
}


# Top-level keys of catalogue.json, split by who narrows them. The first four
# are catalogue wide: `operations` is the union over every bundle, because the
# Go server embeds the whole file and asks the kernel which bundle it loaded.
# The rest are the one loaded bundle's, and are exactly what
# kernel.declarations.compile_json emits, so a new one belongs in BUNDLE_KEYS
# and nowhere else.
CATALOGUE_KEYS = ("capabilities", "bundles", "states", "operations")
BUNDLE_KEYS = ("manifest", "workflows", "views", "instruments", "metrics", "scribe")


def compiled_keys() -> Iterable[str]:
    """Top-level keys of catalogue.json after this contract."""
    return CATALOGUE_KEYS + BUNDLE_KEYS
