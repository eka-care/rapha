---
id: lab.metric.released
type: metric
title: Reports released
summary: Reports released to a referrer.
unit: count
window: day
numerator: {resource: questionnaire_response, where: {questionnaire: lab.schema.release-v1, created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

One per release. Counted from the release form kept as a questionnaire
response, since release writes no other row.
