---
id: lab.op.report-release
type: operation
kind: write
short: Release
title: Release the verified report to the referrer
summary: >
  Send the verified result out of the laboratory to the clinician who ordered
  it. Once it has left, it has left.
capability: lab.result.validate
scope_qualifier: null
station: doctor
instrument: form
preconditions:
  - lab.validated
  - not dispensed.complete
irreversibility: irreversible
input: lab.schema.release-v1
writes: [questionnaire_response]
mapping:
  records:
    - resource: questionnaire_response
      fields:
        questionnaire: {const: lab.schema.release-v1}
        payload: {json: payload}
emits: [dispensed.complete]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
related:
  operations: [lab.op.result-verify]
  concepts: []
---

## In plain words

The report goes to the referrer. A released result is acted on by somebody
this laboratory cannot reach, so the release is irreversible: an agent
cannot propose it and a person has to tap an un-prefilled confirm.

## Before you start

The result must be verified and not yet released. You need
`lab.result.validate`.

## What happens

The release form is kept whole as a questionnaire response. The flag it
raises is called `dispensed.complete`, the free slot in the closed vocabulary
that means something leaving the building. The thread's line is then
complete.

## How you know it worked

The worklist shows the thread under Complete, and the report view's Release
section shows the channel and the time.

## When it goes wrong

- **Released the wrong report.** It cannot be unreleased. An amended report
  is a new thread, and telling the referrer is a phone call, not an
  operation in this bundle.
- **An agent tried to release.** Refused on surface before anything else is
  looked at.
