---
id: phc.op.referral-close
type: operation
kind: write
short: Close referral
title: Close a referral
summary: Record what happened to a referral, and stop chasing it.
capability: handover
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - referral.open
irreversibility: correctable
input: phc.schema.referral-close-v1
writes: [episode_of_care, questionnaire_response]
mapping:
  records:
    - resource: episode_of_care
      fields:
        created_by: {actor: id}
        type: {const: referral}
        status: {const: ended}
        outcome: {answer: outcome}
    # The evidence, kept whole beside the outcome. "Attended" with nothing
    # under it is a tick, and a tick is what this operation exists to stop
    # a referral being closed with.
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.referral-close-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.referral-raise]
  concepts: []
---

## In plain words

Somebody found out what happened to a woman who was sent on, and this is
where they say so. It is the second half of "every referral closed".

## WHAT CLOSES A REFERRAL IS NOT SETTLED, and this is the honest version

There are three answers and they are not equivalent:

- the receiving facility's own record of having seen her, which is the only
  one that is evidence;
- somebody at this centre marking it, which is the only one that works with
  no network and is therefore the only one available today;
- the agent noticing a document appear, which needs a network and a
  document exchange this build does not have.

This operation implements the second and asks for the evidence in words,
because a referral closed on nothing is a referral nobody checked. It is
decision 2 in
`docs/superpowers/specs/2026-11-04-maternal-and-child-health-design.md`, it
is the owner's, and the design note argues that the mechanism should become
a declared query per type so the answer is one line rather than a rewrite.
Nothing here forecloses that.

## The four outcomes, and why three of them are not "she was seen"

Attended is the one that means the referral worked. Did not attend, no
longer needed, and unable to contact all CLOSE THE CHASE AND SAY WHY,
which is a different fact and has to stay a different fact. A product that
records only "closed" cannot tell a district the difference between a
referral pathway that works and one where nobody ever arrives, and that
difference is the entire reason a district would want this.

## Before you start

A referral is open.

## What happens

A second `episode_of_care` row with the outcome, which is how every episode
here ends. From that moment nothing is owed and nothing is chased, because
what was being chased was derived from the referral being open.

## How you know it worked

The referral reads as closed on her record, with the outcome and the
evidence beside it, and nothing is owed on it any more.

## When it goes wrong

- **She attended, but much later.** Close it with the date it is recorded.
  The record will say the centre learned late, which is true.
- **It was closed in error.** It is `correctable` while the visit is open.
  Removing the ending reopens the referral, because open is derived from
  the two counts rather than stored.
