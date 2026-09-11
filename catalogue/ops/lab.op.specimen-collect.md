---
id: lab.op.specimen-collect
type: operation
kind: write
short: Collect
title: Collect and label a specimen
summary: >
  The phlebotomist records that the sample was drawn, what it is and what it
  is in, so the bench can start.
capability: specimen.collect
scope_qualifier: null
station: phlebotomy
instrument: form
preconditions:
  - order.accessioned
  - not specimen.collected
irreversibility: correctable
input: lab.schema.specimen-v1
writes: [specimen]
mapping:
  records:
    - resource: specimen
      fields:
        created_by: {actor: id}
        code: {answer: specimen_type}
        status: {const: available}
emits: [specimen.collected]
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

An order must be accessioned. You need `specimen.collect`, which the
phlebotomist holds and the technologist does not.

## What happens

One specimen row lands with status available, carrying the phlebotomist who
drew it. The specimen moves to processing.

## How you know it worked

The worklist shows the specimen under processing, and the report view's
Specimen section names the container and the time.

## When it goes wrong

- **Haemolysed or clotted.** There is no reject-specimen operation in this
  bundle; the thread has to be re-accessioned.
- **Two tubes.** One row per collect, and the precondition refuses a second
  once one specimen exists.
