---
id: phc.op.lab-order
type: operation
kind: write
short: Order
title: Order an investigation
summary: Ask the laboratory to run a test for this patient.
capability: lab.order
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - consult.documented
irreversibility: reversible
input: phc.schema.lab-order-v1
writes: [service_request]
mapping:
  records:
    - resource: service_request
      per_item: investigations
      fields:
        code: {item: [code, test]}
        status: {const: active}
emits: [lab.ordered]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.lab-result-enter, phc.op.consult-document]
  concepts: []
---

## In plain words

The doctor asks for a test. The request lands on the lab's worklist.

## Before you start

A consultation must be documented. You need `lab.order`.

## What happens

The doctor picks the investigation from the facility's available set and
confirms. The order routes to the laboratory worklist for this patient, and
the doctor's own surface starts showing the result as pending.

## How you know it worked

The lab sees an enter result action for this patient that did not exist
before, and the doctor sees a pending investigation on the thread.

## When it goes wrong

- **The facility cannot run that test.** It is not in the available set. Refer
  rather than ordering something nobody can perform.
- **Ordered by mistake.** This operation is reversible. Cancel it before a
  sample is accessioned.
- **The result never comes back.** It stays pending on the thread rather than
  disappearing, which is the point of the thread carrying state.
