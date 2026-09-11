---
id: phc.view.patient-summary
type: view
kind: summary
title: Visit summary
summary: One visit on one page.
capability: patient.find
workflow: phc.wf.outpatient
sections:
  - title: Visit
    show: line
  - title: Flags
    show: flags
  - title: Vitals
    resource: observation
    where: {category: vital-signs}
    fields: [code, value, unit, created_date]
  - title: Notes
    resource: notes
    fields: [text, created_by, created_date]
  - title: Prescription
    resource: medication_request
    where: {status: active}
    fields: [medication, dosage_instruction, status]
  - title: Investigations
    resource: service_request
    fields: [code, status, created_date]
  - title: Results
    resource: diagnostic_report
    fields: [code, conclusion, status]
  - title: Awaiting confirmation
    show: proposals
  - title: What you can do
    show: actions
  - title: Audit trail
    show: audit
---

## In plain words

The right-hand panel of the thread screen, declared. Sections that read a
resource show the fields listed; sections that `show` a kernel structure
(the line, the flags, pending proposals, the visible actions, the audit) are
drawn by the renderer the same way for every bundle.
