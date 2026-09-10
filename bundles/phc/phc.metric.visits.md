---
id: phc.metric.visits
type: metric
title: Visits
summary: Encounters opened in the window.
unit: count
window: day
numerator: {resource: encounter, where: {created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

How many patients were registered for a visit. A plain count, no
denominator.
