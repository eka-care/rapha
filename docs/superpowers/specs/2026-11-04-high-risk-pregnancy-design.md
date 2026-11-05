# High-risk pregnancy, on the rails that already exist

4 November 2026. Design for owner approval. Nothing is built.

Written to be implemented with as little new code as possible. The headline:
**the core of this needs no kernel code and no Go code at all.** It is
declarations, which both engines already read.

## 1. What the programme actually requires

Marking a woman high risk is not a label in India. It changes her care plan,
and the National Health Mission says how.

Once a pregnant woman is categorised as a high-risk pregnancy:

- She gets **three additional antenatal visits**, with a doctor or
  obstetrician — over and above the four she already has.
- **The ASHA accompanies her** to each one, and is paid ₹100 a time for
  bringing her in.
- She must be **linked to the nearest First Referral Unit** for delivery,
  with free transport under JSSK.
- She is **tracked to day 45 after birth**, with a healthy outcome for
  mother and baby verified by both the ANM and the MO. The ASHA is paid
  ₹500 when that is confirmed.
- Her Mother and Child Protection card gets a **red sticker**; a woman with
  no risk factors gets a green one.

The two indicators the programme monitors are the percentage of high-risk
women who completed their three extra check-ups, and the percentage with a
satisfactory outcome at day 45.

**What makes her high risk:** the list was expanded from 10 categories to 25,
and any one of them is enough. Severe anaemia, pregnancy-induced
hypertension, gestational diabetes, hypothyroidism, HIV, syphilis, hepatitis
B, tuberculosis, malaria, previous caesarean, cephalo-pelvic disproportion,
bad obstetric history, previous stillbirth, twins or more, teenage pregnancy,
early or elderly first pregnancy, short stature, grand multipara, negative
blood group, abnormal fetal heart rate, high fever, RTI or STI.

Sources: the NHM guidance note on extended PMSMA for tracking high-risk
pregnancies, and the MoHFW and PIB updates on PMSMA. The guidance note is the
one that matters here — it is where the three extra visits and the day-45
rule come from.

## 2. The cheapest correct shape

**A high-risk pregnancy is a second episode running alongside the first, not
a replacement for it.**

That single decision is what makes this nearly free. The programme says
*additional* visits, and an additional episode is the honest translation:

- Her four ordinary antenatal check-ups carry on untouched, on the
  `pregnancy` episode she already has.
- A second episode, `pregnancy_high_risk`, opens the day she is marked, and
  carries the three doctor visits.
- Both are open at once. The kernel already pairs episodes by type, so they
  do not interfere with each other.
- Her calendar shows seven visits because it sweeps both.

### Why not convert the pregnancy into a high-risk one

The obvious alternative is to end the `pregnancy` episode and open a
`pregnancy_high_risk` one in its place, the way `phc.op.delivery-record`
already ends a pregnancy and opens postnatal care in a single commit. It
would work, and it is the established pattern.

It is rejected because it splits her history. The check-ups she has already
attended stay on the closed episode and the rest appear on the new one, so
her record shows two pregnancies where there was one. Additive keeps one
pregnancy and adds what the programme adds.

## 3. What this costs to build

**No kernel code. No Go code.** `kernel/schedule.py` matches a schedule to an
episode purely on the episode's `type`, which is the bundle's own word, so a
new type with a new schedule is picked up by both engines without either being
touched. The Go parity fixture gained a high-risk woman (a pregnancy, a
delivery and a loss) so that "no parity work" is checked and not only claimed.

What was written, as built. It is more than the first draft of this section
said, and the growth has two causes. A mapping cannot be conditional, so
every place the high-risk woman needs a different set of rows is a second
operation chosen by state. And contacts are closed by the operation that was
committed, so the extra visits need an operation of their own.

Two schedules:

1. **`phc.sched.antenatal-high-risk`**: `episode: pregnancy_high_risk`, three
   contacts owned by `mo`, escalating to the CHO, each closed by
   `phc.op.antenatal-visit-high-risk`.
2. **`phc.sched.postnatal-high-risk`**: `episode: postnatal_high_risk`, one
   contact, the day-45 check, owned by the ANM.

Six operations, all in `catalogue/ops`:

3. **`phc.op.risk-mark`**: opens the `pregnancy_high_risk` episode with one
   row, as `phc.op.pregnancy-open` does.
4. **`phc.op.antenatal-visit-high-risk`**: the three extra doctor visits.
   Gated on `pregnancy_high_risk.open`, at the doctor's bench, on the ordinary
   antenatal form. The ordinary antenatal visit became a hand-written atom
   instead of a generated template, because a generated form can name only
   one operation.
5. **`phc.op.pregnancy-close-high-risk`** and
   **`phc.op.delivery-record-high-risk`**: the two ways a high-risk pregnancy
   ends. Each ends the pregnancy and the high-risk episode together.
6. **`phc.op.postnatal-outcome`**: the day-45 check; it ends only the tail.
7. **`phc.op.postnatal-close-high-risk`**: ends the home visits and the tail
   together, and is the only way a high-risk mother's death or loss to
   follow-up is recorded.

Four questionnaires are shared and not copied, each naming both its
operations in `styling_metadata.phc.operation`: `delivery-record-v1`,
`pregnancy-close-v1`, `postnatal-close-v1` and `antenatal-visit-v1`. Two are
new: `risk-mark-v1` and `postnatal-outcome-v1`.

Declarations in the bundle: state rules `pregnancy_high_risk.open`,
`pregnancy_high_risk.ended`, `pregnancy.ordinary`, `postnatal_high_risk.open`
and `postnatal_high_risk.ended`; the high-risk type in the calendar view; and
the operations offered at the nurse's and doctor's steps. The ordinary
`phc.op.postnatal-close` gained a gate, `not postnatal_high_risk.open`.

The check is `scripts/check_high_risk.py`.

Everything else (the calendar, the card stack, the arc, the escalation when a
visit is missed, the audit, the FHIR projection, both engines) works on it the
day it compiles.

## 4. The day-45 tail

The one part that is not free. Our postnatal care ends at **day 42**; the
programme tracks a high-risk woman to **day 45**, with a verified outcome.

A schedule is matched to one episode type, so the high-risk tail cannot be a
second postnatal schedule over the same type. It needs its own type, which
means the delivery has to open a different episode for a high-risk woman, and
a mapping cannot choose between two records conditionally. That is a
deliberate limit of the grammar, not an oversight.

So: **two delivery operations**, each gated by a declared state.
`phc.op.delivery-record` keeps `preconditions: [pregnancy.ordinary]`, a new
state meaning open and not high risk. `phc.op.delivery-record-high-risk`
takes `[pregnancy_high_risk.open]` and opens TWO postnatal episodes. The
ordinary `postnatal` episode carries the seven home visits, exactly as for any
mother, so they are not copied. A second, `postnatal_high_risk`, carries only
what is extra: the day-45 outcome check owned by the ANM. Both deliveries
share the existing questionnaire.

Two episodes means two things to close, and a mother who has died must owe
nothing on either. So the closing operations are split by state as well. An
ordinary mother is closed by `phc.op.postnatal-close`, now gated off while a
tail is open. A high-risk mother is closed by `phc.op.postnatal-close-high-risk`,
which ends both episodes. The day-45 form ends only the tail, so it does not
offer "mother died" or "not found"; those are recorded with the closing
operation that ends both.

That is more operations' worth of declaration and one more schedule. Still no
code.

**The alternative, if you would rather not have two delivery operations:**
move everybody to day 45. One number in one file, and every woman gets a
final check three days later than now. It is more care, not less, and it
collapses this whole section to a one-line change. I would want your view
before choosing, because it changes what an ordinary woman is chased for.

## 5. What is deliberately not built

- **No risk scoring.** The system does not decide who is high risk. A nurse
  or doctor marks her, having applied the clinical criteria herself. The 25
  categories go on the form as a list she picks from, so the reason is
  recorded, but nothing infers risk from a reading.
- **No red sticker.** That is a physical card.
- **No ASHA payments.** The incentives are a financial system's business.
  What we can give them is the evidence: the three visits completed and the
  day-45 outcome verified, which is exactly what the payments are verified
  against.
- **No First Referral Unit linkage.** There is no facility directory above
  this centre, and no district tier. The referral that exists today is
  internal. Linking her to an FRU is real work and belongs with the district
  tier when that is built.
- **No reminders.** Unchanged, and still waiting on your decision about
  whose phone and what a message may say.

## 6. Decisions for the owner

1. **When do the three extra visits fall due?** The guidance says three
   follow-ups with a doctor, and PMSMA clinics run on the 9th of each month,
   so monthly from the date she is marked is the natural reading. But the
   register calls them "the 2nd, 3rd and 4th", which could mean her second,
   third and fourth antenatal visits overall. These produce different
   calendars. My proposal is monthly from the marking date, because a woman
   marked at 30 weeks cannot retrospectively attend her second visit.
2. **Day 45 for everybody, or two delivery paths?** Section 4.
3. **Can a woman be unmarked?** *Answered for a mistake, still open for
   recovery.* The owner has decided a mark made in error (wrong patient,
   wrong date) can be undone: `phc.op.risk-unmark` ends the high-risk
   episode as "marked in error" and the three extra visits stop, with both
   the mark and the undo kept in her record. That is a correction of the
   record, not a clinical reversal. **Still open:** if a condition resolves — anaemia treated, a
   fever gone — does her high-risk episode end, and do the remaining extra
   visits stop? The machinery allows it; the clinical answer is yours. My
   instinct is no: the programme treats the category as sticky for the
   pregnancy, and stopping her extra care because one reading improved is
   the kind of decision a system should not make on its own.
4. **Who may mark her?** Not the ASHA — she reports what she finds and the
   centre decides. **Corrected during the build:** the kernel allows an
   operation one station, and refuses to draw it anywhere else, so this
   happens at the nurse's bench. The medical officer holds the capability
   but would have to be at that bench to use it; from the doctor's bench he
   hands over. That is exactly how opening the pregnancy already works, and
   letting an operation declare two stations is a kernel change this does
   not justify. It does mean an MO who diagnoses hypertension at his own
   bench cannot mark her there, which is friction worth knowing about.

## 7. What proves it works

In the style of the existing checks, and mostly by analogy with them:

1. Marking a woman high risk adds three visits and changes none of her
   existing four.
2. Her calendar shows all seven, each on its own day, with the three new ones
   owned by the doctor.
3. A missed high-risk visit escalates, like any other.
4. Recording a delivery stops both arcs at once — no woman is left owing a
   high-risk visit after she has given birth.
5. A miscarriage opens no postnatal care of either kind. The claim that
   already exists, extended to the new type.
6. The day-45 check exists for a high-risk woman and not for an ordinary one.
