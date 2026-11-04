# The calendar: what was decided, and what is still open

4 November 2026. Two pieces of work on `feat/phc-catalogue-and-guard`: the
calendar, then the calendar journey. Sixteen tasks, fifty-odd commits.

You approved both designs. This is the record of the judgement calls made
underneath them that nobody asked you about, and the things still waiting on
you. Each decision says what it costs if it was wrong, so you can undo the
ones you disagree with.

---

## 1. Waiting on you

**The clock.** The system keeps time in UTC, so between midnight and 5:30am
local it believes it is yesterday. That affects every date in the product,
not only the calendar — whether a visit counts as due or missed, what "today"
means on five different screens. A clinic opening at 8am rarely meets it; a
health worker on an early home visit or anyone recording a night delivery
does. Fixing it means deciding whose day the product keeps, and saying so
somewhere in the facility's settings. That is a decision about the product,
not about the code.

**Another session's work is inside two of our commits.** A shared staging
area meant commits `71ecf05` and `0cccf33` swallowed files belonging to the
other sessions working in this repository — the medical-records code, the
paper-scanning code and several screens. Nothing was lost and everything was
restored, but those commits carry work that is not this feature's. You asked
for it to be untangled later. The files are listed in section 5.

**The programme's wording does not reach a phone.** The formal names
("Second antenatal contact") live in hover text, which does not exist on a
touch screen. That matches what you asked for — a front-line worker needs the
plain words — but if supervisors use phones and need the formal terms, say so
and they can go on the screen instead.

**Twelve small things were deliberately left.** They are listed in section 6
with a recommendation for each.

---

## 2. Decisions about what people see

**Visits show on the day they were due, not across the whole window they are
owed in.** The alternative was more truthful about when a woman is expected,
and was rejected because one woman would fill twenty squares and a missed
visit would fill every day after it for ever, turning a month into a wall of
colour nobody reads. *If wrong: the grid understates how long a woman has
been expected.*

**A visit whose day has passed is marked on today.** Otherwise a woman
overdue since September leaves no trace on a November calendar — she has no
square to sit in. This was fixed twice: first for visits already counted as
missed, then for visits merely past their due date, which were vanishing from
the home page for up to four weeks. *If wrong: a woman appears on today
sooner than somebody intended, which is the safe direction.*

**Her record keeps a missed visit on the day it was really due; the centre's
calendar moves it to today.** Two correct answers to two different questions
— her page is a history, and the point of looking at it is seeing when things
slipped. *If wrong: the two screens disagree, which is why it is written into
both files.*

**Cards name the woman, not a count.** One card per visit, so a woman owed two
appears twice; late ones lead; the stack opens on your own work with a line
saying how many belong to others. *If wrong: a nurse scans names where she
wanted a total.*

**Rows name the role that owns a visit, never a worker.** There is no staff
register in this system, so a person's name on a row would be a lie. *If
wrong: a nurse cannot tell which ASHA is meant.*

**Age and village appear only where the register holds them.** The screen
renders the fields it finds rather than naming any, so a facility with a
different register gets sensible cards. *If wrong: a card shows a field
nobody wanted first.*

**Weeks start on Sunday**, matching the Google Calendar you sent.

**The year view shows the whole arc, about eleven months, not a calendar
year.** A calendar year cuts a pregnancy in half whenever it crosses New
Year, which is most of them.

**On a phone the week becomes one day with arrows and the year a scrolling
column.** A seven-column grid and a twelve-month grid are both unusable on a
phone, and this is a tool used on phones.

---

## 3. Decisions about how it is built

**Nothing about a visit is ever stored.** Every date is worked out fresh each
time somebody asks. This is the rule the whole product rests on: a stored
schedule has to be cancelled when a pregnancy ends, somebody has to remember
to cancel it in every path that could end one, and if anyone misses one, a
woman who has just lost a baby gets a call asking why she missed her visit.
Deriving makes that impossible rather than unlikely. Every performance
decision below was made inside that constraint.

**The route answers two different questions, deliberately.** Asking for a day
gives "what is owed on this day", by window. Asking for a span gives "what
falls due in this span", by due date. Neither is a special case of the other,
and a test that asserted they agree was removed because it asserted something
untrue. *If wrong: a reader assumes one day equals a one-day span and gets a
different answer.*

**Where a visit belongs is decided once, by the server, and sent with the
visit.** The screen draws what it is told. The alternative — the browser
working it out — would have been the third copy of a rule that had already
drifted apart twice. *If wrong: one more field on a row.*

**A request can ask for at most 400 days.** It admits a year and a month grid
with its spill days, and refuses a decade. *If wrong: somebody wanting
eighteen months makes two requests.*

**Her page reads her own records, never the whole centre's.** Filtering the
facility's answer in the browser would make one woman's record cost a sweep
of every pregnancy at the centre and would send every other woman's details
to draw one page. *If wrong: nothing; this is strictly cheaper and more
private.*

**The year fetches each month normally rather than a counts-only call.** One
response shape instead of two, nothing extra for the second engine to copy,
and a month at a health centre is tens of rows. *If wrong: the year makes
twelve slightly larger requests.*

**Both engines accept dates only as `2026-11-04`.** A timestamp raises a
timezone question the route cannot answer. *If wrong: a caller passing a
timestamp gets a clear refusal instead of a guess.*

---

## 4. How fast it is

Measured against a seeded centre with 300 open pregnancies and 750 recorded
visits behind them:

| Screen | Time | Target |
|---|---|---|
| Home page | 0.33s | 2.0s |
| One month | 0.11s | 2.0s |
| A whole year (12 requests) | 0.94s | — |

No optimisation was needed. The two-second target is a judgement, not a
requirement from anybody — roughly where a nurse with a queue in front of her
starts to wonder whether the screen is broken.

**Honest limit:** this check would still pass something ten times slower. It
catches a disaster, not a slow decline.

---

## 5. The untangle, when you want it

Commits `71ecf05` and `0cccf33` carry files belonging to other sessions. The
parts that are genuinely this feature's:

- `71ecf05` — `kernel/cohort.py`, `kernel/tests/test_cohort.py`, and the
  `test_cohort` line in `scripts/check.sh`.
- `0cccf33` — `web/src/view/Calendar.tsx`, `web/src/view/day.ts`,
  `web/src/style/calendar.css`, `web/src/types.ts`, `web/src/ui.check.ts`,
  `web/src/thread/Arc.tsx`, `web/src/main.tsx`.

Everything else in those two commits belongs to the medical-records, paper
and assistant work and should move to its own commit.

The cause is worth knowing because it will happen again: four sessions share
one checkout **and one staging area**, so a plain `git commit` writes
everything anybody has staged. Naming files when you stage them is not
enough; the commit itself has to name them. Both sessions now do.

---

## 6. The twelve small things left

**Worth doing before this is used in earnest**

- Month chips clip between about 700 and 1000 pixels wide.
- The week's all-day row has no limit, so sixty visits on one day push the
  hour grid off the screen. The month caps at three and says "+N more".
- The home stack pages one card at a time, so sixty owed visits mean sixty
  clicks.

**Worth doing eventually**

- Clicking a day then paging the grid leaves the sidebar on the day you
  clicked rather than today.
- Two visits due the same day have no defined order.
- A visit with no date sorts oddly and prints a bare label.
- The filter chips flicker while a new span loads.

**Safe to leave**

- Five items about test wording, an unused return value and a long comment.
  They are listed in the working notes and none changes what anybody sees.

---

## 7. What proves it still works

- `sh scripts/check.sh` runs everything and must print "all checks passed".
- `scripts/check_calendar.py` proves seven safety claims, including that a
  miscarriage produces no home visits at all — absent, not cancelled, not
  empty — and that a woman nobody has seen for months still appears on today.
- `scripts/check_calendar_scale.py` proves the span rules and the timing.
- `scripts/check_go_parity.py` runs both engines side by side over 126 cases,
  including open, unseen, delivered and miscarried women, month ends, leap
  days and impossible dates.

Every one of those checks was deliberately broken during the build to confirm
it fails when it should. Two were found to be incapable of failing at all and
were replaced.
