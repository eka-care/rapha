# Maternal and child health, end to end

Design, 2026-11-04. Status: **eight decisions open (§11), three of them
inherited and still unanswered.**

This is the note `2026-11-04-the-build-plan.md` §3 should be built from. That
section lists five things that do not exist -- a referral that stays open,
reminders, tasks that outlive a visit, a district tier, and the pregnancy as
a spine rather than a list of visits -- and they are not five things. They
are one missing object and one missing word in the query grammar, which is
the finding this note is written around.

Nothing here is clinically signed off. Every schedule line in §4 is the
shape of the Indian programme as this build understands it, and each one
needs confirming against the current national operational guideline by a
named clinical officer before it is offered to anybody. That is the same
banner `bundles/phc/bundle.yaml` puts on its three templates and
`terminology/condition-code.json` puts on its three concepts, and it is not
a formality: a schedule is a clinical protocol whether or not we call it
one.

## 1. The finding: there is no clock

Rapha can already do a surprising amount of this. It has a community
station, ASHA and ANM roles with their own capabilities, a household visit
operation, an antenatal template, a catchment that maps a village to its
sub-centre and its worker, a scribe that fills declared fields from speech,
and an ABDM document path. What it cannot do is the one thing a tracker is.

**Every flag in this product is a count with no date in it.** A state rule is
`exists`, `gte` or `all_of` over `{resource, where}`, and the only
time-relative value the grammar has anywhere is `window.start`, which works
in a metric and nowhere else. So the kernel can answer "has this woman had an
antenatal visit" and cannot answer "is one due", because due is a comparison
against today and there is no today.

This was found once already and written down. From
`2026-09-15-glass-heidi-build-plan.md`:

> ALSO DEFERRED, AND I WILL NOT FAKE IT: the follow-up cohort.
> `followup.booked` is `exists: {resource: token_booking, where: {status:
> booked}}` and nothing anywhere ever writes a different status, so the flag
> never clears. The cohort question is date-relative ("booked to come back
> and has not"), which neither the state-rule grammar nor an equality filter
> can ask. Do not ship a row that only grows.

That paragraph is the whole of maternal tracking in miniature. `followup.booked`
is in the shipped bundle today, derived from a resource no operation writes,
and `appointment.book` is a capability four roles hold and no operation
declares. The product has an appointment-shaped hole with a label on it.

So the smallest extension that unlocks the rest is **a clock in the query
grammar**: one more condition value, `now`, with an optional offset, usable
in a `where` exactly as a literal is.

```yaml
# a task whose window has closed and which nothing has discharged
overdue:
  exists: {resource: task, where: {status: open, closes: {lt: now}}}

# the same question a metric would ask, already possible there
numerator: {resource: encounter, where: {created_date: {gte: window.start}}}
```

The adapter can already do the comparison: `adapters/local/store.py`
supports `gte`, `lt`, `gt` and `lte`, and ISO dates sort as strings. What is
missing is the token and its resolution. That is a small change in one
place, and §9 says what it costs in Go.

**Both engines must take `now` from the request, not from their own wall
clock.** `scripts/check_go_parity.py` asks two kernels the same question over
two sockets and diffs the answers. Two wall clocks milliseconds apart will
flap that diff on any row sitting exactly on a boundary, and a check that
fails one run in fifty is a check people learn to rerun. The request carries
the instant; the kernel evaluates against it; the gate stays deterministic.

## 2. One object, not four

The build plan asks whether a referral, a reminder, a follow-up and a task
are one object with a type or four things, and says to argue it rather than
assume. They are **two** objects, and the split is not where it looks.

Three of them are the same thing. A referral to a first referral unit, a
scheduled antenatal contact and a follow-up all answer the identical
question: *something is owed, by someone, by a date, and here is what would
discharge it.* They differ in who owns it, how long the window is, and what
counts as discharge -- and all three of those are fields. A type that only
changes field values is not a type, it is a value.

A reminder is different in kind, and folding it in would be the mistake.
A reminder is not a thing owed; it is **an action the system takes about a
thing owed**. If a reminder were a task it would need its own due date,
its own owner and its own closure, and you would be chasing reminders about
reminders. It is an attempt, and attempts belong to the task they chase,
as a log: when we called, which number, which provider, what came back.
That log is also the only honest answer to "did anyone actually try", which
is the question a district asks and the one nobody can currently answer.

So: **`task`, and `task_attempt`.**

### What a task is

| field | why it is there |
|---|---|
| `subject` | the patient, always; the episode (§3) when it has one |
| `type` | referral, contact, follow-up, home visit, immunisation due |
| `due` | the date it is aimed at |
| `opens`, `closes` | the window, see below |
| `owner` | a role, from the bundle's own `roles` |
| `escalates_to` | a role, when the window closes with it open |
| `status` | open, done, cancelled, expired |
| `closed_by` | what discharged it: the encounter, the row, the person |
| `origin` | the schedule line and generation that produced it, or the operation that raised it by hand |

**The window is the part everyone gets wrong.** A visit due at 28 weeks is
not late at 28 weeks and one day. A contact has a date it is aimed at and a
span either side in which arriving is simply arriving: inside the window it
is pending, after it closes it is missed. Collapsing that to a single date
produces a screen that is red every day for women who are doing nothing
wrong, and a screen that is red every day is a screen nobody reads. The
window is also what makes a rural schedule honest, because a woman who comes
nine days after the day we picked has not failed and neither have we.

**What closes it is a query, declared per type, not code.** That is what
makes the owner's open question answerable in one line instead of a
rewrite:

```yaml
closed_by: {resource: encounter, where: {kind: antenatal, created_date: {gte: opens}}}
```

Whether a referral is closed by the receiving facility's own record, by the
sending clinician ticking it, or by the agent seeing a document appear is
**decision §11.2 and still the owner's.** The mechanism above holds all
three, and the third is only available where there is a network, which is
the argument the decision actually turns on.

**A missed task is not deleted and not a failure flag on a woman.** It
expires, it keeps its window, and it escalates to the next role. The record
of what the centre owed and did not do is the thing a district tier is for,
and deleting it to keep a dashboard green is the single most tempting bad
idea in this whole design.

### Where this lands in the vocabulary

`task` is already a word here, in two places, and neither is this.
`catalogue/vocab.py THREAD_OBJECTS` has `task` as a way of *drawing* a thread
row, and `web/src/thread/Thread.tsx` says in a comment that Task and Comment
are not drawn "because the kernel has no row behind either". This note is
the row behind it. `bundles/phc/phc.view.today-tasks.md` is a view that
derives today's work from flags; once tasks are rows, that view gets simpler
and starts telling the truth across days instead of within one.

## 3. The pregnancy is an episode, and the spine has three levels

`kernel/spine.py` joins encounters by a field on the subject: the workflow
declares `spine: patient` and the route returns the patient row plus every
thread that shares it. That is a flat list, and the build plan §3.5 is right
that a pregnancy is not a list:

> a pregnancy has a start, an expected date, a sequence of contacts and an
> end. `Earlier visits` shows a list; this needs an arc.

A list cannot say which visits belong to *this* pregnancy, which is the first
question anyone asks about a woman on her third. It cannot carry an expected
date for the schedule to hang off. It cannot end, so it cannot stop chasing.

So the spine gets a middle level: **patient, episode, encounter.** The
workflow declares the episode the way it already declares the spine:

```yaml
subject: encounter
spine:   patient
episode: pregnancy        # optional; a bundle with no episodes declares none
```

This is FHIR's `EpisodeOfCare` and not an invention: status, period,
patient, type, care manager and diagnosis are its own fields, and a
pregnancy is the textbook example of one. A bundle that declares no episode
behaves exactly as today, which matters because `bundles/lab` must not grow
a pregnancy.

The child gets its own patient record and its own episode -- the first two
years -- linked to the mother by `RelatedPerson`. **When that record comes
into existence is decision §11.8.** The case for creating it at birth is
that the immunisation schedule starts at birth and a birth dose given to a
child with no record is a dose nobody can count. The case against is that a
patient record created in a delivery room with no identity attached is the
thing that later merges wrongly, and merging two children's records is the
same irreversible harm as merging two ABHA numbers.

## 4. The schedule: what it is and where it comes from

A schedule is the declaration; the tasks are what it produces for one woman.
In FHIR terms the schedule atom is a `PlanDefinition` and the generated set
is a `CarePlan` whose activities are the tasks. Saying that is not
decoration: it means this atom type has a counterpart in the standard we
already publish into, rather than being a shape we made up.

### Why this is a sixth declaration type

`bundles/phc/bundle.yaml` argues against new types, and it is right to. The
plugins key says it plainly: a grouping of ids "costs nothing, and a
declaration type costs a manifest entry, a lint pass, a dataclass, a
compiled key, a Go struct and a renderer type". Templates, plugins,
facilities and the catchment are all keys in `bundle.yaml` for that reason.

A schedule is not a grouping of existing ids. It carries data that exists
nowhere else -- offsets, windows, owners, an authority per line -- and it
needs a prose body saying where each line came from and who signed it off,
the way the templates carry their `sign_off`. A clinical protocol folded
into a YAML key with no body is the exact shape of a schedule nobody can
audit. So it pays the six costs, and `type: schedule` sits beside
`bundle.yaml` with the workflow and the views.

```yaml
id: phc.sched.antenatal
type: schedule
title: Antenatal contacts
subject: pregnancy              # an episode type, not an encounter
anchor: edd                     # the date every offset is measured from
contacts:
  - id: anc1
    title: First antenatal contact
    due:    {before_anchor: 196}      # about 12 weeks of a 280 day pregnancy
    window: {opens: 266, closes: 168} # days before the anchor; opens early, closes late
    owner: anm
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: ANC1
```

`authority` is the field that keeps this honest, and it has three values:

- **statutory** -- the programme requires it and the centre reports it. The
  four antenatal contacts of the RCH register, the Td doses, the
  immunisation schedule. A centre may not switch these off.
- **clinical** -- good practice the centre follows. The WHO 2016 eight
  contacts beyond the statutory four sit here.
- **centre** -- this facility's own choice.

Without that field a centre cannot tell what it is obliged to do from what
somebody added, and the first dispute with a district officer settles it the
wrong way.

### The shape of the real schedules

Each line below needs sign-off. They are written here so the atom has
something concrete to be checked against, not because this build has
verified them.

**Antenatal.** India's programme requires a minimum of four contacts: one in
the first trimester, one between roughly 14 and 26 weeks, one between 28 and
34, and one from 36 weeks to term. WHO's 2016 model is eight contacts, at
roughly 12, 20, 26, 30, 34, 36, 38 and 40 weeks. A centre doing eight still
*reports* four, which is why `reports_as` exists: the schedule carries both
the contact it keeps and the register line it fills. Pradhan Mantri
Surakshit Matritva Abhiyan adds a specialist antenatal check on a fixed
monthly day for women in the second and third trimester, which is a contact
whose due date comes from a calendar rather than from the anchor -- the one
line in this whole design that does not hang off the EDD, and the reason
`due` needs a second form.

**Iron and folic acid, and Td.** IFA is a daily tablet through the back two
trimesters and on through the postnatal period, with albendazole once after
the first trimester. Td is two doses a month apart, or a single booster for
a woman vaccinated recently enough. These are not contacts and must not be
modelled as visits: they are **supply and coverage**, and what a tracker owes
is "has she been given them" rather than "has she turned up". They attach to
a contact as something that contact must record, not as tasks of their own.

**Postnatal and the newborn.** Home based newborn care is a fixed day
sequence from birth -- the first within 24 hours, then roughly days 3, 7,
14, 21, 28 and 42, with the first visit happening at the facility when the
delivery was institutional and at home when it was not. So the schedule
branches on how the woman delivered, which means a schedule line needs
`applies_when`, exactly as a workflow step already has one. The young child
visits continue at three-monthly intervals through the second year.

**Immunisation.** Birth doses, then contacts at 6, 10 and 14 weeks, then 9
to 12 months, then 16 to 24 months. This is the one schedule where the
window is tight at the start and wide later, and where a missed dose does
not simply expire: it leaves a child due for a catch-up, which is a
different task from the one that was missed. **Catch-up is not modelled in
this note** and is named as a gap rather than hidden: it needs a rule per
antigen and that is a clinical list, not a mechanism.

## 5. What starts a pregnancy, and the EDD it starts with

The schedule hangs off the expected date of delivery, so how confidently we
know that date decides how much the schedule is worth. Four things can start
a pregnancy here and they are not equal:

| what started it | what it gives | confidence |
|---|---|---|
| last menstrual period, recalled | EDD by dating rule | poor, and poorer the further from the event |
| a confirmed pregnancy test at the centre | a floor on gestation, not an EDD | partial |
| an ASHA's report from a household visit | a pregnancy, often no date at all | poor |
| a dating scan | the best EDD available | good, and rarely available at a PHC |

A recalled last menstrual period is the common case and it is frequently
wrong by weeks. So **the EDD carries its basis and its confidence, and the
schedule says so on screen.** A contact "due in nine days" off a date the
woman half remembers is a false precision that trains people to ignore the
tracker. Showing "due this month, dated from a recalled period" is less
exact and more true.

An ASHA's report with no date at all still has to start something, because
the alternative is that the woman with the least contact with the system is
the one nobody tracks. The answer is an episode that exists with no anchor:
it generates exactly one task -- *get her dated* -- owned by the ANM, and
the rest of the schedule appears when the anchor does. **Whether an
unconfirmed report should create an episode at all is decision §11.6.**

## 6. How the schedule moves

A schedule that cannot be rewritten is worse than none. A schedule that
silently keeps chasing a visit for a pregnancy that ended is the failure
that would end this product, and it is not a hypothetical: it is the
default behaviour of every naive implementation, because nothing in a
generated row knows that the world changed.

The rule is one sentence. **Tasks are generated from the schedule and the
anchor, and regenerating never destroys evidence.**

- **The EDD is corrected.** A scan at 14 weeks moves the date by three
  weeks. Every open task that nothing has touched is cancelled and replaced
  at the new offsets. A task that was already completed stays completed and
  keeps the window it was completed against, because moving it would rewrite
  what happened. A task somebody has attempted but not closed keeps its
  attempts and gets the new date, because the chase is still the same chase.
- **The baby comes early.** Delivery ends the antenatal episode on the day
  it happens. Every open antenatal task is cancelled with the reason
  `delivered`, visibly, on the thread. The postnatal and newborn schedules
  start from the birth date, not from the EDD, and they start for the child
  as well as the mother.
- **The pregnancy ends without a baby.** A miscarriage or a termination ends
  the episode the same way, with its own reason, and this is the case where
  a cancelled task must leave **no trace that chases anybody**. A woman who
  has lost a pregnancy must not get a call asking why she missed her 28 week
  visit. The only acceptable implementation is that ending the episode
  cancels tasks in the same write, atomically, and the outbox holds nothing
  that was queued before it.
- **Twins.** One pregnancy, one antenatal schedule: the mother has one arc
  and the contacts are hers. At delivery the child side becomes two
  episodes, two patient records, two immunisation schedules. A twin
  pregnancy may carry extra contacts, which is a clinical line with an
  `applies_when`, not a second schedule.
- **She moves.** A woman who leaves the catchment is the case this design
  handles worst and the one the Hera deck's district tier would exist to
  fix. Today her tasks would simply go on being overdue at a centre she will
  never visit again. The minimum honest behaviour is a `transferred` end
  state that stops the chase and keeps the record; a real handover to
  another centre needs the district tier and is **decision §11.3**.

Two properties fall out of this and are worth stating as rules rather than
leaving implicit:

1. **Ending an episode is irreversible in the guard's sense** and must be
   confirmed by a person on the rendered surface. An agent may propose that
   a pregnancy ended; it may never commit it.
2. **A cancelled task says why it was cancelled, on the thread.** The
   build plan's simplicity pass folded system events away; this is the one
   kind that must stay legible, because "why did we stop chasing her" is a
   question with a safeguarding answer.

## 7. Who is chased, how, and what the message may say

`2026-11-03-eka-scribe-backend-notes.md` §5 and §6 settle most of the
mechanism and one of the policies.

The mechanism is Eka's existing telephony layer -- Vobiz, Exotel and Plivo
behind one interface, with a phone-number-to-workspace table. There is no
case for adding Twilio, which the Hera deck names: a fourth provider behind
an interface that already has three is a dependency bought for nothing.

The policy is Eka's own house rule, quoted in §6 of that note: webhook
payloads are identifiers only, and the client fetches details over an
authenticated API, to keep patient data out of the channel. That is exactly
the right rule for a reminder and it is now the platform's practice rather
than our preference.

So **a reminder names no clinical fact.** It says a visit is due at the
centre and gives the centre's own number or token. It does not say pregnant,
does not say high risk, does not carry a result and does not name a
condition. This is not only a data protection position. In a village the
handset is often shared and frequently is not the woman's: a message naming
a pregnancy is a disclosure to the household, and for an unmarried woman, or
one who has not told her family, that disclosure can be dangerous. The
identifiers-only rule is a safeguarding rule here, not a compliance one.

The ladder is: the task's `owner` is chased first, their `escalates_to`
second. For a home visit that is the ASHA then the ANM; for a facility
contact it is the woman then her ASHA. **Whether anything is sent at all in
the first version, or whether the system only shows the overdue list to the
centre, is decision §11.4.** Showing is most of the value and carries none
of the disclosure risk, and it is what the smallest demo should do.

## 8. The use cases, grouped

Each group says who does it, where, what is recorded, what exists today and
what is missing. "Missing" means missing in the declarations, which is the
only kind of missing that matters here.

### Before the pregnancy is known

**The ASHA's household visit.** The ASHA, at the door, speaking.
`phc.op.household-visit` exists, runs on the scribe, takes its own consent at
the door, and asks four questions, one of which is a boolean
`followup_needed` that goes nowhere. The atom itself promises more than the
product does: "Anything needing follow up appears as an action rather than
as a note somebody has to read." It does not. That boolean becoming a task
is the single smallest change in this whole note and the one that makes the
atom's own promise true.

Missing: a pregnancy can be reported but not registered as an episode; there
is no eligible-couple or pregnancy-surveillance list; the visit cannot start
a schedule.

### Antenatal

**The ANM's sub-centre day.** The ANM, at a sub-centre or an outreach
session, with a register. `phc.op.antenatal-visit` exists as a template:
four free-text boxes -- history, examination, assessment, plan -- and its own
sign-off says it codes nothing, because `terminology/condition-code.json`
holds three concepts and none is obstetric.

Missing, and this is the largest content gap in the note: **an antenatal
visit records numbers, and this build has codes for six of them.**
Gestational age, fundal height, fetal heart rate, haemoglobin, urine protein
and sugar, and the mother's weight gain are all observations with LOINC codes
and none is in `observation-code.json`. Each one needs a verified entry
produced by `scripts/seed_terminology.py` against a terminology server, the
way the six vital signs were. Until then an antenatal visit is narrative text
in a document, which is a record and not a measurement, and nothing can trend.

**High risk identification.** Severe anaemia, high blood pressure with
protein, a previous caesarean, age at the extremes, short stature, a
previous loss. Today the kernel raises `vitals.flagged` from declared ranges
and the deck's safety slide says the AI never stratifies risk. **That
contradiction is decision §11.1 and is inherited unanswered.** The
recommendation in the Hera note stands: keep the flags and change the slide,
because declared deterministic rules from a bundle are a stronger story than
the one the slide tells.

What is genuinely missing is not the flagging. It is that a flag today is
scoped to one visit -- `vitals.flagged` is a thread flag and a thread is an
encounter -- so a woman flagged at 20 weeks arrives at 28 weeks with a clean
screen. **A risk marked on a pregnancy belongs on the episode, not on the
visit**, and that is a second reason the episode has to exist.

**Referral to a first referral unit.** The doctor or the ANM, from the
centre. Today this is a sentence in a handover note:
`phc.op.handover` writes one `questionnaire_response`, has no addressee
column, deliberately closes nothing and explicitly "moves nobody". It is the
right object for a conversation and the wrong one for a referral, and the
atom says so in its own words. A referral is a `ServiceRequest` for the
clinical ask and a `task` for the chase of it, with
`Task.focus` pointing at the request -- which is the pattern FHIR already
has for exactly this.

### Delivery and immediately after

**Delivery.** Often not at this centre, and frequently recorded here after
the fact from what the woman brings back. Missing entirely: there is no
delivery operation, no place for mode of delivery, outcome, birth weight or
attendant. The schedule cannot branch on institutional versus home delivery
without it, and §4 says the newborn sequence does branch.

**The immediate postpartum.** Nothing exists. The first 24 hours carry most
of the maternal mortality this programme is aimed at.

### Postnatal and the child

**Postnatal visits and home based newborn care.** The ASHA, at home, on a
day sequence. The household visit operation is the right shape and the
schedule is what makes it a sequence rather than a hope.

**Newborn danger signs.** A fixed assessment with a referral threshold. The
household visit atom already states the rule this must follow: "assessment
scoring is computed by rule and never by the model... The threshold comes
from the instrument, which carries a version and a named clinical owner." So
the mechanism exists in principle and the content does not.

**Immunisation.** Nothing exists. No `Immunization` resource, no projection
for one in `kernel/fhir.py`, no antigen value set. This is a resource
addition, a projection, a value set and a schedule.

**Growth monitoring.** Weight exists as a coded vital. Length, head
circumference and mid-upper-arm circumference do not, and neither does the
derived z-score. A z-score is computed from the WHO tables and is a
**rule, not a model**, which puts it on the right side of the deck's safety
line and makes it the most defensible piece of analysis in the product.

**Anaemia.** Spans both halves: haemoglobin at antenatal contacts, IFA
supply, and the child later. Needs the haemoglobin code and needs supply
modelled, per §4.

**The child's record coming into existence.** Covered in §3 and open as
decision §11.8.

### Across all of it

**Family planning.** Postpartum contraception is part of the same arc and is
a counselling contact plus a supply record. Not modelled; named here so it
is not forgotten when the arc is drawn.

**The district.** Counts across centres, overdue caseload, capacity.
Decision §11.3, inherited and unanswered.

## 9. What this costs in declarations and in Go

| change | where | twice for Go? |
|---|---|---|
| `now` in the query grammar | `catalogue/`, the state evaluator, the adapter | yes, and both must read the instant from the request |
| `task` and `task_attempt` resources | `catalogue/vocab.py CARE_RESOURCES`, the adapter's tables | yes, the adapter half |
| `episode_of_care` resource and `episode:` on a workflow | same, plus `kernel/spine.py` | yes |
| `type: schedule` declaration | a sixth type: lint, dataclass, compiled key, Go struct, renderer | yes, the compiled key and the struct |
| task generation from a schedule | `kernel/`, pure, no I/O | yes |
| a route for a subject's arc and its tasks | `kernel/api.py` | yes; `check_go_parity.py` diffs every route |
| new operations: delivery, episode end, referral, immunisation, growth | `catalogue/ops/*.md` plus questionnaires | no, atoms are shared |
| obstetric and paediatric codes | `terminology/*.json` via `scripts/seed_terminology.py` | no, generated data |
| `Appointment`, `Immunization`, `CarePlan`, `RelatedPerson`, `EpisodeOfCare` projections | `kernel/fhir.py` | not yet; Go does not publish documents |

The renderer gets no new clinical words out of any of this, which is the
test that it has been done correctly. An arc is drawn from a declared
schedule and a list of tasks the kernel returns, the same way the queue is
drawn from a declared view. If `web/` ever has to name a contact, the design
is wrong.

## 10. FHIR, ABDM, and the registers that will disagree

| the thing | the resource |
|---|---|
| the pregnancy | `EpisodeOfCare`, type pregnancy, with its period |
| the expected date and its basis | `Observation`, coded, with the dating method recorded |
| the schedule as declared | `PlanDefinition` |
| the schedule as instantiated for one woman | `CarePlan`, activities referencing the tasks |
| a scheduled contact | `Task`; `Appointment` as well where a real slot is booked |
| a referral | `ServiceRequest` for the ask, `Task` with `focus` for the chase |
| a contact that happened | `Encounter` plus its `Observation` rows |
| a vaccine given | `Immunization` |
| growth, haemoglobin, blood pressure | `Observation` |
| a risk condition | `Condition` |
| mother to child | `RelatedPerson` |

Three collisions with the Indian programme's own registers, and none of them
is solved by the table above.

**The RCH identity is a second identity.** A pregnant woman gets an RCH
number, which is not her ABHA and not our patient id, and the sub-centre
register is keyed on it. A record that cannot carry it cannot be reconciled
with the portal the ANM is actually judged on. It is an identifier on the
patient or the episode, and it is not optional if an ANM is ever to use this
instead of her register rather than beside it.

**The register counts four contacts and a centre may do eight.** This is why
`reports_as` is in the schedule atom in §4. Without it, a centre following
WHO's model reports eight ANC1s or reports nothing coherent, and the first
monthly report settles the argument against the software.

**The Mother and Child Protection card is paper, is the household's, and is
the source of truth in the room.** The woman brings it; it has doses and
dates in it that our record does not; it is frequently more complete than
anything a centre holds. So **a contact must be recordable retrospectively**
-- recorded today, dated to when it happened, attributed to whoever did it
elsewhere -- and the task it closes must accept being closed late and out of
order. A tracker that can only record what happens in front of it will be
wrong about every woman who was seen anywhere else, which in this programme
is most of them.

## 11. Decisions, none of them mine

1. **Do flags stay automatic?** Inherited, unanswered, urgent. §8 adds a
   reason to answer it: risk has to move from the visit to the pregnancy
   either way, and whether a clinician must confirm it changes that work.
   Recommendation unchanged: keep the flags, change the slide.
2. **What closes a referral?** Inherited, unanswered. §2 makes it a declared
   query per task type, so the answer is one line rather than a rewrite --
   but it is still an answer somebody has to give.
3. **Is the district tier real or seeded?** Inherited, unanswered. §6's
   transfer case and §8's district group both wait on it.
4. **Does the first version send reminders, or only show the overdue list?**
   Showing is most of the value and carries none of the disclosure risk.
5. **Whose phone, and what may a message name?** §7 argues identifiers only
   and treats it as safeguarding rather than compliance, but whose number we
   hold -- the woman's, her husband's, the ASHA's -- is a programme decision.
6. **Does an unconfirmed pregnancy report create an episode?** §5. Saying no
   means the woman with least contact is the one least tracked.
7. **Four antenatal contacts or eight in the shipped bundle?** Reporting is
   four. The schedule can carry both, but which the centre is held to is not
   ours to pick.
8. **When does the child's record come into existence?** §3. At birth it can
   be counted; before identity it can be merged wrongly.

## 12. Order, by dependency, and the smallest demo

No dates: the hackathon date is still unknown. This is a dependency order.

1. **`now` in the query grammar**, both engines, reading the instant from the
   request. Nothing else in this note works without it, and it is small.
2. **The `task` resource and `task_attempt`**, with the guard and the audit
   treating a task write like any other write.
3. **The episode**, and `episode:` on the workflow, and the three-level
   spine.
4. **The `schedule` declaration** and generation from it.
5. **The movement rules of §6**, with ending an episode irreversible and
   cancellation visible. This must land with step 4, not after it: a
   generator without a cancel is the failure mode named at the top of §6.
6. **The arc view** -- the pregnancy drawn as a sequence of contacts with
   their windows, which is the screen the deck is really promising.
7. **The referral as `ServiceRequest` plus `task`**, which is "every
   referral closed".
8. **The obstetric and paediatric codes**, which can start any time and
   gates nothing above it except the measurements being measurements.
9. **Delivery, the newborn schedules, immunisation, growth.**
10. **Chasing**, last, because §11.4 may say we do not.

**The smallest credible demo** is steps 1 to 6 plus a hand-raised referral,
on one woman:

She is registered. An ASHA's household visit reports the pregnancy, and the
centre dates it. Her arc appears: contacts with windows, one done, one due
this fortnight, one overdue and escalated from the ASHA to the ANM. The ANM
records a contact and the overdue one closes in front of you. A referral is
raised and stays open on the district list until something closes it. Then
the delivery is recorded early, and every remaining antenatal contact
cancels on screen with the reason written on it.

That last beat is the one to demo deliberately. Everyone shows the happy
path. Showing the system stop chasing a woman whose pregnancy has ended is
the thing that tells a judge this was built by people who thought about her.
