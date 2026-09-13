# Khoj, Home, Tasks and Registration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Fix the registration defect, rename the ask surface to Khoj everywhere including MCP, rebuild the shell and home screen with real visual hierarchy, add a cross-thread tasklist view, and make registration a configurable template with ABHA-locked fields.

**Architecture:** Most of this is declaration work, which is the point of the kernel. View titles, registration templates, tasks and the Khoj vocabulary are atoms. The renderer changes are the shell, the home bands, and the chat bar.

**Tech Stack:** Python 3.9 kernel (no framework, `assert` checks run as `python3 -m x.y`), FastAPI, React + TypeScript + Vite, Go MCP server.

**Spec:** `docs/superpowers/specs/2026-09-13-khoj-home-and-registration.md`

## How this plan is written, and why it differs from the last one

The previous plan specified exact code, and three times that code named things
that do not exist — CSS tokens `--line`/`--muted` (real: `--border`/`--ink-2`),
a class `act act-primary` (real: `btn btn-b`), a predicate
`guard.preconditions_hold` (real: `guard._preconditions_met`). Each cost a fix
round.

So this plan specifies **intent, constraints and the property to prove**, and
requires the implementer to read the surrounding code for names. Where an exact
string matters — a spoken sentence, a term list — it is given verbatim and
marked VERBATIM. Everything else: read the file first.

## Global Constraints

- Nothing in `web/src/` outside `.check.ts` files may name a station, a flag, or a bundle. Point the renderer at `bundles/lab/` and it draws the laboratory's words.
- `kernel/contracts.py` field names are frozen: add, never rename.
- Every check runs with no network, no database server, no CARE. `sh scripts/check.sh` is the gate.
- A `.check.ts` may NEVER import a `.tsx` — `node --experimental-strip-types` does not compile JSX. Assert against source read as text, the way `web/src/voice/voice.check.ts` does.
- No test framework. Plain `assert`, matching the surrounding file exactly. **Read the file before appending to it.**
- **Every check must fail when the thing it guards breaks.** The previous branch shipped seven assertions that passed under a deliberately broken implementation. For each assertion ask: would this still pass if the function ignored its most interesting argument? Commit, apply the shortcut, confirm FAIL, revert, confirm PASS. Put the output in the report.
- Do not weaken: the guard's irreversibility ordering (`surface != RENDERED` denies before `confirmed` is read), propose-never-commit, per-visit consent scoping.
- Copy rule: the thread screen is at 72 visible words, down from 178. Do not spend that budget without saying why.
- Commit before mutating anything for a mutation test.

## Vocabulary, VERBATIM

Acronyms always upper case: `ABHA ABDM PHC OP BP HIP HIU MCP ASR`.
Roles always sentence case: `Frontdesk Nurse Doctor Lab Pharmacist ASHA ANM CHO`.
(`ASHA`, `ANM`, `CHO` are acronyms and stay upper.)

---

### Task 1: The registration defect

**Files:** `catalogue/guard.py`, `catalogue/tests/test_guard.py`, `web/src/main.tsx`, `web/src/loops.check.ts`

Two bugs. Fix both.

**Bug A — the guard echoes its precondition source text.** `not registered`
unmet renders as `precondition not met: not registered`, which to a human says
the opposite of what happened. Read `parse_precondition` and `_preconditions_met`
in `catalogue/guard.py`; render each precondition kind as a sentence. A negated
flag that is present reads **"Already registered."**; a required flag that is
absent reads what it requires. Derive the words from the flag, never a lookup
table of PHC strings — the laboratory must get sentences too.

**Bug B — a surface opens an operation the kernel is not offering.** Six denials
in 28 seconds, `surface rendered`, all frontdesk. `thread.actions` correctly
excludes `patient-register` once registered, so the caller is opening by id.
Audit every `setModal` call site in `web/src/main.tsx` — `register()`,
`offerJourney()`, the Khoj create-on-miss path — and make each one open only an
operation present in that thread's own `actions`. Where it is not present, say
what the kernel said, do not silently do nothing.

- [ ] **Prove both.** For A, a check that no denial message contains a raw precondition literal, for BOTH bundles. For B, a check that fails if a call site can pass an operation absent from `actions`. Mutate each and show the failure.
- [ ] `sh scripts/check.sh` green, then commit.

---

### Task 2: Khoj, everywhere

**Files:** `web/src/Palette.tsx` → `web/src/Khoj.tsx` and its importers, `api/main.py`, `care_phc_mcp/`, `catalogue/`, docs

The ask-and-search surface is named Khoj in the UI, the API, the catalogue and
the MCP tool. The user will say "Khoj" and every layer must know the word.

- `POST /api/v1/phc/khoj` replaces `/agent/say`. **Keep `/agent/say` as a deprecated alias for one release** — the Go binary and any bound agent may still call it. Mark it deprecated in the OpenAPI description.
- The MCP tool is `khoj`. Its description must say it searches, answers and proposes, and **never commits** — propose-never-commit is unchanged.
- The name appears in the compiled catalogue so an agent reading declarations learns it without being told.
- Rebuild the Go binary; `kernel.declarations` copies the catalogue into `care_phc_mcp/`.

- [ ] **Prove it.** A check asserting no `Palette` identifier and no `agent/say` call survives outside the deprecated alias, and that the MCP tool list contains `khoj`. Mutate and show the failure.
- [ ] `go vet ./... && go test ./...` and `sh scripts/check.sh` green, then commit.

---

### Task 3: The shell

**Files:** `web/src/Shell.tsx`, `bundles/phc/phc.view.station-queue.md`, CSS

- Remove **New chat** and **Search** from the sidebar. Khoj is search; threads start from Recents.
- **Home is first and default.**
- Retitle the queue view to **Lines** — this is the atom's `title:`, NOT a renderer string. The laboratory keeps its own word. Recompile.
- **Sidebar collapses and expands**, remembered per viewer in localStorage. Collapsed shows icons with accessible names — never a tooltip-only control, and nothing may leave the tab order.

- [ ] **Prove it.** A check that the nav is built from declarations and that "Lines" appears in no renderer file. Verify collapse/expand and keyboard reachability in the browser.
- [ ] Gate green, commit.

---

### Task 4: Recents — add, sort, filter

**Files:** `web/src/Shell.tsx`, `web/src/loops.ts` (pure helpers), checks

- `+` beside Recents **opens patient search first.** Create is offered only on a miss and says so. This is the existing create-on-miss rule moved to where people actually start — read how Khoj does it today and reuse, do not reimplement.
- Sort: recent, name, station. Filter: by flag, by station.
- **Both derived from the queue view's declared `columns` and `badges`**, so a bundle declaring different ones gets different controls. A hard-coded filter list is a defect.

- [ ] **Prove it.** Pure sort/filter helpers in `loops.ts` with checks that fail if sort ignores its key or filter ignores its predicate. Assert the control set changes when the declaration changes — the voice check does exactly this, copy its technique.
- [ ] Gate green, commit.

---

### Task 5: The tasklist view kind

**Files:** `kernel/contracts.py`, `kernel/declarations.py`, `kernel/views.py`, `bundles/phc/phc.view.today-tasks.md`, a lab equivalent, `web/src/ViewRenderer.tsx`, checks

A task is cross-thread; the thread view by construction answers "what next
*here*". See the spec for the declaration shape.

- `_tasklist` resolver beside `_queue` and `_summary` in `kernel/views.py`.
- **It reads only flags**, which every adapter already serves. Do not add a Store method.
- `operation` is optional: with one, the row is actionable; without, it is a worklist.
- Lint it like every other view kind, including closure — a task naming an unknown flag fails the build.

- [ ] **Prove it.** Resolve for BOTH bundles; the laboratory's tasks must name no PHC word. Mutate the resolver to ignore its `where` and show the check fail.
- [ ] Gate green, commit.

---

### Task 6: Home, rebuilt

**Files:** `web/src/Home.tsx`, CSS, checks

Three bands in this order: **greeting** (name and role, sentence case, one
line, no prose beneath), **data** (the live line and declared metrics), **tasks
and actions** (Task 5's view).

**Cards are draggable with an explicit drag handle** — not tap-and-hold on the
card body, which fails on touch and on crowded screens. Generous drop zones.
Order persists per viewer and survives a reseed. **A focused handle takes arrow
keys** — drag must not be the only way.

- [ ] **Prove it.** Reorder persists across reload; keyboard reorder works; the bands render from declarations with no bundle word in the renderer. Verify all three in the browser.
- [ ] Gate green, commit.

---

### Task 7: The visual system

**Files:** `web/src/theme.css`, component classes

This is the task that decides whether the product stops looking generated.
Read the research in the spec before starting.

- **Not every card is a card.** The live line is the page's subject: draw it flat on the ground. Secondary panels get a surface. Tertiary gets a rule. Today everything shares one radius, one border, one padding, one weight — which is exactly why nothing reads as more important than anything else.
- **One accent, and it only ever means "needs you"** — flags, criticals, the primary action. Nothing else is coloured. A colour used decoratively cannot also mean urgent.
- Radius, border and shadow become a **three-step scale**, not one value.
- Numbers are the largest thing after the greeting.
- Keep the warm neutral ground. Dark mode must hold: this app has a theme toggle and both must be deliberate.

- [ ] **Prove it.** A check asserting the accent token appears only in rules for flag/critical/primary. Screenshot light and dark, both themes, and put them in the report.
- [ ] Gate green, commit.

---

### Task 8: Registration templates

**Files:** `questionnaires/` (three new), `bundles/phc/bundle.yaml`, `api/main.py`, `catalogue/validate.py` or wherever `enable_when` should be read, checks

Three templates ship: **minimal** (name, age, sex, mobile, village),
**standard** (adds category, address, emergency contact, ABHA consent — the
default, closest to today's form), **full** (adds allergies, current
medications, past history, insurance). A facility setting picks one.

`enable_when` **already exists** in the schema and in `types.ts` and is read by
nothing. The templates use it for skip logic, so an established patient
updating a mobile number does not walk the whole form. Implement the reader.

- [ ] **Prove it.** Every template compiles and validates. A check that `enable_when` actually gates a question — mutate the reader to ignore it and show the failure. Walk the standard template in the browser.
- [ ] Gate green, commit.

---

### Task 9: ABHA fields lock

**Files:** `web/src/abha/`, `web/src/Form.tsx`, checks

When a journey returns a profile, name, gender, DOB and mobile are filled and
**locked** — standard ABDM practice, because a local record silently diverging
from the national one is the failure this prevents. One visible control
unlocks, and **recording why is required**, the same shape as the range
override that already exists in `catalogue/validate.py`. Read that first and
match it.

- [ ] **Prove it.** A locked field cannot be written without an unlock reason; the reason reaches the audit. Mutate to allow a silent write and show the failure.
- [ ] Gate green, commit.

---

### Task 10: Acronyms and role casing

**Files:** `web/src/ui.tsx` (`human()`/`title()`), checks

Apply the VERBATIM term list above **in the helpers, not at call sites**.

- [ ] **Prove it.** A check asserting no renderer file contains a hard-cased `Abha`, `Phc`, `Abdm`. Mutate a helper to pass text through unchanged and show the failure.
- [ ] Gate green, commit.

---

### Task 11: The chat bar

**Files:** `web/src/Thread.tsx`, CSS

Full width, edge to edge within the thread column. Two icons inside it:
**scribe** (mounts the scribe instrument, still gated on `capture.consented`)
and **summarise** (opens the summary sheet). Both already exist — this moves
them into the one place a person is already typing. The consent gate must not
weaken.

- [ ] **Prove it.** Scribe absent without consent, present with it. Verify in the browser, both states.
- [ ] Gate green, commit.

---

### Task 12: UX review as the product owner

**Files:** report only

Dispatch an objective UX researcher carrying the product owner's persona,
drawn from their own words across this project:

- Text-light. No fluff, no disclaimers, no prose restating what is on screen.
- Minimal clicks, maximum output. Front desk is a typist with a queue behind them.
- Agent-first, but role-appropriate: front desk has the least use for AI and wants a robotic, predictable form.
- Everything configurable, with presets that carry 70%.
- Clear beginnings and ends; the next cue must be obvious without thinking.
- Hates interfaces that "scream AI made" — generic, evenly-weighted, decorative.
- Wants innovative AND intuitive, not one at the cost of the other.

It walks every role's real loop in the browser and reports what it found,
ranked, with screenshots. It does not fix anything. Findings feed a final pass.

- [ ] Report written; findings triaged into fix-now and defer.
