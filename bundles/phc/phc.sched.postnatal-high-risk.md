---
id: phc.sched.postnatal-high-risk
type: schedule
title: Day 45 check after a high-risk delivery
summary: The one outcome check this centre owes a high-risk mother 45 days after she delivers.
episode: postnatal_high_risk
# Measured from the day she delivered, the same day zero as the ordinary
# postnatal schedule.
anchor:
  delivery: 0
contacts:
  - id: hbnc45
    title: Day 45 check
    due: 45
    opens: 45
    closes: 52
    owner: anm
    escalates_to: cho
    operation: phc.op.postnatal-outcome
    authority: statutory
    reports_as: HRP-OUTCOME
---

## In plain words

One check, by the ANM, 45 days after a high-risk woman delivers. It records
whether mother and baby are well, and it ends this episode.

## Why only one contact is here

A high-risk delivery opens TWO postnatal episodes in the same act. The
ordinary one, `postnatal`, carries the seven home visits and is described in
`bundles/phc/phc.sched.postnatal.md`. This one, `postnatal_high_risk`, carries
only what is extra for a high-risk woman. The seven visits are not copied
here, because a copied schedule is a schedule that drifts: change the visits
in one place and they change for every mother.

So a high-risk mother is visited at home exactly as any mother is, and in
addition the ANM makes this check. The two episodes are closed separately.
The home visits end with `phc.op.postnatal-close`; this one ends when the
outcome is recorded with `phc.op.postnatal-outcome`.

## NEEDS SIGN-OFF

The programme tracks a high-risk woman to day 45. The day is the programme's
number. The window (the day itself, and seven days after it) and the owner
are this bundle's choice, and a named clinical officer has to confirm both
before anybody is asked to act on a missed one. The check is the ANM's and
not the ASHA's because it confirms an outcome rather than checking on a
newborn at home.

## What a window means here

`opens` is the first day the check may count, `due` is the day it is aimed
at, `closes` is the last day it may still count. Before the window it is
upcoming, inside it is due, after it with nothing against it is missed.

## What closes it

A committed `phc.op.postnatal-outcome` inside the window. Recording it also
ends the episode, whatever the outcome, so a mother whose outcome was poor is
not chased for ever. What went wrong is for the follow-up question on the
form and for the doctor.

## And what stops it

Recording the outcome, or never opening it: only a high-risk delivery opens
this episode, and a pregnancy that ended any other way never acquires one.
