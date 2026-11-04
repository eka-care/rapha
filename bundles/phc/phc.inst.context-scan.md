---
id: phc.inst.context-scan
type: instrument
kind: document
title: Scan the paper
summary: Reads a photographed report and fills what it can, for a person to check.
operations: [phc.op.context-add]
fills:
  date: dated
  findings: body
readback: required
commit: tap
fallback: form
---

## In plain words

A patient arrives holding paper. Until now the only way to get it onto the
visit was to read it and type it out, which at a busy centre means it does not
get typed out.

This photographs it instead. The picture goes to Eka's medical records
service, which reads it, and what it read opens in the same editable fields a
person would have typed into. Nothing is written until they tap.

## What it fills, and what it will not

`fills` is two lines and they are the whole contract. `date` is the date the
paper itself carries. `findings` is its table of readings: each one's name,
value, unit, reference range, and whether the laboratory called it high or
low.

It does not fill who wrote the paper, and that is a decision rather than a
gap. The service does answer a field called `source`, and what that field
holds is our own client identifier -- seen live on 4 November 2026 it was
`EC_1789058387727`, which is this integration and not the laboratory. Putting
that where a hospital's name belongs, on the one form whose entire safety
property is that it is plainly somebody else's document, would be worse than
leaving the box empty. So the box is left empty and a person fills it.

## Why a tap is still required

`readback: required` and `commit: tap`, like every other instrument here. A
parse is a Draft in the sense of kernel/contracts.py and a Draft is not a
record. Every value it fills arrives marked unconfirmed, in a field that can
be edited, and the form will not commit until a person has looked.

That matters more here than for a recording, not less. A recording is of
words somebody in the room just said; a scan is of a document nobody in the
room wrote, and a misread decimal point in a creatinine is a misread decimal
point in somebody else's laboratory's creatinine, which is harder to notice
and easier to believe.

## The picture is not kept

The upload exists to be read, and the moment it has been read it is deleted
from the service again, in a `finally`, whether the read worked or not. The
service's own documentation names this as the last step of the flow and the
SDK has the call.

So Eka holds the document for about half a minute, this repository never
holds it at all, and what ends up on the visit is the text a person checked
and committed. A centre that wants the photograph itself kept needs somewhere
to keep it, and this kernel has no such store; that is a separate decision
with a separate cost, and pretending otherwise by quietly leaving the upload
behind would be the worst of both.

## The fallback is the form

`fallback: form`. There is no camera on a desktop, the service can be
unreachable, and a handwritten note from a camp is not a lab report and will
parse to nothing. In every one of those cases the same three fields are there
to type into, which is exactly what they were before this instrument existed.

A parse that finds nothing says so and fills nothing. It never invents a
finding to look useful.
