# The calendar: a facility's day and a woman's year

4 November 2026. Design for owner approval. Nothing is built.

## 1. What this is for

Two screens, from one piece of machinery.

**A facility's day.** Somebody at the centre opens it and sees what is owed
today, across everybody. The late work is at the top. Every line says whose
job it is. The medical officer, the front line worker and the nurse all open
the same screen; it opens filtered to the viewer's own work, and one click
widens it to everybody's.

**One woman's year.** Her pregnancy and the weeks after, on one screen,
twelve small months. Green happened, red was missed and stayed missed, blue
is owed now, grey is still ahead. It exists for a thing a list of rows cannot
show: a four month gap in the middle of a pregnancy, visible at a glance.

### Why now

The maternal arc landed this week. A woman's contacts are derived and correct,
and her own record already shows them. Nothing shows the centre's work in one
place, so an overdue home visit is only found by opening the woman it belongs
to. That is the gap.

### Success

The person who runs the centre opens one screen in the morning and knows what
is late. Today that takes opening patients one at a time.

### Non-goals

- No reminders, no messages, no chasing. The calendar shows; it does not send.
  That decision is still open and belongs to its own piece of work.
- No booking. Nothing on this screen creates an appointment or moves a date.
- No district tier. One facility.

### Anti-goals — the ways this fails even if it works

- **A stored calendar.** If any contact is written into a table so that a
  month loads quickly, this feature has broken the product's safety property
  and must not ship. See section 4.
- **A month grid as the front door.** Day first. A month that is the landing
  screen buys a shape nobody acts on and costs a sweep nobody asked for.
- **A screen that takes ten seconds.** A centre's day must open as fast as the
  queue does.

## 2. What the owner settled

In conversation, 4 November 2026:

1. A month or year scale earns its place **for one patient**, to see her
   progress. The day view is what gets used most.
2. The day view follows Granola's shape: a large date numeral, a coloured bar
   beside each line, one sentence per row, dark and quiet.
3. The medical officer, the front line worker and the nurse can all open it.
4. **Everyone's work shows, with the viewer's own first.** Not a private list.
5. **Placement:** the Granola-style card lives on the home page. The calendar
   itself is a sidebar item.
6. **The month's per-day counts are pregnancy follow-ups only**, not every
   kind of contact at the centre.
7. **A row names the role, not the worker.** "ASHA", not "ASHA Kamla".
   Nothing in the system says which worker covers which household, and
   building that is a separate piece of work.
8. **The day screen is maternal only**: antenatal checks and the home visits
   after birth. Open referrals are not on it, so the day and the month count
   the same thing.

## 3. Constraints this inherits

These are the product's, not this feature's, and none of them is negotiable
here.

- **Declared, not coded.** The renderer may never name a station, a flag, a
  capability, an operation or a view's columns. A calendar is therefore a
  declaration in the bundle, not a screen somebody wrote.
- **Derived, never stored.** `kernel/schedule.py` computes a contact from the
  schedule declaration, the episode's anchor date and the audit, every time
  somebody asks. Nothing is generated when a pregnancy opens and nothing is
  cancelled when it ends. That is what stops a woman who lost a baby being
  chased for a missed visit.
- **Two engines.** Every kernel route is served by Python and by Go, and
  `scripts/check_go_parity.py` diffs the two live. A new route is two routes.
- **The gate.** `sh scripts/check.sh` must exit 0.
- **A view is gated on a capability.** Who may open the calendar is a line in
  a declaration, not a check in a component.

## 4. Approaches

### A. The browser assembles the day — rejected

The web app already fetches one woman's contacts for her record. It could
fetch them for every open episode and assemble the day itself.

Nothing new in the kernel. Rejected anyway: the browser would then hold the
rules about what a contact is, what counts as late, and what a day contains.
That is exactly what the declared-not-coded kernel exists to prevent, and no
lint would catch it, because the kernel would never see the screen.

### B. A derived index table — rejected

Write each contact into a lookup table, rebuilt whenever something is
committed. A month loads in one query.

Rejected on the product's central invariant. A written contact is a contact
somebody has to remember to delete. `kernel/schedule.py` names this failure in
its own header and says plainly what the right fix is instead: "a store method
that answers for many threads at once, not a cache."

### C. A fifth kind of view — chosen

`calendar` joins `queue`, `summary`, `dashboard` and `tasklist` in
`kernel.contracts.VIEW_KINDS`. The bundle declares one. A kernel route answers
"what is owed between these two dates", by deriving it, using a store method
that reads many episodes at once rather than one at a time.

This is the only approach that keeps the clinical rules in declarations and
the contacts underived-until-asked. The cost is a sweep on every load, which
section 6 bounds.

**The owner picked C's cost shape:** the month's dots count pregnancy
follow-ups and nothing else.

## 5. The parts the owner decided

### The day screen

Rows are grouped: **late**, then **owed today**, then **done**. Late first is
not cosmetic — it is the one group where a row means somebody must act now.

Each row carries: the date it was owed (large numeral), a coloured bar, the
woman's name and age, what the contact is in plain words, and the role that
owns it.

**What a day contains — builder's call.** A contact is on a day when that
day falls inside its window, so one contact appears on each day of its window
until something closes it. A contact whose window shut with nothing against it
stays in the late group every day afterwards, until it is done or its episode
ends. The alternative, showing a contact only on its single due date, would
hide a woman whose window is open but whose due date was last Tuesday, which
is the opposite of what this screen is for.

Colour: red late, blue owed, green done, grey still ahead, amber for a birth.

Above the rows, a chip for each role plus "everyone". **The viewer's own role
is selected when the screen opens.**

**Builder's call:** the route returns the whole day and the browser narrows it
by role. The route takes no role parameter. Today the caller's role arrives in
a header rather than from a signed-in identity, so a server-side filter would
be claiming a guarantee this product does not yet make. The chips are then
free, and the honest statement is that this hides work rather than protecting
it.

Above that, a "coming up" card: the next few days, each with a count and a one
line summary.

### The patient screen

Twelve months, small. Each day is a cell. The cell takes its colour from the
contact's state, which `kernel/schedule.py` already answers with exactly four
values: `upcoming`, `due`, `done`, `missed`. A birth gets a ring, not a fill,
because it is an event rather than a contact.

Under each month, one short line naming what happened in it.

A scale control offers day, month and year. Year is the default, because the
reason to open this screen at all is the shape of the whole arc.

**Builder's call:** "year" means her arc, not a calendar year. The window runs
from the episode's anchor date to the last day any contact on it could fall,
which is about fifteen months for a pregnancy carried through its postnatal
weeks. A calendar year would cut an arc in half whenever a pregnancy crosses
New Year, which is most of them.

### Where they live

- The "coming up" card goes on the **home page**.
- The calendar is a **sidebar item** of its own.

### What the month's dots count

Pregnancy follow-ups. **Builder's call, open to the owner's correction:** this
covers both halves of the maternal arc, the antenatal checks and the home
visits after birth, because the home visits are the larger share and a dot
that silently omits them would be misleading rather than merely partial.

## 6. What is left to the builder

### The sweep, and its cost

`schedule.contacts()` takes one episode and costs one audit read per visit in
it. A facility day needs every open episode. Done the obvious way this is N+1
per episode, which `kernel/schedule.py` warns about by name.

The fix the module itself prescribes is a store method that answers for many
threads at once. The builder adds it. It does not cache and it does not store;
it reads in bulk what the single-episode path reads one at a time.

**Finding the open episodes at all — builder's call, and the riskiest part.**
There is no episode table. Episodes are derived from a subject's own visits,
and the store's existing thread read is scoped to a period. A woman with an
open pregnancy and no recent visit therefore has no thread in today's scope,
and she is precisely the woman this screen exists to surface. The builder
sweeps every thread of the workflow, not today's, and derives from there. If
that sweep proves too slow at a real centre's volume, the answer is a better
bulk read, never a stored contact. If a store method that enumerates episodes
turns out to be the only workable shape, that is a twelfth method on a
deliberately small protocol, implemented in Python, in Go and in the CARE
adapter, and it should come back to the owner as its own decision rather than
being added quietly.

Bound the work: the day route derives one day. The month route derives per-day
counts for pregnancy and postnatal episodes only, which is what the owner
chose, and is a strictly smaller sweep than "everything".

### The declaration

A `calendar` view declaration needs at least: a capability gate, a workflow,
and the episode types whose contacts it draws. The lint in
`kernel/declarations.py:_lint_view` gains a branch for the new kind, in the
same shape as the `tasklist` branch: anything a calendar names that does not
exist must fail the gate, not render empty.

Whether a calendar also takes `columns`, `labels` and `badges` like the other
kinds is the builder's call, guided by what the other four already do.

**The capability gate — builder's call.** The calendar uses the same gate as
the existing task list, because the three roles who open it already hold that
one and adding a capability would mean touching every role preset for no
change in who gets in. Check 5 below is then written against a role that
lacks it.

### Go parity

Both new routes exist in Python and in Go before the gate passes.

### Checks that must exist

Written as checks, not comments, in the style of `scripts/check_postnatal.py`:

1. A pregnancy that ended contributes nothing to any day, past or future.
2. A miscarriage contributes no home visits to any day.
3. A contact appears on exactly the days its window covers, and on no other.
4. The day's total equals the sum of its groups.
5. A viewer without the calendar's capability is refused the route, not shown
   an empty screen.
6. The month's counts and the day's list agree for the same date.
7. A woman with an open pregnancy and no visit for months still appears on
   today, because that is the whole reason this screen exists.

### Not specified here

Visual detail beyond the shape above, the exact wording of row summaries, and
the sidebar's icon. The mockups at
`/private/tmp/claude-502/-Users-samdennis-code-killer-doc/a9e1916d-e227-4f18-b64f-a89fdaae3cd2/scratchpad/calendar-mockups.html`
are the agreed shape, not the agreed pixels.

## 7. Still open, and not blocking this

- Whether a day may be opened for a date in the past far enough back that the
  episode has since closed.
- The seven postnatal window widths, which the owner has not yet signed off.
  The calendar renders whatever they become.
- Chasing and sending, which this feature deliberately does not touch.
