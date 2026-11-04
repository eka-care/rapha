---
id: phc.sched.postnatal
type: schedule
title: Postnatal home visits
summary: What this centre owes a mother in the six weeks after she delivers.
episode: postnatal
# One basis, because there is only one thing postnatal care can be measured
# from. A pregnancy can be dated three ways and each means a different number
# of days; a delivery happened on a day, and that day is day zero.
anchor:
  delivery: 0
contacts:
  - id: hbnc1
    title: First home visit
    due: 1
    opens: 0
    closes: 2
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC1
  - id: hbnc2
    title: Third day visit
    due: 3
    opens: 3
    closes: 5
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC2
  - id: hbnc3
    title: Seventh day visit
    due: 7
    opens: 6
    closes: 9
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC3
  - id: hbnc4
    title: Second week visit
    due: 14
    opens: 12
    closes: 17
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC4
  - id: hbnc5
    title: Third week visit
    due: 21
    opens: 19
    closes: 24
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC5
  - id: hbnc6
    title: Fourth week visit
    due: 28
    opens: 26
    closes: 31
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC6
  - id: hbnc7
    title: Six week check
    due: 42
    opens: 40
    closes: 45
    owner: asha
    escalates_to: anm
    operation: phc.op.postnatal-visit
    authority: statutory
    reports_as: HBNC7
---

## In plain words

Seven home visits in the six weeks after a woman delivers. Somebody goes to
the house on the first day, the third, the seventh, then once a week for
three weeks, and once more at six weeks.

They are home visits rather than appointments, and that is the point of
them: a woman who has just given birth does not come to the centre, so
anybody waiting for her at the centre will not see her.

## NEEDS SIGN-OFF

The same banner `bundles/phc/phc.sched.antenatal.md` carries, for the same
reason and with one addition.

Seven visits in six weeks, on the days below, is the shape of India's home
based newborn care. The DAYS were taken from that programme. The WINDOWS
around each day -- how early a visit may count and how late it may still
count -- were not: no published source gives them, and they are a product
choice made here so that a visit a day early is not a visit that did not
happen. A named clinical officer has to confirm both before anybody is asked
to act on a missed one.

The addition is this: **the visits in the real programme are for the mother
AND the newborn, and these are the mother's half only.** The newborn has no
record in this build, because whether and when a child becomes a patient here
is an open decision for this facility's owner. So a visit recorded against
this schedule says somebody went to the house; it does not yet say what was
found about the baby. That gap is named rather than papered over, and
closing it is a schedule for the child, on the child's own record, not more
contacts on this one.

## What a window means here

The same as everywhere else: `opens` is the first day a visit may count,
`due` is the day it is aimed at, `closes` is the last day it may still count.
Before the window it is upcoming, inside it is due, after it with nothing
against it is missed.

THE WINDOWS DO NOT OVERLAP and that is deliberate, because these visits are
close together. Two windows that touched would let a single visit on the
shared day discharge either of two contacts depending on the order they were
read in, and a mother visited once would read as visited twice. There is a
gap between the fourth week and the six week check, which is the programme's
own shape rather than a mistake here: nothing is owed in weeks five and most
of six.

## Who owns one

The ASHA, escalating to the ANM when the window closes with the visit still
undone. That is who does home based newborn care, and the lint confirms she
can: a postnatal visit needs `visit.household` and she holds it.

The lint also confirms that somebody is OFFERED it, which is a different
question and the one that caught something. The obvious operation to close
these with was `phc.op.household-visit`, the general home visit this bundle
already declares. It cannot be performed by anybody: it is loaded, it is
listed by the scribe instrument, and no step of the line draws it, so the
guard refuses every attempt. A schedule built on it would have been owed for
ever. `catalogue/ops/phc.op.postnatal-visit.md` says what was done instead
and what is still the owner's to decide.

The escalation is the ANM rather than the medical officer because the ANM is
the next person who can also go, and an escalation that hands the work to
somebody who cannot do it is a notification rather than an escalation.

## What closes one

A committed `phc.op.postnatal-visit` on a visit belonging to this episode,
inside the window. One visit closes one contact: the earliest open one whose
window contains it.

A visit recorded late closes the latest contact whose window had already
opened, which here means an ASHA entering three days of visits on the day
she gets back to the centre closes them in the order she made them.

## And what stops it

Closing the episode, with `phc.op.postnatal-close`, or never opening it. A
postnatal episode is opened by one operation only, `phc.op.delivery-record`,
which cannot be reached except on an open pregnancy and has no outcome that
means a loss. A woman who miscarried never acquires one of these, so there is
no visit to cancel, because there was never a visit to begin with.
