---
id: lab.op.result-verify
type: operation
kind: write
short: Verify
title: Verify a preliminary result
summary: >
  A second pair of eyes reads the entered values and either verifies the
  result or rejects it. Only a verified result can be released.
capability: result.verify
scope_qualifier: null
station: verification
instrument: form
preconditions:
  - result.entered
  - not result.verified
  # Separation of duties, written down instead of hoped for. Whoever keyed
  # this result cannot verify it, whatever capabilities they hold. Enforced by
  # catalogue/guard.py against the thread's own audit trail, on both surfaces.
  - not actor of lab.op.result-enter
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
        created_by: {actor: id}
        code: {const: verification}
        status: {answer: decision}
    - resource: notes
      fields:
        created_by: {actor: id}
        text: {note: [comment]}
emits: [result.verified, result.rejected]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.result-enter, lab.op.report-release]
  concepts: []
---

## In plain words

A second person says the result is right. This is the separation of duties a
laboratory runs on, and it is the reason this operation exists as its own
step rather than as a checkbox on the result form.

## Before you start

A preliminary result must exist and no verification may. You need
`result.verify`, and you must not be the person who entered this result. The
technologist role does not hold the capability at all; the senior technologist
role holds both, and is refused on this specimen by name.

## What happens

A report row with the decision as its status is written, and the comment as
a note if one was given, both carrying the verifier. `result.verified` is true
only when a row with status verified exists, so a rejection leaves the
specimen at this station and raises `result.rejected` instead.

## How you know it worked

The release action appears. It was not there before, and it was not greyed
out before: it did not exist.

## When it goes wrong

- **Rejected.** The specimen stays at verification and the technologist
  cannot re-enter, because `result.entered` is already true. There is no
  amend loop in this bundle; see bundles/LAB-LOG.md.
- **The same person entered and verified.** Refused, on both surfaces, with
  the reason `precondition not met: not actor of lab.op.result-enter`. On the
  rendered panel it is refused on the tap rather than hidden, because
  api/main.py does not yet tell the kernel who is looking.
