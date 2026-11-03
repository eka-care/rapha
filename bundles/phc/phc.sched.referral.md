---
id: phc.sched.referral
type: schedule
title: Chasing a referral
summary: What this centre owes a woman it sent somewhere else.
episode: referral
anchor_from: opened
anchor:
  raised: 0
contacts:
  - id: confirm
    title: Find out what happened
    due: 7
    opens: 2
    closes: 30
    owner: nurse
    escalates_to: mo
    operation: phc.op.referral-close
    authority: centre
---

## In plain words

A referral that is raised and never followed up is a referral that did not
happen. This says that somebody at the centre owes an answer about it, and
when.

It is one contact. Seven days after she was sent, somebody should know
whether she went; the window opens on the second day, because a woman sent
yesterday has not failed to go yet, and shuts after a month, because a
referral nobody has chased in thirty days is not being chased.

## Why this is a schedule and not a special case

Everything in the antenatal schedule applies here unchanged: a window
rather than a date, an owner who is a role, an escalation when the window
shuts, and a contact that is DERIVED rather than stored so it disappears
the moment the referral is closed. Writing a second mechanism for "chase
this" would be writing the first one again with different words.

The only thing that differs is where the dates are measured from. A
pregnancy is measured from a date somebody recorded, because the thing it
is measured from happened before the record of it. A referral is measured
from the moment it was raised, which IS the record, so this declares
`anchor_from: opened` and nobody is asked to type today's date on a form.

## Who chases it

The staff nurse, escalating to the medical officer. It says `nurse` rather
than `cho` or `anm` for a reason the lint supplied: closing a referral
needs `handover`, and of this bundle's nine roles the three community ones
do not hold it. `phc.op.handover` says the same thing about itself in its
own words.

Whether a community worker should be able to close a referral she is the
one chasing is a live question and not one to settle in a schedule file.
It is the same shape as the ANM holding `encounter.document`, which
`phc.sched.antenatal` raises, and both are the owner's.

## The authority

`centre`. This is not a statutory contact and it is not clinical guidance.
It is this facility saying how long it is prepared to leave a referral
unanswered, which is exactly the kind of thing the third authority value
exists for, and a centre that wants three days instead of seven edits one
number.

## What closes it

`phc.op.referral-close`, which asks what happened and for the evidence. It
closes the referral and this contact together, because the contact is
derived from the referral being open and there is nothing left to derive
it from.

**The deeper question of what SHOULD close a referral is not settled** and
is decision 2 of the design note. This chases; it does not decide what
counts as an answer.
