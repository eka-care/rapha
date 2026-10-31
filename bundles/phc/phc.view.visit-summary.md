---
id: phc.view.visit-summary
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
    fields: [code_display, value, unit, created_date]
  - title: Notes
    resource: notes
    fields: [text, created_by, created_date]
  - title: Prescription
    resource: medication_request
    where: {status: active}
    # The display rather than the code, because this is a screen a person
    # reads, and the five answers the line is made of rather than the one
    # prose string that used to hold them. `dosage_instruction` is gone: it
    # held the dose and the frequency as a sentence, so neither could be read
    # back here as what it is.
    fields: [medication_display, dose, dose_unit, frequency_display,
             route_display, duration, duration_unit, status]
  - title: Investigations
    resource: service_request
    fields: [code, status, created_date]
  # The number, read from the observation it is now stored in. Before the
  # result became a quantity there was nothing to read: the value and its unit
  # were squashed into the report's conclusion as prose, so this screen could
  # show the sentence and nothing could trend or count it.
  - title: Lab results
    resource: observation
    where: {category: laboratory}
    fields: [code_display, value, unit, created_date]
  # The report keeps the narrative and drops the raw code. A reader who wants
  # to know which test it was reads the row above, where the display is; a
  # LOINC number on screen helps nobody.
  - title: Reports
    resource: diagnostic_report
    fields: [conclusion, status, created_date]
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
