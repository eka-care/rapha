---
id: phc.view.calendar
type: view
kind: calendar
title: Calendar
summary: Every contact the centre owes, day by day, across all its patients.
capability: patient.find
workflow: phc.wf.outpatient
episodes: [pregnancy, pregnancy_high_risk, postnatal, postnatal_high_risk]
---

## In plain words

A queue answers "who is here now". This answers "who is owed a contact, and
on which day", across the whole facility. It is a declaration and not a
screen because the contacts already exist as schedules: each says what is
owed and in which window. The calendar only names which episodes to read.
Nothing is stored for it. Every day it is worked out afresh from the records.

The counts are maternal only. Pregnancy and the weeks after delivery are the
only episodes this centre has schedules for. A child's immunisations or a
chronic patient's reviews would appear here the day a schedule is declared
for them, and a name is added to the list above.
