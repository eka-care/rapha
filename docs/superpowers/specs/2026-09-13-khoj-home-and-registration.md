# Khoj, the home screen, tasks, and a configurable registration

Status: approved design, not yet built
Date: 2026-09-13
Builds on: docs/superpowers/specs/2026-09-11-role-weighted-loops-design.md

## Why

The role-weighted loops branch fixed how a *thread* behaves. This one fixes
everything around it: the shell, the home screen, the way work is found, and
the registration form that is currently the worst screen in the product.

Three things drove it. A screenshot of a patient whose status reads
**Registered** above six stacked refusals saying `precondition not met: not
registered`. A home screen that "screams AI made". And a sidebar whose first
two items are things nobody at a health centre does first.

## The registration defect, diagnosed

`phc.op.patient-register` on `enc-001`: allowed at 21:42:19, then denied six
times at 02:38 with `precondition not met: not registered`.

Two bugs stacked:

1. **The message is backwards to a human.** The precondition is `not
   registered`. The guard renders the literal, so a denial for "you are
   already registered" prints as "not registered" — which reads as the exact
   opposite of what happened. `catalogue/guard.py` must render a precondition
   as a sentence, not echo its source text. `not registered` unmet becomes
   **"Already registered."**
2. **Something re-opens registration on a registered thread.** Six denials in
   28 seconds, all `surface rendered`, all from frontdesk. The arrival effect
   is not the cause — `thread.actions` correctly excludes `patient-register`
   once `registered` holds. The ABHA path is the suspect: `offerJourney` and
   the palette's create-on-miss both open registration by id rather than by
   what the kernel is currently offering. Fix by never opening an operation
   the thread's own `actions` does not contain.

## Principles carried forward

Everything in the prior spec still holds. Added here:

12. **Hierarchy is what stops an interface looking generated.** Identical
    cards — same radius, same border, same padding, same weight — mean nothing
    is more important than anything else. Depth, weight and space carry rank;
    colour does not.
13. **One accent, and it only ever means "needs you".** A colour that appears
    decoratively cannot also mean urgent.
14. **An acronym is upper case. A role is sentence case.** ABHA, ABDM, PHC,
    OP, BP. Frontdesk, Nurse, Pharmacist.
15. **A field that came from a national record is locked, not merely marked.**

## 1. Khoj

The ask-and-search surface is named Khoj everywhere: the UI, the API, the
catalogue, and the MCP tool an agent binds to.

- Centred in the header, not right-aligned. It is the primary way to reach
  anything, so it takes the centre.
- `⌘K` unchanged.
- API: `POST /api/v1/phc/khoj` replaces `/agent/say`. The old path stays as a
  deprecated alias for one release, because the MCP binary and any bound agent
  may still call it.
- MCP: the tool is `khoj`. Its description says it searches, answers, and
  proposes — never commits, per propose-never-commit.
- `web/src/Palette.tsx` becomes `web/src/Khoj.tsx`.

The name must appear in the compiled catalogue so an agent reading
declarations learns it without being told.

## 2. The shell

- **New chat and Search leave the sidebar.** Khoj is search; a thread is
  started from Recents.
- **Home is first and default.**
- **`phc.view.station-queue` is retitled "Lines."** This is an atom edit, not
  a renderer edit — `bundles/phc/phc.view.station-queue.md`'s `title:`. The
  laboratory keeps its own word.
- **The sidebar collapses and expands**, remembered per viewer in
  localStorage. Collapsed shows icons with accessible names, never a
  tooltip-only control.
- **Recents gains `+` and a sort/filter control.**
  - `+` opens **patient search first**. Create is offered only on a miss, and
    says so. This is the existing create-on-miss rule, moved to where a person
    actually starts.
  - Sort: recent, name, station. Filter: by flag, by station. Both derived
    from the queue view's declared `columns` and `badges`, so a bundle that
    declares different ones gets different filters.

## 3. Home

Three bands, in this order, because it is the order a person needs them:

1. **Greeting.** Name and role, sentence case. One line. No prose beneath it.
2. **Data.** The live line, and the declared metrics.
3. **Tasks and actions.** New, see §4.

**Cards are draggable**, with an explicit drag handle — not tap-and-hold on
the card body, which fails on touch and on crowded screens. Drop zones are
generous. Order persists per viewer in localStorage and survives a reseed.
Keyboard-reorderable too: a focused handle takes arrow keys.

**Visual direction.** The ground stays warm neutral. What changes is rank:

- Not every card is a card. The live line is the page's subject and is drawn
  flat on the ground; secondary panels get a surface; tertiary gets a rule.
- One accent, used only for "needs you". Flags, criticals, and the primary
  action. Nothing else is coloured.
- Radius, border and shadow become a three-step scale instead of one value.
- Numbers are the largest thing on the screen after the greeting.

## 4. Tasks: a new view kind

`kind: tasklist`, declared like any other view, so the laboratory gets it free.

A task is cross-thread, which is what today's kernel cannot express: the
thread view answers "what next *here*". A tasklist declares a predicate over
threads and a verb.

```yaml
id: phc.view.today-tasks
type: view
kind: tasklist
title: Needs you
capability: patient.find
workflow: phc.wf.outpatient
tasks:
  - title: Waiting on a lab result
    where: {flag: lab.ordered, not: lab.resulted}
    operation: phc.op.lab-result-enter
  - title: Consent never asked
    where: {flag: registered, not: [capture.consented, capture.declined]}
    operation: null
```

`flag` and `not` each take a scalar or a list. The first draft of this spec
wrote two `not:` keys in one mapping, which is not a list — YAML silently keeps
the last one, so the task would have matched half what it claimed. Caught in
implementation.

Each row resolves to a count and a list of threads. `operation` is optional:
a task with one is actionable from the row; a task without is a worklist.

`kernel/views.py` gains a `_tasklist` resolver beside `_queue` and `_summary`.
It reads only flags, which every adapter already serves — no new Store method.

## 5. Registration

**Templates.** Registration forms are declared, not coded, and a facility
picks one. Three ship:

- `minimal` — name, age, sex, mobile, village. What a camp needs.
- `standard` — adds category, address, emergency contact, ABHA consent. The
  default, and what the current form approximately is.
- `full` — adds allergies, current medications, past history, insurance.

These are questionnaires, which are already declarations, so this is three
files and a facility setting. `enable_when` already exists in the schema and
in `types.ts` and is read by nothing — the templates use it for skip logic, so
an established patient updating a mobile number does not walk the whole form.

**ABHA-sourced fields lock.** When a journey returns a profile, name, gender,
DOB and mobile are filled and **locked**, with one visible control to unlock
that records why. Standard ABDM practice, and it stops a local record silently
diverging from the national one. Today we chip them and let anyone type over
them.

**Acronyms.** ABHA, ABDM, PHC, OP, BP render upper case wherever they appear.
A single term list, applied by the existing `human()`/`title()` helpers, so
no call site decides casing for itself.

## 6. The chat bar

Full width, edge to edge within the thread column. Two icons live inside it:

- **Scribe** — mounts the scribe instrument, gated on `capture.consented`
  exactly as now.
- **Summarise** — opens the summary sheet.

Both are instrument and view affordances that already exist; this moves them
into the one place a person is already typing.

## What this does not do

- No patient spine. Still phase 2, still specified in the prior doc.
- No persistence for card order or role overrides beyond localStorage and an
  in-process dict respectively.
- No amend/reject loop, so the close card's quiet undo stays absent.

## Checks

- The guard renders every precondition kind as a sentence; a check asserts no
  denial message contains a raw precondition literal.
- No surface opens an operation absent from the thread's own `actions`.
- `tasklist` resolves for both bundles, and the laboratory's tasks name no
  PHC word.
- Every declared registration template compiles and validates.
- An ABHA-locked field cannot be written without an unlock reason.
- The acronym list is applied by the helpers, not at call sites: a check
  asserts no renderer file contains a hard-cased "Abha" or "Phc".
- Khoj: no `agent/say` or `Palette` identifier survives outside the
  deprecated alias.
