---
id: lab.metric.release-ratio
type: metric
title: Released per accessioned
summary: Reports out over orders in, the nearest declarable thing to throughput.
unit: ratio
window: day
numerator: {resource: questionnaire_response, where: {questionnaire: lab.schema.release-v1, created_date: {gte: window.start}}}
denominator: {resource: service_request, where: {status: active, created_date: {gte: window.start}}}
certified_by: bundle author, unverified against any reference count
---

## In plain words

Not turnaround time. A ratio of two counts in the same window, which says
whether the bench is keeping up and nothing about how long any one specimen
waited.
