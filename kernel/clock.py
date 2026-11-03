"""`now` in the query grammar, and nothing else.

WHY THIS EXISTS. Every flag in this product is a count with no date in it. A
state rule is `exists`, `gte` or `all_of` over `{resource, where}`, and until
this module the only time-relative value the grammar had anywhere was
`window.start`, which works in a metric and nowhere else. So the kernel could
answer "has she had an antenatal visit" and could not answer "is one due",
because due is a comparison against today and there was no today.

That is not a small gap and it was found once before. From
`docs/superpowers/specs/2026-09-15-glass-heidi-build-plan.md`, on why the
follow-up cohort was abandoned:

    The cohort question is date-relative ("booked to come back and has not"),
    which neither the state-rule grammar nor an equality filter can ask. Do
    not ship a row that only grows.

`followup.booked` is still in the shipped bundle, still derived from a
resource no operation writes, and `appointment.book` is still a capability
four roles hold and no operation declares. The reasoning is in
`docs/superpowers/specs/2026-11-04-maternal-and-child-health-design.md` §1.

WHAT IT IS. One symbolic value, `now`, usable as a condition value anywhere a
literal is:

    overdue:
      exists: {resource: task, where: {status: open, closes: {lt: now}}}

WHERE IT RESOLVES, and this is the design decision. In the kernel, BEFORE the
query reaches the Store, so an adapter never learns what `now` means. The
adapter's job is to compare a column against a value; which values are
symbolic is the grammar's business, and the grammar is the kernel's. A second
adapter therefore inherits this for free, which is the whole reason the
boundary is drawn where it is.

It follows `kernel/views.window_start`, which has resolved a symbolic value
this way since metrics existed. The two are deliberately separate functions
rather than one table of symbols: `window.start` is legal only in a metric
and means "the start of the bucket this metric is being asked about", and
`now` is legal everywhere and means the instant the question was asked.
Folding them together would make the narrower one look general.

NO OFFSETS. `now-7d` is not supported. Nothing needs it: a scheduled thing
stores its own window as two dates on the row, so the comparison is always
against a bare instant, and a metric's "since" is `window.start` already. An
offset syntax would be a second date arithmetic to lint, test and port, built
for no caller.

THE INSTANT COMES FROM THE CALLER, OR FROM THIS CLOCK. `at=None` falls back
to the wall clock, which is right for a script and wrong for the gate:
`scripts/check_go_parity.py` asks two kernels the same question over two
sockets and diffs the answers, and two wall clocks a few milliseconds apart
disagree about any row sitting exactly on a boundary. A check that fails one
run in fifty is a check people learn to rerun.

So when a shipped declaration first uses `now`, the instant has to be
resolved once per request at the HTTP edge and threaded down, in BOTH
engines. That is not done here, because no declaration uses `now` yet and
threading a clock through an API for no caller is the speculative half of
this change. The parameter exists all the way down so that step is a change
of callers and not a change of shape. This paragraph is the warning, kept at
the point of danger rather than in a document nobody opens.
"""
from __future__ import annotations

from datetime import datetime, timezone

#: The one symbolic value this module owns.
NOW = "now"


def instant(at=None) -> str:
    """The instant a question is being asked, as the store spells a date.

    Same format as every `created_date` the adapter writes, because the
    comparison is a string comparison: ISO 8601, UTC, seconds, trailing Z.
    `adapters/local/store.now()` writes this shape and ISO dates in this
    shape sort correctly as text, which is what makes `lt` work at all.
    """
    at = at or datetime.now(timezone.utc)
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def bind(where, at=None):
    """A query's `where` with `now` replaced by the instant.

    Returns a new dict; the declaration is compiled data shared between
    threads and is never mutated. A `where` with no `now` in it comes back
    equal to what went in, so this is safe to call on every query and the
    caller needs no test for whether the grammar was used.
    """
    if not where:
        return {}
    resolved = None                      # computed once, and only if needed
    out = {}
    for field, cond in where.items():
        if cond == NOW:
            resolved = instant(at) if resolved is None else resolved
            out[field] = resolved
        elif isinstance(cond, dict):
            swapped = {}
            for op, value in cond.items():
                if value == NOW:
                    resolved = instant(at) if resolved is None else resolved
                    swapped[op] = resolved
                else:
                    swapped[op] = value
            out[field] = swapped
        else:
            out[field] = cond
    return out
