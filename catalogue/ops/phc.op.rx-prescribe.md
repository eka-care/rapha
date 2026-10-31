---
id: phc.op.rx-prescribe
type: operation
kind: write
short: Rx
title: Write a prescription
summary: Prescribe medicines, with pharmacy stock in view.
capability: rx.prescribe
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - consult.documented
  - not rx.confirmed
irreversibility: correctable
input: phc.schema.rx-v1
writes: [medication_request]
mapping:
  records:
    # One MedicationRequest per medicine row. A medicine is a drug, a dose, a
    # route, a frequency and a course length, and all five are columns rather
    # than one `dosage_instruction` string.
    #
    # What this replaces squashed the whole dosage into `{item:
    # [dosage_instruction, dose]}`, which meant a prescription could not be
    # counted, could not be checked against stock by strength, and reached
    # ABDM as a sentence rather than a Dosage. The drug column held free text
    # for the same reason the diagnosis column did.
    #
    # Every coded field is resolved per row, and kernel/mapping._row refuses a
    # row whose coded answer is missing. So a medicine with no route is no row
    # at all rather than a half coded one, and it cannot inherit the route of
    # the medicine above it.
    - resource: medication_request
      per_row: medications
      fields:
        created_by: {actor: id}
        medication: {answer_code: drug}
        medication_system: {answer_code_system: drug}
        medication_display: {answer_code_display: drug}
        dose: {answer: dose}
        dose_unit: {answer_code: dose_unit}
        dose_unit_system: {answer_code_system: dose_unit}
        route: {answer_code: route}
        route_system: {answer_code_system: route}
        route_display: {answer_code_display: route}
        frequency: {answer_code: frequency}
        frequency_system: {answer_code_system: frequency}
        frequency_display: {answer_code_display: frequency}
        duration: {answer: duration}
        duration_unit: {answer_code: duration_unit}
        duration_unit_system: {answer_code_system: duration_unit}
        status: {const: active}
        intent: {const: order}
emits: [rx.confirmed]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [phc.op.pharmacy-dispense, phc.op.consult-document]
  concepts: []
---

## In plain words

The doctor prescribes. Confirming the prescription is what makes the
pharmacist's dispense action exist at all.

## Before you start

A consultation must be documented. You need `rx.prescribe`.

For a community health officer this capability is bounded to an approved
formulary and protocol set. That bound is a qualifier on the capability rather
than a separate capability, so there is one thing for the guard to evaluate.
It is declared and not yet enforced, and it needs a named clinical signatory
before it is.

## What happens

The doctor selects drugs, doses and durations on a form. Scribe output from
the consultation can pre fill it as a draft, which is edited and confirmed
like any other proposal.

Current facility stock is shown at the point of prescribing. An out of stock
drug should be visible to the person choosing it, not discovered by the
patient at the counter. This is the cheapest useful signal in the whole design
and it only works because dispense events feed stock.

## How you know it worked

The prescription is on the thread and the pharmacist's dispense action, which
did not exist a moment ago, appears on their surface.

## When it goes wrong

- **The drug is out of stock.** It is marked at the point of prescribing.
  Choose an alternative then, or accept that the dispense will be partial.
- **An allergy is recorded.** The allergy is on the thread. Read it. Nothing
  here decides for the prescriber.
- **The patient is already on something interacting.** Current medications are
  on the thread for the same reason.
