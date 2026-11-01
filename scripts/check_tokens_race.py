"""The token race, proved by racing: real processes, one real file, no holes.

What this is for
----------------
kernel/tokens.py used to read the day's numbers and let the caller write the
next one. Two steps, no lock, no transaction, so two arrivals inside one
instant were handed the same number and two people in one waiting room
answered to "seven". That was written down in that file for months as the
owner's to schedule. This is the check that holds the fix.

Why a sequential test would be worthless here
---------------------------------------------
A test that issues numbers one after another passes against the broken code.
It passed against the broken code for the whole time the broken code shipped:
`python3 -m kernel.tokens` exercises the arithmetic, and the arithmetic was
never wrong. What was wrong was that two callers could both run the correct
arithmetic on the same stale read. Nothing that happens one call at a time can
see that, so nothing that happens one call at a time is evidence about it.

So this check does the only thing that is evidence: it makes the race happen.

How it races
------------
REAL PROCESSES, not threads, and a REAL FILE, not ":memory:". Both are
deliberate.

- Processes, because CPython holds a lock on its own bytecode and two threads
  doing mostly-SQLite work can interleave far less than two processes do. The
  window being hunted is microseconds wide and a thread test can miss it by
  luck and read as a pass. A separate interpreter per arrival has no such
  lock, and it is also what a clinic actually has: uvicorn workers, or the
  desk's process and the poster's.
- A file, because ":memory:" plus a shared cache is one SQLite instance
  reached through one cache, and the locking a file gets is the thing under
  test. A fix that worked only in memory would be a fix for nothing.

Simultaneity is not left to process startup, which is tens of milliseconds of
jitter and would quietly serialise every arrival. Every worker is given the
same wall-clock DEADLINE, opens its store, does its reads, and then spins
until that moment arrives before issuing anything. So the arrivals genuinely
overlap instead of queueing behind python's import machinery.

Each worker does exactly what `POST /threads` does and in that order, which is
`store.open_thread(token=tokens.issue(store, ...))`. Not a bare call to the
new method: the thing being proved is the production path, and the production
path is a read, an arithmetic step and a write.

What it asserts
---------------
NO DUPLICATE and NO HOLE, against the rows in the database rather than against
what the workers reported, because the waiting room is the rows. A set of
arrivals that produced 1..n exactly once each is the only passing answer.

A hole is as much a defect as a duplicate and is asserted for its own sake: a
sequence that answers a collision by skipping a number is a number called out
to a room where nobody has it, and a desk that trusts the display then waits
for a person who does not exist.

Proved to fail
--------------
Run against the two-step code this replaced, this check fails on the
duplicate assertion. That was done rather than assumed; see the mutation log
at the foot of this file.

Run: python3 scripts/check_tokens_race.py
"""
from __future__ import annotations

import collections
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

# The shape of the race. Eight arrivals at once, six times each, is 48
# numbers out of one sequence through eight interpreters.
#
# Chosen against the failure rather than against a clock: with the two-step
# code every one of the three rounds below produced duplicates on every run
# it was tried on, because eight processes released at one deadline read the
# same row set. Fewer workers, or no deadline, is where a race test starts
# passing for the wrong reason.
WORKERS = 8
PER_WORKER = 6
ROUNDS = 3

# How long the parent gives every worker to boot, import, open the file and
# reach the start line. Generous: a slow machine that misses the deadline does
# not make this check flaky, it makes it less of a race, so the worker says so
# and the parent refuses to call a non-race a pass.
LEAD_SECONDS = 2.5

WORKFLOW = "phc.wf.outpatient"


def worker(path, deadline, count):
    """One arrival process: open the real file, wait for the gun, then issue.

    Imports happen before the deadline on purpose. What must overlap is the
    issuing, and an import inside the measured window is just jitter.
    """
    from adapters.local.store import SqliteStore
    from kernel import tokens

    store = SqliteStore(path)
    # Touch the read path once before the deadline so that the first call's
    # page cache miss is not what separates the workers.
    store.threads(workflow=WORKFLOW, scope="today")

    late = time.time() > deadline
    while time.time() < deadline:
        pass

    out = []
    for _ in range(count):
        number = tokens.issue(store, workflow=WORKFLOW, scope="today")
        thread = store.open_thread(token=number, actor="race")
        out.append({"token": number, "thread": thread})
    print(json.dumps({"late": late, "issued": out}))
    return 0


def run_round(path):
    """Release WORKERS interpreters at one deadline and collect what they got.

    THE PARENT CREATES THE FILE FIRST, and that is not tidiness. Eight
    processes constructing a store on a database that does not exist yet race
    on `PRAGMA journal_mode=WAL`, which needs an exclusive lock and is refused
    outright rather than waiting out the busy timeout, so roughly one run in
    four died with "database is locked" before any number was issued. That is
    a real property of the adapter and it is reported rather than hidden, but
    it is NOT the race under test: it happens at open, not at issue. Creating
    the schema once up front means every worker opens a database that is
    already in WAL, where the pragma is a no-op, and what overlaps is the
    issuing. See the note at the foot of this file.
    """
    from adapters.local.store import SqliteStore

    SqliteStore(path)

    deadline = time.time() + LEAD_SECONDS
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    procs = [subprocess.Popen(
        [sys.executable, str(pathlib.Path(__file__).resolve()),
         "--worker", path, "%.6f" % deadline, str(PER_WORKER)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for _ in range(WORKERS)]

    issued, late = [], 0
    for proc in procs:
        out, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, "a worker died: %s" % (err or out)
        answer = json.loads(out.strip().splitlines()[-1])
        late += 1 if answer["late"] else 0
        issued += answer["issued"]
    return issued, late


def main():
    from kernel import tokens

    checks = 0

    def ok(what):
        nonlocal checks
        checks += 1
        print("ok   %s" % what)

    work = pathlib.Path(tempfile.mkdtemp(prefix="token-race-"))
    try:
        for round_number in range(1, ROUNDS + 1):
            # A fresh file per round, so each round is a facility's own first
            # morning and the expected answer is exactly 1..n. Carrying the
            # file over would make the expected set depend on the previous
            # round and hide a duplicate inside a bigger range.
            path = str(work / ("round-%d.sqlite3" % round_number))
            issued, late = run_round(path)

            assert late == 0, (
                "%d of %d workers reached the start line after the deadline, so "
                "this round did not race and proves nothing. Raise LEAD_SECONDS."
                % (late, WORKERS))

            want = WORKERS * PER_WORKER
            assert len(issued) == want, \
                "round %d: %d arrivals, expected %d" % (round_number, len(issued), want)

            # The rows, not the reports. What the waiting room has is what the
            # database has, and a worker that returned a number it failed to
            # store would otherwise read as a pass.
            from adapters.local.store import SqliteStore
            store = SqliteStore(path)  # already created above; opens WAL as-is
            rows = store.db.execute(
                "SELECT token FROM encounter WHERE created_by = 'race'").fetchall()
            stored = [r["token"] for r in rows]

            assert len(stored) == want, \
                "round %d: %d rows for %d arrivals" % (round_number, len(stored), want)

            numbers = sorted(int(t) for t in stored)
            repeated = sorted(n for n, c in collections.Counter(numbers).items() if c > 1)
            assert not repeated, (
                "round %d: %d arrivals were handed a number somebody else already "
                "had: %s. This is the race, and it is what two patients holding "
                "the same slip looks like." % (round_number, len(repeated), repeated))

            assert numbers == list(range(1, want + 1)), (
                "round %d: the day is not 1..%d. Missing %s, unexpected %s. A hole "
                "is a number called out to a room where nobody has it."
                % (round_number, want,
                   sorted(set(range(1, want + 1)) - set(numbers)),
                   sorted(set(numbers) - set(range(1, want + 1)))))

            ok("round %d: %d arrivals from %d parallel processes against one file "
               "got %d..%d exactly once each, no duplicate and no hole"
               % (round_number, want, WORKERS, numbers[0], numbers[-1]))

        ok("the day sequence issues a number once, ever, under %d rounds of %d "
           "simultaneous arrivals, and the rows prove it rather than the callers"
           % (ROUNDS, WORKERS * PER_WORKER))

        # ------------------------------------------------------------------
        # The floor, which the race above cannot see.
        # ------------------------------------------------------------------
        # A counter alone is not enough and this is the case that proves it.
        # Rows can gain numbers without the counter being told: a seed rolled
        # forward into today (SqliteStore.roll_seed_forward) is exactly that,
        # and so is any row written straight to the table. If issuing read
        # only the counter, the next arrival would be handed a number a row
        # in the room already wears.
        #
        # Sequential on purpose. It is not a race, it is the arithmetic the
        # race test cannot reach, and it is here rather than in a separate
        # file because it is the other half of one promise.
        from adapters.local.store import SqliteStore

        path = str(work / "floor.sqlite3")
        store = SqliteStore(path)

        first = store.issue_token(workflow=WORKFLOW, scope="today", floor=1)
        assert first == 1, first

        # A number arriving from outside the sequence, as a rolled-forward
        # seed's does. The counter still says 1.
        store.open_thread(token="50", actor="seed")
        floor = tokens.after([ref.subject.get("token") for ref
                              in store.threads(workflow=WORKFLOW, scope="today")])
        assert floor == 51, floor

        nxt = store.issue_token(workflow=WORKFLOW, scope="today", floor=floor)
        assert nxt >= floor, (
            "the sequence handed out %d when a row in the room already wore 50. "
            "The counter was followed and the floor was ignored, which is how a "
            "seeded demo day reissues a number somebody is answering to." % nxt)
        assert nxt == 51, nxt

        # And it does not go backwards afterwards either.
        assert store.issue_token(workflow=WORKFLOW, scope="today", floor=1) == 52

        ok("a number that reached the rows from outside the sequence raises the "
           "floor, so the next arrival gets 51 rather than 2, and the counter "
           "never hands back a number a row already wears")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\nok   token race: %d checks" % checks)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2], float(sys.argv[3]), int(sys.argv[4])))
    sys.exit(main())


# ==========================================================================
# Mutations this file is built to fail under. Each one was applied, the old
# text was asserted GONE and the file asserted CHANGED before anything was
# run, this check was run, the real failure was recorded below, and the file
# was restored and compared byte for byte against its pre-mutation copy.
# 4 applied, 4 caught. The recorded sentences are the ones that actually
# printed, not paraphrases.
#
# 1. kernel/tokens.py: restore the two-step issue() this fix replaced, so the
#    number comes from arithmetic over a read instead of from
#    Store.issue_token.
#      -       return str(store.issue_token(workflow=workflow, scope=scope,
#                                           floor=after(seen)))
#      +       return str(after(seen))
#    -> FAILS in round 1 on the duplicate assertion, on every one of the 4
#       runs it was tried on. Recorded: "round 1: 13 arrivals were handed a
#       number somebody else already had: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
#       13, 14]". An earlier run of the same mutation reported 11 duplicates,
#       so the count varies and the failure does not.
#
#       THIS IS THE MUTATION THAT MATTERS, because it is not an invented
#       defect: it is the code that shipped, and the duplicate numbers above
#       are the two-patients-one-slip failure happening.
#
# 2. adapters/local/store.py issue_token: replace the atomic upsert with the
#    read-then-write it exists to avoid (SELECT last, then INSERT or UPDATE).
#    -> FAILS in round 1. Recorded: "a worker died: ... sqlite3.IntegrityError:
#       UNIQUE constraint failed: day_sequence.workflow, day_sequence.scope,
#       day_sequence.day". Two processes both read no row and both inserted.
#       The failure is a crash rather than a duplicate, which is the UNIQUE key
#       refusing to let the race produce one. Noted exactly that way rather
#       than as "fails on duplicates", because it does not.
#
# 3. adapters/local/store.py: drop the PRIMARY KEY from SEQUENCE_DDL, leaving
#    the upsert no conflict target.
#    -> FAILS at store construction. Recorded: "sqlite3.OperationalError: ON
#       CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint".
#       The schema is the enforcement, which is the reason it is in the schema
#       and not in a caller.
#
# 4. adapters/local/store.py issue_token: ignore the floor, using `last + 1`
#    alone instead of MAX(last + 1, excluded.last).
#    -> FAILS on the floor assertion. Recorded: "the sequence handed out 2
#       when a row in the room already wore 50."
#
#       WORTH READING, because this one was missed first time round. The
#       concurrent rounds did NOT catch it and neither did
#       scripts/check_front_desk.py: every round starts on a fresh file where
#       the floor and the counter agree, so ignoring the floor changes
#       nothing there. The floor section above was written because this
#       mutation went uncaught, not before it. A mutation that does not fail
#       means the check is missing, and the honest response is to add the
#       check rather than to record the mutation as covered.
#
# ONE THING THIS CHECK FOUND AND DOES NOT FIX. Eight processes constructing a
# store on a database file that does not exist yet race on `PRAGMA
# journal_mode=WAL`, which SQLite refuses outright instead of waiting out the
# busy timeout, and roughly one run in four died with "database is locked"
# before a single number was issued. run_round() creates the schema in the
# parent first, so what overlaps is the issuing rather than the opening. The
# underlying behaviour is the adapter's and is unchanged: a deployment that
# starts several workers against a brand new file can still meet it. It is
# reported here and in the report accompanying this work rather than patched,
# because changing how the adapter opens a file is not what was scheduled.
# ==========================================================================
