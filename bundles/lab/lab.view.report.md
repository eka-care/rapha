---
id: lab.view.report
type: view
kind: summary
title: Laboratory report
summary: One specimen, referral to release.
capability: worklist.read
workflow: lab.wf.specimen
sections:
  - title: Progress
    show: line
  - title: Flags
    show: flags
  - title: Referral
    resource: questionnaire_response
    where: {questionnaire: lab.schema.accession-v1}
    fields: [payload, created_date]
  - title: Specimen
    resource: specimen
    fields: [code, status, created_date]
  - title: Results
    resource: observation
    where: {category: laboratory}
    fields: [code, value, unit, created_date]
  - title: Report status
    resource: diagnostic_report
    fields: [code, status, created_date]
  - title: Verifier notes
    resource: notes
    fields: [text, created_date]
  - title: Release
    resource: questionnaire_response
    where: {questionnaire: lab.schema.release-v1}
    fields: [payload, created_date]
  - title: Awaiting confirmation
    show: proposals
  - title: What you can do
    show: actions
  - title: Audit trail
    show: audit
---

## In plain words

The report a referrer would read, drawn by the generic summary renderer. It
cannot show a reference interval beside a value or mark a value high or low,
because a section shows columns and the interval is on the questionnaire,
not in a row. The referrer's name is inside the Referral section's JSON.
