# The calendar journey: cards, and a calendar that looks like one

4 November 2026. Design for owner approval. Builds on
`2026-11-04-calendar-design.md`, which is built and merged.

## 1. What this changes and why

The calendar works. It does not yet look like a calendar, and the home page
shows a table where it should show the next few women by name.

Three changes:

**The home page** stops being a list. It becomes a short stack of cards, one
per upcoming contact, the nearest in time largest and the ones behind it
progressively smaller, with arrows to reach later ones. Each card carries the
woman and where she is in her pregnancy, not just a count.

**The calendar page** gains what a calendar has: today's cards down the side,
and beside them a grid that switches between week, month and year, in the
shape of Google Calendar.

**One woman's view** becomes the same grid, filtered to her. The month strips
built on her record are replaced by it.

### Why now

A count tells a nurse how much is coming. A card tells her who. The screen she
opens first should name the woman she is about to see.

### Success

Somebody opening the home page can read the next visit's name, her stage of
pregnancy and who is going, without clicking anything.

### Non-goals

- No booking, still. Nothing here creates or moves an appointment.
- No reminders or messages.
- No new clinical data. Every word on a card already exists in the answer.

### Anti-goals

- **A calendar that is mostly empty chrome.** The grid must carry the work, not
  decorate it.
- **A home page that costs a dozen requests to draw.** See section 6.
- **Storing anything.** Unchanged and non-negotiable: a contact is derived
  every time it is asked for, so a woman whose pregnancy ended owes nothing and
  there is no row anybody must remember to cancel.

## 2. What the owner settled

In conversation, 4 November 2026:

1. The home page shows individual cards, calendar-specific, nearest largest and
   sequentially smaller, with a clicker to reach the farther ones.
2. A card carries the patient's information and her pregnancy details.
3. The calendar page has a sidebar of today's cards and, beside it, a view the
   user can switch between week, month and year.
4. Those three views look like Google Calendar's.
5. Clicking a card opens that patient's calendar: the grid filters to her
   events.
6. **The filtered calendar replaces the patient year view.** The twelve month
   strips go.
7. **The week view keeps the hour grid**, although a contact has no time of
   day, because appointments that can be booked to a time are coming and the
   grid is where they will live. The owner's reason, recorded because it is the
   whole justification for the empty rows.
8. **A contact appears in the grid on its due day only**, not across its whole
   window. The window version is more truthful about when a woman is expected,
   and it was rejected because one woman would fill twenty squares and a missed
   contact would fill every day after it for ever, which turns a month into a
   wall of colour nobody reads. A late contact draws in red on its due day and
   carries a marker on today, so it is not lost by being in the past.
9. **A card says which contact it is and when it is owed** — "Third antenatal
   check, owed 4 Nov". It does **not** say how many weeks pregnant she is. That
   would have to be worked out from her dating in both engines, and it is only
   as good as the dating: from a remembered last menstrual period it can be
   weeks out, and a false precision teaches people to distrust the screen.

## 3. What was decided for the owner, and can be reversed

- **Hand-built, no calendar library.** The project has none, uses hand-written
  CSS throughout, and a library would arrive with its own visual language to
  fight. The grid itself is not hard.
- **A card shows:** her name, which contact this is, when it is owed, and the
  role that owns it. Her age and village go on it **only where the register
  holds them** — `subject_row` carries whatever that facility's register
  declares, so a card renders the fields it finds and omits the ones it does
  not, rather than printing a blank label.
- **One card per contact, not per woman.** A woman with two contacts owed
  appears twice, because each is a separate piece of work somebody must do.
- **The stack is ordered by due date, and late contacts lead it.** That is the
  first design's rule for the day screen and there is no reason for the home
  page to disagree with it.
- **The stack respects the viewer's role**, the way the day screen does: it
  opens on the viewer's own work and falls back to everyone's when the viewer
  owns nothing.
- **The role chips stay**, on the sidebar's day list and on the grid, filtering
  in the browser exactly as they do today.
- **The clicker is arrows**, paging through later cards.
- **One grid component, used twice:** the whole centre, or narrowed to one
  woman. The same code, a different filter, so the two can never disagree about
  what a day contains.
- **Her record keeps the plain list of visits** that predates this work. Only
  the month strips go.

## 4. Constraints this inherits

- **Derived, never stored.** `kernel/schedule.py` explains why at length.
- **Declared, not coded.** The renderer may never name a station, flag,
  capability, operation or view column.
- **A row names the role, never a worker.** There is no staff register.
- **Two engines.** Every kernel route is served by Python and Go, and
  `scripts/check_go_parity.py` diffs them live.
- **The gate.** `sh scripts/check.sh` must exit 0.
- The assistant is a right-docked panel; while open it hides the visit's right
  rail, so no layout may assume the rail is there.

## 5. The one real change below the surface

Today the route answers **one day**: `?on=YYYY-MM-DD` returns that day's rows
and its month's per-day counts. A week needs seven days of rows. A month needs
a month of rows, not only counts. A year needs twelve months of counts.

So the route grows from a day to a **range**. `kernel/cohort.py:owed()` already
takes `since` and `until` — it was built that way — so the derivation does not
change. What changes is the view layer and the route above it, and the Go
mirror of both.

This is the only part of this work that touches the kernel, and the parity
walk must cover the new shape before it ships.

**The shape, decided so the two engines cannot drift while it is argued
about.** The route keeps `?on=` working exactly as it does, because the day
screen and the home card both use it, and gains `?from=` and `?to=`. A range
answer carries rows for every day in it, and the month groups as now. **The
span is capped** — a request for a decade is refused with the same kind of
400 an impossible date gets — because an uncapped range is both a way to hang
the server and a shape the parity walk cannot enumerate. One route, not
several.

**And the patient's grid is NOT a filtered centre-wide sweep.** Her view keeps
reading her own episodes, as her record does today, and renders them through
the same grid component. Filtering a whole-centre answer in the browser would
make one woman's record cost a sweep of every open episode at the facility and
would ship every other woman's name and village to draw one page. It would
also make her record depend on the centre-wide derivation agreeing with the
spine about ended episodes — a dependency the tie-break work on the first
branch showed is exactly the thing to avoid adding. Same component, same
look, two sources, each already correct for its own question.

## 6. The cost, and what to do about it

Each request sweeps every open episode and reads the audit of each of its
visits. That is stated plainly in both `kernel/cohort.py` and
`kernel/schedule.py`. Today a screen costs one or two such sweeps.

A year view is twelve months. Drawn naively it is twelve sweeps on one page
load, and the home page is another.

**Builder's instruction:** the year view asks for counts only, and asks month by
month as each month is needed, not twelve at once. The month and week views ask
for one range each. If that is still too slow at a few hundred open
pregnancies, the answer is the bulk read both modules name — **never a stored
contact, never a cache of derived rows.**

A timed run at a realistic cohort belongs in this work, not after it. The
previous design deferred it; it should not be deferred twice.

**The pass line, so there is something to measure against:** with 300 open
episodes seeded, the home page and the month view each answer in under two
seconds on a developer machine. That number is a judgement, not a
requirement from anybody — it is the point at which a nurse with a queue in
front of her starts to wonder whether the screen is broken. Correct it if you
disagree; what matters is that a number exists before the optimising starts,
so there is a moment at which the work is done.

**The year view loads all twelve months**, each as its own counts-only
request, in view order, with each month drawing as it arrives rather than the
page waiting for the last. A year that loads nothing until it has everything
is a blank page for twelve round trips.

## 7. What the three views are

**Week.** Google's week: seven day columns, an all-day band at the top, and the
hour grid below. Contacts have no time of day and sit in the all-day band. The
hour rows are deliberately empty until appointments exist.

**Month.** Google's month: a six-row grid of days, each day listing its
contacts, with an overflow indicator when there are more than fit.

**Year.** Google's year: twelve small month grids. Google's own year view shows
no events; ours tints a day that has work, so the shape of a centre's year is
visible. Clicking a day opens it.

In every view a contact keeps the colours already agreed: red late, blue owed,
green done, grey still ahead.

## 7a. The small decisions, made

- **Month cells spill into the neighbouring months**, as Google's do, and those
  spill days show their contacts. The month request therefore asks for the
  grid's first visible day to its last, not the calendar month's.
- **The hour grid scrolls**, opening at clinic hours rather than at midnight,
  so the empty night does not take the screen.
- **Clicking a day in the year opens that day**, which is the day list the
  sidebar already draws.
- **Every view is addressable.** The grid carries its scale and its date in the
  address, the way `?on=` already does, so the back button works and a view can
  be sent to somebody.
- **Below about 600px** the week becomes one day at a time with arrows, and the
  year becomes a scrolling column of months. A seven-column grid and a
  twelve-month grid are both unusable on a phone, and this is a tool used on
  phones.

## 8. What is left to the builder

- The exact visual weight of the card stack: how much smaller each card gets,
  and how many are visible before the arrows.
- How many contacts a month cell shows before it overflows.
- Whether the sidebar's today-cards and the home page's cards are one component
  or two.
- Keyboard handling on the grid.

## 9. Still open, not blocking

- **The clock, and it is now the thing most worth deciding first.** The kernel
  decides "today" in UTC, so between midnight and 05:30 in India it believes it
  is yesterday. Every date-relative answer in the product inherits it. Until
  now that showed in one place; this design puts "today" on the home stack, on
  the sidebar, on the week's current column, on the month's current cell and on
  the year's tint. The reviewer of this document asked for it to be settled
  before the work rather than after, and that is the right instinct: a wrong
  "today" drawn in five places at once is a screen a night-shift worker stops
  believing. It is still the owner's decision — whose day the product keeps,
  and where that is declared — and the work can proceed without it, inheriting
  whatever the kernel says, as everything else does.
- The deferred untangle of another session's work from two early commits of the
  first calendar branch.
