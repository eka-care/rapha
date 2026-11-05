# High-Risk Pregnancy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A woman marked high risk gains the three extra doctor visits the programme requires, and is tracked to day 45 after birth.

**Architecture:** A high-risk pregnancy is a **second episode running alongside** the first, not a replacement. `kernel/schedule.py:for_episode` matches a schedule to an episode on its `type` alone, so a new type with a new schedule is picked up by both engines with no code in either. The core of this plan is declarations.

**Tech Stack:** Markdown declarations compiled to `catalogue.json`; Python 3.9 kernel; Go 1.26 mirror. **No new code in either engine is expected.** If a task finds it needs some, that is a finding to report, not to quietly write.

**Spec:** `docs/superpowers/specs/2026-11-04-high-risk-pregnancy-design.md`

## Global Constraints

- **Nothing is stored.** A contact is derived at read time from the schedule, the episode's anchor and the audit. No generated rows.
- **No obstetrics in the kernel.** Every clinical number lives in a declaration. `phc.sched.antenatal.md` says so of itself: "THIS IS THE ONLY OBSTETRICS IN THE SYSTEM."
- **The renderer may never name a station, flag, capability, operation or view column.**
- **Two engines.** Both read the same `catalogue.json`; `scripts/check_go_parity.py` must pass.
- **The gate.** `sh scripts/check.sh` must exit 0 with "all checks passed".
- Tests are plain Python modules with a `__main__` runner, registered in `scripts/check.sh`.
- Four sessions share this checkout and one git index: stage by exact path, **commit with `git commit -m "…" -- <paths>`**, never amend, never reset, never stash, never switch branches, and run `git show --stat` after every commit.
- Changing a declaration recompiles **both** `catalogue/catalogue.json` and `care_phc_mcp/catalogue.json`. Both are tracked and both belong in the commit. Regenerate with `python3 -m kernel.declarations`, **never `python3 -m catalogue.build` alone**, which writes a stripped file.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Decisions the owner settled, or that are mine and reversible

1. **The three extra visits are monthly from the day she is marked** — due at 30, 60 and 90 days, each with a fortnight either side. The guidance can also be read as her 2nd, 3rd and 4th antenatal visits overall; monthly from marking was chosen because a woman marked at thirty weeks cannot retrospectively attend her second.
2. **Two delivery paths**, so an ordinary woman is not chased three days longer than she is today. Changing everybody to day 45 was the cheaper alternative and was rejected: it alters what every woman is chased for in order to save a file.
3. **She cannot be unmarked.** The programme treats the category as sticky for the pregnancy, and stopping her extra care because one reading improved is not a decision a system should make alone.
4. **The nurse and the MO may mark her**, not the ASHA. She reports what she finds; the centre decides. This matches how a pregnancy is opened today.

## Review Focus

Five conditions the spec implies that no task's happy path exercises. Each has its test placed in the task that owns the code.

1. **A woman marked very late.** Marked at thirty-four weeks, her third extra visit falls after her due date. It must still be derived — and must stop the moment delivery is recorded, like any other. Test in Task 3, which has a live kernel to derive against.
2. **Marking her twice.** A second marking must be refused, not silently produce two high-risk episodes owing six visits. Test in Task 1.
3. **Marking a woman with no open pregnancy.** Refused, and written to the audit as a refusal. Test in Task 1.
4. **Delivery while high risk.** Both arcs stop in one commit. No woman is left owing an extra visit after she has given birth. Test in Task 2.
5. **A miscarriage while high risk.** No postnatal care of either kind — absent, not cancelled, not empty. Test in Task 2.

---

### Task 1: The mark, and the three visits it buys

**Files:**
- Create: `bundles/phc/phc.sched.antenatal-high-risk.md`
- Create: `catalogue/ops/phc.op.risk-mark.md`, `questionnaires/phc.schema.risk-mark-v1.json`
- Modify: `bundles/phc/phc.wf.outpatient.md` (states, and the nurse step), `bundles/phc/bundle.yaml` (the loaded list), `bundles/phc/phc.view.calendar.md` (`episodes:`)
- Test: `kernel/tests/test_declarations.py`

**Interfaces:**
- Produces: episode type `pregnancy_high_risk`; schedule `phc.sched.antenatal-high-risk`; operation `phc.op.risk-mark`; states `pregnancy_high_risk.open` and `pregnancy_high_risk.ended`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_high_risk_pregnancy_has_its_own_schedule_of_three_visits():
def test_the_three_visits_are_owned_by_the_doctor_and_escalate():
def test_no_two_high_risk_windows_share_a_day():
def test_marking_needs_an_open_pregnancy_and_refuses_a_second_mark():
def test_the_calendar_sweeps_the_high_risk_type_too():
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python3 -m kernel.tests.test_declarations`
Expected: FAIL — no such schedule

- [ ] **Step 3: Write the schedule**

`episode: pregnancy_high_risk`. Anchor on the day she is marked: a single basis, `marked`, at 0. Three contacts — `hrp1`, `hrp2`, `hrp3` — due at **30, 60 and 90**, each `opens` fourteen days before and `closes` fourteen days after, so no two windows touch. `owner: mo`, `escalates_to: cho`, `operation: phc.op.antenatal-visit`, `authority: statutory`, `reports_as: HRP1`/`HRP2`/`HRP3`.

Titles are the plain words, with the programme's own phrasing beside them as `programme_title`, the way the antenatal schedule now does: "First extra check-up" and "First follow-up ANC for a high-risk pregnancy", and so on.

The body explains what the previous reader will most need: that these are *additional* to her four ordinary visits, that they are owned by the doctor because the programme requires a doctor or obstetrician, and that the ASHA accompanies her — which the system records by who performs the visit, not by a second row.

- [ ] **Step 4: Write the operation and its questionnaire**

Copy `phc.op.pregnancy-open`, which writes a single `episode_of_care` row — **not** `phc.op.delivery-record`, which writes two. `capability: episode.manage`, `station: nurse`, `preconditions: [pregnancy.open, "not pregnancy_high_risk.open"]`, `irreversibility: correctable`.

The questionnaire asks one required question: which risk factor was found. Its options are the programme's categories — severe anaemia, pregnancy-induced hypertension, gestational diabetes, hypothyroidism, HIV, syphilis, hepatitis B, tuberculosis, malaria, previous caesarean, cephalo-pelvic disproportion, bad obstetric history, previous stillbirth, twins or more, teenage pregnancy, early or elderly first pregnancy, short stature, grand multipara, negative blood group, abnormal fetal heart rate, high fever, RTI or STI, other. Recording the reason is the point: the system never infers risk, a clinician names it.

The mapping writes `type: {const: pregnancy_high_risk}`, `status: {const: active}`, `anchor_basis: {const: marked}`, and `anchor_date` from the answer.

- [ ] **Step 5: Wire it up**

Four state rules in the workflow, the `gte`/`all_of` pair every episode uses. The operation on the nurse step. The schedule and operation in `bundle.yaml`. The new type in the calendar view's `episodes:`.

- [ ] **Step 6: Run the tests and the compile**

Run: `python3 -m kernel.declarations && python3 -m kernel.tests.test_declarations`
Expected: PASS, and the compile reports the new schedule.

- [ ] **Step 7: Commit**

```bash
git commit -m "A high-risk pregnancy is a second arc, not a different one" -- bundles/phc catalogue/ops/phc.op.risk-mark.md questionnaires/phc.schema.risk-mark-v1.json kernel/tests/test_declarations.py catalogue/catalogue.json care_phc_mcp/catalogue.json
```

---

### Task 2: The day-45 tail

**Files:**
- Create: `bundles/phc/phc.sched.postnatal-high-risk.md`, `catalogue/ops/phc.op.delivery-record-high-risk.md`
- Modify: `bundles/phc/phc.wf.outpatient.md` (the `pregnancy.ordinary` state, the nurse step), `catalogue/ops/phc.op.delivery-record.md` (its precondition), `bundles/phc/bundle.yaml`
- Test: `kernel/tests/test_declarations.py`

**Interfaces:**
- Consumes: `pregnancy_high_risk.open` from Task 1.
- Produces: state `pregnancy.ordinary`; episode type `postnatal_high_risk`; operation `phc.op.delivery-record-high-risk`.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_ordinary_delivery_cannot_be_recorded_for_a_high_risk_woman():
def test_a_high_risk_delivery_opens_the_tail_that_runs_to_day_45():
def test_the_high_risk_postnatal_schedule_keeps_the_seven_home_visits():
def test_both_delivery_paths_reuse_one_questionnaire():
```

- [ ] **Step 2: Run them to verify they fail**

- [ ] **Step 3: The state, and the two paths**

`pregnancy.ordinary` is `all_of: [pregnancy.open, "not pregnancy_high_risk.open"]` — the same shape the workflow already uses for `abha.pending`. `phc.op.delivery-record`'s precondition becomes `[pregnancy.ordinary]`. The new operation takes `[pregnancy_high_risk.open]`.

The high-risk delivery writes **three** episode rows in one commit, where the ordinary one writes two: it ends the pregnancy, ends the high-risk episode, and opens `postnatal_high_risk`. All three in one mapping, so there is no instant in which she is owed nothing — the same reason `phc.op.delivery-record` writes its two together.

Both operations declare `input: phc.schema.delivery-record-v1`. Nothing stops two operations sharing a questionnaire; if the lint refuses it, report that rather than duplicating the file.

- [ ] **Step 4: The high-risk postnatal schedule**

A copy of `phc.sched.postnatal.md` with `episode: postnatal_high_risk` and one contact added: `hbnc45`, due at **45**, owned by the ANM, `reports_as: HRP-OUTCOME`. The body records that day 45 is the programme's number for a high-risk woman and that an ordinary woman's care still ends at 42, and why the two differ.

- [ ] **Step 5: Run the tests, the compile and the parity check**

Run: `python3 -m kernel.declarations && python3 -m kernel.tests.test_declarations && python3 scripts/check_go_parity.py`

- [ ] **Step 6: Commit**

```bash
git commit -m "A high-risk delivery opens the tail that runs to day forty-five" -- bundles/phc catalogue/ops kernel/tests/test_declarations.py catalogue/catalogue.json care_phc_mcp/catalogue.json
```

---

### Task 3: The proof

**Files:**
- Create: `scripts/check_high_risk.py`
- Modify: `scripts/check.sh`

**Interfaces:**
- Consumes: everything above, through a live kernel on a scratch database.

- [ ] **Step 1: Write the script**

Follow `scripts/check_antenatal.py` and `scripts/check_postnatal.py` exactly in style: a numbered claim each printing what it proved, exiting non-zero on the first failure. The claims:

1. Marking a woman adds three visits and changes none of her existing four.
2. Her calendar shows all seven, each on its own day, the three new ones owned by the doctor.
3. A missed high-risk visit escalates, like any other.
4. **Recording a delivery stops both arcs at once** — no woman is left owing a high-risk visit after she has given birth. *(Review Focus 4.)*
5. **A miscarriage opens no postnatal care of either kind** — absent, not cancelled, not empty. *(Review Focus 5.)*
6. The day-45 check exists for a high-risk woman and not for an ordinary one.
7. **A woman marked at thirty-four weeks still gets her three visits**, and they stop at delivery. *(Review Focus 1.)*

- [ ] **Step 2: Run it against a scratch database**

`PHC_DB` and `PHC_SPOOL` under the session scratchpad, never the shared database.

- [ ] **Step 3: Prove each claim can fail**

Break the thing each checks, in a scratch copy of the kernel and never in the real source, confirm the check fails, restore. Report what you broke and what you saw. Two claims on an earlier branch turned out to compare a value with itself; do not ship another.

- [ ] **Step 4: Register it in `scripts/check.sh`**

Beside `check_postnatal.py`, with a two-line comment in the surrounding style saying what it would catch.

- [ ] **Step 5: Run the whole gate**

Run: `sh scripts/check.sh`
Expected: exits 0, "all checks passed".

- [ ] **Step 6: Commit**

```bash
git commit -m "Seven visits, two arcs, and both of them stop when she delivers" -- scripts/check_high_risk.py scripts/check.sh
```
