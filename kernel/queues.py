"""Audio and national records wait for the line, and never drop.

The problem, in one paragraph
----------------------------
A primary health centre's internet comes and goes. A consultation is recorded
while the line is down and the recording must still reach the speech service.
A visit ends while the line is down and its national document must still reach
ABDM. The product's premise is that the point of care keeps working, so this is
not a convenience bolted on at the end: it is what makes the rest true.

Three properties, each one separate
-----------------------------------
1. NOTHING IS LOST. An attempt is claimed durably BEFORE it is sent, so a
   crash mid-send leaves the item in `sending` rather than back in `ready` or
   gone. `recover()` picks those up.
2. NOTHING IS SENT TWICE. Every item carries a `key` WE supply, not one the
   remote mints, so one item asked for twice is one job on their side. And
   recovery never resends blind: it asks the remote what it already has
   (`Sender.delivered`), and an item the remote cannot speak for is parked in
   `held` for a person rather than guessed about.
3. NOTHING IS REPORTED AS SENT WHEN IT WAS NOT. `sent` is written only after
   a receipt comes back, and if the receipt cannot be written down the item
   stays `sending` and is reported as a failure of that sweep. It does not
   become `sent` on the strength of a send nobody recorded. That is the
   dangerous case kernel/directory.py already names, for the same reason: the
   remote has it, we did not write down that it has it, and the next sweep
   must not hand it over again.

Each of the three is proved in scripts/check_queues.py by MAKING IT HAPPEN, in
a real subprocess killed with SIGKILL against a real file on disk, rather than
by reading this docstring and agreeing with it.

Where the bodies come from, and why documents keep none here
------------------------------------------------------------
kernel/directory.py says of unpublished patients: "the publish queue is not a
queue. It is a query over the rows we already keep." That rule is applied here
as far as it goes.

- A DOCUMENT keeps no body. The rows in the Store are the record, and the
  bundle is re-projected by `kernel.fhir.document()` at the moment of sending,
  through the bundle's own `documents:` declaration. So there is no second copy
  to drift, nothing clinical is written to the outbox, and a correction made
  while the item waited is in the document that finally leaves. THIS IS THE
  FIRST PRODUCTION CALLER OF `fhir.document()`. Until now only checks
  projected documents, so the projection has never run anywhere but a check;
  `document_body()` below is where that changes and it is worth saying plainly.
- AUDIO keeps its bytes, because they exist nowhere else. A recording is not
  derivable from anything, which is exactly why losing it is unrecoverable and
  why `api/scribe.py start()` deleting its one temporary file in a `finally` is
  the gap this module closes. The bytes go to a file named after the item's
  opaque id, outside the repository, and are deleted the moment the remote
  acknowledges them.

What is in the outbox row, which is the privacy decision
--------------------------------------------------------
Identifiers and state. No name, no mobile number, no Aadhaar number, no OTP,
no answer a clinician typed, and for a document no body at all. The one free
text field is `last_error` and `_scrubbed()` below is the only writer of it:
it removes anything Aadhaar shaped through `care_phc/connectors/redact.py`,
reduces anything mobile shaped to its last four digits through the same rule
`care_phc/connectors/abdm/eka.py last4()` states, drops anything OTP shaped
entirely, and truncates. scripts/check_queues.py holds it to all three.

Retry is visible, bounded, and unmeasured
-----------------------------------------
A queue that retries forever is a defect and so is one that gives up quietly.
So: `attempts` and `last_error` are on the row, `status()` turns the whole
outbox into sentences a person can read, and an item that reaches
`MAX_ATTEMPTS` stops in `failed` where it stays visible and is neither retried
nor thrown away. THE NUMBERS BELOW ARE ENGINEERING DEFAULTS AND NOBODY HAS
MEASURED THEM AGAINST A REAL CLINIC LINE, in exactly the sense
`care_phc/connectors/codification/eka.py` records its four second timeout as a
ceiling on a guess.

The guard is re-run at the moment of sending
--------------------------------------------
`test_a_proposal_is_judged_again_at_confirm_and_not_when_it_was_made` in
kernel/tests/test_kernel.py is the precedent: a proposal is judged against the
world as it is when it is acted on, not as it was when it was made. A queue is
that problem with a longer gap. So `pump()` takes a `permit` callable, calls it
BEFORE it claims, and an item the guard now denies becomes `refused` and is
never sent. An item queued under capabilities somebody has since lost, or for
a plugin this centre has since switched off, does not go out.

Pure: everything takes a `Spool`, a `Sender` and a clock, and returns values.
Opens no socket, reads no environment, imports no connector.

Run: python3 -m kernel.queues
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

from kernel import fhir
from kernel.contracts import QUEUE_KINDS, QUEUE_STATES, QueueItem

# --------------------------------------------------------------------------
# Settings. Every number here is a guess and is labelled as one.
# --------------------------------------------------------------------------

# How many times an item is tried before it stops in `failed`. Six, so that
# with the backoff below an item queued at the start of a clinic session is
# still being tried at the end of it and has stopped long before a week of
# them pile up. NOT MEASURED against a real primary health centre's line. A
# deployment that has measured one should raise or lower it and say what it
# measured.
MAX_ATTEMPTS = 6

# The wait before attempt n, in seconds, by how many attempts have already
# been made. Doubling, with a ceiling, so a dead line is not hammered and a
# line that flickers back is used within a minute. AGAIN, NOT MEASURED: the
# shape is the conventional one and the numbers are a guess. What they are
# chosen against is a clinic session rather than a service level: the last
# gap is long enough that an afternoon of outage costs a handful of attempts.
BACKOFF_SECONDS = (0, 30, 120, 600, 1800, 3600)

# How long an item may sit in `sending` before `recover()` considers it
# abandoned rather than in flight. Longer than any single send should take and
# shorter than a clinic session. A GUESS.
IN_FLIGHT_SECONDS = 900

# Where the audio waits. Outside the repository, deliberately and not
# incidentally: a consultation recording is identifiable health data and a
# source tree is copied, zipped and pushed. Overridden per deployment, which
# is where the answer actually belongs, because a facility's disk encryption
# and its backup policy are the things that make this safe and neither is
# ours to choose.
SPOOL_ENV = "PHC_SPOOL"
SPOOL_DEFAULT = "~/.local/share/phc/spool"

# Mode on the directory and on every recording in it: the owner only. A
# clinic machine has more than one account on it.
SPOOL_DIR_MODE = 0o700
SPOOL_FILE_MODE = 0o600


def spool_root():
    """Where recordings wait. Never under the repository."""
    return os.path.abspath(os.path.expanduser(
        os.environ.get(SPOOL_ENV) or SPOOL_DEFAULT))


# --------------------------------------------------------------------------
# What must never reach this row, or a log line about it
# --------------------------------------------------------------------------

# Anything that looks like a one time password, removed whole. OTPs are never
# persisted anywhere in this project and an error message is not an exception
# to that: a gateway that echoes the code back in its own refusal would
# otherwise write it to our disk. Matched on the word beside it rather than on
# the digits alone, because four to eight bare digits is also an age, a token
# number and a systolic reading.
_OTP = re.compile(r"\b(otp|o\.t\.p|one[ -]time[ -](?:password|code|pin)|pin)\b"
                  r"\W{0,4}\d{4,8}\b", re.I)
OTP_MARK = "<otp-removed>"

# Anything mobile shaped, reduced to its last four digits. The rule is the one
# care_phc/connectors/abdm/eka.py last4() states, applied to free text: ten
# digits or more, so a token number, an age and a year are not caught. An
# optional country code is eaten with it, so +91 does not survive as a prefix
# on a number whose body has gone.
_MOBILE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(\d[\d -]{8,}\d)(?!\d)")

# How much of a remote's sentence is kept. Long enough to name a cause, short
# enough that a response body cannot arrive whole through the gap.
ERROR_CHARS = 300


def _mobile_to_last4(match):
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) < 10:
        return match.group(0)
    return "<mobile ending %s>" % digits[-4:]


def scrubbed(text):
    """The only text this module ever writes to disk or to a log.

    Three rules, in the order that makes each one safe. The OTP goes first,
    because it is matched by the word next to it and the mobile rule would
    otherwise have eaten a long enough code. Aadhaar is next and is
    `care_phc/connectors/redact.py`'s, imported rather than re-spelled, which
    is the whole reason that module was taken out of the ABDM connector.
    Mobile is last, because an Aadhaar number is twelve digits and would
    otherwise be reduced to its last four and called a phone number, which is
    a worse answer than removing it: four digits of an Aadhaar number is still
    four digits of an Aadhaar number.
    """
    from care_phc.connectors import redact

    out = _OTP.sub(OTP_MARK, str(text or ""))
    out = redact.aadhaar(out)
    out = _MOBILE.sub(_mobile_to_last4, out)
    return out[:ERROR_CHARS]


# --------------------------------------------------------------------------
# The seam: what sends one item
# --------------------------------------------------------------------------

class Unsendable(RuntimeError):
    """The line was down, the remote refused, or the body would not build.

    Scrubbed by `pump()` before it is written down, never before: a sender
    raises whatever sentence it has and this module is the one filter, so a
    new sender cannot forget to scrub.
    """


@dataclass(frozen=True)
class Delivery:
    """What a remote can tell us about something we may already have sent.

    Three answers and not two, and the third is why this is a dataclass rather
    than an Optional[str]. `known=False` means the remote could not be asked
    or could not say, which is NOT the same as "it does not have it": acting
    on that confusion is how a national record gets filed twice. It is the
    same distinction `DirectoryError.reachable` draws and for the same reason.

        Delivery(known=False)                 cannot say. Nobody resends.
        Delivery(known=True, receipt="")      definitely does not have it.
        Delivery(known=True, receipt="abc")   has it, and calls it abc.
    """
    known: bool
    receipt: str = ""

    @property
    def delivered(self):
        return bool(self.known and self.receipt)


class Sender(Protocol):
    """What the queue needs from whatever carries one kind of item away.

    Two methods, and the second is the one that makes the second property
    provable. A sender with no `delivered()` can only guess after a crash, and
    a guess either loses the item or files it twice.
    """

    def send(self, item: QueueItem, body) -> str:
        """Hand one item over. Returns the remote's receipt, which must be a
        non-empty string: a receipt is the evidence for writing `sent`, so an
        empty one is treated as a failure rather than as a success nobody can
        point at. Raises `Unsendable` for every failure."""

    def delivered(self, item: QueueItem) -> Delivery:
        """What the remote already has under `item.key`.

        For audio this is the scribe's own status endpoint on the transaction
        id api/scribe.py supplies, so it is answerable today. FOR A NATIONAL
        DOCUMENT IT IS NOT KNOWN what the equivalent is, and a sender that
        cannot answer must return `Delivery(known=False)` rather than a guess.
        The item then waits in `held` for a person. That is a gap in what we
        know about ABDM, not a gap in this design, and it is reported as a
        decision somebody has to make.
        """


# --------------------------------------------------------------------------
# Admission: a centre holds nothing for a plugin it does not run
# --------------------------------------------------------------------------

def refusal(*, kind, operation, capability, withheld):
    """Why this item may not be queued here, or "" if it may.

    Called at admission AND again inside `due()`, which is not belt and
    braces: a facility's shape is read at start-up and an item can outlive the
    process that admitted it. An item admitted last week for a plugin this
    centre has since switched off must stop, and the only place that can be
    noticed is the moment somebody looks at it again.
    """
    if kind not in QUEUE_KINDS:
        return "'%s' is not a kind of queued work" % kind
    plugin = (withheld or {}).get(capability)
    if plugin:
        return ("capability %s withheld by plugin '%s': this facility does not "
                "run it, so nothing is held for it" % (capability, plugin))
    return ""


def enqueue(spool, *, kind, key, thread, operation, capability, facility,
            at, actor="", blob="", withheld=None):
    """Put one item in the outbox, or refuse it and keep nothing.

    Refusing means refusing to HOLD it, which is stronger than refusing to
    send it: an item for a plugin this centre does not run leaves no row, no
    recording on disk and nothing for a person to wonder about. Raises rather
    than returning None, because a caller that drops a recording on the floor
    without noticing is the failure this module exists to prevent.
    """
    why = refusal(kind=kind, operation=operation, capability=capability,
                  withheld=withheld)
    if why:
        raise Unsendable(why)
    if not str(key or "").strip():
        # The key is the whole of the not-sent-twice property, so an item
        # without one is refused rather than given a generated one: a key we
        # minted here and the remote never saw deduplicates nothing.
        raise Unsendable("a queued item needs the key the remote will know it "
                         "by, and this one has none")
    item = QueueItem(id=_new_id(), kind=kind, key=str(key), thread=thread,
                     operation=operation, capability=capability,
                     facility=facility, created_at=at, actor=actor or "",
                     blob=blob, state="ready")
    spool.put(item)
    return item


def _new_id():
    import uuid
    return "q-" + uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# What is due, and what is stuck
# --------------------------------------------------------------------------

def _moment(text):
    try:
        when = datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _waited(since, now, seconds):
    """Has `seconds` passed between these two moments? An unreadable or
    missing timestamp counts as long enough: an item whose clock we cannot
    read must still move, and the alternative is an item that waits forever
    because of a bad string."""
    start, end = _moment(since), _moment(now)
    if start is None or end is None:
        return True
    return end - start >= timedelta(seconds=seconds)


def backoff(attempts):
    """The wait owed after this many attempts. A guess; see the constant."""
    if attempts <= 0:
        return 0
    return BACKOFF_SECONDS[min(attempts, len(BACKOFF_SECONDS)) - 1]


def due(spool, *, now, limit=50, max_attempts=MAX_ATTEMPTS):
    """Items ready to try, oldest first. Two reasons one is not: it has had
    its limit of attempts, or it is still inside its backoff.

    Deliberately NOT a place that asks whether this centre may send the item.
    Dropping a withheld item here was the first shape of this function and it
    was wrong: kernel/plugins.py's doctrine is that a plugin that is off
    DENIES AND DOES NOT HIDE, with the capability and the plugin named in an
    audit row. An item filtered out here would instead sit in `ready` forever
    with nothing written down, which is both hiding and the silent giving up
    that this module is supposed to make impossible. So authorisation happens
    in exactly one place, `permit`, and this function only answers "is a try
    owed yet".
    """
    out = []
    for item in spool.items(state="ready", limit=max(limit * 4, limit)):
        if item.attempts >= max_attempts:
            continue
        if item.kind not in QUEUE_KINDS:
            continue
        if item.attempts and not _waited(item.claimed_at, now,
                                         backoff(item.attempts)):
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def stuck(spool, *, now, seconds=IN_FLIGHT_SECONDS, limit=200):
    """Items claimed and never settled: every crash mid-send lands here."""
    return [i for i in spool.items(state="sending", limit=limit)
            if _waited(i.claimed_at, now, seconds)]


# --------------------------------------------------------------------------
# The guard, re-run at the moment of sending
# --------------------------------------------------------------------------

# What a queue send is called on the audit line. The guard's own vocabulary
# has `allowed`, and that is the right word: steps 1 to 4 passed and the
# caller is about to do 5 to 7, which is exactly the situation. A new outcome
# word would be a sixth thing every reader of the audit trail has to learn.
QUEUE_SURFACE_NOTE = "queued"


def permit_with_guard(store, bundle, *, caps, actor, at, withheld=None,
                      surface=None, workflow=None):
    """A `permit` for `pump()`: the guard, against the world as it is NOW.

    `test_a_proposal_is_judged_again_at_confirm_and_not_when_it_was_made` is
    the precedent and this is the same rule over a longer gap. The
    capabilities, the facility's shape and the thread's own flags are read at
    the moment of sending, not at the moment of queueing, so an item queued
    under capabilities somebody has since lost does not go out.

    WHICH GUARD STEPS THIS RE-RUNS, exactly, because overstating it would be
    worse than not doing it:

    - step 2, capability, and step 3, preconditions. Through
      `catalogue.guard.visible`, which is the ONE predicate both enforcement
      and the surfaces already read, including the `actor of` separation of
      duties rule. Not re-implemented here, so it cannot drift.
    - the plugin subtraction, by naming the plugin in the sentence the same
      way `guard.evaluate` does, so an audit line is reconstructable against a
      bundle.yaml that has since been edited.

    What it does NOT re-run, and why:

    - step 1, the payload schema. A queued item carries no payload. A
      document's content is the rows in the Store, which were validated by
      the guard when they were committed, and re-validating a projection
      against a questionnaire is not a thing that means anything. Audio has
      no payload at all; what it produces is a Draft, and a Draft goes through
      the whole guard when a person taps it.
    - step 4, the irreversibility rule, and the scope qualifier. Both are
      about who may invoke an operation on which surface, and sending is not
      invoking it: the operation already happened. An irreversible operation
      that a person performed on the rendered surface does not become
      un-performed because its document waited for a line.

    THE AUDIT ROW IS WRITTEN BEFORE THE SEND, which is the guard's step order
    and is not relaxed for a queue: `pump()` calls this before it claims, and
    an allowed item is audited before a byte leaves. A denial is audited too,
    naming the capability and, where there is one, the plugin.
    """
    from catalogue import guard
    from kernel import proposals, state

    flow = workflow or bundle.workflow()
    held_back = dict(withheld if withheld is not None else (bundle.withheld or {}))
    held = set(caps or ())

    def permit(item):
        op = (bundle.operations or {}).get(item.operation)
        if op is None:
            return _refused(store, item, at, actor,
                            "%s is not an operation this kernel loads, so "
                            "nothing may be sent for it" % item.operation)
        why = refusal(kind=item.kind, operation=op["id"],
                      capability=op["capability"], withheld=held_back)
        if why:
            # One sentence for a withheld plugin, from the same function
            # `enqueue` uses, so admitting and sending cannot disagree about
            # what this centre runs or about how it says so.
            return _refused(store, item, at, actor, why)
        if op["capability"] not in held:
            return _refused(store, item, at, actor,
                            "missing capability %s" % op["capability"])
        flags = state.flags(store, item.thread, flow)
        who = item.actor or actor
        if not guard.visible(op, held, flags, actor=who,
                             performers=state.performers(store, item.thread)):
            return _refused(store, item, at, actor,
                            "the preconditions for %s no longer hold on this "
                            "visit" % op["id"])
        # Allowed, and audited before anything is sent.
        proposals.audit_row(store, {
            "operation": op["id"], "actor": actor,
            "surface": surface or guard.RENDERED,
            "payload": {"queued": item.kind, "item": item.id, "key": item.key},
            "outcome": "allowed"}, thread=item.thread, at=at)
        return guard.Decision(True, "allowed", audit={})

    return permit


def _refused(store, item, at, actor, reason):
    """One denial: the audit row first, then the decision.

    Written here and not left to the caller for the reason the guard gives
    for building the record itself: a denial nobody wrote down is a denial
    that did not happen as far as anybody reading the trail can tell.
    """
    from catalogue import guard
    from kernel import proposals

    proposals.audit_row(store, {
        "operation": item.operation, "actor": actor, "surface": guard.RENDERED,
        "payload": {"queued": item.kind, "item": item.id, "key": item.key},
        "outcome": "denied: %s" % reason}, thread=item.thread, at=at)
    return guard.Decision(False, reason, audit={})


# --------------------------------------------------------------------------
# The bodies
# --------------------------------------------------------------------------

def document_body(store, bundle, item, *, now, document="consultation"):
    """A waiting visit, projected now rather than when it was queued.

    THE FIRST PRODUCTION CALL OF `kernel.fhir.document()` in this repository.
    Everything that projected a document before this line was a check. The
    declaration it is projected through is the bundle's own `documents:` key,
    which kernel/declarations.py already compiles into exactly the keyword
    arguments `fhir.document()` takes, so no placement is typed here: that was
    the whole point of moving it into the bundle.

    Projected at send time and not at queue time for two reasons. A
    correction made while the item waited belongs in the document that
    actually leaves. And a bundle written to the outbox would be a second copy
    of a patient's record on disk, which is the thing the document path is
    designed not to need.
    """
    declared = dict(bundle.documents or {})
    if document not in declared:
        raise Unsendable("this bundle declares no '%s' document, so there is "
                         "nothing to publish" % document)
    try:
        return fhir.document(store, item.thread, now=now, **declared[document])
    except KeyError as broke:
        # A visit with no subject, or a section the profile does not declare.
        # Not a line failure: no number of retries fixes it, so it comes back
        # as an Unsendable and the attempt counter stops it.
        raise Unsendable("this visit cannot be published: %s" % broke) from None


def audio_body(item):
    """The recording's bytes, read from the one copy we kept."""
    path = item.blob
    if not path or not os.path.exists(path):
        raise Unsendable("the recording is no longer on disk, so there is "
                         "nothing to send")
    with open(path, "rb") as handle:
        return handle.read()


# --------------------------------------------------------------------------
# The pump
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Sweep:
    """What one pass did. `failed` is not an error: an item that could not be
    sent stays in the answer and is tried again, exactly as
    kernel/directory.py's `Published` says of a patient who could not be
    published. `unrecorded` is the dangerous one and is listed on its own,
    because an item the remote accepted and we could not write down is neither
    a success nor an ordinary failure."""
    sent: list = field(default_factory=list)          # (item id, receipt)
    failed: list = field(default_factory=list)        # (item id, why)
    refused: list = field(default_factory=list)       # (item id, why)
    stopped: list = field(default_factory=list)       # (item id, why) reached the limit
    held: list = field(default_factory=list)          # (item id, why) nobody may guess
    unrecorded: list = field(default_factory=list)    # (item id, why) accepted, not written

    @property
    def count(self):
        return len(self.sent)


def pump(spool, senders, *, permit, bodies, now, limit=50,
         max_attempts=MAX_ATTEMPTS, delete=None):
    """One pass over what is due. The order of the steps is the design.

    `senders` is {kind: Sender}. `bodies` is callable(item) -> body, raising
    `Unsendable`. There is no `withheld` argument: which plugins this centre
    runs is a question for `permit`, and one authorisation check in one place
    is the whole reason `permit` exists. `permit` is callable(item) -> an
    object with `.allowed` and
    `.reason`, which is `catalogue.guard.Decision`'s shape; it is given rather
    than built here so this module imports no guard, no bundle and no store,
    and so the audit row the guard writes is written by whoever owns the
    audit trail. `delete` removes a sent recording's bytes.

    Per item, in this order and not another:

    1. THE GUARD, BEFORE THE CLAIM. An item the guard now denies becomes
       `refused` without ever entering `sending`, so a denial costs no attempt
       and leaves no in-flight row for `recover()` to reason about. This is
       where `test_a_proposal_is_judged_again_at_confirm_and_not_when_it_was_made`
       applies to a queue: judged now, against the capabilities and the
       facility shape as they are now.
    2. CLAIM, durably. After this returns, a crash leaves `sending`.
    3. Build the body. For a document this projects the visit as it stands.
    4. Send.
    5. Write the receipt. Only now is anything `sent`.
    6. Delete the recording, after the receipt and never before.
    """
    report = Sweep()
    for item in due(spool, now=now, limit=limit, max_attempts=max_attempts):
        decision = permit(item)
        if not getattr(decision, "allowed", False):
            reason = getattr(decision, "reason", "") or "refused"
            spool.settle(item.id, state="refused", at=now,
                         error=scrubbed(reason))
            report.refused.append((item.id, scrubbed(reason)))
            continue

        claimed = spool.claim(item.id, at=now)
        if claimed is None:
            continue                      # another pump took it

        sender = (senders or {}).get(claimed.kind)
        if sender is None:
            _give_up(spool, report, claimed, now,
                     "nothing is configured to send a %s item" % claimed.kind,
                     max_attempts)
            continue

        try:
            body = bodies(claimed)
            receipt = sender.send(claimed, body)
        except Unsendable as broke:
            _give_up(spool, report, claimed, now, str(broke), max_attempts)
            continue
        except Exception as broke:
            # A sender that raises something else is still just a failure, and
            # the type name is all that is kept: an arbitrary exception's text
            # on this path is a response body, and a response body here is a
            # consultation.
            _give_up(spool, report, claimed, now,
                     "the service failed with %s" % type(broke).__name__,
                     max_attempts)
            continue

        if not str(receipt or "").strip():
            # Property 3, at its sharpest. A send that came back with nothing
            # to point at is not a success: there is no evidence, so there is
            # no `sent`.
            _give_up(spool, report, claimed, now,
                     "the service accepted nothing and returned no receipt",
                     max_attempts)
            continue

        try:
            spool.settle(claimed.id, state="sent", at=now, receipt=str(receipt))
        except Exception as broke:
            # The dangerous case, and the reason this is not a bare call. The
            # remote has it and we could not write down that it does. It is
            # NOT reported as sent, and the row stays `sending`, which is
            # exactly where `recover()` looks and where `delivered()` will
            # settle it without a second send. Reported rather than raised:
            # raising would also throw away the record of everything this
            # sweep already sent, which is kernel/directory.py's own reasoning.
            report.unrecorded.append((
                claimed.id,
                scrubbed("the service accepted it as %s and the receipt could "
                         "not be written: %s" % (receipt, broke))))
            continue

        report.sent.append((claimed.id, str(receipt)))
        if claimed.blob and delete is not None:
            # After the receipt, never before. A recording deleted before the
            # receipt is written is a recording lost to a crash in between.
            try:
                delete(claimed.blob)
            except OSError:
                pass
    return report


def _give_up(spool, report, item, now, why, max_attempts):
    """End one failed attempt: back to `ready`, or stop in `failed`.

    Stopping is a state, not a silence. The item stays in the outbox with its
    attempt count and its last reason on it, so `status()` can say that one
    recording has failed six times and stopped, which is the whole of the
    "visible, not forever" requirement.
    """
    text = scrubbed(why)
    # `error=scrubbed(...)` written out rather than `error=text`, and the same
    # at every other call. scripts/check_queues.py reads the syntax tree and
    # requires every `error=` reaching `settle()` to be literally a
    # `scrubbed()` call or a constant string: a rule a machine can check is
    # worth one repeated call, because a variable is a rule nobody can check.
    if item.attempts >= max_attempts:
        spool.settle(item.id, state="failed", at=now, error=scrubbed(why))
        report.stopped.append((item.id, text))
    else:
        spool.settle(item.id, state="ready", at=now, error=scrubbed(why))
        report.failed.append((item.id, text))


# --------------------------------------------------------------------------
# Recovery: what a crash left behind
# --------------------------------------------------------------------------

def recover(spool, senders, *, now, seconds=IN_FLIGHT_SECONDS,
            max_attempts=MAX_ATTEMPTS):
    """Settle everything a crash left in `sending`, by asking the remote.

    This is the whole of property 2. The naive recovery is to put a stuck item
    back in `ready`, and that sends anything the remote already took a second
    time, which for a national health record means a duplicate document about
    a real person. So nothing is resent on the strength of our own ignorance:

      the remote has it        -> `sent`, with the receipt it gives
      the remote does not      -> `ready`, to be tried again
      the remote cannot say    -> `held`. Not retried, not discarded, visible.

    `held` is the honest third answer and the only one that is not automatic.
    It means a person has to look, and for a national document that is the
    right answer today, because what ABDM's equivalent of "do you already have
    this?" is has not been established here.
    """
    report = Sweep()
    for item in stuck(spool, now=now, seconds=seconds):
        sender = (senders or {}).get(item.kind)
        if sender is None:
            why = ("nothing is configured to say whether a %s item was "
                   "delivered, so nobody may resend it" % item.kind)
            spool.settle(item.id, state="held", at=now, error=scrubbed(why))
            report.held.append((item.id, scrubbed(why)))
            continue
        try:
            answer = sender.delivered(item)
        except Exception as broke:
            answer = Delivery(known=False, receipt="")
            why = "asking whether it was delivered failed with %s" % type(broke).__name__
        else:
            why = "the service cannot say whether it already has this"
        if not getattr(answer, "known", False):
            spool.settle(item.id, state="held", at=now, error=scrubbed(why))
            report.held.append((item.id, scrubbed(why)))
        elif answer.delivered:
            spool.settle(item.id, state="sent", at=now,
                         receipt=str(answer.receipt))
            report.sent.append((item.id, str(answer.receipt)))
        elif item.attempts >= max_attempts:
            spool.settle(item.id, state="failed", at=now,
                         error=scrubbed("the service does not have it and the "
                                        "attempt limit is spent"))
            report.stopped.append((item.id, "the attempt limit is spent"))
        else:
            spool.settle(item.id, state="ready", at=now,
                         error=scrubbed("interrupted before the service "
                                        "answered; it does not have it"))
            report.failed.append((item.id, "interrupted before it was sent"))
    return report


# --------------------------------------------------------------------------
# Retention: audio that nobody ever came back for
# --------------------------------------------------------------------------

def sweep_audio(spool, *, now, delete, max_hold=None):
    """Delete recordings held longer than the retention backstop allows.

    The backstop is `care_phc/connectors/scribe/base.py`'s
    AUDIO_MAX_HOLD_SECONDS, imported rather than chosen again here: how long
    unconfirmed consultation audio may be kept is one rule about one kind of
    data, and that file already carries it with the sentence saying it needs a
    sign-off. A queue that invented its own number would be a second answer to
    a question that already has one unsigned answer, which is worse.

    An item whose bytes are deleted this way is NOT marked sent, because it
    was not. It stops in `failed` saying the recording aged out, which is the
    honest record: the audio is gone, nobody got a transcript, and the note
    was typed or it was not.
    """
    if max_hold is None:
        from care_phc.connectors.scribe import base
        max_hold = base.AUDIO_MAX_HOLD_SECONDS
    # Every candidate is listed BEFORE any of them is settled. Settling moves
    # an item into `failed`, which is one of the states being walked, so
    # listing and settling in the same loop found the same recording twice and
    # reported it deleted twice. The check caught it.
    waiting = []
    for state in ("ready", "held", "failed"):
        waiting += [i for i in spool.items(state=state, kind="audio", limit=500)
                    if i.blob and _waited(i.created_at, now, max_hold)]

    gone = []
    for item in waiting:
        try:
            delete(item.blob)
        except OSError:
            continue
        if item.state != "failed":
            spool.settle(item.id, state="failed", at=now,
                         error="the recording was held longer than the "
                               "retention backstop allows and was deleted "
                               "without being transcribed")
        gone.append(item.id)
    return gone


# --------------------------------------------------------------------------
# Legibility: somebody can see that twelve recordings are waiting
# --------------------------------------------------------------------------

# What one item of each kind is called in a sentence, singular and plural.
# Here and not in a renderer, because the renderer may never name one of this
# bundle's words and these are the queue's own words, not the bundle's.
NOUNS = {"audio": ("recording", "recordings"),
         "document": ("national record", "national records")}


def _plural(kind, n):
    one, many = NOUNS.get(kind, ("item", "items"))
    return one if n == 1 else many


@dataclass(frozen=True)
class Standing:
    """The outbox as counts, per kind and state, plus the worst offender.

    A dataclass and not a printed report, so the one caller that needs to
    render it can and nothing here draws anything. `lines()` is the plain
    English, and it is correct at nought and at one as well as at twelve,
    which is the rule web/src/agent.check.ts already holds the brief to.
    """
    counts: dict = field(default_factory=dict)        # (kind, state) -> n
    worst: dict = field(default_factory=dict)         # kind -> (item id, attempts)

    def total(self, kind=None, state=None):
        return sum(n for (k, s), n in self.counts.items()
                   if (kind is None or k == kind) and (state is None or s == state))

    def lines(self):
        """One sentence per thing a person needs to know, or one saying there
        is nothing. No prose beyond a count and a state: the copy rule
        TaskRow already follows."""
        out = []
        for kind in QUEUE_KINDS:
            waiting = self.total(kind, "ready") + self.total(kind, "sending")
            if waiting:
                out.append("%d %s waiting for the line"
                           % (waiting, _plural(kind, waiting)))
            for state, word in (("failed", "failed and stopped"),
                                ("refused", "refused by the guard"),
                                ("held", "waiting for somebody to decide")):
                n = self.total(kind, state)
                if not n:
                    continue
                said = "%d %s %s" % (n, _plural(kind, n), word)
                worst = self.worst.get(kind)
                if state == "failed" and worst and worst[1]:
                    said += " after %d attempt%s" % (worst[1],
                                                     "" if worst[1] == 1 else "s")
                out.append(said)
        return out or ["nothing is waiting to be sent"]


def status(spool, *, limit=2000):
    """The whole outbox, counted. The one read a person's view would make."""
    counts, worst = {}, {}
    for state in QUEUE_STATES:
        for item in spool.items(state=state, limit=limit):
            counts[(item.kind, state)] = counts.get((item.kind, state), 0) + 1
            if state == "failed":
                best = worst.get(item.kind)
                if best is None or item.attempts > best[1]:
                    worst[item.kind] = (item.id, item.attempts)
    return Standing(counts=counts, worst=worst)


def demo():
    """The module against a dictionary spool. The properties that need a real
    crash are in scripts/check_queues.py, which kills a real process."""
    from adapters.local.spool import SqliteSpool

    now = "2026-10-31T10:00:00+00:00"
    spool = SqliteSpool(":memory:")

    # ---- a centre holds nothing for a plugin it does not run
    withheld = {"visit.household": "outreach"}
    try:
        enqueue(spool, kind="audio", key="t-1", thread="enc-1",
                operation="phc.op.household-visit", capability="visit.household",
                facility="consulting-room-only", at=now, withheld=withheld)
        raise AssertionError("an item was held for a plugin this centre is not running")
    except Unsendable as broke:
        assert "outreach" in str(broke), broke
    assert spool.items() == [], "a refused item left a row behind"

    # ---- an item with no key is refused: a key we minted dedupes nothing
    try:
        enqueue(spool, kind="audio", key="", thread="enc-1",
                operation="phc.op.consult-document", capability="encounter.document",
                facility="all-plugins", at=now)
        raise AssertionError("an item with no idempotency key was accepted")
    except Unsendable as broke:
        assert "key" in str(broke), broke

    item = enqueue(spool, kind="document", key="enc-1", thread="enc-1",
                   operation="phc.op.consult-document",
                   capability="encounter.document", facility="all-plugins",
                   at=now, actor="user:mo")
    assert item.state == "ready" and item.attempts == 0
    assert [i.id for i in due(spool, now=now)] == [item.id]

    # ---- the guard refuses at send time and nothing goes
    class Yes:
        allowed, reason = True, "allowed"

    class No:
        allowed, reason = False, "missing capability encounter.document"

    class Counting:
        def __init__(self):
            self.sent = []

        def send(self, item, body):
            self.sent.append(item.key)
            return "r-" + item.key

        def delivered(self, item):
            return Delivery(known=True,
                            receipt="r-" + item.key if item.key in self.sent else "")

    sender = Counting()
    report = pump(spool, {"document": sender}, permit=lambda i: No(),
                  bodies=lambda i: {"body": True}, now=now)
    assert report.sent == [] and len(report.refused) == 1, report
    assert sender.sent == [], "a refused item was sent anyway"
    assert spool.get(item.id).state == "refused"
    assert spool.get(item.id).attempts == 0, \
           "a guard denial cost an attempt, so a denial can exhaust an item"

    # ---- and one the guard allows goes, once, with a receipt
    spool.settle(item.id, state="ready", at=now)
    report = pump(spool, {"document": sender}, permit=lambda i: Yes(),
                  bodies=lambda i: {"body": True}, now=now)
    assert report.sent == [(item.id, "r-enc-1")], report
    assert spool.get(item.id).state == "sent"
    assert spool.get(item.id).receipt == "r-enc-1"

    # ---- a send that failed is not recorded as a success
    second = enqueue(spool, kind="document", key="enc-2", thread="enc-2",
                     operation="phc.op.consult-document",
                     capability="encounter.document", facility="all-plugins",
                     at=now)

    class Dead:
        def send(self, item, body):
            raise Unsendable("there is no line")

        def delivered(self, item):
            return Delivery(known=True, receipt="")

    report = pump(spool, {"document": Dead()}, permit=lambda i: Yes(),
                  bodies=lambda i: {"body": True}, now=now)
    assert report.sent == [] and len(report.failed) == 1, report
    row = spool.get(second.id)
    assert row.state == "ready" and row.attempts == 1 and not row.receipt, row

    # ---- a receipt that is empty is a failure, not a success
    class Mute:
        def send(self, item, body):
            return "  "

        def delivered(self, item):
            return Delivery(known=True, receipt="")

    spool.settle(second.id, state="ready", at=now)
    report = pump(spool, {"document": Mute()}, permit=lambda i: Yes(),
                  bodies=lambda i: {"body": True}, now="2026-10-31T12:00:00+00:00")
    assert report.sent == [] and spool.get(second.id).state == "ready"

    # ---- a remote that cannot say holds the item instead of guessing
    spool.settle(second.id, state="sending", at=now)

    class Silent:
        def send(self, item, body):
            raise Unsendable("no")

        def delivered(self, item):
            return Delivery(known=False)

    report = recover(spool, {"document": Silent()}, now="2026-10-31T14:00:00+00:00")
    assert [i for i, _ in report.held] == [second.id], report
    assert spool.get(second.id).state == "held"

    # ---- and one that can say it has it settles without a second send
    spool.settle(second.id, state="sending", at=now)
    report = recover(spool, {"document": Counting()},
                     now="2026-10-31T14:00:00+00:00")
    assert report.sent == [] and [i for i, _ in report.failed] == [second.id], \
        "a remote that does not have it must try again, not hold"

    # ---- the outbox reads as sentences, at nought, one and many
    assert status(SqliteSpool(":memory:")).lines() == ["nothing is waiting to be sent"]
    one = SqliteSpool(":memory:")
    enqueue(one, kind="audio", key="t-9", thread="enc-9",
            operation="phc.op.consult-document", capability="encounter.document",
            facility="all-plugins", at=now)
    assert status(one).lines() == ["1 recording waiting for the line"], \
        status(one).lines()
    for n in range(11):
        enqueue(one, kind="audio", key="t-%d" % n, thread="enc-9",
                operation="phc.op.consult-document",
                capability="encounter.document", facility="all-plugins", at=now)
    assert status(one).lines() == ["12 recordings waiting for the line"], \
        status(one).lines()

    # ---- the scrubber, on all three rules
    assert "1234 5678 9012" not in scrubbed("aadhaar 1234 5678 9012 refused")
    assert "<aadhaar-redacted>" in scrubbed("aadhaar 1234 5678 9012 refused")
    assert "9876543210" not in scrubbed("mobile 9876543210 is unknown")
    assert "ending 3210" in scrubbed("mobile 9876543210 is unknown")
    assert "123456" not in scrubbed("OTP 123456 has expired")
    assert OTP_MARK in scrubbed("OTP 123456 has expired")

    print("ok   kernel/queues: a centre holds nothing for a plugin it does not run")
    print("ok   kernel/queues: the guard refuses at send time and nothing goes")
    print("ok   kernel/queues: a failed send is not recorded as a success")
    print("ok   kernel/queues: an empty receipt is a failure, not a success")
    print("ok   kernel/queues: a remote that cannot say holds the item")
    print("ok   kernel/queues: the outbox reads as sentences at 0, 1 and 12")
    print("ok   kernel/queues: a queue row's text carries no Aadhaar, no OTP "
          "and no mobile beyond its last four")


if __name__ == "__main__":
    demo()
