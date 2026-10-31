---
# GENERATED FILE. Do not edit. It is derived from the `templates` declaration in bundles/phc/bundle.yaml by kernel/templates.py, and `sh scripts/check.sh` fails on a hand edit. Change the declaration.
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
  concepts: []
---

## In plain words

An antenatal visit. It asks for the history, what you found, your
assessment and the plan, and it does not offer the coded diagnosis
rows, because this build can code three conditions and not one of them
is obstetric. The whole of this visit travels as narrative text into
the published document, which is what that fallback was built for.

This narrowing is a fact about this build's vocabulary and not a
clinical judgement: terminology/condition-code.json holds three
concepts and says it is not a diagnosis list, so there is no obstetric
concept for a coded row to carry. It follows that this template codes
NOTHING. It is not clinically useful as a coded record until a
published obstetric list is signed off by a named clinical officer, and
it should not be mistaken for one. What it does do is keep the visit as
text in a record that reaches ABDM.

## Before you start

The same as phc.op.consult-document, which this template narrows: nothing about who may do this,
where, or what must already be true is changed by asking fewer questions.

## What happens

Exactly what phc.op.consult-document does. The form is narrower, the mapping is the base's own
narrowed to the questions this form asks, and the record published is the
same kind of record filed under the same heading.

## How you know it worked

The note is on the thread under this template's own title, and an answer this
form did not ask is absent rather than empty.

## When it goes wrong

- **A question you needed is not on this form.** Use phc.op.consult-document, which asks all of
  them. Narrowing is a declaration in bundles/phc/bundle.yaml and not a code
  change.
- **The finding you want to record cannot be coded.** It belongs in the
  narrative, which still reaches the published document as text. That is the
  designed fallback and not a workaround.
