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
from catalogue.vocab import INSTRUMENT_KINDS  # noqa: F401  re-exported

# --------------------------------------------------------------------------
# Closed vocabularies for the new declaration types. These join, not replace,
# the ones in catalogue/vocab.py. Lint rejects anything outside them.
# --------------------------------------------------------------------------

DECLARATION_TYPES = ("operation", "workflow", "view", "instrument", "metric",
                     "schedule")
VIEW_KINDS = ("queue", "summary", "dashboard", "tasklist")
VIEW_SCOPES = ("today", "open", "all")
SUMMARY_SHOW = ("line", "actions", "proposals", "audit", "flags")
# INSTRUMENT_KINDS is re-exported from catalogue/vocab.py above, not defined
# here: an instrument atom's `kind:` and an operation's `instrument:` are one
# vocabulary, the second being the subset a pill can draw. Writing it out in
# both files is what let them drift (`palette` here, `spoken-prompt` there).
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
    # The level between the spine and the subject: one course of care that
    # starts, runs and ends, holding some of a person's visits. Optional,
    # and a bundle whose work genuinely does not group that way declares
    # none and writes no episode row. See kernel/spine.py.
    episode: Optional[str] = None


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
    # Which of `columns` a row wears as a LABEL rather than as detail: a pill
    # beside the name, against the quiet line underneath. The renderer had
    # been inferring this from the shape of the question that collects the
    # answer, offering a closed set and not requiring one. That rule picked
    # exactly the right column today and would have picked a second one
    # silently the day a bundle added another optional choice. A bundle says
    # which, or none of them are labels. A subset of `columns`.
    labels: list = field(default_factory=list)
    # How a row reached this queue, and the three things a screen needs to
    # draw it without knowing what it means: `column` (which of `columns`
    # carries the fact), `mark` (the single value that earns a mark on the
    # row's number) and `label` (what a filter chip over those rows is
    # called). Empty for a view that does not distinguish arrivals, and then
    # no mark and no chip are drawn.
    #
    # Separate from `labels` because this is not a pill. It is the least
    # important thing on a row, so it is a mark beside the number rather than
    # a word competing with the programme; and it still has to be filterable,
    # because "who walked in without the desk seeing them" is a question the
    # queue is the only place to ask.
    provenance: dict = field(default_factory=dict)
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
    says: Optional[str] = None      # a line shown or spoken beside the fields
    spoken: bool = True             # whether that line is spoken aloud
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
class Contact:
    """One thing a schedule says is owed, measured in days from the anchor.

    `due` is the day it is aimed at and `opens`/`closes` are the window
    either side, because A VISIT DUE AT 28 WEEKS IS NOT LATE AT 28 WEEKS AND
    ONE DAY. Collapsing the window to a single date paints a screen red
    every day for women who are doing nothing wrong, and a screen that is
    red every day is one nobody reads.

    `authority` is `statutory` (the programme requires it and the centre
    reports it), `clinical` (good practice this centre follows) or `centre`
    (this facility's own choice). Without it nobody can tell what a centre
    is obliged to do from what somebody added, and the first dispute with a
    district officer settles it the wrong way.
    """
    id: str
    title: str
    due: int
    opens: int
    closes: int
    owner: str
    operation: str
    authority: str
    escalates_to: Optional[str] = None
    # The line this contact fills in the programme's own register, which is
    # not the same as the contact: a centre following eight antenatal
    # contacts still reports four.
    reports_as: Optional[str] = None


@dataclass(frozen=True)
class Schedule:
    """What a centre owes somebody over the life of one episode.

    In FHIR this is a PlanDefinition and what it produces for one person is
    a CarePlan. It is a declaration rather than a key in bundle.yaml --
    against the standing presumption there, which plugins, templates and the
    catchment all follow -- because it carries data that exists nowhere else
    and needs a body naming each line's clinical source and its sign off. A
    clinical protocol folded into a YAML key with no body is a protocol
    nobody can audit.
    """
    id: str
    title: str
    summary: str
    # The episode TYPE this applies to, in the bundle's own word.
    episode: str
    # Days from the recorded date to the start of the arc, per dating basis.
    # A woman dated from her last period is at day 0 on that date; one dated
    # from a scan's estimated delivery date is 280 days before it. THIS IS
    # THE ONLY OBSTETRICS IN THE SYSTEM and it is in a bundle, where a
    # facility can read it and a clinician can sign it off.
    anchor: dict
    contacts: tuple
    # Where the date the offsets apply to comes from. `recorded` (the
    # default) is the date somebody wrote down, which is right for an event
    # that happened before the record of it. `opened` is the moment the
    # episode itself was opened, which is right for one where the record IS
    # the event, such as a referral being raised.
    anchor_from: str = "recorded"
    type: str = "schedule"


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
    # Optional, and the only manifest list that is: every bundle that
    # existed before schedules did has no `schedules:` key, and a required
    # one would have made adding this type a change to every bundle file
    # including a laboratory's, which schedules nothing.
    schedules: list = field(default_factory=list)
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
    """Adapter interface. Deliberately small: eleven methods, and a SQLite file
    and a REST client over somebody else's record can both satisfy every one.

    Every read is scoped to a thread. How a resource joins to the thread's
    subject (patient via encounter, dispense via encounter) is the adapter's
    business and is not expressible in a declaration; that keeps the
    declarations portable and the adapters honest about their schema.

    Nothing here commits a proposal. The kernel confirms by evaluating the
    guard again and then calling write(); the store only stores.

    TEN METHODS UNTIL 2026-11-01, AND THE ELEVENTH IS A LOCK THIS SEAM DID NOT
    HAVE. `issue_token` is the one method here that is not a read or a plain
    write: it is an atomic reservation, and it is on the protocol because
    kernel/tokens.py could not keep its promise without one. Reading the day's
    numbers and then writing the next one is two steps, so two arrivals inside
    one instant were handed the same number. That was written down in
    kernel/tokens.py as the owner's to schedule rather than discovered from two
    patients holding the same slip, and this is the scheduled change.

    It is the protocol's business and not an adapter extra for the reason the
    Spool comment below gives about queues: a property every adapter must hold
    cannot be optional on the interface. An adapter that cannot issue a number
    once has not implemented this protocol.
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

    def issue_token(self, *, workflow: str, scope: str, floor: int) -> int: ...
    # -> the number this arrival is given, and it is given to nobody else.
    #
    # The one method on this protocol that must be ATOMIC against every other
    # caller, including callers in other processes against the same file. Two
    # arrivals racing must come back with two different numbers, and a set of
    # them must have no hole: a waiting room is one room and a number nobody
    # was issued is a number nobody answers to.
    #
    # `floor` is the lowest number the adapter may hand out, and it is the
    # KERNEL's arithmetic: one past the highest already issued, skipping any
    # token that is not on the sequence. That rule stays in kernel/tokens.py
    # so that two adapters cannot answer it differently. What the adapter owns
    # is only the atomicity, which is the half the kernel cannot provide: it
    # holds no lock and has no transaction, and inventing one here would put a
    # transaction in the kernel.
    #
    # So the contract is exactly: return a number not less than `floor`, never
    # return the same number twice for one (workflow, scope, day), and do it
    # in one indivisible step. An adapter that reads and then writes has not
    # implemented this.

    # proposals and audit
    def put_proposal(self, proposal: Proposal) -> None: ...
    # insert or replace by proposal.id

    def proposals(self, thread: str, *, status: Optional[str] = None) -> list: ...

    def append_audit(self, record: AuditRecord) -> None: ...

    def audit(self, thread: str) -> list: ...


# --------------------------------------------------------------------------
# The Spool protocol: what the kernel needs from a facility's outbox.
#
# BESIDE Store, not behind it, and the reason is the Store docstring's own
# sentence: "a SQLite file and a REST client over somebody else's record can
# both satisfy every one". Three things break that if an outbox goes behind
# Store:
#
# 1. `write(resource, record: Mapping) -> id` takes a mapping. A consultation
#    recording is a blob. Putting blobs behind Store makes every adapter a
#    blob store, including a REST client over an EMR that is not ours.
# 2. An outbox row is not clinical state. It is this facility's own record of
#    what it still owes a remote service, and `resource` would have to join
#    vocab.CARE_RESOURCES for a thing no CARE resource corresponds to.
# 3. An outbox must survive the system of record being unreachable, which is
#    the whole point. A queue kept inside somebody else's record is a queue
#    that is empty exactly when it is needed.
#
# So: five methods, their own protocol, their own adapter, and the kernel
# reads both through its own module (kernel/queues.py). What is NOT duplicated
# is the pending set: for a national document there is no body here at all,
# because the rows already in the Store are the record and the document is
# re-projected at send time. That is kernel/directory.py's rule, which says
# "the publish queue is not a queue", applied as far as it goes. It does not
# reach audio, because audio's bytes exist nowhere else.
#
# KNOWN, AND PINNED BY A CHECK RATHER THAN FIXED HERE: kernel/directory.py
# calls `store.record_directory_id(...)`, an eleventh method the Store
# protocol above does not declare. scripts/check_queues.py holds the list of
# off-protocol Store calls in the kernel at exactly that one, so a second one
# fails the gate. Fixing the first is a change to the protocol and to the
# adapter test that pins its ten names, and is not this module's to make.
# --------------------------------------------------------------------------

# What a queued item is for. `audio` is a consultation recording owed to a
# speech service; `document` is a visit owed to a national record. Two kinds
# and not one because the bodies come from different places: audio's bytes
# are held here, a document's body is re-projected from the Store.
QUEUE_KINDS = ("audio", "document")

# An item's life. Every one of these is a state somebody can be shown.
#
#   ready     waiting for a line
#   sending   claimed, and the outcome is not yet known
#   sent      the remote acknowledged it, and said so with a receipt
#   failed    tried the limit and stopped. Visible, not retried, not lost.
#   refused   the guard denied it at the moment it would have been sent
#   held      the remote cannot say whether it already has this, so nobody
#             may resend it and nobody may throw it away. A person decides.
QUEUE_STATES = ("ready", "sending", "sent", "failed", "refused", "held")


@dataclass(frozen=True)
class QueueItem:
    """One thing this facility owes a remote service.

    WHAT THIS ROW HOLDS, which is the most sensitive decision in the module:
    identifiers and state, never content. No name, no mobile number, no
    Aadhaar number, no OTP, no answer a clinician typed, and for a document no
    body at all. `blob` is a path to bytes for an `audio` item and empty
    otherwise, and the file it names is called after `id`, which is opaque.
    `last_error` is the one free text field and it is scrubbed before it is
    written; kernel/queues.py is the only writer and scripts/check_queues.py
    holds it to all three of this project's rules.

    `key` is what the remote is asked under, and it is the whole of the
    not-sent-twice property: it is supplied by us rather than minted by them,
    so the same item asked for twice is one job on their side. For audio it is
    the scribe transaction id, which api/scribe.py already supplies as
    `txn_id`. For a document it is the encounter id, which kernel/fhir.py
    already writes as `identifier.value`. Neither is invented here.
    """
    id: str
    kind: str                       # QUEUE_KINDS
    key: str                        # the idempotency key the remote is asked under
    thread: str
    operation: str                  # the operation this item belongs to
    capability: str                 # what the guard re-judges at send time
    facility: str                   # the shape this was admitted under
    created_at: str
    # Text, not Optional[str]: every field on this row persists as text and a
    # None that reads back as "" is a field whose type lies about the table.
    actor: str = ""
    blob: str = ""                  # audio only: the path to the bytes
    state: str = "ready"            # QUEUE_STATES
    attempts: int = 0
    last_error: str = ""            # scrubbed by kernel/queues.py, never raw
    claimed_at: str = ""
    sent_at: str = ""
    receipt: str = ""               # what the remote called it


class Spool(Protocol):
    """A facility's outbox. Five methods, and `claim` is the only subtle one.

    Nothing here decides anything. It does not know what a plugin is, what the
    guard is, or when to retry: kernel/queues.py owns all of that, exactly as
    kernel/state.py owns what a flag means and Store only stores.
    """

    def put(self, item: QueueItem) -> None: ...
    # insert or replace by item.id

    def get(self, item_id: str) -> Optional[QueueItem]: ...

    def items(self, *, state: Optional[str] = None, kind: Optional[str] = None,
              limit: int = 500) -> list: ...
    # -> list[QueueItem], oldest first

    def claim(self, item_id: str, *, at: str) -> Optional[QueueItem]: ...
    # Move ready -> sending and add one to attempts, ATOMICALLY, and return
    # the item as it now stands. None if it was not ready any more, which is
    # how two pumps running at once cannot both take one item. The write must
    # be durable before this returns: a crash one instruction later has to
    # leave the item in `sending`, because an item that is still `ready` after
    # a crash mid-send is an item a recovery will send a second time.

    def settle(self, item_id: str, *, state: str, at: str, receipt: str = "",
               error: str = "") -> None: ...
    # The one write that ends an attempt. `state` is a QUEUE_STATES value.



# --------------------------------------------------------------------------
# The PatientDirectory protocol: what the kernel needs from a patient
# directory. Here beside Store, and not in care_phc/connectors/directory/,
# for one structural reason: the kernel needs this interface. Resolving who is
# standing at the desk is kernel logic (kernel/directory.py), so a protocol
# kept in a connector would make the kernel import a connector, which the
# layer table in kernel/ARCHITECTURE.md forbids. The scribe and ABDM
# interfaces stay in their own connectors because nothing above them needs
# one; this one is the Store pattern instead, protocol here and implementation
# outside.
#
# Settled 2026-10-31: Eka's patient directory is the source of truth for
# patient identity and we do not rebuild a local patient master. The vendor is
# care_phc/connectors/directory/eka.py.
# --------------------------------------------------------------------------

class DirectoryError(RuntimeError):
    """Any failure from a patient directory, scrubbed on the way out.

    The only error type that crosses this boundary, for the reason AbdmError
    and ScribeError exist: a vendor exception carries the response body
    verbatim, and a patient profile is in that body.

    `reachable` separates "the directory answered and said no" from "there was
    no directory to ask". kernel/directory.py treats those differently and a
    clinic depends on the difference: one means nobody matched, the other
    means nobody looked, and a clerk who cannot tell them apart registers a
    duplicate.
    """

    def __init__(self, message, *, status=None, reachable=True):
        super().__init__(message)
        self.status = status
        self.reachable = reachable


@dataclass(frozen=True)
class DirectoryPatient:
    """One directory profile, in this product's words rather than the wire's.

    A vendor's field names are abbreviated and an implementation translates
    them. They are not repeated above this boundary, because the day the
    vendor changes is the day that would be two translations instead of one.

    `directory_id` is the directory's own identifier (Eka's `oid`). It is an
    identifier and never this product's row id, for the same reason
    `abha_number` is not: a national or platform identifier is a fact about a
    person, not our name for their row. See kernel/directory.py.
    """
    directory_id: str
    name: str = ""
    sex: str = ""                   # this product's words: female | male | other
    dob: str = ""                   # ISO 8601, as the directory holds it
    age: Optional[int] = None       # derived from dob where there is one
    phone: str = ""
    abha_address: str = ""
    abha_number: str = ""
    # Which field the search matched on, kept so a suggestion can say why this
    # person was offered. The readback rule is the one voice already has: a
    # value shown with the words it came from.
    matched_on: str = ""
    extras: dict = field(default_factory=dict)


class PatientDirectory(Protocol):
    """Four methods, and the split between them is the whole design.

    A read that fails is a smaller answer, not a broken clinic:
    kernel/directory.py answers from the local cache and reports that the
    directory was not asked. A write that fails is a row that stays
    unpublished and is published later.

    There is deliberately no `update`: a profile edit belongs to whoever owns
    the profile, and a facility that can edit the master has rebuilt the
    master. There is deliberately no `delete`: Eka's REST API has one and
    nothing in this product may call it, because deleting a person while their
    visits sit in our store leaves clinical records pointing at nobody.

    What a caller may never do with a result is write it. A hit is a
    suggestion about who is at the desk, and a suggestion is not an assertion:
    it becomes values in editable fields, committed by a tap through
    phc.op.patient-register, so there is still one path to a write and the
    guard is on it.
    """

    def search(self, prefix: str, *, limit: int = 10) -> Sequence[DirectoryPatient]:
        """Profiles whose name, mobile or username starts with `prefix`.

        Raises DirectoryError with `reachable=False` when the directory could
        not be asked. It never returns an empty list to mean "could not ask".
        """

    def by_mobile(self, mobile: str) -> Sequence[DirectoryPatient]: ...
    # Profiles on this number. A household shares one, so several come back.

    def fetch(self, directory_id: str) -> Optional[DirectoryPatient]: ...
    # One profile, or None if the directory has no such id.

    def publish(self, patient: Mapping[str, Any]) -> str: ...
    # Put a locally registered patient in the directory, return its id.


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
    # The patient directory. `search` always answers 200: a directory that
    # could not be asked is a field in the body, never a status, because a
    # clerk looking for somebody already in today's line must not be shown an
    # error about a directory they were not relying on.
    "patient_search": "GET  /api/v1/phc/patients/search/?q=",
    "patient_pending": "GET  /api/v1/phc/patients/pending/",
    "patient_publish": "POST /api/v1/phc/patients/publish/",   # facility.admin
    "view": "GET  /api/v1/phc/views/{id}/",
    "catalogue": "GET  /api/v1/phc/catalogue/",
    # What every form asks, by the slug an operation names. The renderer
    # read these off disk through a build time glob until this route
    # existed, which left the forms the one part of a screen the kernel
    # did not serve.
    "questionnaires": "GET  /api/v1/phc/questionnaires/",
    "valueset": "GET  /api/v1/phc/valuesets/{slug}/?q=",
}


# Top-level keys of catalogue.json, split by who narrows them. The first four
# are catalogue wide: `operations` is the union over every bundle, because the
# Go server embeds the whole file and asks the kernel which bundle it loaded.
# The rest are the one loaded bundle's, and are exactly what
# kernel.declarations.compile_json emits, so a new one belongs in BUNDLE_KEYS
# and nowhere else.
CATALOGUE_KEYS = ("capabilities", "bundles", "states", "operations")
# `plugins`, `facilities` and `vocabulary` are the declarations an engine that
# is not the Python needs in order to answer GET /facility for itself: which
# plugins a bundle declares, which shapes it declares, and the bundle's own
# capability, role and state words. They are carried UNRESOLVED, so the
# compiled catalogue stays byte identical across every facility shape of one
# bundle and the shape is still chosen at runtime by PHC_FACILITY.
# `mapping` is which answer becomes which column, per operation, compiled by
# kernel/mapping.py. It was deliberately absent from the compiled artifact
# while nothing outside the kernel wrote rows; kernel/mapping.py's own
# docstring says to add it "when an out of process consumer needs one", and
# the Go backend's write path is that consumer. Carried per operation and
# already resolved: the `question:` codings are bound at build time, so what
# travels is plain JSON and the engine that reads it re-checks every code
# against the same value set before it fills a column.
#
# `documents` is which section of which profile each kind of row is filed
# under: bundles/<id>/bundle.yaml's own `documents:` key, linted by
# kernel.declarations._lint_documents against kernel/fhir.PROFILES. Added
# 2026-11-01, after G7, on the owner's decision. It was deliberately absent
# while nothing outside the kernel projected a document; the outbox is the
# first production caller of kernel.fhir.document(), the outbox is being
# ported, and a Go engine that cannot read the placement cannot publish at
# all.
#
# ITS SECTIONS ARE A LIST AND NOT A MAPPING, which is the whole of its shape
# decision and is `state_order`'s reason over again. The projection iterates
# the declared sections IN ORDER, and that order is observable three times: the
# order the sections come out in, the order the Bundle's entries come out in,
# and the order the authors are discovered in. write_catalogue dumps this file
# with sort_keys=True, so a mapping would arrive alphabetically; the PHC
# bundle declares ChiefComplaints, Medications, DocumentReference, which is not
# alphabetical, so a mapping here would silently publish every consultation
# with its narrative and its medicines the other way round. A list cannot be
# reordered by a dumper, so the order is carried rather than restated beside
# the thing it orders.
BUNDLE_KEYS = ("manifest", "workflows", "views", "instruments", "metrics",
               "scribe", "plugins", "facilities", "vocabulary", "mapping",
               "documents", "schedules")


def compiled_keys() -> Iterable[str]:
    """Top-level keys of catalogue.json after this contract."""
    return CATALOGUE_KEYS + BUNDLE_KEYS
