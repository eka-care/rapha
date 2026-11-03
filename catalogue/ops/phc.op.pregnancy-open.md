---
id: phc.op.pregnancy-open
type: operation
kind: write
short: New pregnancy
title: Start a pregnancy record
summary: Open the pregnancy this centre will follow, and the date it is measured from.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - registered
  - not pregnancy.open
irreversibility: correctable
input: phc.schema.pregnancy-open-v1
writes: [episode_of_care]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        # The bundle's word for what kind of episode this is. The kernel has
        # no obstetrics in it and must not gain any: `episode_of_care` is a
        # generic table and this const is the only place the word appears.
        type: {const: pregnancy}
        status: {const: active}
        anchor_date: {answer: dating_date}
        anchor_basis: {answer: dating_basis}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pregnancy-close, phc.op.antenatal-visit]
  concepts: []
---

## In plain words

A woman is pregnant and this centre is going to follow her for nine months.
This is the record that says so, and it is the thing every later date hangs
off.

It exists because a thread is one visit. A visit is the right unit for the
guard, which asks questions about what has happened here today, and it is
the wrong unit for a pregnancy, which has a start, a sequence of contacts
and an end. A flat list of a woman's visits cannot say which of them belong
to this pregnancy, cannot carry the date the sequence is measured from, and
cannot END, so nothing derived from it can ever stop.

## Before you start

She is registered, and she has no open pregnancy already. The second
precondition is the one that matters: two open pregnancies on one woman is
not a state anyone can reason about, and the schedule derived from them
would be two overlapping arcs.

You hold `episode.manage`.

## The two questions, and why the second one is not just a date

A pregnancy is dated from something, and what it is dated from decides how
much the dates after it are worth. A remembered last period is frequently
wrong by weeks. A dating scan is good and is rarely available at a primary
health centre. A best estimate is what an experienced ANM does with a woman
who does not remember, and it is honest to call it that rather than to
write it down as a period.

So the form asks for the basis and then for the date it refers to, and both
are required. Every screen that shows a date derived from this says which
basis it came from. A contact "due in nine days" computed from a half
remembered period is a false precision, and a false precision teaches people
to ignore the tracker, which is worse than not having one.

What the basis MEANS -- how many days from that date the arc begins -- is
not here. It is the schedule's declaration, because it is obstetrics and
this operation is a form.

## What happens

One `episode_of_care` row, `status: active`, carrying the date and the
basis. No flag is emitted: `pregnancy.open` is derived from the rows, the
way almost every flag here is, so it is true for the next visit and the one
after without anything being carried between threads.

Nothing is scheduled by this operation. A schedule is derived from this row
and the schedule declaration, at the moment somebody asks, and derived is
the whole point: when the date is corrected, the arc moves, and when the
pregnancy ends there is nothing left to chase because the thing that
generated the chasing has stopped.

## How you know it worked

The pregnancy appears on the patient's record and the woman's later visits
sit under it rather than beside it.

## When it goes wrong

- **The date was wrong.** Correct it. This is `correctable`, the amend path
  applies while the visit is open, and the whole arc moves with it, because
  nothing downstream was written down.
- **She is not pregnant after all.** Close it, with that outcome. Do not
  delete it: a record that was made and found to be wrong is part of what
  happened.
- **An ASHA reported it and nobody at the centre has confirmed it.** The
  ASHA cannot open this: `episode.manage` is held at the centre and by the
  ANM, and not by `asha`. That is a DELIBERATE DEFAULT AND AN OPEN QUESTION,
  not a settled position. The argument for letting an ASHA open one is that
  the woman with the least contact with the system is otherwise the one
  nobody tracks; the argument against is that a pregnancy nobody has
  confirmed starts a schedule that chases somebody. It is decision 6 in
  `docs/superpowers/specs/2026-11-04-maternal-and-child-health-design.md`
  and it is the owner's.

## Verification

Unverified against CARE. `episode_of_care` is a new table in the local
adapter and has no CARE counterpart confirmed yet; FHIR R4 EpisodeOfCare is
what it is shaped from.
