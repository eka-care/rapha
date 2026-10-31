---
id: lab.op.result-enter
type: operation
kind: write
short: Result
title: Enter panel results
summary: One value per analyte, keyed or read from the analyser.
capability: result.enter
scope_qualifier: null
station: processing
instrument: form
preconditions:
  - specimen.collected
  - not result.entered
irreversibility: correctable
input: lab.schema.panel-result-v1
writes: [observation, diagnostic_report]
mapping:
  ignored: [override_reason]
  records:
    - resource: observation
      per_question: [haemoglobin, wbc, platelets, glucose, creatinine, sodium, potassium]
      fields:
        created_by: {actor: id}
        category: {const: laboratory}
        code: {question: link_id}
        value: {question: answer}
        unit: {question: unit}
        # `preliminary`, which is R4's own word for a value recorded and not
        # yet verified. It matches the report this same operation writes
        # below, and it stops matching by itself: `lab.op.result-verify` is a
        # separate operation a separate person performs, and until they do,
        # these values are not verified. They were published as `final`
        # anyway until 2026-10-31, because kernel/fhir.py chose the status.
        #
        # They stay `preliminary` after verification too, and that is a named
        # limit rather than an oversight: a mapping cannot address an existing
        # row, so verification writes a second report row and cannot reach
        # these. A stale `preliminary` says the value may change, which is
        # merely out of date; a `final` on an unverified value says a second
        # person stood behind it. Only one of those is a false claim.
        status: {const: preliminary}
    - resource: diagnostic_report
      fields:
        created_by: {actor: id}
        code: {answer: panel}
        status: {const: preliminary}
emits: [result.entered, lab.critical]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.specimen-collect, lab.op.result-verify]
  concepts: []
---

## In plain words

A number per analyte. Each analyte carries three bands on its own question:
a plausible band that blocks the write, a critical band that raises
`lab.critical`, and a reference interval that is written down but that
nothing in the kernel reads.

## Before you start

A specimen must exist and no result may exist yet. You need `result.enter`.
Entering is not verifying, and whoever enters is barred from verifying this
specimen by name, not by which capabilities they were given.

## What happens

Every answered analyte becomes one observation row with the unit from its
question and the technologist as its author, and one preliminary report row
is written. A value outside its plausible band is refused unless a reason is
given. A value inside the plausible band but outside the critical band
commits and raises `lab.critical`. A value outside the reference interval but
inside the critical band commits and raises nothing, because the grammar has
one flag per question and it is spent on critical.

## How you know it worked

The worklist moves the specimen to verification and the report view lists
the observations.

## When it goes wrong

- **Wrong analyte for the panel.** `enable_when` hides the field in the
  renderer; the server does not enforce it. A glucose on a CBC commits.
- **Keyed twice.** The second entry is refused: `result.entered` is already
  true and there is no amend operation.
