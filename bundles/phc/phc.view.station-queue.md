---
id: phc.view.station-queue
type: view
kind: queue
title: Lines
summary: Today, grouped by station.
capability: patient.find
workflow: phc.wf.outpatient
scope: today
group_by: station
# A facility-tunable default, not a value the spec measured or derived: 30
# minutes before a row starts inking amber is defensible for a PHC OPD wait,
# but it is a placeholder for whoever actually owns this facility's target,
# not a number to read back as researched.
target_minutes: 30
columns: [name, age, sex, village, token]
badges:
  abha.pending: warn
  vitals.flagged: crit
  lab.critical: crit
  dispensed.partial: mute
  capture.declined: mute
---

## In plain words

The queue every station looks at. One tab per station, a count on each, and a
Complete tab for patients whose line has finished. A patient appears under
the station they are at, which the workflow decides, not the screen.

A visit the patient declined recording on carries a quiet badge here, so the
next station can see the answer instead of asking for it again.
