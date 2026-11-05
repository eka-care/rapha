---
id: phc.op.pregnancy-close
type: operation
kind: write
short: End pregnancy
title: Close a pregnancy record
summary: Record how the pregnancy ended, and stop everything still scheduled for it.
capability: episode.manage
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - pregnancy.ordinary
irreversibility: correctable
input: phc.schema.pregnancy-close-v1
writes: [episode_of_care]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: pregnancy}
        # The SECOND row. An episode ends by gaining one rather than by
        # having its first rewritten, because every clinical table here is
        # insert only and the audit has to keep both halves. `pregnancy.open`
        # is the count comparison between the two.
        status: {const: ended}
        outcome: {answer: outcome}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pregnancy-open, phc.op.pregnancy-close-high-risk]
  concepts: []
---

## In plain words

The pregnancy is over, however it ended, and this is what says so. It is
the most important operation in the maternal half of this product, and not
because of what it records.

It is important because of what it STOPS.

## The failure this exists to prevent

A tracker that cannot be told a pregnancy has ended goes on chasing it. The
woman who has just lost a baby gets the call asking why she missed her
twenty eight week visit. That is not a bug report, it is the thing that
would end this product, and no amount of apologising afterwards undoes one
phone call.

So the architecture is arranged so that stopping is not something anybody
has to remember to do. Nothing scheduled is written down anywhere: a
contact is DERIVED, at the moment somebody asks, from this pregnancy and
the schedule declaration. The moment this row exists the pregnancy is no
longer open, the derivation stops producing contacts, and there is nothing
left to chase. There is no queue to drain, no rows to cancel and no outbox
holding something queued a minute ago.

That is the whole argument for deriving rather than generating, and it is
worth more than the convenience: a generated schedule needs somebody to
remember to cancel it, and "somebody remembered" is not a safety property.

## Before you start

There is an open pregnancy, and it has not been marked high risk. If it has,
this form is not offered to her and she is given End pregnancy for a
high-risk woman instead (`phc.op.pregnancy-close-high-risk`). A form cannot
choose between one ending row and two, so the choice is made by state: this
one ends the pregnancy only, and using it for a high-risk woman would leave her
three extra doctor visits owed after the pregnancy had ended. Nothing else
is required.

## The outcomes, and why `not_pregnant` is one of them

Six: a live birth, a stillbirth, a miscarriage, a termination, that she has
moved away, and that she turned out not to be pregnant. The last two are
not clinical outcomes and they are on the list anyway, because the
alternative is a record that stays open forever on a woman this centre will
never see again, which is exactly the thing that fills an overdue list with
noise until nobody reads it.

The list is this bundle's and carries no code. It is not bound to a value
set because none of the three value sets this build has verified holds an
obstetric concept, and inventing one here would be the thing
`terminology/condition-code.json` carries a banner about.

## What happens

One `episode_of_care` row, `status: ended`, carrying the outcome. The
pregnancy stops being open on the next read, for every reader, including
the one that decides what is due.

A live birth does NOT create the child's record. That is a separate act and
a separate decision -- when a child's record should come into existence is
decision 8 in the design note and it is the owner's, because a patient
record created in a delivery room with no identity attached is the one that
later merges wrongly, and merging two children is irreversible.

## How you know it worked

The pregnancy reads as closed on her record, with the outcome and the date,
and nothing is due any more.

## When it goes wrong

- **It was recorded by mistake.** It is `correctable`, so amend it while
  the visit is open. Correcting it reopens the pregnancy, because open is
  derived from the two counts and removing the ending restores it.
- **She delivered somewhere else and came back weeks later.** Record it
  now, dated to this visit. The record will say the centre learned late,
  which is true and is better than a record that says it never happened.
- **Twins.** One pregnancy, one record, one ending. Two children are two
  records on the child side, and that is the other half of the design.
