---
id: phc.view.station-queue
type: view
kind: queue
title: Today's patients by station
summary: Everyone seen today, grouped by where they are standing now.
capability: patient.find
workflow: phc.wf.outpatient
scope: today
group_by: station
columns: [name, age, sex, village, token]
badges:
  abha.pending: warn
  vitals.flagged: crit
  lab.critical: crit
  dispensed.partial: mute
---

## In plain words

The queue every station looks at. One tab per station, a count on each, and a
Complete tab for patients whose line has finished. A patient appears under
the station they are at, which the workflow decides, not the screen.
