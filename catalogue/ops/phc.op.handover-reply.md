---
id: phc.op.handover-reply
type: operation
kind: write
short: Reply
title: Reply to a handover
summary: A comment on the handover, and the state it leaves it in.
capability: handover
scope_qualifier: null
station: doctor
instrument: form
presents: handover
preconditions:
  - handover.raised
irreversibility: correctable
input: phc.schema.handover-reply-v1
writes: [questionnaire_response]
mapping:
  records:
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.handover-reply-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.handover]
  concepts: []
---

## In plain words

A handover is a conversation, not a delivery. Somebody asked for something;
this is the answer, and it carries the state the asker needs to see: that it
has been picked up, that it is being worked on, that it is done, or that it
has come back.

It writes a comment and a state and nothing clinical. A repeat blood pressure
is recorded by the operation that records blood pressure; saying "done, 154/94"
here is a message about work, not a reading, and nothing downstream will treat
it as one.

## Before you start

A handover has to have been raised on this visit; that is the `handover.raised`
precondition, and it is derived from the handover's own questionnaire response
rather than stored, so it is true exactly when one exists.

You need `handover` -- the same capability as raising one, because replying to
a request and making one are the same kind of act and splitting them would
create a role that can be asked but cannot answer.

## What happens

The comment lands on the thread under the handover it answers, and the
handover's state becomes whatever this reply set. The state is read from the
replies in order, so the current state is the last one anybody set.

## How you know it worked

The handover on the thread shows the new state and your comment beneath it.
Resolving one does not remove it: a resolved handover stays readable, because
what was asked and what came back is the part somebody will want later.

## When it goes wrong

- **Two people reply at once.** Both comments stand and the later state wins.
  Nothing is lost and nobody is told they were too slow, which is the right
  trade for a facility where two people genuinely do pick up the same note.
- **It was resolved and the problem came back.** Reopen it rather than raising
  a second handover, so the history stays in one conversation.
- **The reply is really a clinical finding.** Record it with the operation
  that records it. This one writes no clinical row and a value typed here is
  not in the record.

## What it cannot do

It cannot address a different person: reassignment (§12.1) would need the
reply to name a new addressee and nothing here does yet. It cannot close a
handover on another visit, because every operation is scoped to its thread.

Multiple handovers on one visit are one conversation to this operation. The
kernel stores a reply as a questionnaire response with no reference to which
handover it answers, so a second concurrent handover on the same thread would
share the first one's replies. One at a time is the honest limit today.
