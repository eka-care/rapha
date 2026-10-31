"""Run: python3 scripts/check_queues.py

The outbox: nothing lost, nothing sent twice, nothing reported as sent when it
was not. Each of those three is a separate property and each one is PROVED BY
MAKING IT HAPPEN rather than by reading the code and agreeing with it.

How the three crash proofs work
-------------------------------
A real child process, against a real SQLite file in a real temporary
directory, is killed with SIGKILL at a chosen instant. SIGKILL and not an
exception, and a process and not a mock, because what is being proved is that
the ROW ON DISK is right after the program stopped existing: no `finally`
ran, no `atexit` ran, no buffer flushed. The child is this same file, re-run
with `--crash=<where>`, so there is nothing to keep in step with it:

  --crash=before-send   killed between claiming the item and sending it
  --crash=after-send    killed after the remote took it, before the receipt
                        could be written down
  --crash=in-settle     killed in the middle of writing the receipt

The stand-in remote is a log file with one line per send, fsynced, which is
the only way a parent can count what a child that no longer exists did. Its
`delivered()` reads that log, which is what an idempotency key is FOR: the
remote is asked "do you already have the thing we call this?" rather than
guessed about.

What this does NOT prove. No request is made to Eka or to ABDM from this file
or from anything it imports, by instruction: the gate is offline and
deterministic. So what is proved is the queue's own machinery and every
decision either side of a send, and nothing about what either service does
with a real item. In particular `Sender.delivered` is answerable today for
audio, because api/scribe.py already supplies the transaction id, and IS NOT
ESTABLISHED for a national document; the design's answer to that is `held`,
which is proved here, and the question itself is a decision for a person.

Mutations this is built to fail under are listed at the bottom of the file.
"""
from __future__ import annotations

import ast
import atexit
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from adapters.local.spool import SqliteSpool                   # noqa: E402
from adapters.local.store import SqliteStore                   # noqa: E402
from catalogue import vocab                                    # noqa: E402
from kernel import declarations, plugins, proposals, queues     # noqa: E402
from kernel.contracts import QUEUE_KINDS, QUEUE_STATES, QueueItem  # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


BUNDLE = declarations.load("phc")
NOW = "2026-10-31T10:00:00+00:00"
LATER = "2026-10-31T14:00:00+00:00"
MO = set(vocab.for_bundle("phc").roles["mo"])
NURSE = set(vocab.for_bundle("phc").roles["nurse"])
A_DOCTOR = "user:ravi"


# ==========================================================================
# The child process: this same file, killed at a chosen instant.
# ==========================================================================

class LoggingRemote:
    """A stand-in remote whose whole memory is one appended, fsynced line.

    A log file and not an object, because the parent has to count what a
    process that no longer exists did. One line per send, so "sent twice"
    is two lines and is not a matter of interpretation.
    """

    def __init__(self, log, *, crash_after_send=False):
        self.log = log
        self.crash_after_send = crash_after_send

    def send(self, item, body):
        with open(self.log, "a") as out:
            out.write("%s\n" % item.key)
            out.flush()
            os.fsync(out.fileno())
        if self.crash_after_send:
            os.kill(os.getpid(), signal.SIGKILL)
        return "receipt-" + item.key

    def delivered(self, item):
        try:
            with open(self.log) as handle:
                keys = [line.strip() for line in handle]
        except FileNotFoundError:
            keys = []
        if item.key in keys:
            return queues.Delivery(known=True, receipt="receipt-" + item.key)
        return queues.Delivery(known=True, receipt="")


class KillingRemote:
    """Dies before the send. Nothing reaches the log, so the parent can tell
    this apart from a crash after the send."""

    def send(self, item, body):
        os.kill(os.getpid(), signal.SIGKILL)

    def delivered(self, item):
        return queues.Delivery(known=True, receipt="")


class KillingSpool:
    """The spool, killed in the middle of writing `sent`.

    This is the third property's sharpest form: the remote has the item, the
    receipt is half written, and the process ends. Everything else delegates,
    so what is exercised is the real adapter.
    """

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def settle(self, item_id, *, state, at, receipt="", error=""):
        if state == "sent":
            os.kill(os.getpid(), signal.SIGKILL)
        return self.inner.settle(item_id, state=state, at=at, receipt=receipt,
                                 error=error)


def child(where, db, log):
    """One pump pass, killed at `where`. Never returns on a crash."""
    spool = SqliteSpool(db)
    allow = type("Yes", (), {"allowed": True, "reason": "allowed"})()
    if where == "before-send":
        sender = KillingRemote()
    else:
        sender = LoggingRemote(log, crash_after_send=(where == "after-send"))
    if where == "in-settle":
        spool = KillingSpool(spool)
    queues.pump(spool, {"audio": sender}, permit=lambda i: allow,
                bodies=lambda i: b"bytes", now=NOW)
    # Reached only if nothing crashed, which is itself a failure of the proof.
    print("CHILD SURVIVED", where)


if len(sys.argv) > 1 and sys.argv[1].startswith("--crash="):
    child(sys.argv[1].split("=", 1)[1], sys.argv[2], sys.argv[3])
    raise SystemExit(0)


# ==========================================================================
# 1. The three properties, by killing a real process.
# ==========================================================================

# Removed on the way out WHATEVER happens, including a failed assertion.
# Registered with atexit and not left to a line at the bottom of the file,
# because this directory holds bytes standing in for consultation audio, and
# the runs that leave it behind are exactly the runs nobody tidies up after: a
# mutation run left 39 of these directories in the system temporary directory
# before this was registered.
WORK = tempfile.mkdtemp(prefix="phc-queue-check-")
atexit.register(shutil.rmtree, WORK, ignore_errors=True)


def one_audio_item(name, *, bytes_on_disk=True):
    """A real file, a real row, a real recording on disk."""
    db = os.path.join(WORK, "%s.sqlite3" % name)
    log = os.path.join(WORK, "%s.log" % name)
    spool = SqliteSpool(db)
    blob = ""
    if bytes_on_disk:
        blob = spool.keep("pre-" + name, b"a consultation",
                          root=os.path.join(WORK, name))
    item = queues.enqueue(spool, kind="audio", key="txn-" + name,
                          thread="enc-1", operation="phc.op.consult-document",
                          capability="encounter.document",
                          facility="all-plugins", at=NOW, blob=blob)
    return db, log, spool, item


def crash(where, db, log):
    done = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__)), "--crash=" + where, db, log],
        capture_output=True, text=True, cwd=str(ROOT))
    assert b"CHILD SURVIVED" not in done.stdout.encode(), \
        "the child was meant to be killed at %s and was not: %s" % (where, done.stdout)
    assert done.returncode == -signal.SIGKILL, \
        "the child did not die of SIGKILL at %s: returncode %s, stderr %s" % (
            where, done.returncode, done.stderr[-800:])
    return done


def lines(log):
    if not os.path.exists(log):
        return []
    return [l.strip() for l in open(log) if l.strip()]


# ---- property 1: a crash between taking an item and sending it loses nothing
db, log, spool, item = one_audio_item("lost")
crash("before-send", db, log)

reopened = SqliteSpool(db)
row = reopened.get(item.id)
assert row is not None, "the item vanished when the process was killed"
assert row.state == "sending", \
    "a crash mid-send left the item %r, so a recovery cannot tell tried from " \
    "untried work" % row.state
assert row.attempts == 1, row
assert lines(log) == [], "it was sent, so this is not the window being tested"
assert os.path.exists(row.blob), "the recording was deleted before it was sent"
assert open(row.blob, "rb").read() == b"a consultation", \
    "the recording came back truncated or changed"
ok("a process killed between claiming a recording and sending it loses "
   "nothing: the row survives as 'sending' and the bytes are intact")

# And it comes back: the remote says it does not have it, so it is tried again.
report = queues.recover(reopened, {"audio": LoggingRemote(log)}, now=LATER)
assert reopened.get(item.id).state == "ready", reopened.get(item.id)
assert [i for i, _ in report.failed] == [item.id], report
ok("and recovery returns it to the queue, because the remote says it never "
   "arrived")

# ---- property 2: a crash between sending and recording success does not
#      send twice
db2, log2, spool2, item2 = one_audio_item("twice")
crash("after-send", db2, log2)

assert lines(log2) == [item2.key], \
    "the remote did not receive it exactly once before the crash: %s" % lines(log2)
again = SqliteSpool(db2)
assert again.get(item2.id).state == "sending", again.get(item2.id)
assert not again.get(item2.id).receipt, \
    "a receipt was written, so this is not the window being tested"
ok("a process killed after the remote took a recording and before the "
   "receipt could be written leaves the item 'sending' with no receipt")

report = queues.recover(again, {"audio": LoggingRemote(log2)}, now=LATER)
assert lines(log2) == [item2.key], \
    "RECOVERY SENT IT A SECOND TIME: %s" % lines(log2)
settled = again.get(item2.id)
assert settled.state == "sent" and settled.receipt == "receipt-" + item2.key, settled
assert [i for i, _ in report.sent] == [item2.id], report
ok("and recovery settles it from the remote's own answer: it is marked sent, "
   "once, and nothing is sent a second time")

# The same crash, recovered the naive way, to show the assertion above has
# teeth. This is what putting a stuck item back in `ready` costs: for a
# national health record it is a duplicate document about a real person.
#
# A second real crash rather than a copy of the first one's database. Copying
# a SQLite file in WAL mode leaves the recent commits behind in the -wal
# companion, so the copy came back without the crash on it and the comparison
# silently proved nothing. That is how this comment came to exist.
db2n, log2n, _, item2n = one_audio_item("twice-naive")
crash("after-send", db2n, log2n)
assert lines(log2n) == [item2n.key], lines(log2n)

allow = type("Yes", (), {"allowed": True, "reason": "allowed"})()
naive = SqliteSpool(db2n)
assert naive.get(item2n.id).state == "sending", naive.get(item2n.id)
naive.settle(item2n.id, state="ready", at=LATER)          # the naive recovery
queues.pump(naive, {"audio": LoggingRemote(log2n)},
            permit=lambda i: allow, bodies=lambda i: b"bytes", now=LATER)
assert lines(log2n) == [item2n.key, item2n.key], \
    "the naive recovery did not double send, so the check above proves nothing"
ok("whereas putting the same stuck item straight back in the queue sends it "
   "twice, which is what asking the remote first prevents")

# ---- property 3: a send that failed is not recorded as a success
db3, log3, spool3, item3 = one_audio_item("unrecorded")
crash("in-settle", db3, log3)

assert lines(log3) == [item3.key], lines(log3)
third = SqliteSpool(db3)
row3 = third.get(item3.id)
assert row3.state != "sent", \
    "the item is marked sent although the write recording it never finished"
assert row3.state == "sending" and not row3.receipt, row3
ok("a process killed in the middle of writing the receipt does not leave the "
   "item marked sent: there is no evidence, so there is no claim")

# Not sent twice on the way out of that either.
queues.recover(third, {"audio": LoggingRemote(log3)}, now=LATER)
assert lines(log3) == [item3.key], lines(log3)
assert third.get(item3.id).state == "sent", third.get(item3.id)
ok("and it settles from the remote's answer without a second send")

# The same property stated about the REPORT and not only about the row. A
# caller, and an operator reading a sweep, must not be told an item went when
# it did not; the crash above proves the row, and this proves the answer.
# Written because mutation 3 (report the unwritable receipt as a success
# anyway) changed only the report and the crash check did not notice.
class Unwritable:
    """The spool, with the one write that records a receipt broken."""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def settle(self, item_id, *, state, at, receipt="", error=""):
        if state == "sent":
            raise OSError("the outbox is read only")
        return self.inner.settle(item_id, state=state, at=at, receipt=receipt,
                                 error=error)


box = SqliteSpool(":memory:")
lost = queues.enqueue(box, kind="document", key="enc-unwritable",
                      thread="enc-u", operation="phc.op.consult-document",
                      capability="encounter.document", facility="all-plugins",
                      at=NOW)
sent_log = os.path.join(WORK, "unwritable.log")
report = queues.pump(Unwritable(box), {"document": LoggingRemote(sent_log)},
                     permit=lambda i: allow, bodies=lambda i: {"x": 1}, now=NOW)
assert lines(sent_log) == [lost.key], \
    "the remote did not take it, so this is not the situation being tested"
assert report.sent == [], \
    "a receipt that could not be written was REPORTED as sent"
assert [i for i, _ in report.unrecorded] == [lost.id], report
assert "receipt could not be written" in report.unrecorded[0][1], report.unrecorded
assert box.get(lost.id).state == "sending", box.get(lost.id)
ok("an item the remote accepted and whose receipt could not be written is "
   "reported as unrecorded rather than as sent, and left where recovery "
   "looks for it")

# And recovery finishes it without a second send.
queues.recover(box, {"document": LoggingRemote(sent_log)}, now=LATER)
assert lines(sent_log) == [lost.key], lines(sent_log)
assert box.get(lost.id).state == "sent", box.get(lost.id)
ok("and recovery completes it from the remote's own answer, once")

# The same property without a crash: a remote that raises, and one that
# answers with nothing to point at.
class Refusing:
    def __init__(self, how):
        self.how = how

    def send(self, item, body):
        if self.how == "raise":
            # A real gateway's refusal carries whatever it was sent. This one
            # carries a mobile number and an Aadhaar number, so the scrubber
            # is on the path a sender's own sentence takes and not only on the
            # paths this module writes itself.
            raise queues.Unsendable("the gateway refused it: mobile 9876543210 "
                                    "and Aadhaar 1234 5678 9012 do not match")
        if self.how == "explode":
            raise ValueError("9876543210 is not a known patient")
        return ""

    def delivered(self, item):
        return queues.Delivery(known=True, receipt="")


# One fresh outbox per case, and not one item retried three times. Two reasons,
# both found by this check failing: `settle` back to `ready` clears the last
# reason and the backoff stops the next attempt being due, so a reused row
# tested the first case twice; and an item left over from the previous case
# sorts ahead of the new one, so a reused outbox tested the first case again.
failures = {}
for how, why in (("raise", "a sender that raises"),
                 ("explode", "a sender that raises something else"),
                 ("mute", "a sender that returns no receipt")):
    plain = SqliteSpool(":memory:")
    one = queues.enqueue(plain, kind="document", key="enc-" + how,
                         thread="enc-dead",
                         operation="phc.op.consult-document",
                         capability="encounter.document",
                         facility="all-plugins", at=NOW)
    report = queues.pump(plain, {"document": Refusing(how)},
                         permit=lambda i: allow, bodies=lambda i: {"x": 1},
                         now=NOW, limit=1)
    after = plain.get(one.id)
    assert report.sent == [], "%s was recorded as a success" % why
    assert after.state != "sent" and not after.receipt, (why, after)
    assert after.attempts == 1, (why, after)
    assert after.last_error, "%s stopped without saying why" % why
    failures[how] = after
ok("a sender that raises, one that raises something unexpected, and one that "
   "returns no receipt are all three failures and none is recorded as sent")

# A sender's own refusal is scrubbed on the way to the row, not trusted.
kept = failures["raise"].last_error
assert "9876543210" not in kept and "1234 5678 9012" not in kept, kept
assert "ending 3210" in kept and "<aadhaar-redacted>" in kept, kept
ok("a sender's own refusal is scrubbed before it reaches the row, so a "
   "gateway echoing what it was sent cannot write it to our disk")

# And the unexpected one's own words never reach the row.
assert "9876543210" not in failures["explode"].last_error, failures["explode"]
assert "ValueError" in failures["explode"].last_error, failures["explode"]
ok("and an unexpected failure is recorded by type alone, so a response body "
   "carrying a patient's words cannot reach the outbox")


# ==========================================================================
# 2. The guard, re-run at the moment of sending.
# ==========================================================================

def consulted():
    """A real store, a real registered patient, a real documented visit."""
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="A01", actor=A_DOCTOR)
    assert proposals.commit(
        store, BUNDLE, "phc.op.patient-register", thread=thread,
        payload={"name": "Sunita Devi", "age": 34, "sex": "female",
                 "phone": "9876500000", "village": "Yadiki",
                 "category": "general"},
        caps=NURSE | MO, actor=A_DOCTOR)
    assert proposals.commit(
        store, BUNDLE, "phc.op.consult-document", thread=thread,
        payload={"history": "cough for three days", "examination": "chest clear",
                 "assessment": "viral illness", "plan": "fluids and rest"},
        caps=MO, actor=A_DOCTOR)
    return store, thread


store, thread = consulted()
outbox = SqliteSpool(":memory:")
doc = queues.enqueue(outbox, kind="document", key=thread, thread=thread,
                     operation="phc.op.consult-document",
                     capability="encounter.document", facility="all-plugins",
                     at=NOW, actor=A_DOCTOR)


class Watching:
    """A sender that reads the audit trail at the moment it is called.

    This is how "the audit row is written BEFORE execute" is proved rather
    than asserted: the row either is there when the send happens or it is not,
    and only the send can tell.
    """

    def __init__(self, store, thread):
        self.store, self.thread, self.saw = store, thread, []

    def send(self, item, body):
        self.saw.append([r.outcome for r in self.store.audit(self.thread)])
        return "abdm-" + item.key

    def delivered(self, item):
        return queues.Delivery(known=True, receipt="")


watch = Watching(store, thread)
permit = queues.permit_with_guard(store, BUNDLE, caps=MO, actor=A_DOCTOR, at=NOW)
report = queues.pump(outbox, {"document": watch}, permit=permit,
                     bodies=lambda i: queues.document_body(store, BUNDLE, i, now=NOW),
                     now=NOW)
assert report.sent == [(doc.id, "abdm-" + thread)], report
assert watch.saw and watch.saw[-1][-1] == "allowed", \
    "the audit row was not on the trail when the send happened: %s" % watch.saw
ok("a national document is sent only after its audit row is already on the "
   "trail, proved by the sender reading the trail as it is called")

# Now the same item, with the capability gone. A queued write judged under
# yesterday's capabilities is a hole in the guard, so it must not go.
for label, caps, expect in (
        ("a caller who has lost the capability", MO - {"encounter.document"},
         "missing capability encounter.document"),
        ("a centre that no longer runs the plugin", MO, "withheld by plugin")):
    store2, thread2 = consulted()
    box2 = SqliteSpool(":memory:")
    it = queues.enqueue(box2, kind="document", key=thread2, thread=thread2,
                        operation="phc.op.consult-document",
                        capability="encounter.document", facility="all-plugins",
                        at=NOW, actor=A_DOCTOR)
    held_back = ({"encounter.document": "baseline"}
                 if "plugin" in expect else {})
    silent = Watching(store2, thread2)
    report = queues.pump(
        box2, {"document": silent},
        permit=queues.permit_with_guard(store2, BUNDLE, caps=caps,
                                        actor=A_DOCTOR, at=NOW,
                                        withheld=held_back),
        bodies=lambda i: {"x": 1}, now=NOW)
    assert silent.saw == [], "%s: it was sent anyway" % label
    assert report.sent == [] and len(report.refused) == 1, (label, report)
    assert expect in report.refused[0][1], (label, report.refused)
    assert box2.get(it.id).state == "refused", box2.get(it.id)
    assert box2.get(it.id).attempts == 0, \
        "%s: a guard denial cost an attempt, so denials can exhaust an item" % label
    trail = [r.outcome for r in store2.audit(thread2)]
    assert trail[-1].startswith("denied: "), (label, trail)
    assert expect in trail[-1], (label, trail)
ok("an item queued yesterday is refused at send time when the capability has "
   "gone, with a denial on the audit trail and nothing sent")
ok("and refused the same way when the centre has since switched the plugin "
   "off, with the plugin named in the row")

# A precondition that has gone since queueing. The operation is still the
# caller's to perform; this visit is no longer one it may be performed on.
store3, thread3 = consulted()
box3 = SqliteSpool(":memory:")
gone = queues.enqueue(box3, kind="document", key=thread3, thread=thread3,
                      operation="phc.op.capture-withdraw",
                      capability="encounter.document", facility="all-plugins",
                      at=NOW, actor=A_DOCTOR)
watched3 = Watching(store3, thread3)
report = queues.pump(
    box3, {"document": watched3},
    permit=queues.permit_with_guard(store3, BUNDLE, caps=MO, actor=A_DOCTOR, at=NOW),
    bodies=lambda i: {"x": 1}, now=NOW)
assert watched3.saw == [] and report.sent == [], report
assert "preconditions" in report.refused[0][1], report.refused
ok("and refused when the preconditions for its operation no longer hold on "
   "that visit, through the one predicate the surfaces already read")


# ==========================================================================
# 3. A centre holds nothing for a plugin it does not run.
# ==========================================================================

MANIFEST = __import__("yaml").safe_load(
    (ROOT / "bundles" / "phc" / "bundle.yaml").read_text())
WITHHELD = plugins.withheld(MANIFEST, "consulting-room-only")
assert WITHHELD.get("visit.household") == "outreach", WITHHELD

# The community worker's recording, at a consulting room with no outreach.
# `phc.op.household-visit` is on the scribe instrument's own list for the
# community station, so this is a recording this bundle really can produce.
box = SqliteSpool(":memory:")
root = os.path.join(WORK, "refused-audio")
try:
    queues.enqueue(box, kind="audio", key="txn-hh", thread="enc-hh",
                   operation="phc.op.household-visit",
                   capability="visit.household",
                   facility="consulting-room-only", at=NOW, withheld=WITHHELD)
    raise AssertionError("a recording was held for a plugin this centre is "
                         "not running")
except queues.Unsendable as broke:
    assert "outreach" in str(broke) and "visit.household" in str(broke), broke
assert box.items() == [], "a refused item left a row in the outbox"
assert not os.path.isdir(root), "a refused item left a recording on disk"
ok("a centre that does not run outreach refuses to HOLD a household visit's "
   "recording at all: no row, no bytes, nothing for anybody to wonder about")

# An item can outlive the process that admitted it, so the shape is asked
# again at send time. It is REFUSED with the plugin named, and not quietly
# left in the queue: kernel/plugins.py's doctrine is that a plugin that is off
# denies and does not hide, and an item filtered out of the due list would sit
# in `ready` forever with nothing written down. That was this module's first
# shape and this check is what found it.
store5, thread5 = consulted()
box = SqliteSpool(":memory:")
never = os.path.join(WORK, "never.log")
admitted = queues.enqueue(box, kind="audio", key="txn-hh2", thread=thread5,
                          operation="phc.op.household-visit",
                          capability="visit.household", facility="all-plugins",
                          at=NOW, actor=A_DOCTOR)
assert [i.id for i in queues.due(box, now=NOW)] == [admitted.id], \
    "the item is not even due, so it cannot be refused and said so"
report = queues.pump(
    box, {"audio": LoggingRemote(never)},
    permit=queues.permit_with_guard(store5, BUNDLE, caps=MO | {"visit.household"},
                                    actor=A_DOCTOR, at=NOW, withheld=WITHHELD),
    bodies=lambda i: b"x", now=NOW)
assert not os.path.exists(never), "it was sent after the plugin went"
assert report.sent == [] and len(report.refused) == 1, report
assert "outreach" in report.refused[0][1], report.refused
assert box.get(admitted.id).state == "refused", box.get(admitted.id)
trail = [r.outcome for r in store5.audit(thread5)]
assert trail[-1].startswith("denied: ") and "outreach" in trail[-1], trail
ok("and an item admitted before the centre dropped the plugin is refused at "
   "send time with the plugin named in an audit row, rather than left waiting "
   "with nothing written down")

# Every capability in this bundle either belongs to a plugin or is always on.
# A capability no plugin claims is always on, which is the default-on rule;
# this holds the queue's admission test to the SAME dict the guard reads, so
# the two cannot answer differently.
for fid in plugins.facilities(MANIFEST):
    back = plugins.withheld(MANIFEST, fid)
    for oid, op in BUNDLE.operations.items():
        why = queues.refusal(kind="audio", operation=oid,
                             capability=op["capability"], withheld=back)
        denied = op["capability"] in back
        assert bool(why) == denied, (fid, oid, why, denied)
ok("across every shape this bundle ships, the outbox admits exactly the "
   "operations the guard would allow and refuses exactly the ones it withholds")


# ==========================================================================
# 4. The first production caller of fhir.document().
# ==========================================================================

store4, thread4 = consulted()
item4 = QueueItem(id="q-doc", kind="document", key=thread4, thread=thread4,
                  operation="phc.op.consult-document",
                  capability="encounter.document", facility="all-plugins",
                  created_at=NOW)
built = queues.document_body(store4, BUNDLE, item4, now=NOW)
assert built["resourceType"] == "Bundle" and built["type"] == "document", built
assert built["identifier"]["value"] == thread4, built["identifier"]
kinds = [e["resource"]["resourceType"] for e in built["entry"]]
assert kinds[0] == "Composition", kinds
assert "Patient" in kinds and "Encounter" in kinds, kinds
ok("a waiting visit projects to a real OPConsultRecord bundle through the "
   "bundle's own `documents` declaration, which is this repository's first "
   "production call of fhir.document()")

# The key the remote is asked under is the bundle's own identifier, not a
# number this module made up. That is what makes "not sent twice" mean
# anything on their side rather than only on ours.
assert item4.key == built["identifier"]["value"], \
    "the idempotency key and the document's identifier have come apart"
ok("and the key it is sent under IS that document's own identifier, so the "
   "remote can recognise a repeat")

# Queued, then corrected, then sent: the document that leaves is the corrected
# one, because no body was ever copied into the outbox.
before = len([e for e in built["entry"]
              if e["resource"]["resourceType"] == "DocumentReference"])
assert proposals.commit(store4, BUNDLE, "phc.op.consult-document", thread=thread4,
                        payload={"history": "cough for five days, not three",
                                 "examination": "chest clear",
                                 "assessment": "viral illness",
                                 "plan": "fluids, review in two days"},
                        caps=MO, actor=A_DOCTOR)
after = queues.document_body(store4, BUNDLE, item4, now=LATER)
grew = len([e for e in after["entry"]
            if e["resource"]["resourceType"] == "DocumentReference"])
assert grew > before, (before, grew)
ok("a correction made while the item waited is in the document that finally "
   "leaves, because the outbox holds no copy of it")

# A visit with no person on it is a refusal, not a retry: no number of
# attempts fixes it.
empty = SqliteStore(":memory:")
blank = empty.open_thread(token="A02", actor=A_DOCTOR)
try:
    queues.document_body(empty, BUNDLE,
                         QueueItem(id="q-x", kind="document", key=blank,
                                   thread=blank,
                                   operation="phc.op.consult-document",
                                   capability="encounter.document",
                                   facility="all-plugins", created_at=NOW),
                         now=NOW)
    raise AssertionError("a visit with nobody on it was published")
except queues.Unsendable as broke:
    assert "cannot be published" in str(broke), broke
ok("and a visit with nobody on it is refused rather than retried forever")


# ==========================================================================
# 5. Retry is bounded, and stopping is visible.
# ==========================================================================

box = SqliteSpool(":memory:")
doomed = queues.enqueue(box, kind="audio", key="txn-doom", thread="enc-d",
                        operation="phc.op.consult-document",
                        capability="encounter.document",
                        facility="all-plugins", at=NOW)
clock = ["2026-10-31T%02d:00:00+00:00" % h for h in range(10, 23)]
for tick in clock:
    queues.pump(box, {"audio": Refusing("raise")}, permit=lambda i: allow,
                bodies=lambda i: b"x", now=tick)
row = box.get(doomed.id)
assert row.attempts == queues.MAX_ATTEMPTS, \
    "it was tried %d times against a limit of %d" % (row.attempts,
                                                     queues.MAX_ATTEMPTS)
assert row.state == "failed", row
assert row.last_error, "it stopped without saying why"
ok("an item on a dead line is tried %d times and then stops in 'failed', "
   "rather than retrying forever" % queues.MAX_ATTEMPTS)

tried = row.attempts
queues.pump(box, {"audio": Refusing("raise")}, permit=lambda i: allow,
            bodies=lambda i: b"x", now="2026-11-02T10:00:00+00:00")
assert box.get(doomed.id).attempts == tried, "a stopped item was tried again"
assert box.get(doomed.id).state == "failed", "a stopped item did not stay stopped"
ok("and a stopped item stays stopped: it is neither retried nor thrown away")

# Backoff: within the wait it is not due, after it it is. Checked against the
# declared table rather than against a number typed here twice.
box = SqliteSpool(":memory:")
waiting = queues.enqueue(box, kind="audio", key="txn-wait", thread="enc-w",
                         operation="phc.op.consult-document",
                         capability="encounter.document",
                         facility="all-plugins", at=NOW)
# The first retry is owed no wait at all, which is deliberate: a line that
# flickered is worth trying again at once. The waits start from the second.
assert queues.backoff(1) == 0, \
    "the first retry now waits, so a momentary drop costs a clinic a delay"
for _ in range(2):
    box.claim(waiting.id, at="2026-10-31T10:00:00+00:00")
    box.settle(waiting.id, state="ready", at=NOW, error="no line")
assert box.get(waiting.id).attempts == 2, box.get(waiting.id)
owed = queues.backoff(2)
assert owed > 0, "the third attempt is owed no wait at all"
assert queues.due(box, now="2026-10-31T10:00:%02d+00:00" % (owed - 1)) == [], \
    "it was due before its backoff had passed"
assert [i.id for i in queues.due(
    box, now="2026-10-31T10:00:%02d+00:00" % owed)] == [waiting.id], \
    "it was still not due once its backoff had passed"
ok("the first retry is immediate and later ones wait out a backoff from the "
   "one declared table before they are due again")

# Visible: twelve waiting and one failed eight times, in sentences.
box = SqliteSpool(":memory:")
for n in range(12):
    queues.enqueue(box, kind="audio", key="t-%d" % n, thread="enc-%d" % n,
                   operation="phc.op.consult-document",
                   capability="encounter.document", facility="all-plugins",
                   at=NOW)
stopped = queues.enqueue(box, kind="audio", key="t-stop", thread="enc-s",
                         operation="phc.op.consult-document",
                         capability="encounter.document",
                         facility="all-plugins", at=NOW)
box.put(box.get(stopped.id).__class__(**dict(
    {f: getattr(box.get(stopped.id), f) for f in
     [x.name for x in __import__("dataclasses").fields(QueueItem)]},
    state="failed", attempts=8, last_error="there is no line")))
said = queues.status(box).lines()
assert "12 recordings waiting for the line" in said, said
assert "1 recording failed and stopped after 8 attempts" in said, said
ok("the outbox says in plain words that twelve recordings are waiting and "
   "that one has failed eight times")

for n, expect in ((0, "nothing is waiting to be sent"),
                  (1, "1 recording waiting for the line")):
    box = SqliteSpool(":memory:")
    for i in range(n):
        queues.enqueue(box, kind="audio", key="k-%d" % i, thread="enc",
                       operation="phc.op.consult-document",
                       capability="encounter.document",
                       facility="all-plugins", at=NOW)
    assert queues.status(box).lines() == [expect], queues.status(box).lines()
ok("and it reads correctly at nought and at one, not only at twelve")


# ==========================================================================
# 6. Two pumps, one item.
# ==========================================================================

box = SqliteSpool(os.path.join(WORK, "race.sqlite3"))
contested = queues.enqueue(box, kind="audio", key="txn-race", thread="enc-r",
                           operation="phc.op.consult-document",
                           capability="encounter.document",
                           facility="all-plugins", at=NOW)
won, errors = [], []


def grab():
    try:
        got = SqliteSpool(os.path.join(WORK, "race.sqlite3")).claim(
            contested.id, at=NOW)
        if got is not None:
            won.append(got.id)
    except Exception as broke:               # noqa: BLE001
        errors.append(broke)


racers = [threading.Thread(target=grab) for _ in range(8)]
for r in racers:
    r.start()
for r in racers:
    r.join()
assert not errors, errors
assert won == [contested.id], \
    "%d of 8 pumps claimed one item, so that many would have sent it" % len(won)
assert box.get(contested.id).attempts == 1, box.get(contested.id)
ok("eight pumps racing for one item produce exactly one claim and one "
   "attempt, so a second worker cannot send what a first one took")


# ==========================================================================
# 7. What a queued item stores, and what a log line about it may contain.
# ==========================================================================

# Read from the syntax tree, not from a stripped string: scripts/engine_code.py
# drops any string that begins a statement, so in a multi-line dict it drops
# every key and cannot assert about them. The columns of an outbox row are
# exactly the kind of thing that needs asserting, so the tree is read.
SPOOL_SRC = ast.parse((ROOT / "adapters/local/spool.py").read_text())
COLUMNS = None
for node in ast.walk(SPOOL_SRC):
    if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == "COLUMNS" for t in node.targets):
        COLUMNS = [e.value for e in node.value.elts]
assert COLUMNS, "COLUMNS is no longer a literal tuple in the spool adapter"

# The allowlist. A column added to the outbox has to be added here too, by
# somebody who has thought about whether it is identifiable.
ALLOWED = {
    "id", "kind", "key", "thread", "operation", "capability", "facility",
    "created_at", "actor", "blob", "state", "attempts", "last_error",
    "claimed_at", "sent_at", "receipt",
}
assert set(COLUMNS) == ALLOWED, \
    "the outbox has grown or lost a column: %s" % (set(COLUMNS) ^ ALLOWED)

# None of them is content. Named individually rather than by a pattern,
# because a pattern over column names proves nothing about what they hold.
CONTENT = ("name", "payload", "answer", "value", "text", "note", "transcript",
           "phone", "mobile", "aadhaar", "abha", "otp", "dob", "age", "sex",
           "address", "village", "body", "document", "audio")
for column in COLUMNS:
    assert column not in CONTENT, \
        "the outbox stores %r, which is content and not state" % column
ok("an outbox row holds %d columns and not one of them is content: no name, "
   "no payload, no answer, and for a document no body at all" % len(COLUMNS))

# The scrubber, on the three rules this project already has. These are the
# strings a gateway really does send back.
CASES = [
    ("aadhaar", "Aadhaar 1234 5678 9012 is already linked",
     ["1234 5678 9012", "123456789012"], "<aadhaar-redacted>"),
    ("aadhaar, unspaced", "linking 123456789012 failed",
     ["123456789012"], "<aadhaar-redacted>"),
    ("mobile", "no profile for mobile 9876543210", ["9876543210"], "ending 3210"),
    ("mobile with a country code", "+91 98765 43210 is unknown",
     ["9876543210", "98765 43210"], "ending 3210"),
    ("otp", "OTP 123456 has expired, request another",
     ["123456"], queues.OTP_MARK),
    ("one time password", "the one-time password 4821 was wrong",
     ["4821"], queues.OTP_MARK),
]
for label, raw, forbidden, expected in CASES:
    out = queues.scrubbed(raw)
    for bad in forbidden:
        assert bad not in out, "%s survived the scrubber in %r: %r" % (bad, label, out)
    assert expected in out, "%s: %r does not carry %r" % (label, out, expected)
ok("a failure sentence reaching the outbox carries no Aadhaar number, no OTP, "
   "and no mobile number beyond its last four digits, on %d real shapes"
   % len(CASES))

# An Aadhaar number is removed, not reduced to four digits: four digits of an
# Aadhaar number is still four digits of an Aadhaar number.
out = queues.scrubbed("Aadhaar 1234 5678 9012 refused")
assert "ending 9012" not in out, \
    "an Aadhaar number was treated as a phone number and kept its last four"
ok("and an Aadhaar number is removed whole rather than reduced to four "
   "digits, which the mobile rule would otherwise have done")

# A long remote body cannot arrive whole through the error field.
assert len(queues.scrubbed("x" * 5000)) <= queues.ERROR_CHARS
ok("and a long response body is truncated rather than stored")

# The only writer of that field is the kernel module, so a sender cannot get
# raw text onto the row by raising something unusual. Asserted from the source
# of every call to settle() with an error, across the repository.
WRITERS = set()
for path in sorted(ROOT.glob("kernel/*.py")) + sorted(ROOT.glob("api/*.py")) \
        + sorted(ROOT.glob("adapters/local/*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", "") != "settle":
            continue
        for kw in node.keywords:
            if kw.arg != "error":
                continue
            # Exactly two shapes are allowed: a `scrubbed(...)` call, or a
            # constant string this repository typed itself. A variable is
            # refused even when it holds scrubbed text, because a variable is
            # a rule nobody can check from here.
            clean = (
                (isinstance(kw.value, ast.Call)
                 and getattr(kw.value.func, "id", "") == "scrubbed")
                or (isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)))
            assert clean, (
                "%s:%d passes error= to settle() as something other than a "
                "scrubbed() call or a constant string"
                % (path.relative_to(ROOT), node.lineno))
            WRITERS.add(str(path.relative_to(ROOT)))
assert WRITERS == {"kernel/queues.py"}, WRITERS
ok("and kernel/queues.py is the only module in the kernel, the API or the "
   "adapter that writes that field, every time through the scrubber")

# A recording's own filename carries nothing either: a directory listing is
# as readable as a log line.
box = SqliteSpool(":memory:")
root = os.path.join(WORK, "names")
path = box.keep("q-abc123", b"audio", root=root)
assert os.path.basename(path) == "q-abc123.bin", path
assert oct(os.stat(path).st_mode)[-3:] == "600", oct(os.stat(path).st_mode)
assert oct(os.stat(root).st_mode)[-3:] == "700", oct(os.stat(root).st_mode)
ok("a waiting recording is named after its opaque item id, readable by its "
   "owner only, in a directory readable by its owner only")

# And it waits outside the repository, whatever the environment says.
for value in ("", "~/somewhere-else"):
    os.environ[queues.SPOOL_ENV] = value
    where = queues.spool_root()
    assert not where.startswith(str(ROOT)), \
        "recordings would wait inside the repository: %s" % where
os.environ.pop(queues.SPOOL_ENV, None)
assert not queues.spool_root().startswith(str(ROOT)), queues.spool_root()
ok("and it waits outside this repository by default, because a source tree "
   "is copied, zipped and pushed")

# The retention backstop is the scribe connector's number and not a second
# one invented here.
from care_phc.connectors.scribe import base as scribe_base   # noqa: E402

QUEUES_SRC = (ROOT / "kernel/queues.py").read_text()
assert "AUDIO_MAX_HOLD_SECONDS" in QUEUES_SRC, \
    "the queue no longer reads the scribe's retention rule"
assert not re.search(r"MAX_HOLD\w*\s*=\s*\d", QUEUES_SRC), \
    "the queue has invented its own retention window beside the scribe's"

box = SqliteSpool(":memory:")
old = queues.enqueue(box, kind="audio", key="txn-old", thread="enc-o",
                     operation="phc.op.consult-document",
                     capability="encounter.document", facility="all-plugins",
                     at="2026-10-01T10:00:00+00:00",
                     blob=box.keep("q-old", b"audio",
                                   root=os.path.join(WORK, "old")))
removed = []
gone = queues.sweep_audio(box, now=NOW, delete=removed.append,
                          max_hold=scribe_base.AUDIO_MAX_HOLD_SECONDS)
assert gone == [old.id], gone
assert removed and removed[0].endswith("q-old.bin"), removed
aged = box.get(old.id)
assert aged.state == "failed" and "retention" in aged.last_error, aged
assert not aged.receipt, "audio that aged out was recorded as sent"
ok("a recording held past the retention backstop is deleted and the item "
   "stops in 'failed', never marked sent, under the scribe connector's own "
   "window rather than a second one")


# ==========================================================================
# 8. Wiring, and the protocol seam.
# ==========================================================================

CHECK_SH = (ROOT / "scripts/check.sh").read_text()
assert "scripts/check_queues.py" in CHECK_SH, \
    "this file is not in scripts/check.sh, so the gate does not run it"
ok("the gate runs this file: scripts/check.sh names it")

# The Spool protocol, pinned against the adapter the way the Store protocol's
# ten names are pinned in adapters/local/tests/test_store.py. The count is
# asserted from the class and not from the prose, which is how the Store
# docstring was caught calling ten methods nine.
from kernel.contracts import Spool                              # noqa: E402

declared = sorted(n for n in vars(Spool) if not n.startswith("_"))
assert declared == ["claim", "get", "items", "put", "settle"], declared
for name in declared:
    assert callable(getattr(SqliteSpool, name, None)), "SqliteSpool has no " + name
ok("the Spool protocol's five names are all on the adapter")

# And the kernel calls nothing on a Spool that the protocol does not declare.
# This is the hole the Store protocol HAS: see below.
tree = ast.parse((ROOT / "kernel/queues.py").read_text())
called = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and getattr(node.func.value, "id", "") == "spool":
        called.add(node.func.attr)
extra = called - set(declared) - {"keep", "drop"}
assert not extra, \
    "kernel/queues.py calls %s on a Spool, which the protocol does not declare" % sorted(extra)
ok("and the kernel calls nothing on a Spool that the protocol does not "
   "declare, so a second spool implementation cannot fail at runtime")

# THE CONTRADICTION THIS PINS RATHER THAN FIXES. kernel/directory.py calls
# `store.record_directory_id(...)`, an eleventh method the Store protocol does
# not declare, so the protocol's own claim that "a SQLite file and a REST
# client over somebody else's record can both satisfy every one" is not true
# today: a second adapter would pass the ten-name test in
# adapters/local/tests/test_store.py and then raise AttributeError inside
# publish_pending(). It is reported rather than fixed, because fixing it means
# changing the protocol and the test that pins its ten names, which is a
# decision about the Store seam and not this module's to make. Held at exactly
# one so a SECOND one fails the gate.
from kernel.contracts import Store                              # noqa: E402

store_names = {n for n in vars(Store) if not n.startswith("_")}
off_protocol = {}
for path in sorted(ROOT.glob("kernel/*.py")):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and getattr(node.func.value, "id", "") == "store" \
                and node.func.attr not in store_names:
            off_protocol.setdefault(path.name, set()).add(node.func.attr)
assert off_protocol == {"directory.py": {"record_directory_id"}}, \
    "the kernel's off-protocol Store calls have changed: %s. Either a new one " \
    "was added, which breaks the second-adapter promise, or the known one was " \
    "fixed and this check should say so." % off_protocol
ok("the kernel's only off-protocol Store call is still the one known hole "
   "(kernel/directory.py record_directory_id), so a second one fails the gate")

print("ok   queues: %d checks" % checks)


# ==========================================================================
# Mutations this file is built to fail under. Each one was applied, the whole
# gate was run, the first failing check was recorded, and it was reverted and
# the gate confirmed green again (exit 0, 722 ok). 17 applied, 17 caught.
#
# Two of them were refused by the harness before they ran, in both cases
# because the replacement text still CONTAINED the text it replaced, so the
# mutation would have been a no-op dressed as a change. They were re-anchored
# and then caught. That trap is the reason the harness asserts the file
# changed AND the old text is gone, on a string, before it writes anything.
#
#   mutation                                      first check to fail
#   -----------------------------------------------------------------------
#   claim leaves the state alone                  a crash mid-send left the
#     (adapters/local/spool.py)                   item 'ready'
#   claim without the compare-and-set             8 of 8 pumps claimed one item
#   recovery returns a stuck item to the          it was not settled from the
#     queue without asking the remote             remote's own answer
#   a remote that cannot say is guessed about     kernel/queues demo: a remote
#                                                 that cannot say holds it
#   an unwritable receipt reported as sent        it was REPORTED as sent
#   permit judged after the claim                 a guard denial cost an attempt
#   permit's answer ignored entirely              it was sent anyway
#   a withheld plugin not refused at send time    it was sent anyway
#   an empty receipt counts as a success          recorded as a success
#   the error path does not scrub                 the syntax tree: error= is
#                                                 not a scrubbed() call
#   the mobile rule before the Aadhaar rule       an Aadhaar number kept as
#                                                 "ending 9012"
#   audio that aged out recorded as sent          it did not stop in 'failed'
#   a canned document body instead of the         the bundle has no identifier
#     projection
#   the kernel reaches past the Spool protocol    AttributeError: no 'vacuum'
#   a content column on the row (dataclass only)  spool demo: COLUMNS and
#                                                 QueueItem have drifted
#   the same column in BOTH places                the outbox has grown a column
#   the gate's line running this file deleted     check_templates.py: the gate
#                                                 does not run check_queues.py
#
# No assertion was deleted for being unfailable.
# ==========================================================================
