---
id: lab.op.specimen-collect
type: operation
kind: write
short: Collect
title: Collect and accession a specimen
summary: >
  The phlebotomist records that the sample was drawn, what it is and what it
  is in, so the bench can start.
capability: assessment.record
scope_qualifier: null
station: nurse
instrument: form
preconditions:
  - lab.ordered
  - not vitals.recorded
irreversibility: correctable
input: lab.schema.specimen-v1
writes: [specimen]
mapping:
  records:
    - resource: specimen
      fields:
        code: {answer: specimen_type}
        status: {const: available}
emits: [vitals.recorded]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.referral-accession, lab.op.result-enter]
  concepts: []
---

## In plain words

The sample is drawn and labelled. From here the specimen, not the person, is
what moves through the laboratory.

## Before you start

An order must be accessioned. You need `assessment.record`, because the
vocabulary has no phlebotomy capability and this is the one the nurse role
holds that the technologist role does not. The flag this raises is called
`vitals.recorded` for the same reason: the vocabulary is closed and this is
the free slot at the second station.

## What happens

One specimen row lands with status available. The thread moves to the bench.

## How you know it worked

The worklist shows the specimen under the bench, and the report view's
Specimen section shows its type.

## When it goes wrong

- **Haemolysed or clotted.** There is no reject-specimen operation in this
  bundle; the thread has to be re-accessioned.
- **Two tubes.** One row per collect; run the operation twice only if the
  precondition allows it, which it does not once one specimen exists.
