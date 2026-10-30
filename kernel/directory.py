"""Who is standing at the desk: the local register first, the directory second.

The decision this module implements
-----------------------------------
Settled 2026-10-31: Eka's patient directory is the source of truth for patient
identity and we do not rebuild a local patient master. The "for now" is real,
so the vendor sits behind one interface (`contracts.PatientDirectory`) and
this module is written against that interface and a `Store`, exactly as
`kernel/state.py` is written against a `Store` and nothing else.

What "source of truth" means here, and what it does not
-------------------------------------------------------
The directory decides **who a person is**: it mints the identifier, it
dedupes, and it holds the canonical profile. A profile edit goes to the
directory and comes back; there is no `update` on the interface, because a
facility that can edit the master has rebuilt the master.

The local `patient` table is **not** that master. It is two things, and
neither is a competing source of truth:

1. a cache of profiles this facility has seen, which the queue already
   required: `Store.threads` merges the patient row into every queue row's
   subject, so a line that draws names was always reading a local row. What is
   new is that the row now says where it came from and when it last agreed.
2. the staging area for a patient registered while the directory could not be
   asked. Such a row is not a master record, it is an unpublished one.

The identifier question, resolved
---------------------------------
The brief asked for a thread's subject to become an Eka patient id, and
flagged an ABHA shaped question inside it. The question is which of the two
identifiers is the row's identity, and the code forces the answer:

**`patient.id` stays this product's own, and the Eka `oid` is an identifier
column on that row.** Exactly as `abha_number` is, and for the same reason,
which `kernel/fhir.patient()` already states: a national or platform
identifier is a fact about a person, not our name for their row.

It has to be this way round, and the reason is the offline requirement rather
than taste. A clinical record is created at the moment a person is in front of
a clerk. If the row's primary key were the directory's id, then creating a
record while the directory is unreachable would mean either refusing to
register (a clinic that stops when the line does) or minting a provisional key
and rewriting it later (a clinical record whose identifier changes after the
fact, with audit payloads and any already generated FHIR bundle left pointing
at a ghost). Neither is acceptable, so the row keeps its own key forever and
the directory's id arrives beside it whenever it arrives.

`kernel/spine.py` is untouched by all of this: it joins `encounter.patient` to
`patient.id`, and that join did not move.

One column decides, not two
---------------------------
There is no `directory_status`. A row with a `directory_id` is known to the
directory; a row without one is not. Two columns for one fact is two facts
that can disagree, and the one that disagrees is the one that decides whether
a person gets published twice. `directory_synced` records when we last agreed
with the directory, which is freshness and not status.

So **the publish queue is not a queue.** It is `pending()` below, a query over
the rows we already keep, which is why it cannot drift from them and why a
registration taken while the line was down needs nothing bolted on to be
retried: it is already in the answer.

A directory hit is a suggestion, and a suggestion is not an assertion
--------------------------------------------------------------------
Nothing here writes a clinical row, and nothing here may. A match is a
`Suggestion`: values for the register form, with the field the match came from
beside each one. A person reads it, edits it if it is wrong, and taps commit,
and the tapped values go through `phc.op.patient-register` and
`catalogue.guard.evaluate` like anything else. So there is still exactly one
path to a write and the guard is on it, which is rule 2 of
`kernel/ARCHITECTURE.md` and is not bent here.

Pure in the sense that matters: everything takes a `Store` and a directory and
returns values. `scripts/check_directory.py` runs the whole of it against a
store whose `write` raises, and against a directory that cannot be reached.

Run: python3 -m kernel.directory
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from kernel.contracts import DirectoryError

# The register questionnaire's link_ids that a directory profile can fill. The
# questionnaire is the authority on what may be answered, so this is the
# intersection and not a second list of fields: a link_id here that the
# questionnaire does not ask for is refused by `catalogue/validate.py` on the
# commit, and scripts/check_directory.py asserts every one of these is a
# question on the form.
FILLS = ("name", "age", "sex", "phone", "village", "category", "directory_id")

# Which patient columns hold a cached profile, and so which ones a refresh
# from the directory may overwrite. Deliberately short: a column that is this
# facility's own observation about a person, rather than the directory's fact
# about them, must not be rewritten by a refresh.
CACHED = ("name", "age", "sex", "phone")

# A query that is only digits, spaces, hyphens or a leading plus is a phone
# number. Ten digits or more, so a token number or an age is not mistaken for
# one.
_MOBILE = re.compile(r"^[+\d][\d\s-]{8,}$")


def looks_like_mobile(query):
    """Is this query a mobile number rather than a name?

    It decides which endpoint is asked, and that matters for more than
    neatness. Eka's own specification says of the prefix search endpoint:
    "Global Search is exclusive to specific workspaces only." The by-mobile
    endpoint carries no such note, so a numeric query takes the path that is
    more likely to be enabled, which is also the path a clerk has: in practice
    they have the phone number.
    """
    return bool(_MOBILE.match(str(query or "").strip()))


class AbsentDirectory:
    """No directory configured, or no line to it. The designed path, not a stub.

    Every method raises DirectoryError with `reachable=False`, which is what
    the rest of this module is written against: a search answers from the
    local cache and reports that the directory was not asked, and a
    registration is an ordinary registration that has not been published yet.

    This is what `scripts/check_directory.py` runs the whole flow against, so
    "the clinic works with no directory" is checked on every run rather than
    asserted in a comment. It is also what `api/main.py` falls back to when no
    credential is configured, so a developer with no Eka account gets the
    degraded path rather than a traceback.

    It lives in the kernel and not in a connector because it is not a vendor:
    it is the kernel's own answer to having no vendor, in the same class as the
    dict backed fake the state tests run on.
    """

    reason = "no patient directory is configured or reachable"

    def _no(self):
        raise DirectoryError(self.reason, reachable=False)

    def search(self, prefix, *, limit=10):
        self._no()

    def by_mobile(self, mobile):
        self._no()

    def fetch(self, directory_id):
        self._no()

    def publish(self, patient):
        self._no()


@dataclass(frozen=True)
class Suggestion:
    """One directory profile, as values for the register form.

    Deliberately NOT `kernel.contracts.Draft`, although it carries the same
    three things. A `Draft` names the instrument declaration that produced it,
    and there is no instrument for a directory lookup: `vocab.INSTRUMENT_KINDS`
    is closed at five, a bundle cannot invent a sixth without renderer code,
    and `scripts/check_instruments.py` refuses a kind no atom declares and no
    pill draws. Declaring a sixth kind to borrow a dataclass would be a
    promise no screen keeps.

    What it does share with a Draft is the rule: values in editable fields,
    each shown with where it came from, committed by a tap.
    """
    directory_id: str
    values: dict
    evidence: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Resolution:
    """The answer to "who is this", from both sides.

    `local` are rows this facility already holds, which is the offline answer
    and always present. `suggestions` are directory profiles not already
    cached locally, which is the online answer and may be empty.

    `reachable` is False only when the directory could not be ASKED. A
    directory that answered and refused is reachable and `reason` says what it
    said. A clerk needs those apart: one means "nobody matched", the other
    means "I could not look", and a clerk who cannot tell them apart
    registers a duplicate.
    """
    query: str
    local: list
    suggestions: list
    reachable: bool = True
    reason: str = ""

    @property
    def offline(self):
        return not self.reachable


def _row_matches(row, query):
    """Does a cached row match this query? Name prefix, or phone substring.

    Name is a prefix match because that is what the directory does and two
    search boxes that behave differently is one search box too many. Phone is
    a substring match on the digits, because a clerk types the last few.
    """
    want = str(query or "").strip().lower()
    if not want:
        return False
    if str(row.get("name") or "").strip().lower().startswith(want):
        return True
    digits = re.sub(r"\D", "", want)
    phone = re.sub(r"\D", "", str(row.get("phone") or ""))
    return bool(digits) and len(digits) >= 4 and digits in phone


def cached(store, query, *, limit=10):
    """Rows this facility already holds that match, newest first.

    A scan, and honest about it: every patient row this store has ever cached
    is read and filtered here, because the query grammar in
    `kernel/contracts.py` has equality, presence, `gte` and `lt` and no prefix
    condition. Right for a health centre's own register, which is thousands of
    rows at the outside, and wrong for a district. The fix when it matters is a
    `prefix` condition in the grammar, in one place, and not a cache in front
    of this.
    """
    rows = store.select("patient", thread=None, where={}, fields=(), limit=5000)
    hits = [dict(r) for r in rows if _row_matches(r, query)]
    hits.sort(key=lambda r: str(r.get("created_date") or ""), reverse=True)
    return hits[:limit]


def _suggestion(profile):
    values, evidence = {}, {}
    for link_id, value in (("name", profile.name), ("sex", profile.sex),
                           ("age", profile.age), ("phone", profile.phone)):
        if value not in (None, ""):
            values[link_id] = value
            # Where it came from, which is the readback rule voice already has.
            evidence[link_id] = "the patient directory%s" % (
                ", matched on %s" % profile.matched_on if profile.matched_on else "")
    for ours, theirs in (("village", "phc_village"), ("category", "phc_category")):
        # Our own words, if the directory still has the ones we published.
        value = str((profile.extras or {}).get(theirs) or "").strip()
        if value:
            values[ours] = value
            evidence[ours] = "recorded here previously, kept in the directory"
    values["directory_id"] = profile.directory_id
    evidence["directory_id"] = "the directory's own identifier for this person"
    return Suggestion(directory_id=profile.directory_id, values=values,
                      evidence=evidence,
                      # Not a probability. A directory match is somebody with a
                      # similar name or the same phone, which is exactly the
                      # case the renderer must not let through unread, so it is
                      # capped under the renderer's SURE threshold like every
                      # other machine filled value.
                      confidence={k: 0.5 for k in values})


def resolve(store, directory, query, *, limit=10):
    """Who this query might be, from the local register and the directory.

    The local half always runs and never needs a socket. The directory half is
    attempted and is allowed to fail; a failure is reported rather than raised,
    because a clerk with a reachable patient in today's line must not be shown
    an error about a patient they were not looking for.

    A profile this facility already holds is returned as a local row and not
    as a suggestion, so a clerk sees one person once.
    """
    local = cached(store, query, limit=limit)
    known = {str(r.get("directory_id") or "") for r in local} - {""}
    suggestions, reachable, reason = [], True, ""
    try:
        if looks_like_mobile(query):
            found = directory.by_mobile(str(query).strip())
        else:
            found = directory.search(str(query).strip(), limit=limit)
        for profile in found or ():
            if profile.directory_id in known:
                continue
            known.add(profile.directory_id)
            suggestions.append(_suggestion(profile))
    except DirectoryError as broke:
        reachable, reason = bool(broke.reachable), str(broke)
    return Resolution(query=str(query or ""), local=local,
                      suggestions=suggestions[:limit],
                      reachable=reachable, reason=reason)


def pending(store, *, limit=200):
    """Patients registered here that the directory does not know about.

    Not a queue and not a table: a query over rows we already keep. A
    registration taken while the line was down is in this answer by virtue of
    having no directory id, so nothing had to be enqueued and nothing can fall
    out of sync with the record it is about.

    `"*"` is the query grammar's "present and not null", so this is its
    negation done the only way the grammar allows: ask for the ones that have
    one, and subtract. Adding a `not present` condition to the grammar would
    be the tidier fix and is a bigger change than this needs.
    """
    rows = [dict(r) for r in store.select("patient", thread=None, where={},
                                          fields=(), limit=5000)]
    unpublished = [r for r in rows if not str(r.get("directory_id") or "").strip()]
    unpublished.sort(key=lambda r: str(r.get("created_date") or ""))
    return unpublished[:limit]


@dataclass(frozen=True)
class Published:
    """What one sweep did. `failed` is not an error state: a row that could not
    be published stays in `pending()` and is tried again."""
    published: list = field(default_factory=list)      # (patient id, directory id)
    failed: list = field(default_factory=list)         # (patient id, why)
    reachable: bool = True

    @property
    def count(self):
        return len(self.published)


def publish_pending(store, directory, *, at, limit=50):
    """Hand unpublished patients to the directory and record what it returns.

    The only thing in this module that changes the store, and it changes two
    columns on a row that already exists: the identifier the directory minted
    and when we agreed. It writes no clinical row and raises no flag, which is
    what keeps `catalogue.guard` the only path to a clinical write.
    `scripts/check_directory.py` proves it by running this against a store
    whose `write` and `raise_flag` both raise.

    It stops at the first unreachable failure rather than hammering a dead
    line with the rest of the day's registrations.
    """
    done, failed, reachable = [], [], True
    for row in pending(store, limit=limit):
        try:
            directory_id = directory.publish(row)
        except DirectoryError as broke:
            failed.append((row.get("id"), str(broke)))
            if not broke.reachable:
                reachable = False
                break
            continue
        try:
            store.record_directory_id(row["id"], directory_id, at=at)
        except Exception as broke:
            # The dangerous one, and the reason this is not a bare call. The
            # directory has accepted the patient and we could not write down
            # the identifier it gave us, so the next sweep would publish the
            # same person again and put a duplicate in a national directory.
            # Reported as a failure on this row, which keeps it in pending()
            # and keeps the honest state visible, rather than raised: a raise
            # here would also throw away the record of every publish that
            # already succeeded in this sweep.
            failed.append((row.get("id"),
                           "the directory accepted them as %s and the receipt "
                           "could not be written: %s" % (directory_id, broke)))
            continue
        done.append((row.get("id"), directory_id))
    return Published(published=done, failed=failed, reachable=reachable)


def refresh(store, directory, patient_id, *, at):
    """Bring one cached profile back into line with the directory.

    Only the columns in `CACHED` are rewritten, so a facility's own words about
    a person are never overwritten by a refresh. Returns None when the row has
    no directory id (nothing to refresh against) or the directory has no such
    profile any more, which is a state to report rather than to act on: a
    profile that has gone leaves clinical records pointing at somebody, and
    deciding what that means is not this function's business.
    """
    rows = store.select("patient", thread=None, where={"id": patient_id},
                        fields=(), limit=1)
    if not rows:
        return None
    row = dict(rows[0])
    directory_id = str(row.get("directory_id") or "").strip()
    if not directory_id:
        return None
    profile = directory.fetch(directory_id)
    if profile is None:
        return None
    fresh = {}
    for column, value in (("name", profile.name), ("sex", profile.sex),
                          ("age", profile.age), ("phone", profile.phone)):
        if column in CACHED and value not in (None, ""):
            fresh[column] = value
    store.record_directory_id(patient_id, directory_id, at=at, profile=fresh)
    return dict(row, **fresh)


def demo():
    from kernel.contracts import DirectoryPatient

    class Fake:
        """Enough Store for this module: one select and one receipt."""

        def __init__(self, rows):
            self.rows = [dict(r) for r in rows]
            self.receipts = []

        def select(self, resource, *, thread, where, fields, limit):
            assert resource == "patient", resource
            if "id" in where:
                return [r for r in self.rows if r["id"] == where["id"]]
            return list(self.rows)

        def record_directory_id(self, patient_id, directory_id, *, at, profile=None):
            self.receipts.append((patient_id, directory_id, at))
            for row in self.rows:
                if row["id"] == patient_id:
                    row["directory_id"] = directory_id
                    row.update(profile or {})

        def write(self, *a, **kw):
            raise AssertionError("kernel/directory.py wrote a clinical row")

        def raise_flag(self, *a, **kw):
            raise AssertionError("kernel/directory.py raised a flag")

    store = Fake([
        {"id": "pat-1", "name": "Sunita Devi", "age": "34", "phone": "9876500000",
         "directory_id": "oid-1", "created_date": "2026-10-30T09:00:00+00:00"},
        {"id": "pat-2", "name": "Ramesh Kumar", "age": "51", "phone": "9876511111",
         "directory_id": "", "created_date": "2026-10-31T09:00:00+00:00"},
    ])

    assert looks_like_mobile("9876500000") and looks_like_mobile("+91 98765 00000")
    assert not looks_like_mobile("Sunita") and not looks_like_mobile("A01")
    assert not looks_like_mobile("34"), "an age is not a phone number"

    # ---- the whole thing with no directory at all
    gone = resolve(store, AbsentDirectory(), "Sunita")
    assert [r["id"] for r in gone.local] == ["pat-1"], gone.local
    assert gone.suggestions == [] and gone.offline, gone
    assert "configured or reachable" in gone.reason, gone.reason

    assert [r["id"] for r in cached(store, "9876511")] == ["pat-2"], "last digits"
    assert cached(store, "") == [], "an empty query matches nobody"
    assert cached(store, "999") == [], "too few digits to be a phone search"

    # ---- a reachable directory, and the local row winning
    class Live:
        def __init__(self, found):
            self.found = found
            self.asked = []

        def search(self, prefix, *, limit=10):
            self.asked.append(("search", prefix))
            return self.found

        def by_mobile(self, mobile):
            self.asked.append(("mobile", mobile))
            return self.found

        def fetch(self, directory_id):
            return self.found[0] if self.found else None

        def publish(self, patient):
            return "oid-new"

    already = DirectoryPatient(directory_id="oid-1", name="Sunita Devi",
                               matched_on="search")
    fresh_one = DirectoryPatient(directory_id="oid-9", name="Sunita Rao", sex="female",
                                 age=29, phone="9000000000", matched_on="search",
                                 extras={"phc_village": "Yadiki"})
    live = Live([already, fresh_one])
    got = resolve(store, live, "Sunita")
    assert live.asked == [("search", "Sunita")], live.asked
    assert [r["id"] for r in got.local] == ["pat-1"]
    assert [s.directory_id for s in got.suggestions] == ["oid-9"], \
        "a profile already cached locally is one person shown once"
    (one,) = got.suggestions
    assert one.values["name"] == "Sunita Rao" and one.values["age"] == 29
    assert one.values["village"] == "Yadiki", one.values
    assert one.values["directory_id"] == "oid-9"
    assert all(v <= 0.5 for v in one.confidence.values()), one.confidence
    assert "matched on search" in one.evidence["name"], one.evidence
    assert got.reachable and got.reason == ""

    assert resolve(store, Live([]), "9876500000").local[0]["id"] == "pat-1"
    assert Live([]).asked == [], "a fresh fake"
    numeric = Live([])
    resolve(store, numeric, "9876500000")
    assert numeric.asked == [("mobile", "9876500000")], numeric.asked

    # ---- publishing, and the row that stays pending
    assert [r["id"] for r in pending(store)] == ["pat-2"], pending(store)
    report = publish_pending(store, Live([]), at="2026-10-31T10:00:00+00:00")
    assert report.published == [("pat-2", "oid-new")], report
    assert report.count == 1 and not report.failed and report.reachable
    assert pending(store) == [], "a published row leaves the pending answer"
    assert store.receipts == [("pat-2", "oid-new", "2026-10-31T10:00:00+00:00")]

    store.rows[1]["directory_id"] = ""
    dead = publish_pending(store, AbsentDirectory(), at="now")
    assert dead.published == [] and not dead.reachable, dead
    assert [r["id"] for r in pending(store)] == ["pat-2"], \
        "a registration the directory never saw is still waiting, with nothing enqueued"

    # ---- a refresh rewrites the directory's facts and nothing else
    store.rows[0]["village"] = "Yadiki"
    moved = DirectoryPatient(directory_id="oid-1", name="Sunita Devi Rao",
                             sex="female", age=35, phone="9876500001")
    back = refresh(store, Live([moved]), "pat-1", at="now")
    assert back["name"] == "Sunita Devi Rao" and back["age"] == 35, back
    assert back["village"] == "Yadiki", "a refresh overwrote a facility's own word"
    assert refresh(store, Live([moved]), "pat-2", at="now") is None, \
        "a row with no directory id has nothing to refresh against"

    print("ok   kernel.directory")


if __name__ == "__main__":
    demo()
