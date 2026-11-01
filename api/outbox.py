"""The outbox, switched on: what holds a recording when the line is down, and
what deletes it when its 24 hours are up.

Why this file exists at all
---------------------------
`kernel/queues.py` was complete and proved for a month and WIRED TO NOTHING.
Its own prose said so, and said why: surviving an outage MEANS holding
consultation audio on a clinic's disk, and the retention window that made that
safe had no clinical or legal sign-off. The order it named was "sign the
retention window, then wire the route".

The window is signed. `docs/DECISIONS-2026-11-01.md` decision 2: a recording
may be held for 24 hours, with that ceiling "enforced rather than documented".
So this is the route, and the enforcement is the point of it rather than a
footnote: `sweep()` below is the only thing in this repository that has ever
called `queues.sweep_audio` outside a check.

What runs, and on what clock
----------------------------
One background thread per API process, started by `api/main.py`. Every
`SWEEP_SECONDS` it does three things in this order, and the order is the
design:

1. `recover()` first, because an item left in `sending` by a crash must be
   asked about before anything new is claimed. Resending blind is the one
   thing the outbox may never do.
2. `pump()`, which is the sending pass. The guard runs again per item, before
   the claim, so an item queued under capabilities somebody has since lost
   does not go out.
3. `sweep_audio()` LAST, so a recording that could have gone out in this very
   pass is not deleted a moment before its chance. A sweep that ran first
   would turn a flickering line into lost audio.

A thread and not a cron entry, deliberately. The whole deployment story is one
process on a clinic PC with no internet and nobody administering it; a
retention rule that depends on somebody installing a timer is a retention rule
that is off at the sites that need it most. It is a daemon thread, so it never
holds the process open on shutdown, and every pass is wrapped: a sweeper that
dies silently would leave audio on disk forever, so a failed pass is logged and
the next one still happens.

THE CEILING IS NOT ENFORCED HERE AND THAT IS ON PURPOSE. `queues.held_ceiling`
clamps it, on the deleting path, in the kernel. If the clamp lived in this
file, a deployment that replaced this file would have replaced the ceiling.

What this module does NOT do
----------------------------
- It writes nothing clinical to the outbox. That is `kernel/queues.py`'s
  privacy decision, stated in its own prose and carried here rather than
  re-derived: identifiers and state, no name, no number, and for a document no
  body at all.
- It expires no TEXT. The decision draws that line and it is load bearing: a
  household visit form held offline in a village is text and does not have a
  clock on it. `sweep_audio` walks `kind="audio"` only, and nothing here
  touches a document's row.
- It publishes no national document. There is no ABDM connector in this build,
  so `senders()` configures a sender for audio and NOT for documents. An
  unsendable kind is not silently dropped: `pump()` stops it in `failed`
  saying nothing is configured to send it, which is the honest answer, and a
  document's body is re-projected from the Store at send time anyway so
  nothing is lost by waiting.

Run the check: python3 scripts/check_audio_ceiling.py
"""
from __future__ import annotations

import contextlib
import logging
import os
import threading

from kernel import queues

log = logging.getLogger("phc.outbox")

# How often a pass happens. Five minutes: short enough that a line coming back
# is used inside one consultation, long enough that a clinic PC is not doing
# this instead of drawing a screen. NOT MEASURED against a real clinic line, in
# exactly the sense kernel/queues.py labels its own backoff numbers guesses.
#
# It also bounds how late a deletion can be: a recording is deleted within one
# pass of its window expiring, so the effective ceiling is 24 hours plus up to
# five minutes rather than 24 hours exactly. Said plainly because a ceiling
# that is quietly approximate is the sort of claim this work exists to stop.
DEFAULT_SWEEP_SECONDS = 300
SWEEP_SECONDS = int(os.environ.get("PHC_SWEEP_SECONDS") or DEFAULT_SWEEP_SECONDS)

# Where this process keeps its outbox database. Beside the spool rather than
# beside the clinical store: an outbox must survive the system of record being
# unreachable, which is kernel/contracts.py's reason for the Spool protocol
# existing at all.
SPOOL_DB = "outbox.sqlite3"


def spool_path():
    """The outbox database's own file, under the spool root and not the repo."""
    root = queues.spool_root()
    os.makedirs(root, mode=queues.SPOOL_DIR_MODE, exist_ok=True)
    return os.path.join(root, SPOOL_DB)


def open_spool():
    """This process's outbox, owner readable only.

    The directory mode protects the file by stopping anybody else traversing
    into it, and the file is narrowed anyway: defence in depth costs one
    syscall, and a directory mode is one `chmod` by a well meaning
    administrator away from being wider than it was. SQLite's own journal and
    write-ahead files inherit the mode of the database they belong to, so
    narrowing this one narrows those.

    An outbox row carries identifiers and state and nothing clinical, which is
    kernel/queues.py's privacy decision. This is not a reason to leave it
    readable: which operations a named person performed on which threads, and
    when, is a record of a clinic's day.
    """
    from adapters.local.spool import SqliteSpool

    path = spool_path()
    spool = SqliteSpool(path)
    for suffix in ("", "-wal", "-shm"):
        with contextlib.suppress(OSError):
            os.chmod(path + suffix, queues.SPOOL_FILE_MODE)
    return spool


def remove(path):
    """Delete one recording's bytes. The only thing that unlinks a blob.

    Separate from the sweep so the checks can watch what was deleted without
    reaching into the filesystem, and so a path never reaches a log line: a
    recording's filename is the one piece of this that must not be logged.
    """
    os.remove(path)


def hold_recording(spool, audio, *, thread, actor, operation, capability,
                   facility, at, suffix=".webm", key=None, withheld=None):
    """Keep one recording that could not be sent, and queue it.

    THE BYTES GO OUTSIDE THE REPOSITORY, OWNER READABLE ONLY. That is
    kernel/queues.py's rule and it is the whole of what makes holding audio
    tolerable: a source tree is copied, zipped and pushed, and a clinic machine
    has more than one account on it. The directory is 0700 and the file is
    0600, both from the kernel's own constants rather than chosen again.

    The file is named after the item's opaque id and nothing else. Not the
    thread, not the patient, not the time: a filename is metadata that survives
    deletion in a directory listing and in a backup index.

    Written BEFORE the row is queued, and the row is what the sweeper reads, so
    a crash between the two leaves a stray file rather than a queued item with
    no bytes. The stray is swept by the connector's own directory sweep, which
    is what `AudioRetention(directory=...)` is for; a queued item pointing at
    nothing would be retried to its attempt limit instead.
    """
    import uuid

    root = queues.spool_root()
    os.makedirs(root, mode=queues.SPOOL_DIR_MODE, exist_ok=True)
    # The directory may predate this process with wider bits on it.
    os.chmod(root, queues.SPOOL_DIR_MODE)

    name = "audio-%s%s" % (uuid.uuid4().hex[:16], suffix)
    path = os.path.join(root, name)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                     queues.SPOOL_FILE_MODE)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(audio)
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(path)
        raise

    try:
        return queues.enqueue(spool, kind="audio", key=key or name,
                              thread=thread, operation=operation,
                              capability=capability, facility=facility,
                              at=at, actor=actor, blob=path,
                              withheld=withheld)
    except Exception:
        # Refusing to HOLD it means keeping nothing, which is
        # kernel/queues.enqueue's own rule: an item for a plugin this centre
        # does not run leaves no row, no recording on disk and nothing for a
        # person to wonder about.
        with contextlib.suppress(OSError):
            os.remove(path)
        raise


class ScribeSender:
    """Sends one held recording to the speech service.

    `kernel.contracts.Sender`'s two methods and nothing else. It imports
    api/scribe rather than a connector directly, so the credentials and the
    scrubbing stay in the one module that already owns them.
    """

    def send(self, item, body):
        """Upload the bytes and return the receipt the remote knows it by.

        The receipt is the transaction id, which is what makes the item's key
        meaningful: asked for twice, it is one job on their side.
        """
        from api import scribe

        try:
            return scribe.start(body, suffix=_suffix_of(item.blob))
        except Exception as broke:                   # noqa: BLE001
            # Every failure crosses this boundary as Unsendable, scrubbed by
            # pump() and never here: one filter, so a new sender cannot forget
            # to scrub.
            raise queues.Unsendable(str(broke)) from None

    def delivered(self, item):
        """Whether the service already has this recording.

        Delivery(known=False), always, and that is the honest answer rather
        than a stub. The upload is keyed by a transaction id WE mint per
        attempt, and there is no route at the service that answers "do you
        already have the recording I called X": the status route takes a
        transaction id it issued, so asking about an attempt whose id we never
        got back is unanswerable.

        What that costs is spelled out in kernel/queues.py: an item the remote
        cannot speak for is parked in `held` for a person rather than guessed
        about. For audio that is the right way round. Resending a recording
        costs a duplicate transcription nobody reads; reporting one as sent
        when it was not costs the consultation.
        """
        return queues.Delivery(known=False)


def _suffix_of(path):
    """The extension the held file was written with, or the default."""
    import os.path

    return os.path.splitext(path or "")[1] or ".webm"


def live_senders():
    """What this process can actually send, and nothing it cannot.

    Audio only. THERE IS NO DOCUMENT SENDER because there is no ABDM connector
    in this build, and configuring one that pretended would be the worst
    outcome available: `pump()` stops an item with no sender in `failed`
    saying nothing is configured to send it, which is a sentence a person can
    read, and a document's body is re-projected from the Store at send time so
    nothing is lost by its waiting.
    """
    return {"audio": ScribeSender()}


class Outbox:
    """One facility's outbox and the thread that works it.

    Holds the spool, the senders and the permit. Nothing here knows what a
    blood pressure is, and nothing here names a station, a flag, a capability
    or a bundle's word: it moves opaque items and deletes expired bytes.
    """

    def __init__(self, store, bundle, *, spool=None, senders=None,
                 now=None, delete=remove):
        self.store = store
        self.bundle = bundle
        self.spool = spool if spool is not None else open_spool()
        self.senders = senders if senders is not None else {}
        self._now = now or queues_now
        self.delete = delete

    def hold(self, audio, *, thread, actor, operation, capability,
             suffix=".webm", at=None):
        """Keep one recording this process could not send, and queue it.

        The facility and the plugin subtraction come from the bundle rather
        than from the caller, so a route cannot queue an item for a plugin this
        centre has switched off: `queues.enqueue` refuses it and keeps nothing.
        """
        return hold_recording(
            self.spool, audio, thread=thread, actor=actor,
            operation=operation, capability=capability,
            facility=(self.bundle.manifest.id if self.bundle.manifest else ""),
            at=at or self._now(), suffix=suffix,
            withheld=dict(self.bundle.withheld or {}))

    def permit(self, at):
        """The guard, against the world as it is at `at`.

        Built per pass rather than held, because a facility's shape and a
        person's capabilities are exactly the things that may have changed
        while an item waited. `kernel.queues.permit_with_guard` is the one
        predicate; nothing is re-implemented here.

        The actor is the SWEEPER and says so. It is not a clinician and must
        not borrow one's name: an audit row saying a nurse sent something at
        three in the morning because a background thread woke up would be a
        false record of who did what. What the guard judges is the capability
        the item already carries, which was a person's at the time.
        """
        return queues.permit_with_guard(
            self.store, self.bundle,
            caps=sorted((self.bundle.vocabulary or {}).get("capabilities") or ()),
            actor="sweeper:outbox", at=at, surface="mcp")

    def bodies(self, at):
        """What one item's body is. Audio reads its bytes; a document is
        re-projected from the Store at this moment, so a correction made while
        it waited is in what finally leaves."""
        def body(item):
            if item.kind == "audio":
                return queues.audio_body(item)
            return queues.document_body(self.store, self.bundle, item, now=at)
        return body

    def pass_once(self, at=None):
        """One pass: recover, pump, then sweep. Returns (sweep, gone).

        The order is the design and is argued in this module's own docstring.
        Separated from the loop so a check can run exactly one pass with its
        own clock, which is how the ceiling is proved.
        """
        at = at or self._now()
        queues.recover(self.spool, self.senders, now=at)
        report = queues.pump(self.spool, self.senders, permit=self.permit(at),
                             bodies=self.bodies(at), now=at, delete=self.delete)
        # LAST, so a recording that could have gone out in this pass was given
        # its chance first.
        gone = queues.sweep_audio(self.spool, now=at, delete=self.delete)
        return report, gone

    def stop(self):
        """Ask the sweeper to finish its wait and exit. For a check, and for a
        process that wants a clean shutdown rather than a daemon thread dying
        with it."""
        if getattr(self, "_stop", None) is not None:
            self._stop.set()
        thread = getattr(self, "_thread", None)
        if thread is not None:
            thread.join(timeout=5)

    def run_forever(self, interval=None, stop=None):
        """The loop the thread runs. Every pass is wrapped.

        A sweeper that dies on one bad pass leaves audio on a disk forever,
        which is the failure this whole file exists to prevent, so an
        exception is logged and the loop continues. The sentence logged is
        scrubbed by the same rule the outbox row uses, because a remote's
        refusal can carry a number.
        """
        wait = interval or SWEEP_SECONDS
        stop = stop or threading.Event()
        while not stop.wait(wait):
            try:
                report, gone = self.pass_once()
                if gone:
                    log.info("%d held recording(s) reached the retention "
                             "ceiling and were deleted untranscribed", len(gone))
                if report.count():
                    log.info("outbox pass: %s", report.count())
            except Exception as broke:          # noqa: BLE001
                log.warning("an outbox pass failed and the next one will still "
                            "run: %s", queues.scrubbed(str(broke)))


def queues_now():
    """This process's clock, as the string a row stores."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start(store, bundle, *, senders=None, interval=None):
    """Start the sweeper for this process and return the Outbox.

    Called once by api/main.py, at import, so the ceiling is being enforced
    before the first request rather than after it. A daemon thread, so it never
    holds the process open; `stop()` is on the object for a caller that wants
    it back.

    PHC_SWEEP_SECONDS=0 starts no thread and is for a check that drives
    `pass_once` with its own clock. It does not switch the CEILING off: a
    process that is not sweeping is holding nothing new, and the next process
    to open this spool sweeps on its first pass.

    STARTING MUST NOT BE ABLE TO STOP THE API. The spool is a file on a disk
    this process may not own, so a failure to open it is caught: the answer is
    a kernel that serves and refuses to hold recordings, with the reason
    logged, rather than a clinic whose screens do not come up because an
    outbox could not be created.
    """
    try:
        box = Outbox(store, bundle, senders=senders)
    except Exception as broke:                       # noqa: BLE001
        log.error("the outbox could not be opened, so no recording will be "
                  "held and none will be swept: %s", queues.scrubbed(str(broke)))
        return None
    wait = interval if interval is not None else SWEEP_SECONDS
    if not wait:
        return box
    box._stop = threading.Event()
    box._thread = threading.Thread(
        target=box.run_forever, args=(wait, box._stop),
        name="phc-outbox", daemon=True)
    box._thread.start()
    log.info("the outbox sweeper is running every %ds; held audio is deleted "
             "after at most %ds", wait, queues.AUDIO_CEILING_SECONDS)
    return box
