---
id: lab.op.referral-accession
type: operation
kind: write
short: Accession
title: Accession a referred patient and their order
summary: >
  Register the person a referring clinician sent, and the panel they asked
  for, so the laboratory has a subject and an order to work against.
capability: patient.register
scope_qualifier: null
station: reception
instrument: form
preconditions:
  - not registered
irreversibility: reversible
input: lab.schema.accession-v1
writes: [patient, service_request, questionnaire_response]
mapping:
  records:
    - resource: patient
      fields:
        name: {answer: name}
        age: {answer: age}
        sex: {answer: sex}
        phone: {answer: phone}
    - resource: service_request
      fields:
        code: {answer: panel}
        status: {const: active}
    # The referring clinician does not work here and no CARE column on this
    # adapter names one, so the whole accession form is kept as a
    # questionnaire_response and the report view shows it from there.
    - resource: questionnaire_response
      fields:
        questionnaire: {const: lab.schema.accession-v1}
        payload: {json: payload}
emits: [registered, lab.ordered]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.specimen-collect]
  concepts: []
---

## In plain words

Somebody outside this laboratory asked for a test. The front desk records who
the patient is, who asked, and which panel. Nothing clinical is asserted yet.

## Before you start

The thread must be empty. You need `patient.register`; there is no
`accession` capability in the vocabulary, so the front desk role stands in.

## What happens

One form writes three rows: the patient, an active service request carrying
the panel code, and the form itself as a questionnaire response, which is the
only place the referrer's name survives. The thread moves to collection.

## How you know it worked

The worklist shows the person under collection, and the report view's
Referral section names the referrer.

## When it goes wrong

- **Wrong panel.** The operation is reversible; accession again on a fresh
  thread. There is no edit path.
- **The referrer is not on any list.** A free text name is accepted. The
  laboratory has no referrer directory in this bundle.
