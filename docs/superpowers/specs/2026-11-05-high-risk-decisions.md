# High-risk pregnancy: what was built, and what is still yours

5 November 2026. Sixteen commits on `feat/phc-catalogue-and-guard`.

You approved the design. This is the record of the judgement calls made
underneath it that nobody asked you about, and the things still waiting on
you. Each decision says what it costs if it was wrong, so you can undo the
ones you disagree with.

---

## 1. What a woman gets now

A nurse can mark a pregnant woman high risk. From that day she is owed
**three extra visits with the doctor**, a month apart, on top of the four
check-ups she already had. Her existing four do not change.

When she gives birth, her extra visits stop, and she is owed the usual
seven home visits plus **one final check at day 45**, which the programme
counts. If she loses the baby instead, everything stops and no home visits
are created at all.

A mark made by mistake can be undone. Her extra visits stop; her pregnancy
carries on untouched; both the mark and the undo stay in her record.

**This needed almost no programming.** The whole of it is written in the
clinical files, and both halves of the system picked it up for free. That
was the design's central claim and it held.

---

## 2. Waiting on you

**A woman who dies while pregnant has no honest answer on the closing
form.** A reviewer called this a real gap and I agree. It is not new and
not this work's fault, but somebody has to choose the wording.

**Closing a high-risk mother's care as "completed" loses her day-45
result.** The programme counts that result, so a facility that closes her
this way reports nothing. Either the closing form should ask for it, or
the indicator should be defined to accept the gap.

**The 23 risk factors on the nurse's form are not clinically signed off.**
They were taken from the programme's published list. Somebody clinical
should read them once.

**Whether a woman who gets better stops being high risk.** You answered
the question about a *wrong* mark. This is the other one: her anaemia is
treated, her fever has gone — do her extra visits stop? The programme
treats the category as sticky for the whole pregnancy, so my instinct is
no, and nothing in the build assumes otherwise. The undo offers no medical
reason, only "the record was wrong".

**The clock.** Unchanged from last time and still yours: the system keeps
time in UTC, so between midnight and 5:30am local it believes it is
yesterday.

---

## 3. Decisions about care

**A high-risk pregnancy is a second arc alongside the first, not a
different pregnancy.** The programme says *additional* visits, so we add
an arc rather than replacing one. The alternative split her history in
two and showed two pregnancies where there was one. *If wrong: her extra
visits live on a separate record from her ordinary ones.*

**The mark happens at the nurse's bench, not the doctor's.** The system
allows a form at one bench only. A doctor who diagnoses high blood
pressure at his own bench has to hand over. *If wrong: friction for the
doctor. The alternative was a change to the engine, which this did not
justify.*

**Her seven home visits are the ordinary seven.** Only the day-45 check
is separate. This replaced an earlier shape that copied all seven, because
a copied list of visits is a list that drifts out of step. *If wrong: her
home visits look the same as any mother's at the bench.*

**Her care is closed once, not twice.** A single form ends both halves
together, so no path leaves a mother who has died still owed a visit.
*If wrong: nothing; this is strictly safer.*

**A woman marked at thirty weeks counts from the day she was marked**, not
from an earlier visit she cannot now attend.

**The extra visits have their own form.** This was a late fix, and the
most serious thing found: one recorded visit was closing an ordinary
check-up *and* an extra one together, so she was getting fewer visits than
the programme requires, and a nurse's visit was ticking off the doctor's.

**No invented official codes.** Four crept in during the build and all
four were removed. A code printed on a nurse's card looks official, and
inventing one teaches people the system is making things up.

---

## 4. What is deliberately not built

Risk scoring — the system never decides who is high risk, a clinician
does. The red sticker, which is a paper card. The ASHA's payments, which
belong to a financial system; what we give them is the evidence those
payments are checked against. Linking her to a referral unit, which needs
a district tier that does not exist. And reminders, still waiting on your
decision about whose phone and what a message may say.

---

## 5. Four things known and left

- **Marking, undoing and re-marking inside one second** pairs the records
  wrongly and dates her visits from the old mark. Nobody can do this by
  hand; it needs three actions in the same second.
- **Undoing after a real extra visit was recorded** keeps the visit in her
  record but drops it from her schedule. That follows from never storing a
  schedule, and I believe it is the honest behaviour.
- **The doctor's dictation menu lists the extra visit for every patient.**
  That menu has never filtered by who the form is for; this work is the
  first to add a form that names a rare situation. The system still
  refuses the recording.
- **A nurse who means "she got better" could record it as a mistake.** The
  form offers no medical reason, and the audit would show what was said.

---

## 6. What proves it works

- `sh scripts/check.sh` runs everything and must print "all checks
  passed". It now includes the end-to-end test over a real connection.
- `scripts/check_high_risk.py` proves thirteen claims, including that one
  recorded visit closes one visit, that no path leaves a mother who has
  died owing care, and that a woman marked late still gets visits falling
  after her due date.
- Every claim was deliberately broken to confirm it fails when it should.
  Several turned out to be incapable of failing and were replaced. Three
  mutations proved nothing and were reported as such rather than dressed
  up as proof.
- Both halves of the system are run side by side over 126 cases, now
  including a high-risk pregnancy, a high-risk birth and a high-risk loss.
