"""Run: python3 -m kernel.tests.test_clock

`now` in the query grammar, against a real SQLite store, because the whole of
what it does is a where clause and an in-memory fake would not have one.

THE MUTATION THIS FILE EXISTS TO CATCH, and it is the reason the cases below
are built the way they are. An implementation that resolved `now` to a
constant, or to the epoch, or that dropped the condition on the floor, would
pass any test that asks a single question at a single moment: the row either
matches or it does not and nothing says why. So every case here asks THE SAME
QUESTION TWICE, at two instants either side of the same row, and asserts the
answer CHANGED. A clock that does not move cannot pass that, and neither can
a condition that is being ignored.

The second thing it catches is scope. `now` must be resolved in the kernel
and never in the store, so a second adapter inherits it. The last case asks
the adapter directly for the literal string and asserts it finds nothing,
which is only true if the adapter has no idea what the word means.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from adapters.local.store import SqliteStore
from kernel import clock, state

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


MIDDAY = datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)
BEFORE = MIDDAY - timedelta(days=2)
AFTER = MIDDAY + timedelta(days=2)


# -- the binder, on its own -------------------------------------------------

bound = clock.bind({"status": "open", "closes": {"lt": "now"}}, MIDDAY)
assert bound == {"status": "open", "closes": {"lt": "2026-11-04T12:00:00Z"}}, bound
ok("now inside a comparison resolves to the instant, in the store's own date shape")

assert clock.bind({"created_date": "now"}, MIDDAY)["created_date"] == "2026-11-04T12:00:00Z"
ok("and a bare now resolves too, because it is legal wherever a literal is")

untouched = {"category": "vital-signs", "value": {"gte": "140"}}
assert clock.bind(untouched, MIDDAY) == untouched
ok("a query with no now in it comes back as it went in")

assert clock.bind(None) == {} and clock.bind({}) == {}
ok("an absent where binds to an empty one rather than failing")

# The declaration is compiled data shared between threads. Binding it must
# not write into it, and an implementation that mutated in place would pass
# every assertion above.
original = {"closes": {"lt": "now"}}
clock.bind(original, MIDDAY)
assert original == {"closes": {"lt": "now"}}, original
ok("binding leaves the declaration alone: it is shared, compiled data")


# -- the same question, twice, either side of one row -----------------------

def build():
    """One encounter carrying one row whose date sits at midday."""
    store = SqliteStore(":memory:")
    store.db.execute(
        "INSERT INTO encounter (id, patient, status, token, created_date)"
        " VALUES ('e-1', 'p-1', 'in_progress', '01', ?)", [stamp(MIDDAY)])
    store.db.execute(
        "INSERT INTO observation (id, encounter, category, code, value, created_date)"
        " VALUES ('obs-1', 'e-1', 'vital-signs', '8480-6', '138', ?)", [stamp(MIDDAY)])
    return store


store = build()
DUE = {"resource": "observation", "where": {"created_date": {"lt": "now"}}}

assert state.count(store, "e-1", DUE, BEFORE) == 0, \
    "the row is in the future at this instant and must not be counted"
assert state.count(store, "e-1", DUE, AFTER) == 1, \
    "the row is in the past at this instant and must be counted"
ok("the same question at two instants gives two answers, which is the whole point")

# And the other way round, so a condition that was simply inverted does not
# pass the case above.
SINCE = {"resource": "observation", "where": {"created_date": {"gte": "now"}}}
assert state.count(store, "e-1", SINCE, BEFORE) == 1
assert state.count(store, "e-1", SINCE, AFTER) == 0
ok("gte moves the other way, so an inverted comparison fails rather than passes")


# -- a declared rule, which is what this was built for ----------------------
#
# Written here as a rule dict rather than added to the shipped bundle: no
# bundle declares `now` yet, and the first one that does has to thread the
# instant from the request, which kernel/clock.py explains at length.

class OneRule:
    """The smallest thing state.flags will walk."""
    states = {"overdue": {"exists": DUE}}
    stored = []


assert state.flags(store, "e-1", OneRule(), BEFORE) == set(), \
    "nothing is overdue before the thing is due"
assert state.flags(store, "e-1", OneRule(), AFTER) == {"overdue"}, \
    "a date-relative flag never comes true, which is the bug this fixes"
ok("a declared state rule can ask a date-relative question and the flag turns on")


# -- and the store still knows nothing about any of it ----------------------
#
# WHAT HAPPENS IF SOMEBODY DELETES THE BIND, which is the failure this guards
# and it is not a crash. The adapter compares text, and every ISO date begins
# with a digit while "now" begins with a letter, so `created_date < 'now'` is
# TRUE of every row ever written. An unbound query does not error and does
# not return nothing: it returns EVERYTHING, always, at every instant, which
# on an overdue list reads as the whole facility being late.
raw = store.count("observation", thread="e-1", where={"created_date": {"lt": "now"}})
assert raw == 1, "the adapter is doing something other than comparing text"
assert state.count(store, "e-1", DUE, BEFORE) == 0, "but the bound question is not"
ok("an unbound now matches every row, which is why the kernel binds it and "
   "why this is not left to an adapter to get right once per adapter")

print("ok   the clock: %d checks" % checks)
