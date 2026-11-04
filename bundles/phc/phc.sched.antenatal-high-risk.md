---
id: phc.sched.antenatal-high-risk
type: schedule
title: Extra antenatal contacts for a high-risk pregnancy
summary: The three additional check-ups a woman is owed once she is marked high risk.
episode: pregnancy_high_risk
# The arc begins the day she is marked, so the only basis is that day.
# NEEDS SIGN-OFF: every number here is a clinical protocol.
anchor:
  marked: 0
contacts:
  - id: hrp1
    title: First extra check-up
    programme_title: First follow-up ANC for a high-risk pregnancy
    due: 30
    opens: 16
    closes: 44
    owner: mo
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: HRP1
  - id: hrp2
    title: Second extra check-up
    programme_title: Second follow-up ANC for a high-risk pregnancy
    due: 60
    opens: 46
    closes: 74
    owner: mo
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: HRP2
  - id: hrp3
    title: Third extra check-up
    programme_title: Third follow-up ANC for a high-risk pregnancy
    due: 90
    opens: 76
    closes: 104
    owner: mo
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: HRP3
---

## In plain words

Once a pregnant woman is marked high risk, India's national programme gives
her three more antenatal visits with a doctor or obstetrician. This is
that sequence. It runs beside her ordinary four, never in place of them.

## Additional, not instead

Her four ordinary check-ups stay on her pregnancy and are untouched. This
is a second episode, opened the day she is marked. Ending the pregnancy and
opening a high-risk one would split her history into two pregnancies where
there was one.

## Who owns them

The medical officer, escalating to the community health officer, because
the programme requires a doctor or obstetrician. The ASHA accompanies her.
The system records that by who performs the visit, not by a second row.

## The numbers

Monthly from the day she is marked: due at 30, 60 and 90 days, each window
opening fourteen days before and closing fourteen days after, so no two
windows touch. The programme could also be read as her 2nd, 3rd and 4th
visits overall. Monthly from marking was chosen because a woman marked at
thirty weeks cannot retrospectively attend her second. This reading needs
clinical sign-off.

## What closes one

A committed antenatal visit inside the window, as for the ordinary four.
