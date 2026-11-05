---
id: phc.op.antenatal-visit
type: operation
kind: write
short: Antenatal
title: Antenatal visit
summary: An antenatal visit, recorded as narrative.
capability: encounter.document
scope_qualifier: null
station: doctor
instrument: scribe
preconditions:
- registered
irreversibility: correctable
input: phc.schema.antenatal-visit-v1
writes:
- encounter
- notes
mapping:
  records:
  - resource: encounter
    fields:
      created_by:
        actor: id
      status:
        const: in_progress
  - resource: notes
    fields:
      created_by:
        actor: id
      text:
        note:
        - history
        - examination
        - assessment
        - plan
emits:
- consult.documented
surfaces:
- rendered
- mcp
verified:
  status: unverified
  against: care-local
related:
  operations:
  - phc.op.consult-document
  - phc.op.antenatal-visit-high-risk
  concepts: []
---

## In plain words

An antenatal visit. It asks for the history, what you found, your
assessment and the plan, and it does not offer the coded diagnosis
rows, because this build can code three conditions and not one of them
is obstetric. The whole of this visit travels as narrative text into
the published document, which is what that fallback was built for.

This is one of a pair. A woman marked high risk is owed three more
visits, with a doctor, over and above her ordinary four. Those are
recorded with `phc.op.antenatal-visit-high-risk`, which asks the same
questions on this same form. They are two operations because a recorded
visit closes the contacts of the operation that was committed, and one
operation for both would let a single visit close an ordinary contact and
an extra one together. This one closes only an ordinary contact.

This narrowing is a fact about this build's vocabulary and not a
clinical judgement: terminology/condition-code.json holds three
concepts and says it is not a diagnosis list, so there is no obstetric
concept for a coded row to carry. It follows that this operation codes
NOTHING. It is not clinically useful as a coded record until a
published obstetric list is signed off by a named clinical officer, and
it should not be mistaken for one. What it does do is keep the visit as
text in a record that reaches ABDM.

## Before you start

The same as phc.op.consult-document, which this operation narrows: nothing
about who may do this, where, or what must already be true is changed by
asking fewer questions.

## What happens

Exactly what phc.op.consult-document does. The form is narrower, the mapping is
the base's own narrowed to the questions this form asks, and the record
published is the same kind of record filed under the same heading.

This operation and its high-risk twin were generated from a declaration in
the bundle until the twin was added. A generated form can name only one
operation, so both are now written by hand, and the mapping here is the
base's own narrowed to the four narrative questions. If the base changes,
this one has to be changed with it.

## How you know it worked

The note is on the thread under this operation's own title, and an answer this
form did not ask is absent rather than empty.

## When it goes wrong

- **A question you needed is not on this form.** Use phc.op.consult-document,
  which asks all of them.
- **The finding you want to record cannot be coded.** It belongs in the
  narrative, which still reaches the published document as text. That is the
  designed fallback and not a workaround.
- **She is high risk and this is one of her three extra visits.** Use the high
  risk version, or the wrong contact will be marked.
