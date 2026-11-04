---
id: phc.sched.antenatal
type: schedule
title: Antenatal contacts
summary: What this centre owes a pregnant woman, and the window each is due in.
episode: pregnancy
# Days from the recorded date to day zero of the arc, per dating basis. A
# woman dated from the first day of her last period is at day zero on that
# date. A scan reports an estimated delivery date, which by the same 280 day
# convention is day 280, so the arc began 280 days before it.
#
# THIS IS THE ONLY OBSTETRICS IN THE SYSTEM. The kernel has none and must
# gain none: it reads these numbers and does arithmetic.
anchor:
  last_menstrual_period: 0
  dating_scan: -280
  best_estimate: 0
contacts:
  - id: anc1
    title: First check-up
    programme_title: First antenatal contact
    due: 84
    opens: 0
    closes: 90
    owner: anm
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: ANC1
  - id: anc2
    title: Second check-up
    programme_title: Second antenatal contact
    due: 154
    opens: 98
    closes: 182
    owner: anm
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: ANC2
  - id: anc3
    title: Third check-up
    programme_title: Third antenatal contact
    due: 210
    opens: 196
    closes: 238
    owner: anm
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: ANC3
  - id: anc4
    title: Fourth check-up
    programme_title: Fourth antenatal contact
    due: 252
    opens: 245
    closes: 294
    owner: anm
    escalates_to: cho
    operation: phc.op.antenatal-visit
    authority: statutory
    reports_as: ANC4
---

## In plain words

A woman is pregnant, and from that moment this centre owes her a sequence of
contacts over about nine months. This is that sequence: what is owed, when
each one is aimed at, and how wide a window counts as arriving on time.

It is four contacts because four is what India's programme requires and
reports. It is not four because four is good obstetrics.

## NEEDS SIGN-OFF, and what that means here

Every number in this file is a clinical protocol whether or not anybody
calls it one, and no clinician has read it. A named clinical officer has to
confirm it against the current national operational guideline before this
is offered to anybody, exactly as the three templates in `bundle.yaml` carry
the same banner and for the same reason.

What is written above is this build's reading of the Reproductive and Child
Health programme's minimum: a first contact in the first trimester, a second
between roughly fourteen and twenty six weeks, a third between twenty eight
and thirty four, and a fourth from thirty six weeks to term. The days are
those weeks multiplied out, with the windows drawn to meet each other so no
day of a pregnancy falls between two contacts with neither open.

## What is deliberately not here

**The eight contact model.** WHO recommended eight antenatal contacts in
2016 and India's register still counts four. A centre that follows eight
would declare the four extra ones with `authority: clinical` and give them
no `reports_as`, which is exactly what that pair of fields is for: the
contact it keeps and the register line it fills are not the same thing. The
shipped bundle declares the statutory four, because reporting four while
the screen insists on eight is how software loses an argument with a
district officer.

**The monthly specialist day.** Pradhan Mantri Surakshit Matritva Abhiyan
adds an antenatal check on a fixed day each month. Its due date comes from a
calendar and not from the anchor, which is the one line in this design that
does not hang off a pregnancy's own dates, and `due` as written here cannot
express it. Naming it as missing rather than approximating it.

**Iron and folic acid, and the tetanus and diphtheria doses.** These are
not contacts and modelling them as visits would be wrong. They are supply
and coverage: the question is whether she has been given them, not whether
she turned up. They belong on what a contact RECORDS, and the antenatal
visit form does not ask yet.

**Everything after delivery.** The postnatal and newborn sequences branch on
whether she delivered at a facility or at home, which needs a delivery
record this build does not have, and a schedule line needs an
`applies_when` that this type does not carry yet.

## The windows, and the gaps between them

A contact aimed at twenty eight weeks is not late at twenty eight weeks and
one day. A woman who walks eleven kilometres and arrives nine days after the
day a piece of software picked has not failed, and neither have we. That is
what the window is for, and it is why a contact has three dates rather than
one.

THE WINDOWS DO NOT ALL TOUCH, and an earlier draft of this file claimed they
did. The second contact runs to twenty six weeks and the third opens at
twenty eight, so there are about two weeks of a pregnancy in which nothing
is due and nothing is late. That gap is the programme's, not a mistake here,
and the honest thing is to say so rather than to widen a clinical window to
make a screen tidier.

What it means for a reader: in a gap, the arc shows the contact she has just
missed or completed and the one coming, and nothing is asked of anybody. It
is not the same as everything being fine, and a screen drawing this should
not say "nothing due" without saying which of those two it means.

## Who owns one, and the thing that found out

The ANM, escalating to the community health officer when the window closes
with the contact still open. The owner is a role and not a person, because a
sub-centre's staff change and a schedule naming one of them would be wrong
on the day they did.

IT SAYS `anm` BECAUSE THE LINT MADE SOMEBODY DECIDE. The first draft of this
file assigned every contact to the ANM, which is who runs antenatal care at
a sub-centre in India, and the build refused it in these words:

    contact 'anc1': owner 'anm' does not hold 'encounter.document', so the
    person this is assigned to could not perform it

That was true. `phc.op.antenatal-visit` is a template of the general
consultation, so it needs `encounter.document`, and at that point only the
medical officer and the community health officer held it. An ANM could not
record an antenatal visit in this product. Nobody had decided that; it fell
out of an antenatal visit being a kind of consultation and an ANM not being
a doctor.

The owner decided on 4 November 2026: give the ANM `encounter.document`.
That is recorded in `bundle.yaml` beside the capability, with what it costs.
It also lets her document any consultation, which is the part that had to be
decided rather than inferred. The narrower alternative, a capability of its
own for the antenatal visit, is still open and is still smaller; it was not
taken because it means naming a new capability and nothing is waiting on
that.

Escalation goes to the community health officer and not straight to the
medical officer. She is the next person up the line who can also perform the
contact, so the escalation hands the work to somebody who can finish it
rather than to somebody who can only ask about it.

The check that refused the first draft is worth keeping whichever way it
goes: a schedule assigned to somebody who could not possibly perform it
fails the build instead of failing in a village.

## What closes one

A committed `phc.op.antenatal-visit` on a visit belonging to this pregnancy,
inside the window. One visit closes one contact: the earliest open one whose
window contains it.

**Recording it late is allowed and has to be**, because the Mother and Child
Protection card is paper, is the household's, and is frequently more
complete than anything this centre holds. A woman who was seen at another
centre brings the evidence with her, and a tracker that can only record what
happens in front of it will be wrong about most women in this programme.
