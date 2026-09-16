# Clinical Workspace Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the whole of `web/src`'s presentation layer with the interface
described in EMR UI/UX Spec v0.3, and add the kernel reads that spec needs,
without touching the declaration contract that makes the renderer portable.

**Architecture:** The UI stays a pure function of four declarations
(`Facility`, `Catalogue`, `ViewResult`, `ThreadView`). The pure logic modules
survive untouched; only the React and CSS above them are replaced. Colour lives
in exactly one file so the palette stays swappable, and one check enforces that
mechanically.

**Tech Stack:** React 19, Vite 7, TypeScript 5.9, plain CSS custom properties.
No component library. No CSS framework. Icons are inline SVG (Lucide geometry,
1.5px stroke) — no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-09-16-emr-ui-ux-spec-v0.3.md`

---

## Global Constraints

These apply to every task. Copied from the spec, with corrections noted.

**Colour containment.** `web/src/style/tokens.css` is the ONLY file in
`web/src` permitted a hex literal, `rgb(`, `hsl(` or `oklch(`. Every other rule
references `var(--color-*)`. Enforced by `style.check.ts`.

**Contrast.** Spec §68 targets WCAG 2.2 AA. The spec's own §48 light palette
fails it. Six tokens are corrected (hue preserved, verified against all five
light surfaces and each chip's own soft background):

| token | spec §48 | corrected | reason |
|---|---|---|---|
| `--color-text-tertiary` | `#8D8981` | `#69665F` | 2.75:1 → 4.51:1 |
| `--color-agent`         | `#72798A` | `#606675` | 3.44:1 → 4.53:1 |
| `--color-success`       | `#74856B` | `#5D6A56` | 3.12:1 → 4.52:1 |
| `--color-warning`       | `#9A7B48` | `#7B6239` | 3.12:1 → 4.54:1 |
| `--color-critical`      | `#A96E67` | `#8E5751` | 3.24:1 → 4.56:1 |
| `--color-abdm`          | `#657FB8` | `#4A65A1` | 3.13:1 → 4.51:1 |

§49 dark needs no change. `--color-text-disabled` stays below 4.5:1 by
definition and may only be used on genuinely disabled controls, never on text
a person must read.

**Handover is not agent activity.** Spec §57 borders `.handover` with
`--color-agent`, which §50 reserves for AI. Use `--color-border-strong`; the
`@from → @to` route line carries the identity. Deviation from spec, deliberate.

**Semantic colour only (§50).** No colour on a pixel that is merely decorative.
No gradients, no glow, no purple, no sparkles for AI (§71).

**Geometry (§45–47).** Spacing 4/8/12/16/20/24/32/40/48/64. Radius
6/8/12/16/pill. Shadows only on popovers, menus, dialogs, floating surfaces —
borders everywhere else.

**Type (§44).** Geist Sans, Geist Mono, with a system fallback stack.
Display 28/34/600 · Page 22/28/600 · Section 17/24/600 · Body 14/21/400 ·
Body-strong 14/21/550 · Label 13/18/500 · Metadata 12/17/400 · Micro 11/15/500.

**Copy (§93, §94).** Short, concrete, operational. No "AI powered", no "magic",
no "smart". No disclaimers. No badges naming a taxonomy (owner's instruction,
2026-09-15).

**Accessibility (§68).** Keyboard reachable, visible focus, semantic HTML,
`aria-label` on every icon-only control, 44px minimum touch target,
`prefers-reduced-motion` honoured, status never conveyed by colour alone.

**The renderer never names a station, flag, capability or bundle.** Portability
is proved by `bundles/lab/check.py` running the same renderer. A word on screen
comes from a declaration or it does not appear.

**Every commit leaves `scripts/check.sh` green, unskipped.** No `SKIP_E2E=1`.

---

## File Structure

### Deleted

`main.tsx` `Shell.tsx` `Home.tsx` `Thread.tsx` `ViewRenderer.tsx`
`OperationPanel.tsx` `Form.tsx` `Khoj.tsx` `Roles.tsx` `ui.tsx` `CloseCard.tsx`
`theme.css` `renderer.css` — and the checks that pin their shape:
`layout.check.ts` `design.check.ts` `home.check.ts` `shell.check.ts`
`keys.check.ts` `tasklist.check.ts`.

### Kept untouched

`api.ts` `types.ts` `loops.ts` `messages.ts` `words.ts` `tone.ts` `validate.ts`
`grants.ts` `structured.ts` `search.ts` `ask.ts` `declarations.ts`
`icons.tsx` (extended) — and their checks: `loops.check.ts`
`messages.check.ts` `validate.check.ts` `grants.check.ts`, plus
`abha/` `scribe/` `voice/` and their checks.

### Created

```
web/src/style/
  tokens.css        §44,46,47,48,49  the only file with a colour literal
  base.css          §51              reset, type scale, focus
  shell.css         §52,53           app grid, sidebar, topbar
  list.css          §54,67           patient list, rows, mobile cards
  thread.css        §55,56,57        thread, message, object, handover
  composer.css      §58,59,60        composer, recording, menus
  parts.css         §61,62           chips, status, buttons, inputs, dialog,
                                     drawer, toast, skeleton
web/src/app/
  App.tsx           routing + data loading
  Sidebar.tsx       §4.1,4.2,4.3     nav from declarations, recents, user menu
  Topbar.tsx        §52
  Palette.tsx       §35              ⌘K over search.ts
web/src/screens/
  Today.tsx         §5
  ListScreen.tsx    §6.2             a queue view as a table
  Encounter.tsx     §8               thread + context panel
  Patient.tsx       §7               (Pass 4)
  Settings.tsx      §32              roles and capability grants
web/src/thread/
  Thread.tsx        §9               the message stream
  Message.tsx       §9.2
  ThreadObject.tsx  §56              the generic object frame
  objects.tsx       §10              the eight first-class objects
  Composer.tsx      §16,17,18
  Menu.tsx          §60              @ and / menus
web/src/form/
  Form.tsx          §39,40
  Field.tsx         §40
web/src/view/
  View.tsx          the four declared view kinds
web/src/style.check.ts     colour containment + AA contrast, light and dark
web/src/shell.check.ts     nav from declarations (rewritten)
web/src/thread.check.ts    the eight objects, each backed by a kernel record
web/src/composer.check.ts  @ and / sourced from declarations, not literals
web/src/a11y.check.ts      aria-labels, targets, reduced motion, focus
```

---

## Pass 1 — Foundation and shell

### Task 1: tokens.css and the check that guards it

**Files:**
- Create: `web/src/style/tokens.css`, `web/src/style.check.ts`
- Modify: `web/package.json` (add to `check`), `scripts/check.sh`

**Interfaces:**
- Produces: every `--color-*`, `--space-*`, `--radius-*`, `--shadow-*`,
  `--duration-*`, `--ease-out`, `--font-*` name used by every later task.

- [ ] **Step 1: Write `style.check.ts` first — it fails with no tokens.css**

Three assertions, each of which must fail if its rule is broken:

1. **Containment.** Read every `.css` under `web/src`. Any file other than
   `tokens.css` containing `#rrggbb`, `#rgb`, `rgb(`, `rgba(`, `hsl(` or
   `oklch(` fails, naming file and line. (`rgba(` inside `tokens.css` shadows
   is allowed; shadows are colour and belong there.)
2. **Contrast.** Parse `tokens.css` for both blocks. For every
   (foreground, background) pair the spec actually uses, assert ≥4.5:1 for
   text and ≥3:1 for borders and focus rings, in BOTH themes. The pair list is
   data in the check, and each entry names the spec section it comes from.
3. **Completeness.** Every `var(--x)` used in any `web/src` CSS resolves to a
   declaration in `tokens.css`. This is the check that would have caught the
   Vernier sweep's 34 orphans.

- [ ] **Step 2: Run it. Expected: FAIL — tokens.css does not exist.**

- [ ] **Step 3: Write tokens.css** — §51 foundation values, §48 light and §49
  dark, with the six corrected values from Global Constraints. Dark is
  `[data-theme="dark"]`; light is bare `:root`; a `@media (prefers-color-scheme: dark)`
  block guarded `:root:not([data-theme="light"])` carries the same dark values
  so the system default works without a stamped attribute.

- [ ] **Step 4: Run it. Expected: PASS, and report the contrast margin of the
  tightest pair so a future edit that shaves it is visible.**

- [ ] **Step 5: Mutation-prove all three assertions.** For each: break it
  (put a hex in `base.css`; set `--color-warning` back to `#9A7B48`; reference
  `var(--color-nonexistent)`), confirm FAIL, revert, confirm PASS. A check that
  cannot fail is not a check — this is the rule the whole harness turns on.

- [ ] **Step 6: Commit.**

### Task 2: base.css, fonts, and the shell grid

**Files:**
- Create: `web/src/style/base.css`, `web/src/style/shell.css`
- Modify: `web/index.html` (font loading), `web/package.json`

- [ ] **Step 1:** Add Geist. Prefer the self-hosted `geist` npm package —
  a rural PHC is offline (§41), so a CDN font is wrong. If `npm i geist` cannot
  reach the registry, fall back to the §51 stack with `system-ui` and record
  the deviation in the commit message. Do not silently ship a CDN link.
- [ ] **Step 2:** Write `base.css` — §51 verbatim, plus the eight-step type
  scale from §44 as utility classes.
- [ ] **Step 3:** Write `shell.css` — §52 and §53 verbatim.
- [ ] **Step 4:** Run `style.check.ts`. Expected PASS (no literals introduced).
- [ ] **Step 5:** Commit.

### Task 3: App, Topbar, Sidebar

**Files:**
- Create: `web/src/app/App.tsx`, `Topbar.tsx`, `Sidebar.tsx`
- Rewrite: `web/src/shell.check.ts`
- Delete: `web/src/main.tsx` `Shell.tsx` `Home.tsx` (replaced), and the six
  checks listed under File Structure
- Modify: `web/src/main.tsx` becomes a four-line mount

**Interfaces:**
- Consumes: `api`, `useAsync`, `Facility`, `Catalogue` from the kept modules.
- Produces: `<App/>`; route shape `#/today`, `#/view/<id>`, `#/thread/<id>`,
  `#/patient/<id>`, `#/settings`.

- [ ] **Step 1: Rewrite `shell.check.ts`** to assert the new structure:
  every nav row's label comes from `facility.views[].title`, and the renderer
  source contains no declared view title as a literal. Mutation-prove by
  hard-coding one title and confirming FAIL.
- [ ] **Step 2:** Write `Sidebar.tsx` per §4.1 — brand, `+ New` (§4.2), nav
  from declared views, RECENTS, user menu (§4.3). Nothing from §4.1's
  "do not put in primary navigation" list appears.
- [ ] **Step 3:** Write `Topbar.tsx` and `App.tsx` with hash routing.
- [ ] **Step 4:** Delete the six obsolete checks and their entries in
  `scripts/check.sh`; add the new ones.
- [ ] **Step 5:** `npm run build` and `scripts/check.sh` green, unskipped.
- [ ] **Step 6:** Verify live in the browser: sidebar at 248px, nav labels
  equal to declared view titles, no horizontal scroll at 1280/1100/900/700px.
  Measure, do not eyeball.
- [ ] **Step 7: Commit.**

### Task 4: Command palette (§35)

**Files:** Create `web/src/app/Palette.tsx`. Consumes `search.ts` unchanged.

- [ ] **Step 1:** ⌘K opens; searches patients, views, commands via `search.ts`.
- [ ] **Step 2:** Find-before-create (§36, §2.9): a miss shows an explicit
  "Register new patient" button, never silent creation.
- [ ] **Step 3:** Keyboard: ↑↓ move, Enter opens, Escape closes, focus returns
  to the invoking element.
- [ ] **Step 4:** Verify live, then commit.

---

## Pass 2 — Thread, composer, lists

### Task 5: `View.tsx` — the four declared view kinds
Renders `queue` as §54's table (columns and badges from the declaration),
`tasklist`, `summary`, `dashboard`. Absorbs the deleted `tasklist.check.ts`
assertions into `thread.check.ts`. Row click opens the thread; context menu
per §6.3, built from `thread.actions`, never a literal list.

### Task 6: `ListScreen.tsx` (§6.2, §6.5, §67)
Search, filter, sort, configurable columns defaulting to the declared five.
Preserves filter, sort, scroll position and columns across navigation (§88).
Below 768px becomes cards, not a squeezed table (§67).

### Task 7: Thread and the eight objects (§9, §10, §56)
`Thread.tsx`, `Message.tsx`, `ThreadObject.tsx`, `objects.tsx`. Each of the
eight object types maps to a record the kernel actually returns — message and
agent insight from `messages.ts`, clinical event from `audit`, artifact from
`writes`, command result from `proposals`. `thread.check.ts` asserts every
rendered type has a kernel source and that no ninth type is invented.
Comment, Task and full Handover state render only what Pass 5 backs; until
then their absence is honest, not stubbed.

### Task 8: Composer (§16, §17, §60) and quick actions (§33, §34)
`Composer.tsx` and `Menu.tsx`. Carries forward the working `/` and `@` logic
from commit `a1c670f`. Quick actions capped at six, remainder behind `/`
(§33). `composer.check.ts` asserts `/` is sourced from `thread.actions` and
`@` from declared roles, both mutation-proved.

### Task 9: Forms (§39, §40)
`Form.tsx`, `Field.tsx`. Compact, validation adjacent to the field, tabular
numerals, no nested cards. Critical values require the §40 readback checkbox
before commit — which is the kernel's irreversibility guard, already enforced
server-side; the UI must not be the only thing asking.

---

## Pass 3 — Scribe into the composer

### Task 10: Scribe as a composer mode (§18, §19, §20, §2.6)
The microphone moves into `Composer.tsx`. Recording expands the composer
(§18). Live transcript renders in the thread at low visual weight (§19).
On stop, the draft becomes a **proposal**, not form fields — reusing the
propose-never-commit path Khoj already uses. `Recorder.tsx`'s
`(schema, payload, ids, onValues)` interface is replaced by one that emits a
proposal. Provenance per §24: "Drafted from today's conversation", never
"AI generated". Accepting writes the artifact (§20).

Scribe gains no nav item, no panel, no dashboard (§2.6).

---

## Pass 4 — The patient spine

### Task 11: Kernel read — encounters for a patient
No Store protocol change: `select("encounter", thread=None,
where={"patient": id}, fields=[...], limit=n)` already works, and
`_where` already joins `patient` through `encounter`.

- [ ] Kernel function returning a patient and their encounters, newest first.
- [ ] Route `GET /api/v1/phc/patients/{id}/`, added to `contracts.ROUTES`.
- [ ] Route `GET /api/v1/phc/patients/?q=` for §36's tolerant search.
- [ ] Tests in `kernel/tests/` and `api/tests/test_api.py`, mutation-proved.
- [ ] `bundles/lab/check.py` still green — the route must be as portable as
      the rest; a laboratory has subjects too.

### Task 12: `Patient.tsx` (§7, §2.3, §26)
Header (§7.1), Overview / Encounters / Timeline / Documents (§7.2). The active
encounter opens the workspace. Timeline (§26) is longitudinal and built from
the encounter list; clicking an item jumps to that thread.

---

## Pass 5 — Remaining kernel objects, in priority order

Each is a declaration plus a kernel rule plus a renderer, in that order, and
each lands as its own commit with the gate green. Anything not reached is
reported as not reached — no stub that looks finished.

1. **Handover states (§12.1).** Seven states on the existing handover
   operation. Reply, reassign, resolve, reopen. This is the owner's own
   most-recent request and outranks the rest.
2. **Comments (§11).** Attached to an object, expanding inline.
3. **Tasks (§28, §29).** A real object with owner, due date and status —
   distinct from today's `TaskRow` worklist, which stays.
4. **People (§13).** A user directory so `@Priya` resolves, not only `@nurse`.
   Note: `caller()` reads a header and is explicitly not a security boundary;
   a people directory must not be mistaken for authentication.
5. **Patient lists (§6.1, §6.4).** Personal, shared, cohort, dynamic.
6. **Offline and sync (§41, §42).** Largest, least urgent for a demo.

---

## Self-review notes

- **Spec coverage.** §1–§40 and §44–§103 map to a task above. §41/§42
  (offline) and §6.1/§6.4 (list CRUD) are deliberately last and explicitly
  flagged as unreached if unreached.
- **Deviations from spec, all deliberate and stated:** six contrast
  corrections; `.handover` border colour; Lucide inlined rather than added as
  a dependency.
- **The risk this plan is built to avoid.** Seven assertions have passed under
  deliberately broken implementations on this branch. Every check written here
  is mutation-proved in its own step — break it, confirm FAIL, revert, confirm
  PASS — because on this codebase that is the only evidence that has ever held.
