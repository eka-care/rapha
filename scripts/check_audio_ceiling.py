"""The 24 hour ceiling on held audio, proved the way a clinic would meet it.

What is being proved
--------------------
`docs/DECISIONS-2026-11-01.md` decision 2 says a recording may be held for 24
hours and that the ceiling must be "enforced rather than documented". Three
things have to be true for that sentence to mean anything, and each is a
separate section below.

1. THE BYTES ARE ACTUALLY GONE FROM THE DISK. Not the row marked deleted, not
   a flag set, not a path forgotten about: the file is not there any more. A
   retention rule that leaves the recording on the disk with its row tidied up
   is the worst of both, because the liability is still on the disk and nobody
   is looking for it.

2. THE RECORD OF WHAT HAPPENED IS HONEST. The item is NOT `sent`, because it
   was not. It stops in `failed` saying the recording aged out without being
   transcribed, so the thing a person reads is "nobody got a transcript and
   the note was typed or it was not" rather than silence.

3. SOMETHING CALLS IT ON A SCHEDULE. This is the one that was missing. The
   sweep was complete and proved for a month and its only callers in the whole
   repository were checks, so a clinic running this code would have held audio
   until the disk filled. A ceiling enforced by a function nobody calls is a
   documented ceiling.

And two lines the decision draws that must not blur
---------------------------------------------------
4. TEXT HAS NO CLOCK. "Text and audio are now different questions, and only
   audio has a clock on it." A household visit form held offline in a village
   is text. The sweep must walk past it, at any age.

5. THE CEILING IS A CLAMP AND NOT A DEFAULT. A deployment that configures 48
   hours gets 24. A number that is merely the default is a number a facility
   can raise, which is exactly what "documented rather than enforced" means.

Nothing here is a sequential restatement of the sweep's own unit tests, which
already exist in scripts/check_queues.py. What this file adds is the
production path: the real spool, real files on a real disk, the real wiring in
api/outbox.py, and the clock moved forward rather than the window shortened.

Run: python3 scripts/check_audio_ceiling.py
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# Its own spool, before anything imports the app: api/main.py starts the
# sweeper at import, and this check must not touch a developer's own outbox.
_SPOOL = pathlib.Path(tempfile.mkdtemp(prefix="audio-ceiling-")) / "spool"
os.environ["PHC_SPOOL"] = str(_SPOOL)
# No sweeper thread. Every pass here is driven by hand with its own clock,
# because what is being proved is WHEN a recording goes, and a background
# thread on a five minute timer cannot be asked about that.
os.environ["PHC_SWEEP_SECONDS"] = "0"
_DB = pathlib.Path(tempfile.mkdtemp(prefix="audio-ceiling-db-")) / "phc.sqlite3"
os.environ["PHC_DB"] = str(_DB)
os.environ["PHC_DIRECTORY"] = "absent"

from adapters.local.store import SqliteStore                  # noqa: E402
from api import outbox                                        # noqa: E402
from kernel import declarations, queues                       # noqa: E402

BUNDLE = declarations.load("phc")
WORKFLOW = BUNDLE.workflow()

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def moment(when):
    return when.isoformat(timespec="seconds")


NOW = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)

# An operation a recording may fill, taken from the declarations rather than
# typed, so a bundle that renames one does not leave this check asserting
# against a word nobody uses.
SCRIBE_OPS = sorted(
    op for inst in (BUNDLE.instruments or {}).values()
    if getattr(inst, "kind", "") == "scribe"
    for op in (getattr(inst, "operations", None) or ()))
assert SCRIBE_OPS, "this bundle declares no scribe instrument, so there is " \
                   "no operation a held recording could be for"
OPERATION = SCRIBE_OPS[0]
CAPABILITY = (BUNDLE.operations or {})[OPERATION]["capability"]


def fresh():
    """A store, an outbox and an empty spool directory. No sweeper thread."""
    shutil.rmtree(_SPOOL, ignore_errors=True)
    store = SqliteStore(":memory:")
    thread = store.open_thread(token="1", actor="user:frontdesk")
    box = outbox.Outbox(store, BUNDLE, spool=outbox.open_spool(), senders={})
    return store, box, thread


# ==========================================================================
# 1 and 2. The bytes are gone, and the row is honest about it.
# ==========================================================================

store, box, thread = fresh()
item = box.hold(b"a consultation nobody came back for",
                thread=thread, actor="user:doctor",
                operation=OPERATION, capability=CAPABILITY,
                at=moment(NOW))
held = item.blob

assert os.path.exists(held), "the recording was not written"
assert os.path.getsize(held) > 0, "the recording is an empty file"
ok("a recording the line could not take is held as a real file on the disk, "
   "which is what makes losing it possible and is why the clock exists")

# Owner readable only, and outside the repository. Both are kernel/queues.py's
# own rules and both are asserted here rather than trusted, because the whole
# argument for holding audio at all rests on them.
assert oct(os.stat(held).st_mode)[-3:] == "600", oct(os.stat(held).st_mode)
assert oct(os.stat(os.path.dirname(held)).st_mode)[-3:] == "700", \
    oct(os.stat(os.path.dirname(held)).st_mode)
assert ROOT not in pathlib.Path(held).resolve().parents, \
    "the recording is under the repository: %s" % held
ok("and it waits OUTSIDE the repository, owner readable only (file 600, "
   "directory 700), because a source tree is copied, zipped and pushed")

# Just short of the window: still there. The window is the connector's six
# hours, under the owner's 24 hour ceiling.
window = queues.held_ceiling(None)
box.pass_once(at=moment(NOW + timedelta(seconds=window - 60)))
assert os.path.exists(held), \
    "the recording was deleted before its window was up, which costs a " \
    "consultation to save nothing"
early = box.spool.get(item.id)
assert early.state != "sent", early.state
assert early.blob == held, "the row stopped pointing at its own recording"
ok("a pass one minute before the window is up deletes nothing and the row "
   "still points at the recording, so a flickering line does not cost it")

# WHAT THE GUARD DID TO THIS ITEM, because it is the case that found a hole.
#
# The pass above did not leave the item `ready`. The guard refused it, which is
# the ordinary outcome for a recording whose operation's preconditions do not
# hold on that visit, and `pump()` wrote `refused`. Until 2026-11-01 the sweep
# walked `ready`, `held` and `failed` ONLY, so a refused recording's bytes were
# in a state no sweep looked at and stayed on the disk for as long as the disk
# did. Driving the production path is what showed it; reading the sweep did not.
#
# Asserted rather than narrated, so the hole cannot quietly reopen.
assert early.state == "refused", (
    "this check expects the guard to refuse %s on an empty visit, and it did "
    "not (%r). The sweep's coverage of `refused` is what matters, so if this "
    "ever changes, hold a refused item here deliberately instead of removing "
    "the section." % (OPERATION, early.state))
assert "refused" in queues.SWEPT_STATES, \
    "the sweep does not walk `refused`, so a recording the guard denied keeps " \
    "its bytes past the ceiling. This was true until 2026-11-01."
ok("and the item the guard refused is in a state the sweep DOES walk, which "
   "it was not until this slice: refused audio kept its bytes for a year")

# Past the window: gone from the disk.
box.pass_once(at=moment(NOW + timedelta(seconds=window + 60)))
assert not os.path.exists(held), \
    "THE RECORDING IS STILL ON THE DISK past its retention window: %s" % held
ok("a pass after the window is up deletes the recording from the disk: the "
   "file is not there, rather than its row being tidied up around it")

# And the record says what happened, in those words.
after = box.spool.get(item.id)
assert after is not None, "the item vanished with its bytes"
assert after.state == "failed", (
    "an aged out recording is in state %r. It must not be 'sent': nobody got "
    "a transcript, and reporting one as sent when it was not is the failure "
    "kernel/queues.py exists to prevent." % after.state)
assert after.sent_at in ("", None), after.sent_at
assert after.receipt in ("", None), after.receipt
assert "without being transcribed" in (after.last_error or ""), after.last_error
ok("and the record is honest: the item stops in 'failed' with no receipt and "
   "no sent_at, saying the recording was deleted without being transcribed")

# The row never held anything clinical, which is the privacy decision
# kernel/queues.py states in its own prose and this check carries rather than
# re-derives. Asserted over every field of the row.
leaked = [name for name, value in vars(after).items()
          if isinstance(value, str)
          and ("consultation nobody" in value or "a consultation" in value)]
assert not leaked, "the recording's content reached the outbox row: %s" % leaked
ok("and no part of the recording ever reached the outbox row, which carries "
   "identifiers and state and no clinical content at all")


# ==========================================================================
# 3. Something calls it on a schedule.
# ==========================================================================
# The gap this work closed. Asserted against the SOURCE, because what is being
# held is that a production module reaches the sweep: a check that called it
# itself would prove only that it is callable, which was never in doubt.

sweepers = {}
for path in sorted((ROOT / "api").glob("*.py")):
    text = path.read_text()
    body = "\n".join(l for l in text.splitlines()
                     if not l.lstrip().startswith(("#", '"', "'")))
    if "sweep_audio" in body:
        sweepers[path.name] = True
assert sweepers, (
    "NOTHING under api/ calls queues.sweep_audio, so the retention ceiling is "
    "documented and not enforced. This is the state this check was written "
    "for: the sweep existed, was proved, and had no caller but a check.")
ok("a production module calls the sweep rather than only a check: %s"
   % ", ".join(sorted(sweepers)))

# And it is on a timer, with the timer's own period bounding how late a
# deletion can be.
runner = (ROOT / "api" / "outbox.py").read_text()
assert "run_forever" in runner and "threading.Thread" in runner, \
    "the sweep has a caller but nothing runs it repeatedly"
assert "daemon=True" in runner, \
    "the sweeper is not a daemon thread, so it would hold the process open"
app = (ROOT / "api" / "main.py").read_text()
assert "outbox.start(" in app, \
    "api/main.py never starts the sweeper, so a running kernel sweeps nothing"
# The DEFAULT period, not this check's own: PHC_SWEEP_SECONDS is 0 here so
# that every pass can be driven with its own clock, and reporting that back
# would be this check describing its own environment as the product's.
ok("and api/main.py starts it with the process, on a %ds timer by default, so "
   "the ceiling is being enforced before the first request rather than after it"
   % outbox.DEFAULT_SWEEP_SECONDS)

# The order of a pass, which is the design: a recording that could have gone
# out in this very pass must not be deleted a moment before its chance.
pump_at = runner.index("queues.pump(")
sweep_at = runner.index("queues.sweep_audio(")
recover_at = runner.index("queues.recover(")
assert recover_at < pump_at < sweep_at, (
    "a pass does recover, pump, sweep in that order, and this one does not: "
    "recover %d, pump %d, sweep %d" % (recover_at, pump_at, sweep_at))
ok("and one pass recovers, then sends, then sweeps, so the sweep never "
   "deletes a recording the same pass could have sent")


# ==========================================================================
# 3b. And the OTHER engine runs it too, or the ceiling is off half the time.
# ==========================================================================
# "Both engines or neither" is the repository's rule and this is the place it
# bites hardest. The two engines open the SAME spool, exactly as they open the
# same database, so a Go kernel running beside or instead of the Python's is
# looking at a spool with real recordings in it that the Python put there. A
# Go-only process with no sweeper is a clinic where the ceiling silently is
# not enforced, and nothing else in this repository would have said so.
#
# Asserted against the source for the same reason as section 3: what is being
# held is that a production path reaches the sweep.

go_api = ROOT / "care_phc_mcp" / "cmd" / "api"
go_sources = {path.name: path.read_text() for path in go_api.glob("*.go")}
sweeping = {name for name, text in go_sources.items()
            if "queues.SweepAudio(" in text}
assert sweeping, (
    "NOTHING in care_phc_mcp/cmd/api calls queues.SweepAudio, so the Go "
    "engine holds whatever the Python put in the shared spool and never "
    "deletes it. The ceiling would be enforced only while the Python is the "
    "one running.")
started = {name for name, text in go_sources.items()
           if "startSweeper(" in text and "func startSweeper" not in text}
assert started, (
    "the Go engine has a sweeper and nothing starts it, which is the same "
    "thing as not having one")
assert any("go func()" in text for name, text in go_sources.items()
           if name in sweeping), \
    "the Go sweeper is not on a goroutine, so it would run once or block the " \
    "server"
ok("and the Go engine sweeps the same spool on its own timer (%s, started "
   "from %s), so the ceiling is enforced whichever engine a clinic runs"
   % (", ".join(sorted(sweeping)), ", ".join(sorted(started))))

# The two engines' own numbers agree. Read out of the Go source rather than
# guessed, because a ceiling that differs by engine is two ceilings.
go_queues = (ROOT / "care_phc_mcp" / "queues" / "queues.go").read_text()
assert "AudioCeilingSeconds = 24 * 60 * 60" in go_queues, \
    "the Go engine's ceiling is not the owner's 24 hours"
assert 'SweptStates = []string{"ready", "held", "failed", "refused", "sent"}' \
    in go_queues, "the two engines sweep different states"
ok("and both engines name the same 24 hour ceiling and the same swept states, "
   "which scripts/check_go_parity.py then compares by running them")


# ==========================================================================
# 4. Text has no clock.
# ==========================================================================
# The line decision 2 draws and the one most easily blurred by a tidy
# implementation: a sweep over "everything old" would take the village form
# with the recording and nobody would notice for a year.

store, box, thread = fresh()
paper = queues.enqueue(box.spool, kind="document", key="doc-1", thread=thread,
                       operation=OPERATION, capability=CAPABILITY,
                       facility="phc", at=moment(NOW), actor="user:nurse")
audio = box.hold(b"a recording from the same visit", thread=thread,
                 actor="user:doctor", operation=OPERATION,
                 capability=CAPABILITY, at=moment(NOW))

# THE SWEEP ON ITS OWN, not a whole pass, and that is the point of this
# section. A pass also runs the guard, and the guard refuses both of these on
# an empty visit, so a pass would leave the document in `refused` and this
# check would be asserting about the guard while claiming to be about
# retention. What is being proved here is one thing: the retention sweep walks
# audio and walks PAST text. So it is called directly.
#
# A year later. Far past any ceiling anybody could configure.
gone = queues.sweep_audio(box.spool, now=moment(NOW + timedelta(days=365)),
                          delete=outbox.remove)

assert gone == [audio.id], (
    "the sweep took %s and the only recording is %s" % (gone, audio.id))
assert not os.path.exists(audio.blob), "the recording outlived a year"

still = box.spool.get(paper.id)
assert still is not None, "the held text was deleted with the audio"
assert paper.id not in gone, (
    "the retention sweep took a held DOCUMENT. Text has no clock on it: a "
    "household visit form held offline in a village does not expire.")
assert still.state == "ready", (
    "a held document moved to %r, untouched by anything but this sweep"
    % still.state)
assert not still.blob, "a document kept a body in the outbox"
ok("a year on, the recording is gone and the held TEXT is untouched and still "
   "ready: only audio has a clock, which is the line decision 2 draws")


# ==========================================================================
# 5. The ceiling is a clamp, not a default.
# ==========================================================================

assert queues.AUDIO_CEILING_SECONDS == 24 * 60 * 60, \
    queues.AUDIO_CEILING_SECONDS
assert queues.held_ceiling(48 * 60 * 60) == queues.AUDIO_CEILING_SECONDS, \
    "a deployment asking for 48 hours was given it"
assert queues.held_ceiling(60 * 60) == 60 * 60, \
    "a deployment asking for one hour was overridden upwards"
assert queues.held_ceiling(0) == 0, \
    "zero is a supported window and must not be read as unset"
ok("the ceiling is 24 hours and it CLAMPS: a deployment configuring 48 hours "
   "gets 24, one configuring an hour keeps its hour, and zero stays zero")

# The clamp bites on the deleting path, not only in the constant. Asked for
# 48 hours directly, the sweep still deletes at 24.
store, box, thread = fresh()
item = box.hold(b"held under a window somebody widened", thread=thread,
                actor="user:doctor", operation=OPERATION,
                capability=CAPABILITY, at=moment(NOW))
gone = queues.sweep_audio(box.spool, now=moment(NOW + timedelta(hours=25)),
                          delete=outbox.remove, max_hold=48 * 60 * 60)
assert gone == [item.id], gone
assert not os.path.exists(item.blob), \
    "a 48 hour window was honoured by the code that deletes, so the ceiling " \
    "is a constant nobody reads"
ok("and the clamp is applied by the code that deletes: a sweep asked for a 48 "
   "hour window still removed the recording at 25 hours")

# The connector's own retention object is clamped too, so a facility cannot
# reach around the ceiling by configuring the class the scribe uses.
from care_phc.connectors.scribe import base                   # noqa: E402

assert base.AudioRetention(max_hold_seconds=48 * 60 * 60).max_hold_seconds \
    == queues.AUDIO_CEILING_SECONDS
assert base.AUDIO_MAX_HOLD_SECONDS <= queues.AUDIO_CEILING_SECONDS, \
    "the operational window is above the signed ceiling"
ok("and the connector's own retention is clamped by the same rule, so a "
   "facility cannot widen the window by configuring the class instead")

shutil.rmtree(_SPOOL.parent, ignore_errors=True)
shutil.rmtree(_DB.parent, ignore_errors=True)

print("\nok   the audio retention ceiling: %d checks" % checks)


# ==========================================================================
# Mutations this file is built to fail under. For each one the anchor was
# asserted unique, the replacement asserted absent, the file asserted changed
# by digest, and the old text asserted GONE, all BEFORE anything was run. Then
# this check was run, the sentence it printed was recorded verbatim below, and
# the file was restored and compared byte for byte against its pre-mutation
# copy. 6 applied, 5 caught, and the sixth is the interesting one.
#
# 1. api/main.py: build the Outbox without starting the sweeper, which is the
#    state this whole slice found the repository in.
#      -  OUTBOX = outbox.start(store, BUNDLE, senders=outbox.live_senders())
#      +  OUTBOX = outbox.Outbox(store, BUNDLE, senders=outbox.live_senders())
#    -> FAILS: "api/main.py never starts the sweeper, so a running kernel
#       sweeps nothing".
#
# 2. kernel/queues.py sweep_audio: stop clamping, using the connector's number
#    directly, so the ceiling is a constant nobody reads.
#      -  max_hold = held_ceiling(max_hold)
#      +  max_hold = max_hold if max_hold is not None else 6 * 60 * 60
#    -> FAILS on the 48 hour case: the sweep honoured a widened window and
#       returned [] where the recording should have gone at 25 hours.
#
# 3. kernel/queues.py: drop "refused" from SWEPT_STATES, which is the hole this
#    slice closed.
#    -> FAILS: "the sweep does not walk `refused`, so a recording the guard
#       denied keeps its bytes past the ceiling. This was true until
#       2026-11-01."
#
# 4. kernel/queues.py sweep_audio: settle an aged out recording as `sent`
#    instead of `failed`.
#    -> FAILS: "an aged out recording is in state 'sent'. It must not be
#       'sent': nobody got a transcript, and reporting one as sent when it was
#       not is the failure kernel/queues.py exists to prevent."
#
# 5. care_phc_mcp/cmd/api/main.go: remove the startSweeper call, leaving the Go
#    engine with a sweeper nothing runs.
#    -> FAILS: "the Go engine has a sweeper and nothing starts it, which is the
#       same thing as not having one".
#
# 6. kernel/queues.py sweep_audio: remove the `kind="audio"` filter, so the
#    sweep walks every kind and text would get a clock.
#    -> DID NOT FAIL, AND IT PROVES NOTHING. Recorded rather than quietly
#       dropped, because a mutation that passes is a fact about the code.
#
#       The reason is that the filter is redundant: a document keeps NO BODY in
#       the outbox, which is the privacy decision kernel/queues.py states, so
#       its `blob` is empty, and the sweep's candidate list requires a blob. A
#       document is therefore skipped whatever the kind filter says, and would
#       be skipped again by the delete of an empty path failing. Text is
#       protected structurally rather than conditionally, which is a better
#       answer than the filter, and the filter is kept because it says what is
#       meant.
#
#       So a mutation WAS found that bites, and section 4 is what catches it:
#       adding a second loop to sweep_audio that settles aged held DOCUMENTS to
#       `failed` and reports them gone, which is what giving text a retention
#       clock would actually look like.
#       -> FAILS: "the sweep took ['q-bb3a3b6ba109', 'q-6cb86f6eda24'] and the
#          only recording is q-6cb86f6eda24".
# ==========================================================================
