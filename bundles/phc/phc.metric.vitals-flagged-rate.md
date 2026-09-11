---
id: phc.metric.vitals-flagged-rate
type: metric
title: Flagged vitals rate
summary: Visits where a vital crossed a critical band.
unit: percent
window: week
numerator: {resource: thread_flag, where: {flag: vitals.flagged, created_date: {gte: window.start}}}
denominator: {resource: encounter, where: {created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

Stored flags are records too. Adapter 0 keeps them in a `thread_flag` table
so a metric can count them like any other resource; adapter 1 reads them
from EncounterThread.flags. `thread_flag` is the one resource name in this
bundle that is not in vocab.CARE_RESOURCES, and lint allows it only in a
metric numerator.
