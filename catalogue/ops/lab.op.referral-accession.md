---
id: lab.op.referral-accession
type: operation
kind: write
short: Accession
title: Accession a referral
summary: Register the referred patient and the panel ordered for them.
capability: order.accession
scope_qualifier: null
station: accession
instrument: form
preconditions:
  - not order.accessioned
irreversibility: reversible
input: lab.schema.accession-v1
writes: [patient, service_request, questionnaire_response]
mapping:
  records:
    - resource: patient
      fields:
        created_by: {actor: id}
        name: {answer: name}
        age: {answer: age}
        sex: {answer: sex}
        phone: {answer: phone}
    - resource: service_request
      fields:
        created_by: {actor: id}
        code: {answer: panel}
        status: {const: active}
    # The referring clinician does not work here and no CARE column on this
    # adapter names one, so the whole accession form is kept as a
    # questionnaire_response and the report view shows it from there.
    - resource: questionnaire_response
      fields:
        created_by: {actor: id}
        questionnaire: {const: lab.schema.accession-v1}
        payload: {json: payload}
emits: [order.accessioned]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.specimen-collect]
  concepts: []
---

## In plain words

Somebody outside this laboratory asked for a test. The accession desk records
who the patient is, who asked, and which panel. Nothing clinical is asserted
yet.

## Before you start

The thread must carry no order yet. You need `order.accession`, which in this
bundle the phlebotomist holds.

## What happens

One form writes three rows: the patient, an active service request carrying
the panel code, and the form itself as a questionnaire response, which is the
only place the referrer's name survives. Every row records who accessioned
it. The specimen moves to phlebotomy.

## How you know it worked

The worklist shows the person under phlebotomy, and the report view's
Referral section names the referrer.

## When it goes wrong

- **Wrong panel.** The operation is reversible; accession again on a fresh
  thread. There is no edit path.
- **The referrer is not on any list.** A free text name is accepted. The
  laboratory has no referrer directory in this bundle.
