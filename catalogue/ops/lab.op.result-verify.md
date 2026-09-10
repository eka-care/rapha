---
id: lab.op.result-verify
type: operation
kind: write
short: Verify
title: Verify a preliminary result
summary: >
  The pathologist reads the entered values and either verifies the result or
  rejects it. Only a verified result can be released.
capability: lab.result.validate
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - lab.resulted
  - not lab.validated
irreversibility: correctable
input: lab.schema.verify-v1
writes: [diagnostic_report, notes]
mapping:
  records:
    # The decision is the status, so a rejection never reads as verified. A
    # second report row is written rather than the preliminary one updated,
    # because a mapping cannot address an existing row.
    - resource: diagnostic_report
      fields:
        code: {const: verification}
        status: {answer: decision}
    - resource: notes
      fields:
        text: {note: [comment]}
emits: [lab.validated]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.result-enter, lab.op.report-release]
  concepts: []
---

## In plain words

A second person, holding a capability the first does not, says the result is
right. This is the separation of duties a laboratory runs on.

## Before you start

A preliminary result must exist and no verification may. You need
`lab.result.validate`. The technologist role does not hold it.

## What happens

A report row with the decision as its status is written, and the comment as
a note if one was given. `lab.validated` is true only when a row with status
verified exists, so a rejection leaves the thread at this station.

## How you know it worked

The release action appears. It was not there before, and it was not greyed
out before: it did not exist.

## When it goes wrong

- **Rejected.** The thread stays at verification and the technologist cannot
  re-enter, because `lab.resulted` is already true. There is no amend loop in
  this bundle; see the log.
- **The same person entered and verified.** The guard cannot tell. The
  capability split is the whole of the separation of duties, and the
  `lab_incharge` role holds both capabilities.
