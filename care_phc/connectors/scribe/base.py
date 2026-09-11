"""The scribe connector boundary, and the audio retention rule behind it.

Two methods, in the same spirit as care_phc/connectors/abdm/base.py: submit
audio for one operation, and fetch the Draft it turned into. Everything else a
caller needs is composition, so it lives here as `transcribe()` rather than as
a third method every implementation would have to reimplement.

The scribe never commits. It produces `kernel.contracts.Draft`, which is the
same shape the voice instruments produce and the same one the renderer already
draws in editable fields behind a tap. There is no second draft shape and
there must not be one: `phc.inst.consult-scribe` declares `readback: required`
and `commit: tap`, and a discrete value a scribe heard is a discrete value a
machine heard, so it is marked unconfirmed exactly as a spoken number is.

AUDIO RETENTION is here rather than in the implementation because it is a
property of the boundary: any scribe, on any gateway, holds raw consultation
audio for a while and must stop. `AudioRetention` is the whole of it, and the
grace window is a named setting with a conservative default, NOT an agreed
number. See the constants below.
"""
from __future__ import annotations

import os
import time
from typing import Optional, Protocol

from kernel.contracts import Draft


# --------------------------------------------------------------------------
# Settings. Every one of these is a decision somebody has to sign, and the
# defaults here are the conservative end of the argument, not the answer.
# --------------------------------------------------------------------------

# How long the derived audio is kept after the doctor confirms the draft it
# produced. The window exists so a correction made straight after a confirm can
# be checked against what was said; nothing else uses it.
#
# THIS NUMBER NEEDS A CLINICAL AND LEGAL SIGN OFF AND DOES NOT HAVE ONE.
# Fifteen minutes is chosen because it is long enough to re-open a note you
# have just confirmed and short enough that a clinic does not accumulate a day
# of consultations on disk. Addendum E.3 says audio retention is separate from
# record retention and that the default is deletion once the derived payload is
# confirmed; it does not name a window. Whoever signs it should also decide
# whether the window is zero, which is a supported value here.
AUDIO_GRACE_SECONDS = 15 * 60

# The backstop for audio nobody ever confirmed: an abandoned consultation, a
# crashed browser, a draft the doctor ignored. Unconfirmed audio is deleted
# after this whether or not anything was derived from it, because keeping it
# longer has no clinical use and every day of it is a liability.
AUDIO_MAX_HOLD_SECONDS = 6 * 60 * 60

# Polling bounds for transcribe(). Two live runs of the same 92 second
# consultation against api.eka.care on 2026-09-11 came back in 25s and in 52s,
# so the turnaround varies by a factor of two on identical audio and neither
# number is a ceiling. A ten minute consultation has never been measured here.
# 120 is therefore a floor under a guess: raise it once a real clinic's
# recordings have been timed, and note that a timeout costs nothing but a
# second fetch, since the session id survives on the error.
POLL_TIMEOUT_SECONDS = 120
POLL_INTERVAL_SECONDS = 3


class ScribeError(RuntimeError):
    """Any failure from the scribe side, scrubbed on the way out.

    The only error type that crosses this boundary, for the reason
    AbdmError exists: an SDK exception carries the gateway's response body and
    the local file path verbatim, and the file path of a consultation recording
    is an identifier. `session` is set on a timeout so a caller can come back
    for the same session later instead of asking the doctor to say it again.
    """

    def __init__(self, message, *, code=None, status=None, session=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.session = session


class ScribeConnector(Protocol):
    """What the consultation needs from a scribe.

    Deliberately two methods. Submit is separate from fetch because the
    gateway is asynchronous and a clinician's screen must not be held open on
    a socket: a timeout on the fetch loses nothing, since the session id is
    still good.
    """

    def submit(self, audio_path, *, operation: str, thread: Optional[str] = None) -> str:
        """Hand over one audio file. Returns the session id.

        Takes ownership of the file: an implementation may rename it, and is
        responsible for deleting it under the retention rule above. `thread` is
        kept locally so a consent withdrawal can find this visit's audio; an
        implementation must not send it to the gateway, because the encounter
        id is an identifier and the gateway does not need one.
        """

    def fetch(self, session: str, *, operation: str) -> Optional[Draft]:
        """The Draft for that operation, or None while the gateway is still
        working. A Draft with no values is the fail closed outcome and means
        the gateway returned nothing this operation asks for: show the form.
        Never invents a value that was not returned."""


def transcribe(connector, audio_path, *, operation, thread=None,
               timeout=POLL_TIMEOUT_SECONDS, interval=POLL_INTERVAL_SECONDS,
               sleep=time.sleep, clock=time.monotonic) -> Draft:
    """Submit, then poll until there is a Draft or the clock runs out.

    Polling, not webhooks, and the reason is not preference: a webhook needs a
    public URL, a registered endpoint and a receiver, and nothing in this
    repository has any of the three. Eka's own status endpoint is documented as
    the alternative to the webhook and answers in seconds, so the honest
    integration today is to poll it. A deployment that has an ingress should
    take the webhook instead and call `fetch()` from it; the boundary is the
    same either way, which is why the poll loop is here and not in the
    implementation.

    Bounded on purpose. On timeout this raises rather than returning an empty
    Draft, because "we do not know yet" and "the scribe heard nothing" are
    different sentences to put in front of a doctor. The session id rides on
    the error so the caller can fetch again later.
    """
    session = connector.submit(audio_path, operation=operation, thread=thread)
    deadline = clock() + timeout
    while True:
        draft = connector.fetch(session, operation=operation)
        if draft is not None:
            return draft
        if clock() >= deadline:
            raise ScribeError(
                "The scribe has not answered in %ds. Use the form; the "
                "recording is still being worked on." % timeout,
                code="timeout", session=session)
        sleep(interval)


def _scan(directory):
    """(path, mtime) for everything in a directory. Replaceable in a check."""
    try:
        return [(e.path, e.stat().st_mtime) for e in os.scandir(directory) if e.is_file()]
    except FileNotFoundError:
        return []


class AudioRetention:
    """Deletes consultation audio: on confirm after a grace window, on consent
    withdrawal at once, and on a backstop for audio nobody ever confirmed.

    Held in memory, which is honest about what it is: a process that dies
    forgets what it was holding. That is why `directory` exists. Given one,
    `sweep` also deletes any file in it older than the backstop, whether or not
    this process put it there, which is what catches the audio a restart
    orphaned.

    Nothing in the kernel calls this yet. Like the ABDM connector, it is wiring
    waiting for an operation: there is no route here that records a confirm, so
    `confirmed()` has no caller outside the checks. Said plainly rather than
    left to be discovered.
    """

    def __init__(self, *, grace_seconds=AUDIO_GRACE_SECONDS,
                 max_hold_seconds=AUDIO_MAX_HOLD_SECONDS, directory=None,
                 remove=os.remove, clock=time.time, scan=_scan):
        self.grace_seconds = grace_seconds
        self.max_hold_seconds = max_hold_seconds
        self.directory = directory
        self._remove = remove
        self._clock = clock
        self._scan = scan
        self._held = {}          # session -> {path, thread, held_at, confirmed_at}

    def hold(self, session, path, *, thread=None, at=None):
        """This file is ours now, and it is on a clock from this moment."""
        self._held[session] = {"path": path, "thread": thread,
                               "held_at": at if at is not None else self._clock(),
                               "confirmed_at": None}

    def confirmed(self, session, at=None):
        """The derived payload was confirmed by a person. The audio has done
        its job; the grace window is the only thing keeping it."""
        held = self._held.get(session)
        if held is not None:
            held["confirmed_at"] = at if at is not None else self._clock()

    def discard(self, *, session=None, thread=None):
        """Delete now, no window. This is the consent withdrawal path: E.3
        says withdrawal stops capture and discards the audio from that point,
        and a visit may have produced several recordings, so a thread deletes
        all of its own. Returns how many files went."""
        gone = 0
        for sid in [s for s, h in self._held.items()
                    if (session is not None and s == session)
                    or (thread is not None and h["thread"] == thread)]:
            gone += self._delete(sid)
        return gone

    def sweep(self, at=None):
        """Delete everything past its window. Call it on a timer. Returns how
        many files went; it returns no paths, because a path is the one thing
        that must not end up in a caller's log line."""
        now = at if at is not None else self._clock()
        gone = 0
        for sid, held in list(self._held.items()):
            confirmed = held["confirmed_at"]
            expired = (confirmed is not None and now - confirmed >= self.grace_seconds) \
                or (now - held["held_at"] >= self.max_hold_seconds)
            if expired:
                gone += self._delete(sid)
        if self.directory:
            ours = {h["path"] for h in self._held.values()}
            for path, mtime in self._scan(self.directory):
                if path not in ours and now - mtime >= self.max_hold_seconds:
                    gone += self._unlink(path)
        return gone

    def pending(self):
        """How many recordings are still on disk under this rule."""
        return len(self._held)

    def _delete(self, session):
        held = self._held.pop(session, None)
        return self._unlink(held["path"]) if held else 0

    def _unlink(self, path):
        try:
            self._remove(path)
        except OSError:
            return 0     # already gone, or never written. Not worth a line.
        return 1
