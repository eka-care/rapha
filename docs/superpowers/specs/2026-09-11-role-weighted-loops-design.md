# Role-weighted surface, explicit loops, and the records rail

Status: approved design, not yet built
Date: 2026-09-11
Supersedes nothing. Implementation plan to follow.

## Why

The nurse's screen carries 28 interactive targets, 92 text nodes and 178
visible words. The job on that screen is to enter four numbers.

Counted, not felt, against a running build:

- Three operations render twice. "Record vitals and triage" is in the agent's
  card and again as "Vitals" in the bottom bar. Same for ABHA and Consult.
  Half the bottom bar duplicates the thing directly above it.
- The right rail shows "Capabilities held": 19 raw slugs, `rx.prescribe`,
  `lab.result.validate`, `facility.admin`. That is a permissions debug panel
  shipped as product UI.
- Home carries two search boxes 200px apart and two chips duplicating the two
  sidebar nav items above them.
- The nurse opens onto reception's completed six-row registration card, then
  agent prose restating it.
- `DEVICE`, `IRREVERSIBLE`, `SCRIBE`, `frontdesk`, `form` render as badges.
  That is our taxonomy leaking.
- `http://localhost:8000` renders as permanent chrome.
- An agent message reads "Proposed Record vitals and triage for you to
  confirm... I have no way to do that" with no confirm affordance in reach.

And on commit the kernel toasts "Recorded" and reloads. The clerk is left
looking at a patient who is no longer their problem, with no cue what to do
next. That is the defect this design exists to fix.

## What the research supports

- Role-specific interfaces are the current consensus; the universal template
  that routes a physician, a nurse and a billing clerk through one menu
  labyrinth is the named cause of overload and long onboarding.
- Cognitive load splits in two. Better *data* usability raises germane load
  (people engage harder with meaningful information); better *system*
  usability lowers extraneous load. These pull opposite ways, so cuts must be
  aimed. Our 19 capability slugs are extraneous. A trend on a blood pressure
  would be germane. Indiscriminate stripping removes both.
- Documentation burden is driven by workflow *fragmentation*, not field count.
  Making the nurse traverse reception's context to reach her own task is
  fragmentation; adding a field to a focused form is cheap by comparison.
- Ambient AI saves real time but its output "still requires extensive human
  review", and clinicians systematically edit the model's hedging language.
  The review surface is the product. A proposal with no confirm in reach is
  the failure mode that destroys trust in all of it.

## Principles

1. The screen owes you one obvious next action. Everything else is one level
   down. Two things of equal visual weight means we have not decided.
2. Say a thing once. No operation appears in both a card and a toolbar. No
   identity renders twice within a fold.
3. Voice is a modality, not the mode. v2dd wins where hands are busy and the
   room is private. At a public counter, typing wins: you cannot say a
   stranger's phone number aloud in a waiting room.
4. The agent narrates nothing already on screen.
5. Never propose without a confirm in reach.
6. Our data model is not the user's vocabulary. Capabilities shape what is
   present, never what is displayed.
7. Cut extraneous, protect germane.
8. A role sees its own work, not the handover log.
9. Enter commits, Escape cancels, Tab never traps. For a typist the mouse is
   a failure.
10. Everything is configurable, and the presets carry 70%. See "Configurable",
    including its honest ceiling.
11. Clear beginnings and ends. Every task has a visible start, a visible
    close, and the close offers the next start.

## The mechanism: loops are already declared

`phc.wf.outpatient` gives every step a `station`, a `done_when` and its
`operations`. Two derivations, no new bundle fields:

- **Loop-closer**: the operation at my station that emits my step's
  `done_when`. `patient-register` emits `registered` and closes reception.
  `vitals-record` closes nurse. `consult-document` closes doctor, which
  correctly leaves `rx-prescribe` and `lab-order` *inside* the doctor's loop
  rather than ends of it.
- **Loop-opener**: the operation whose preconditions are satisfiable against
  an empty snapshot. Only `patient-register` qualifies
  (`preconditions: [not registered]`). Roles holding it loop on new subjects;
  roles that do not loop on the queue at their station.

`main.tsx` already has `firstOperation(cat, workflow)`, documented in its own
comment as "the bundle's own answer to what registers somebody". That is the
loop-opener. It exists; it is simply never called a second time.

Derivation is deliberate over an explicit `loop:` block per role: the facts
are already in the declarations, and a second place to state them is a second
place to be wrong.

## Role weighting: three weights

**Weight 1 - one primary action.** At a thread a role sees exactly one filled
button: the loop-closer if its preconditions hold, else the first available
operation. Everything else moves to overflow. This alone deletes the duplicate
bottom bar and the agent's three equal-weight rows.

**Weight 2 - the instrument opens; nothing offers to open it.** Every
operation declares `instrument: form | device | voice | scribe`. Arriving
where my primary action is available opens that instrument inline, focused.

This is how role-appropriate AI falls out instead of being special-cased.
`patient-register` declares `instrument: form`, so the front desk gets a form
and touches no AI, because that is what its operations declare. `vitals-record`
declares `device`; `consult-document` declares `scribe`. No rule anywhere says
"front desk gets less AI" - the declarations already said it.

**Weight 3 - other stations collapse.** Completed work from a station that is
not mine renders as one line, `Registered - frontdesk - 09:58`, expandable.
The nurse stops opening onto reception's form.

## The loop, per role

Every loop ends in a **close card**: what happened, where the patient went,
one primary cue, and a quiet undo while the operation is still `correctable`.

| Role | Opens on | Closes on | Close card cue |
|---|---|---|---|
| frontdesk | new thread, register form | `registered` | **Add next patient** (Enter) |
| nurse | queue at `nurse` | `vitals.recorded` | **Next at nurse: <name>** |
| mo | queue at `doctor` | `consult.documented` | **Next at doctor: <name>** |
| lab, lab_incharge | queue at `lab` | `lab.resulted` | **Next at lab: <name>** |
| pharmacist | queue at `pharmacy` | `dispensed.complete` | **Next at pharmacy: <name>** |
| asha, anm, cho | new thread (hold `patient.register`) | `registered` | **Add next patient** |

An empty queue says "Nobody waiting at nurse" and does not invent work.

The front desk consequence, concretely: **register, hand over, empty form
focused with the cursor in Full name.** They never see the queue, never click
a list, never navigate. Commit and type.

A role holding no loop-closer at a station (because an admin removed the
capability) falls back to the "Next at <station>" cue. A role holding no
operation at a station does not see that station at all.

## The records rail

The rail today shows our data model. It should show what the thread produced.

Three things make this cheap and non-arbitrary:

1. **The artefact types are already declared.** `phc.view.patient-summary`'s
   sections are the list: Vitals, Notes, Prescription, Investigations,
   Results. One declaration, two renderings: as a page it is the visit
   collation, as a rail it is the artefact list.
2. **They are also ABDM's units.** `care_phc/connectors/abdm/base.py:61`
   already carries `hi_type: str = "OPConsultation"`. ABDM shares health
   records as documents: Prescription, DiagnosticReport, OPConsultation,
   WellnessRecord. The rail and the ABHA share sheet show the same list.
3. **Visits are the grouping**, newest first:

```
RECORDS
  Today - 11 Sep
      Registration form       09:58 - frontdesk
      Vitals                  10:14 - nurse
  3 Aug - Consultation, Prescription
  12 Jun - Consultation, Lab report
```

Click a dated group for that visit's collation; click an artefact for that
document. A patient summary compiles down the rail.

The rail goes from four panels to two: **Where this stands** (the live loop,
germane, stays) and **Records**.

**What cannot collapse:** the guard writes audit *before* execute, so audit
rows exist for denials and rejected proposals - events that produced no
document. Those belong in the visit collation as events, not in the rail.
The rail is what exists; the collation is what happened.

`phc.view.patient-summary` is misnamed. Its title is "Visit summary - One
visit on one page" and every section is encounter-scoped. It is renamed to
what it is, and the patient-scoped view is added above it in phase 2.

## Consent

Per visit. Not patient-level, not standing, no expiry.

**Asked at reception, not at the doctor.** The consent question lives on
`phc.schema.register-v1.json`, so it is answered once at the desk and the
recording it authorises happens later in the consulting room. This is
deliberate and worth stating because it is easy to assume otherwise: it costs
the doctor no consultation time, and by the time the scribe is available the
answer is already a thread flag. The doctor's only consent surface is
`phc.op.capture-withdraw`, which asks one question and is absent unless there
is a consent to withdraw. The workflow already
states why: "a thread is one encounter, so consent is scoped to the visit and
the next encounter starts with nothing raised. There is nothing patient scoped
to leak." A consent to ambient recording that outlives the visit is not a
consent we are willing to ship.

Today the clerk reads 53 words aloud from the form's `description`. That is
replaced by a spoken instrument: the agent asks, the clerk taps the answer.

New atom `phc.inst.consent-speak`:

```yaml
id: phc.inst.consent-speak
type: instrument
kind: spoken-prompt
title: Ask for consent aloud
summary: The agent asks; the clerk taps what the patient answered.
operations: [phc.op.patient-register]
fields: [capture_consent, capture_declined]
says: >-
  May we record this visit to write your notes?
  You can say no, or stop it any time.
language: facility
spoken: true
commit: tap
fallback: text
```

On screen the question text becomes **"Record this visit?"** with Yes and No.
The 53-word `description` is deleted from `phc.schema.register-v1.json`; the
spoken line carries what it carried.

`spoken:` on the atom is the default; a facility setting overrides it, and
the override is the off switch. When it resolves false the sentence renders on
screen for a person to read and nothing else changes. The linter refuses a
`spoken-prompt` with an empty `says`, because the off switch must always have
something to fall back to.

The spoken line must convey four things and does: that it is a recording,
what for, that refusal is free, that it can be stopped. Seventeen words.
Shortening further loses one of the four.

`capture.declined` keeps its own field. A visit the patient said no to stays
visibly declined rather than merely unconsented, so no station asks twice.

## Configurable, and its ceiling

**The claim.** Everything the surface does is derived from declarations, so
configuration is not a feature bolted on - it is a consequence. The primary
action, the instrument, the loop, and the rail are all derived from the
operations a role can reach. Grant `vitals.record` to frontdesk and they get
the vitals pad, and vitals folds into their loop, with no UI work per grant.
Remove it from nurse and the pad and the loop-closer go.

**Verified, not assumed.** `kernel/proposals._decide` gates on
`drawn_by(workflow, op)`, then capability, then preconditions over thread
state. It never checks which station the actor is standing at. `station:` on
an operation orders the line; it does not gate permission. So the grant above
genuinely works today.

**Presets.** `bundles/phc/bundle.yaml` already ships nine: frontdesk, nurse,
mo, lab, lab_incharge, pharmacist, asha, anm, cho. Those are the 70%. A
facility's own combination is an `is_system=False` role in the DB, which
CARE's `sync_permissions_roles` deliberately does not touch - the bundle
comment already anticipates this. The admin surface edits a role's capability
set and saves a facility role; it never mutates a preset.

**The ceiling, stated honestly.** Two things a capability grant cannot do:

1. `drawn_by` refuses any operation the workflow does not draw. Granting
   `visit.household` to frontdesk does nothing, because `phc.op.household-visit`
   stands at `community` and the outpatient line has no such step. This is the
   guard that stopped that operation appearing on every clinic encounter. To
   give frontdesk household visits you edit the *workflow*, not the role.
   Capabilities are configurable per role; which operations exist at all is
   the workflow's call.
2. Capabilities are a flat grant. `scope_qualifier` is null on register and
   vitals, so "nurse may record vitals only for patients at their own station"
   is not expressible through a capability. It needs a scope qualifier on the
   operation.

Both belong in the admin surface's copy, not buried here: the screen should
say why a grant is inert rather than silently doing nothing.

## Phase 2: the patient spine

Not in this build. Specified so phase 1 does not foreclose it.

**A patient cannot be a single thread across visits.** Three things break:

1. Every precondition inverts permanently. `vitals-record` declares
   `preconditions: [registered, not vitals.recorded]`. Thread = patient makes
   `vitals.recorded` true forever after visit one and the nurse can never
   record vitals again. Same for register, consult, dispense. `done_when` and
   preconditions are both defined over thread state; making thread state
   lifetime state stops the workflow engine on visit two for every patient.
2. Consent leaks across visits, per the section above.
3. `station-queue` is over threads, so every patient ever joins today's line.

**Two levels instead.** Patient is the durable spine; encounter is the visit
thread, unchanged. `adapters/local/store.py` already has `encounter.patient` -
the join exists and is only ever traversed downward
(`THREAD_COLUMN` maps `patient` via `id IN (SELECT patient FROM encounter
WHERE id = ?)`, one encounter).

**The one kernel change.** Store's contract says "every read is scoped to a
thread". A spine needs a patient-scoped read: `select` and `count` take either
`thread=` or `subject=`, where subject scopes `patient` to `id` and everything
else to `encounter IN (SELECT id FROM encounter WHERE patient = ?)`. About a
dozen lines in the local adapter. It widens the Store protocol, so the CARE
adapter must honour it too - conceptually fine since FHIR Patient has many
Encounters, but the CARE adapter has never run against an authenticated
instance and this design claims nothing about it. A patient-scoped read has a
wider blast radius than a thread-scoped one, so the guard's capability check
applies at the spine, not only at the visit.

**What it buys.** Cross-visit grouping in the rail, a real patient summary,
and a true new-vs-returning distinction: a returning patient opens a new
encounter on an existing patient row, which makes duplicate patients and
duplicate ABHAs visible instead of theoretical.

## Deletions

Target: 178 visible words down to roughly 60 on the nurse's screen.

- "Capabilities held" (19 slugs). Delete.
- Bottom-bar actions duplicating the agent's rows. Subsumed by weight 1.
- Agent narration of any card already on screen.
- Home's greeting hero, its second search box, and the two chips duplicating
  sidebar nav.
- `http://localhost:8000` in the topbar.
- `DEVICE` / `IRREVERSIBLE` / `SCRIBE` badges. Irreversibility becomes confirm
  *behaviour*, not a red label.
- Identity rendered twice inside one fold.
- The 53-word consent `description`.
- Junk recents, and recents drop ids the kernel no longer serves.

## Defects found while measuring

- The home board adds a patient to recents but does not navigate.
- The thread error state does not recover on hashchange; it renders
  "Nothing at /views/thread/." with an empty id until a reload.
- `.claude/launch.json`'s `web-lab` starts against the PHC API.

## Checks

- No operation renders twice across a role's action surfaces for one thread.
- A loop-closer resolves for every station in **both** bundles. The lab bundle
  is the test that this is kernel behaviour and not PHC wiring.
- Every role in `bundle.yaml` resolves a close-card cue.
- Front desk register-to-register is reachable with keys only.
- The spoken consent line asserts all four elements; the linter refuses a
  `spoken-prompt` whose `says` is empty when `spoken: true`.
- A capability grant for an operation the workflow does not draw surfaces an
  explanation, not silence.

## Known limits

- Scope qualifiers remain unexpressible per role (see ceiling, item 2).
- Browser speech accuracy for the spoken prompt is untested.
- The CARE adapter has never run against an authenticated CARE.
- `kernel/contracts.py` says the Store has nine methods; it declares ten.
