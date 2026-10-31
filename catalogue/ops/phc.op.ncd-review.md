---
# GENERATED FILE. Do not edit. It is derived from the `templates` declaration in bundles/phc/bundle.yaml by kernel/templates.py, and `sh scripts/check.sh` fails on a hand edit. Change the declaration.
id: phc.op.ncd-review
type: operation
kind: write
short: NCD review
title: Review a long term condition
summary: A review visit for a condition already being treated.
capability: encounter.document
scope_qualifier: null
station: doctor
instrument: scribe
preconditions:
- registered
irreversibility: correctable
input: phc.schema.ncd-review-v1
writes:
- encounter
- notes
- condition
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
  - resource: condition
    per_row: diagnosis
    fields:
      created_by:
        actor: id
      code:
        answer_code: condition
      code_system:
        answer_code_system: condition
      code_display:
        answer_code_display: condition
      clinical_status:
        answer_code: clinical_status
      clinical_status_system:
        answer_code_system: clinical_status
      verification_status:
        answer_code: verification_status
      verification_status_system:
        answer_code_system: verification_status
      onset:
        answer: onset
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

A review of a condition somebody is already being treated for. It asks
the same five things the general consultation asks, and it will not
commit without what you found on examination, because a review whose
measurements are missing is a visit nobody can compare the next one to.

NEEDS SIGN-OFF. That the examination is required here, rather than
optional as it is on the general consultation, is a product choice made
without a clinician. It states no interval, no target and no threshold,
and it must not be read as a review protocol. A named clinical officer
has to confirm it before this template is offered to anybody.

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
