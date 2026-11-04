# Calendar Journey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The home page names the next few women; the calendar page looks like a calendar, in week, month and year; and one woman's record uses the same grid.

**Architecture:** The calendar route grows from one day to a capped range, in both engines. A new grid component places each contact on its **due day** and is used three times — the whole centre, the sidebar's day, and one woman. The patient's grid keeps reading her own episodes, not a centre-wide sweep. The month strips built on the previous branch are removed.

**Tech Stack:** Python 3.9 + FastAPI (kernel, api), Go 1.25 (`care_phc_mcp`), React 19 + TypeScript 5.9 + Vite 7 with hand-written CSS (`web`). No calendar library.

**Spec:** `docs/superpowers/specs/2026-11-04-calendar-journey-design.md`

## Global Constraints

- **Nothing is stored.** A contact exists only as the return value of a derivation. No cache, no memo, no table.
- **The renderer may never name a station, flag, capability, operation or view column.**
- **A row names the ROLE that owns it, never a worker.**
- **Two engines.** Every kernel route is served by Python and Go; `scripts/check_go_parity.py` diffs them live and must pass.
- **The gate.** `sh scripts/check.sh` must exit 0.
- **A contact sits on its DUE day in the grid**, never across its window. The window rule stays for the day list's "what is owed today" — the two questions are different and both are right.
- **The Store protocol stays at its existing method set.**
- Four sessions share this checkout and one git index: stage by exact path and **commit with a pathspec** (`git commit -- <path>`), never amend, never reset, never stash, never switch branches, and run `git show --stat` after every commit.
- Tests are plain Python modules with a `__main__` runner registered in `scripts/check.sh`, or `.check.ts` files run by node and registered there. A test the gate does not run is worth nothing.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Ruling that departs from the spec

The design says the year view asks for **counts only**, month by month. This plan instead has the year fetch each month as an ordinary range and count the rows by due date in the browser. One response shape instead of two, no new route flag, no second thing for the Go engine to mirror; and a month of contacts at a primary health centre is tens of rows, not thousands. If the timed run in Task 7 says otherwise, a counts-only flag is the fix, and it is a small one.

## Review Focus

Five conditions the spec implies that no task's happy path exercises. Each has its test placed in the task that owns the code.

1. **A range that spans a year boundary**, and one that is a single day. The capped range must handle both ends of its own validity. Test in Task 1.
2. **A contact whose due date falls outside the requested range** but whose window overlaps it. It must not appear in the grid, because the grid places by due day — and it must still appear in the day list if its window covers that day. Test in Task 1.
3. **A month grid's spill days.** The first and last cells belong to neighbouring months; contacts due there must draw, which means the request covers the visible grid, not the calendar month. Test in Task 3.
4. **A woman with no episodes at all**, opened on the patient grid. It must say so, not draw an empty frame. Test in Task 6.
5. **A day with far more contacts than a month cell can show.** The overflow indicator must be right, and no contact may be silently dropped. Test in Task 3.

---

### Task 1: The route answers a range

**Files:**
- Modify: `kernel/views.py` (`resolve`, `_calendar`)
- Modify: `api/main.py` (`get_view`)
- Test: `kernel/tests/test_views.py`, `api/tests/test_api.py`

**Interfaces:**
- Consumes: `cohort.owed(bundle, store, workflow, *, types, since, until, at=None)`, unchanged.
- Produces: `resolve(..., on=None, since=None, until=None)`. `GET /views/{id}?from=YYYY-MM-DD&to=YYYY-MM-DD` returns rows for every day in the range plus the existing `groups`. `?on=` keeps its present behaviour exactly. A range longer than **400 days**, or inverted, raises `ValueError` → 400, with one sentence in the style of the existing date refusal.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_range_answers_every_day_in_it_and_not_one_day_more():
def test_on_still_answers_exactly_what_it_did_before():
def test_a_range_crossing_a_year_boundary_is_whole():
def test_a_range_of_one_day_equals_the_same_day_asked_with_on():
def test_a_range_longer_than_the_cap_is_refused_with_400():
def test_an_inverted_range_is_refused():
def test_from_without_to_is_refused_rather_than_guessed():
def test_a_contact_due_outside_the_range_is_absent_though_its_window_overlaps():
```

The last one is Review Focus 2 and is the one that matters: it pins that the range selects by what the grid will draw.

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m kernel.tests.test_views`
Expected: FAIL — `resolve()` takes no `since`

- [ ] **Step 3: Implement the range in `_calendar` and `resolve`, and the two parameters in `get_view`**

Keep `on` and the range mutually exclusive; passing both is a refusal, not a precedence rule nobody will remember.

- [ ] **Step 4: Run the tests**

Run: `python3 -m kernel.tests.test_views && python3 -m api.tests.test_api`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -- kernel/views.py api/main.py kernel/tests/test_views.py api/tests/test_api.py -m "A calendar answers a span of days, not only one"
```

---

### Task 2: Go parity for the range

**Files:**
- Modify: `care_phc_mcp/views/views.go`, `care_phc_mcp/cmd/api/views.go`
- Modify: `scripts/check_go_parity.py`
- Test: `care_phc_mcp/views/views_test.go`

**Interfaces:**
- Consumes: Task 1's behaviour, which is the specification.
- Produces: identical JSON from both engines for every range the parity walk asks.

- [ ] **Step 1: Write the failing Go test**

Mirror Task 1's refusals: over the cap, inverted, `from` without `to`, both `on` and a range. Assert the same sentence the Python raises, as `views_test.go` already does for bad dates.

- [ ] **Step 2: Run it**

Run: `cd care_phc_mcp && go test ./views/...`
Expected: FAIL

- [ ] **Step 3: Implement the range in the Go resolver and route**

- [ ] **Step 4: Extend the parity walk**

Add ranges to the existing calendar scenario: a week, a month with its spill days, a year boundary, a single day, and each refusal. The scenario already seeds open, unseen, delivered and miscarried women — reuse it rather than seeding a second.

- [ ] **Step 5: Run both engines**

Run: `cd care_phc_mcp && go build ./... && go test ./...`, then `python3 scripts/check_go_parity.py`
Expected: both PASS

- [ ] **Step 6: Commit**

```bash
git commit -- care_phc_mcp/views/views.go care_phc_mcp/cmd/api/views.go care_phc_mcp/views/views_test.go scripts/check_go_parity.py -m "The other engine answers a span too"
```

---

### Task 3: The grid

**Files:**
- Create: `web/src/view/grid.ts` (pure), `web/src/view/Grid.tsx`, `web/src/style/grid.css`
- Create: `web/src/view/grid.check.ts`
- Modify: `scripts/check.sh`

**Interfaces:**
- Consumes: `CalendarRow[]` from Task 1.
- Produces, from `grid.ts`:
  ```ts
  export type Scale = "week" | "month" | "year";
  export function span(scale: Scale, anchor: string): { from: string; to: string };
  export function cells(scale: Scale, anchor: string, rows: CalendarRow[], max: number):
    { key: string; inMonth: boolean; isToday: boolean; rows: CalendarRow[]; more: number }[];
  ```
  `span` is the range to request, including a month's spill days. `cells` places each row on **`row.due`** and reports overflow beyond `max`.

- [ ] **Step 1: Write the failing checks**

```ts
// A month's span starts before the 1st and ends after the last, covering the visible grid.
// A contact draws in the cell of its due date and in no other cell.
// A contact due in a spill day draws there.                      // Review Focus 3
// A cell with more rows than max reports the remainder and drops none.  // Review Focus 5
// A week's span is seven days; a year's is twelve months.
// Today's cell is marked, and only one cell is.
// No state, flag, operation or column name is written in grid.ts or Grid.tsx.
```

- [ ] **Step 2: Run them**

Run: `cd web && node --experimental-strip-types src/view/grid.check.ts`
Expected: FAIL

- [ ] **Step 3: Implement `grid.ts`, then `Grid.tsx` and its CSS**

Week is Google's: seven day columns, an all-day band carrying the contacts, and the hour grid below, scrolled to clinic hours. Month is Google's six-row grid with spill days and an overflow indicator. Year is twelve small month grids, a day tinted when it has work. Colours are the agreed four.

- [ ] **Step 4: Run the checks and the type build**

Run: `cd web && npx tsc --noEmit && node --experimental-strip-types src/view/grid.check.ts`

- [ ] **Step 5: Look at all three scales in a browser** on your own ports, then stop the servers by port.

- [ ] **Step 6: Commit**

```bash
git commit -- web/src/view/grid.ts web/src/view/Grid.tsx web/src/style/grid.css web/src/view/grid.check.ts scripts/check.sh -m "A week, a month and a year, in the shape of a calendar"
```

---

### Task 4: The calendar page

**Files:**
- Modify: `web/src/view/Calendar.tsx`, `web/src/view/day.ts`, `web/src/types.ts`, `web/src/api.ts`
- Test: `web/src/ui.check.ts`

**Interfaces:**
- Consumes: `Grid` and `span` from Task 3; the range route from Task 1.
- Produces: the calendar screen — today's cards down the side, the grid beside them, a scale switcher, all of it addressable.

- [ ] **Step 1: Write the failing checks**

```ts
// The scale and the anchor date are both read from and written to the address.
// Switching scale requests the new span, not the old one.
// The role chips still filter, on both the sidebar and the grid.
// An empty day still shows its sentence beside a drawn grid.
```

- [ ] **Step 2: Run them, expect failure. Step 3: Implement. Step 4: Re-run with `tsc --noEmit`.**

- [ ] **Step 5: Look at it**, including the back button after two scale changes.

- [ ] **Step 6: Commit**

```bash
git commit -- web/src/view/Calendar.tsx web/src/view/day.ts web/src/types.ts web/src/api.ts web/src/ui.check.ts -m "The calendar page: today beside the month"
```

---

### Task 5: The card stack

**Files:**
- Modify: `web/src/screens/Today.tsx`, `web/src/view/day.ts`
- Create: `web/src/view/Cards.tsx`, `web/src/style/cards-stack.css`
- Test: `web/src/ui.check.ts`

**Interfaces:**
- Consumes: rows from the range route.
- Produces: `stack(rows, now)` in `day.ts`, returning the ordered contacts for the stack; `<Cards>` drawing them.

- [ ] **Step 1: Write the failing checks**

```ts
// Late contacts lead the stack, then the soonest owed.
// One card per contact, so a woman owed two appears twice.
// A card shows her name, the contact, when it is owed and the owning role.
// A card omits a register field the subject does not carry, rather than drawing a blank label.
// The stack opens on the viewer's own role and falls back to everyone when they own nothing.
// The arrows page to later cards and cannot page past the end.
// A card opens that woman's calendar, at the date the contact is owed.
```

That last one is the journey the owner asked for and it is easy to leave out: a card is not a label, it is the way into her record. It navigates to her patient view with the grid anchored on the contact's due date, so the screen opens on the thing the card was about.

- [ ] **Step 2–4: fail, implement, pass.** The nearest card is largest and each behind it smaller; the exact scale step is the builder's.

- [ ] **Step 5: Look at it. Step 6: Commit**

```bash
git commit -- web/src/screens/Today.tsx web/src/view/day.ts web/src/view/Cards.tsx web/src/style/cards-stack.css web/src/ui.check.ts -m "Coming up, by name"
```

---

### Task 6: One woman, in the same grid

**Files:**
- Modify: `web/src/thread/Arc.tsx`, `web/src/screens/Patient.tsx`
- Delete: `web/src/thread/arc-scale.ts`, `web/src/thread/arc-scale.check.ts`
- Modify: `scripts/check.sh` (remove the deleted check), `web/tsconfig.json` (remove its exclusion)

**Interfaces:**
- Consumes: `Grid` from Task 3, and her episodes as her record already loads them.
- Produces: her contacts drawn in the shared grid. **Her source does not change** — it stays her own episodes, never a centre-wide sweep.

- [ ] **Step 1: Write the failing check**

```ts
// Her contacts draw in the shared grid, placed on their due dates.
// A woman with no episodes gets a sentence, not an empty frame.   // Review Focus 4
// Two episodes stay two, and are distinguishable.
// The plain list of visits still exists; only the month strips are gone.
// Arriving with a date in the address opens her grid anchored there, so a card from
// the home stack lands on the contact it named rather than on today.
```

- [ ] **Step 2: Run it, expect failure.**

- [ ] **Step 3: Draw her episodes through `Grid`, then remove the month-strip code**

Remove `arc-scale.ts`, its check and its registrations **in the same commit** as the replacement, so the branch never has two ways to draw her year. The owner approved this replacement explicitly; do not remove anything else.

- [ ] **Step 4: Run the checks and the full gate.** The gate must not reference the deleted check file.

- [ ] **Step 5: Look at her record. Step 6: Commit**

```bash
git commit -- web/src/thread/Arc.tsx web/src/screens/Patient.tsx web/src/thread/arc-scale.ts web/src/thread/arc-scale.check.ts scripts/check.sh web/tsconfig.json -m "Her year, in the same calendar as everybody else's"
```

---

### Task 7: The timed run, and the proof

**Files:**
- Create: `scripts/check_calendar_scale.py`
- Modify: `scripts/check.sh`, `scripts/check_calendar.py`

**Interfaces:**
- Consumes: everything above.
- Produces: a check in the gate, and a measured answer to "is it fast enough".

- [ ] **Step 1: Seed 300 open episodes in a scratch database and time the three requests**

The home page's range, a month, and the twelve the year makes. Report each. The pass line is **under two seconds** for the home page and the month view; the year is twelve requests and is judged on when its first month draws, not its last.

- [ ] **Step 2: If anything is over, fix it with a bulk read**

Never a cache of derived rows, never a stored contact. If a bulk read is not enough, stop and report rather than reaching for one.

- [ ] **Step 3: Write `scripts/check_calendar_scale.py`**

Follow `scripts/check_calendar.py` exactly in style. It proves: a range answers the same rows as asking each of its days with `?on=`; a contact appears in the grid on its due day and nowhere else; the cap refuses an over-long range; and the timing stays under the line with 300 open episodes.

- [ ] **Step 4: Prove the checks can fail.** Break each claim in a scratch copy and show it fails. Report what you broke and what you saw.

- [ ] **Step 5: Register it and run the whole gate**

Run: `sh scripts/check.sh`
Expected: exits 0, "all checks passed".

- [ ] **Step 6: Commit**

```bash
git commit -- scripts/check_calendar_scale.py scripts/check.sh scripts/check_calendar.py -m "A span costs what we said it would"
```

---

### Task 8: Plain names on screen, the programme's words on hover

Added after the owner saw the screens and said the wording was "too specific, not something a rural FLW will understand", then asked that the programme's own phrasing be kept as a tooltip.

**Files:**
- Modify: `bundles/phc/phc.sched.antenatal.md`, `bundles/phc/phc.sched.postnatal.md`
- Modify: `kernel/contracts.py` (the `Contact` dataclass), `kernel/declarations.py` (the schedule lint), `kernel/schedule.py` (`contacts()`), `kernel/spine.py` (`of()`)
- Modify: `care_phc_mcp/` — the Go twins of the above
- Modify: `scripts/check_go_parity.py`, `scripts/check_antenatal.py`, `scripts/check_postnatal.py`
- Modify: `web/src/view/Grid.tsx`, `web/src/view/Cards.tsx`, `web/src/view/Calendar.tsx`
- Test: `kernel/tests/test_declarations.py`, `web/src/view/grid.check.ts`

**Interfaces:**
- Produces: each contact carries two names — `title`, the plain words shown, and a second field holding the programme's own phrasing, shown on hover. `reports_as` is untouched: it is the statutory reporting code (ANC2, HBNC1) and is a third thing again.
- Produces: the subject answer gains `generated_at`, the way a view answer already has one.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_contact_carries_both_a_plain_name_and_the_programme_s():
def test_a_schedule_declaring_no_programme_name_still_compiles():   # the field is optional
def test_the_subject_answer_carries_the_date_it_was_generated():
```

```ts
// A chip shows the plain name and carries the programme's name as its tooltip.
// A contact with no programme name shows the plain name and no tooltip.
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: The declarations**

The four antenatal titles become plain — "First check-up" through "Fourth check-up" — and each gains the programme's phrasing, "First antenatal contact" and so on. **The postnatal titles are already plain** ("First home visit", "Third day visit", "Six week check") and gain the second field only where the programme's own wording differs from them. Do not invent a formal name where none exists.

- [ ] **Step 4: Carry it through both engines**

The field is optional, so a bundle declaring none still compiles. `kernel/spine.py:of()` gains `generated_at` beside its other keys.

- [ ] **Step 5: The parity walk covers both additions**

- [ ] **Step 6: The screens**

The chip, the card and the day list show the plain name, with the programme's phrasing as the hover text. Where a contact has no programme name, no tooltip.

- [ ] **Step 7: Her page takes today from the kernel**

`web/src/screens/Patient.tsx` reads the date from the subject answer's new `generated_at` rather than from `new Date()`, so her page and the facility page cannot disagree about what day it is.

- [ ] **Step 8: Run the gate, commit**

```bash
git commit -- <exact paths> -m "The screen says check-up, the programme's own words are a breath away"
```
