---
id: phc.op.handover
type: operation
kind: write
short: Hand over
title: Hand over
summary: A note on this visit, addressed to whoever picks it up next.
capability: handover
scope_qualifier: null
station: doctor
instrument: form
presents: handover
preconditions:
  - registered
irreversibility: correctable
input: phc.schema.handover-v1
writes: [questionnaire_response]
mapping:
  records:
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: phc.schema.handover-v1}
        payload: {json: payload}
emits: []
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.consult-document]
  concepts: []
---

## In plain words

A handover is a note with somebody's name on it. The nurse tells the doctor
what the mother said about the cough; the doctor tells the pharmacist why the
dose is halved; the ASHA asks whether to visit again this week. It is not a
transfer of custody and it moves nobody: the patient is where the line says
they are, and this adds a sentence to the visit.

It is deliberately back and forth. Nothing here closes a conversation, there
is no acknowledgement to chase and no inbox to clear, so a reply is another
note and the visit carries the whole exchange.

## Before you start

The visit is registered. That is the only precondition: a handover is a sentence
about a person the facility has on its books, and nothing else about the line
needs to be true for one to be worth writing.

You hold `handover`. Six roles do already, so in practice everyone at a desk
does.

## What happens

One `questionnaire_response` row is written, signed with the actor and the
time, and the visit carries it from then on. No step closes and the patient does
not move. A reply is another note.

It deliberately does NOT write `notes`. The first draft did, and the gate caught
it within minutes: `consult.documented` is `exists: {resource: notes}`, so a
nurse's handover closed the doctor's step and the consultation was recorded as
done without one. A flag derived from a resource does not care which operation
wrote the row, so `emits: []` bought nothing. `questionnaire_response` carries a
`questionnaire` discriminator, drives no PHC state rule, and is the same shape
the laboratory's release already uses.

## Where it stands

`station: doctor` is where this operation SORTS, not where it is allowed.
kernel/state.actions() filters on drawn_by, capability and preconditions and
never on the caller's station, so the note is reachable from every desk on the
line. Handing over is not the property of one station, and the alternative -
one near-identical atom per station - would put five Hand over rows in the
same menu.

## What it cannot do

It emits no flag AND writes no resource any `done_when` is derived from, so it
moves no step of the line. Both halves are needed: the second is the one that
matters, and the one the first draft got wrong.

Six roles hold `handover` already (bundles/phc/bundle.yaml): frontdesk, nurse,
mo, lab, lab_incharge and pharmacist. The three community roles do not, so an
ASHA can be addressed in a note and cannot write one until a facility grants
the capability - which is one line in the role editor, not a code change.

## The addressee

There is no `to` field. The note is one sentence and the name is in it, the way
`@nurse` is in a message anywhere else. A separate addressee was drafted and cut:
the `notes` resource has no such column, so the answer would have been collected
and discarded, and the linter said so in those words. The composer's `@` menu is
built from this bundle's declared roles, so the name in the sentence is spelled
the way the bundle spells it.

## How you know it worked

The note appears on the visit, signed with who wrote it and when, and the
records rail counts one more note. Nothing else moves: the station is the same,
the line is the same, and no step has closed.

## When it goes wrong

An empty note is refused by the validator before anything is written. A caller
without `handover` is refused at guard step 2 and the row never appears on their
screen. An agent may propose a note and may not commit one, like every other
write here.

## Verification

Unverified against CARE. It writes the same `questionnaire_response` resource
that the laboratory's release already writes, so it inherits that mapping's
verification and adds no new field.
