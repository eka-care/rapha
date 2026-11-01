---
id: phc.op.patient-register
type: operation
kind: write
short: Register
title: Register a new patient
summary: Create a record for a patient the facility has not seen before.
capability: patient.register
scope_qualifier: null
station: reception
instrument: form
preconditions:
  - not registered
irreversibility: correctable
input: phc.schema.register-v1
writes: [patient]
mapping:
  records:
    - resource: patient
      fields:
        created_by: {actor: id}
        # THE PERSON THE CLERK PICKED. The desk searches this centre's own
        # register before it offers to create anybody, and when the clerk
        # takes one of those rows this carries which row it was. Without it
        # the form carried only her answers, the adapter saw a record with no
        # id, and finding her correctly still wrote a second her: seventy-two
        # rows for one woman on the day this was found, each with its own
        # visit and its own half of her history.
        #
        # Identity is the clerk's CHOICE and never a guess made here. Nothing
        # matches on a name or a mobile: a household shares one handset, and
        # merging a mother into her daughter is the one mistake in this
        # product that cannot be undone.
        #
        # Blank for a new patient, and a blank answer is not a column, so a
        # walk-in inserts exactly as it always did.
        id: {answer: patient_id}
        name: {answer: name}
        age: {answer: age}
        sex: {answer: sex}
        phone: {answer: phone}
        village: {answer: village}
        category: {answer: category}
        # Eka's own identifier for this person, when a directory suggestion
        # carried one. Mapped rather than ignored because it is what makes a
        # returning patient one person instead of two rows, and it arrives the
        # same way every machine filled value does: in an editable field, read
        # by a person, committed by their tap.
        directory_id: {answer: directory_id}
emits: [registered, abha.pending]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.abha-link]
  concepts: []
---

## In plain words

Make a new patient record. This is the second thing the clerk does, never the
first. The first thing is always to search.

## Before you start

A search must have been run and returned nothing that matches. You need
`patient.register`.

## What happens

The chat opens on the search palette, not on a registration form. Only when a
search misses does the clerk get an explicit prompt reading "no match,
register new patient?", and that confirm is un-prefilled.

The reason is arithmetic rather than taste. Most outpatient footfall is repeat
patients, so making create the default and search the thing the clerk has to
remember reliably manufactures duplicate records, and a duplicate cannot be
undone. Near miss candidates are shown on the same screen as the create
confirm, so the clerk can see what they are about to duplicate.

Search tolerates the real mess: transliteration variants, no fixed surname
order, shared household phone numbers, approximate ages.

## How you know it worked

The patient exists, holds a token, and is in the queue. The thread emits
`registered` and, because no ABHA is attached yet, `abha.pending`.

## When it goes wrong

- **A near miss is actually the same person.** Pick them. Do not create.
- **Two people share a phone number.** Common in a household. Match on phone
  plus partial name plus age band, not phone alone.
- **A programme needs extra fields.** Those forms are conditional on the
  encounter type, not asked routinely of everyone.
