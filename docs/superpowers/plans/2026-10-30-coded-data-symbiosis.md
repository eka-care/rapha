# Coded data: how the kernel, FHIR valuesets, Eka and ABDM divide the work

> **For agentic workers:** steps use checkbox (`- [ ]`) syntax. Every step leaves
> `sh scripts/check.sh` green and unskipped, and every check it adds is mutation
> proved: break the implementation, confirm FAIL, revert, confirm PASS.

**Goal.** Make every clinical fact this product records carry a code that means
the same thing in another facility, without asking a medical officer to do
medical coding, and without letting a model's guess enter a record as a fact.

**Status.** Proposed. Nothing here is built. Two decisions below block the first
step and both are the owner's.

**Why this document exists.** Four systems now have a claim on the same record:
our declarations, FHIR's valueset model, Eka's models, and the ABDM profiles we
must emit. Left unstated, they overlap and each one quietly becomes the
authority on something it should not own. This fixes who answers what.

---

## 1. One table, which is the whole design

| The question | Who answers it | Why not anyone else |
|---|---|---|
| What may be recorded here, and by whom | our declarations | the kernel exists for this; a plugin may narrow it and never widen it |
| Which codes are legal for this answer | a ValueSet, declared as a branch of an ontology | an enumerated list goes stale on every ontology release; a branch does not |
| Which legal code did this person mean | Eka codification (Parrotlet) | multilingual concept ranking over 12 Indian languages is the one piece we cannot build and should not try |
| Does that code actually exist | a terminology server | only it knows; SNOMED is licensed, versioned, and not ours to copy |
| Does it enter the record | a person, by a tick | model output is a proposal; a record is an assertion |
| Which words it came from | our evidence span | nothing upstream keeps this, and without it a wrong code is unarguable |
| Where it lands in a shared document | the ABDM profile | we do not get to choose; `OPConsultRecord` already names the sections |

Read the table as a rule: **no row may be answered by the party in another
row.** Most of the ways this design can go wrong are a violation of exactly one
line of it. Codification deciding what enters the record is the worst of them.

## 2. Four seams

Each is a small interface with a real implementation and a stub, in the same
spirit as `kernel/contracts.py Store`: the seam is the thing of value, because
it is what makes the far side swappable without a rewrite.

### 2.1 Terminology

```
validate(valueset, code)             -> bool            # on every write
bound(valueset, code)                -> Coding          # the only constructor
expand(valueset, query, count)       -> [Coding]        # for a picker
```

`validate` takes a **code and not a coding**, and the signature cannot be the
other way round once I1 is held as above: if a `Coding` is only constructible
by validating, then `validate` cannot take one. `bound` is the constructor that
does both, and it is the only one. Corrected 2026-10-31 against the
implementation in `kernel/terminology.py`.

**Decided: we host it.** There is no hosted terminology server to point at.
SNOMED CT is free to use in India and still requires an Affiliate License from
MLDS, which NHA answers twice in its own FAQ because "free" keeps being read as
"no licence needed". Once the licence is approved you download release files;
the India extensions and CDCI, Common Drug Codes for India, come from the
NRCeS national releases. CDCI is a better medication vocabulary for ABDM than
any vendor's internal drug identifiers.

Implementations, in the order we adopt them:

1. **Local file**, seeded from step 2 below. `validate` is a set membership
   test, `expand` a substring match. Enough for every PHC question whose code
   is fixed, and it is what keeps the licence off the Monday path.
2. **Local index** built from the NRCeS release files, same two methods.

Both are local on purpose. A PHC on a bad line needs `validate` to work with no
network, so the offline path is the only path rather than a fallback we would
have to test separately.

### 2.2 Codification

```
suggest(text, valueset_slug, context) -> [{coding, score, linked}]
```

One implementation: Eka's `POST /med-link/nel/link` and `/batch` (5 at a time).
`context` carries unit and specimen for LOINC, where Eka's own docs say
accuracy depends on it, and we already hold both.

The stub returns an empty list. **Everything must still work when it does.** A
facility with no network gets a picker instead of a prefill, which is slower
and not broken. If anything becomes unusable when `suggest` returns nothing, we
have made codification load bearing, which the table forbids.

### 2.3 Capture

Already half decided and unchanged by this document:

```
transcribe(audio)                 -> transcript        # Eka scribe
extract(transcript, questionnaire)-> answers + spans   # ours, api/extract.py
```

Eka owns audio to transcript. We keep `api/extract.py`, because its rule, that
an answer without a span copied from the transcript is dropped, is the one
thing no upstream system does for us.

Eka's scribe can also return a whole FHIR bundle with entities already typed
and optionally codified. That is genuinely useful and we should read it, but as
**a set of proposals addressed to the tick**, never as rows. See invariant I4.

### 2.4 Bundle

```
bundle(thread, profile) -> FHIR Bundle
```

Rows in, document out. We store flat rows because trends and district counts
need columns, and we generate the document at the edge because that is what
ABDM consumes. The mapping already declares which resource each answer becomes,
so this is mechanical rather than clever.

## 3. The invariants

These hold whichever implementation is behind each seam. Each becomes a check.

- **I1.** A stored coding is in the valueset its question is bound to. Held in
  two places, because one of them cannot be enough. **Built 2026-10-31.**
  *At build time:* `Coding` has exactly one constructor, `Terminology.bound()`,
  and it consults the valueset before it returns, so a coding nothing vouched
  for is unconstructible anywhere in the product. The constructor is gated by a
  module private sentinel that `kernel/terminology.py` never exports, so
  `Coding(...)` called from any other file raises. A question declaring a code
  its valueset does not hold fails the build, naming both.
  *At write time:* `kernel/mapping._bound_fact` re-checks the code against the
  same authority before it will fill a column with it, and refuses a coding
  column that would land null.
  This wording replaces "enforced as a type at the write path, not as a lint",
  which is not achievable and the reason is structural rather than awkward: the
  compiled mapping is served to the renderer (`web/src/structured.ts` reads it,
  so `web/src/messages.check.ts` runs `json.dumps` over the whole of it), so a
  type object cannot reach the write path. The facts arrive as strings, a string
  carries no proof, and the proof is re-established where the row is made. The
  re-check is a dictionary lookup in an lru_cached local file: no socket, no
  database, nothing that can be down. Stronger than the lint wording it
  replaces, in both halves.
- **I2.** An answer a recording filled carries the span it came from.
  *(exists: `api/extract.py`)*
- **I3.** A non-text value a recording filled is owed a tick before commit.
  *(exists: `api/fill.py build_draft`, `web/src/scribe/scribe.check.ts`)*
- **I4.** A suggestion is not a confirmation. Anything arriving from
  codification or from Eka's bundle carries how sure it is. **There is no
  review queue and no human coding step**; the status is the mechanism. A
  codifier that reports `linked` writes `verification_status: confirmed`, and
  one that does not writes `unconfirmed`. Nothing blocks either way. What is
  forbidden is discarding the signal and storing a low confidence guess as a
  settled fact, because that record travels under the patient's ABHA number to
  clinicians who cannot ask us what it meant.
- **I5.** The audit row is written before the write executes. *(exists)*
- **I6.** A negated, hypothetical, family or historical finding is stored with
  that status, never dropped and never asserted. FHIR already has the fields;
  see section 4.

I6 is the one that is new and the one that is dangerous to get wrong. "Patient
denies chest pain" becoming a chest pain diagnosis is the failure that would
most damage trust in the record, and it is invisible once stored.

## 4. What we take from CARE, and what we do not

We take the **design**, which is plain FHIR. We take no dependency on CARE the
system; its adapter was deleted on 2026-10-30 and stays deleted.

**Bind questions to valuesets, do not enumerate codes.** CARE's entire symptom
and disease vocabulary is one filter:

```
system "http://snomed.info/sct"
filter concept is-a 404684003        # Clinical finding
```

Every descendant of that concept is legal. Observations are all of LOINC. Units
are all of `unitsofmeasure.org`. There is no list to author and none to
maintain across ontology releases.

**Two bindings, because there are two kinds of question.**

- `code` on the question, when the question *is* the concept. Systolic BP is
  always LOINC `8480-6`.
- `answer_value_set` on the question, when the *answer* carries the concept.
  Diagnosis is a slot; "type 2 diabetes" is the concept.

**Certainty and attribution are fields, not cleverness.** FHIR's Condition
already carries `verification_status` (unconfirmed, provisional, differential,
confirmed, **refuted**, entered-in-error), `clinical_status` (active, relapse,
inactive, remission, resolved), `category` (problem list, encounter diagnosis,
chronic), plus onset and severity. A denied symptom is `refuted`. A past
illness is `resolved` with an onset. A scribe's guess is `unconfirmed` until a
person confirms it. That is I6 satisfied by the standard, with nothing invented.

**Repeating groups, not `structured`.** This is the one place we do not copy
CARE, because CARE has not solved it and says so: `structured_type` carries
`# TODO : Add validation later`, and the response validator opens with
`if questionnaire["type"] == QuestionType.structured.value: return`, skipping
validation for exactly the fields that most need it.

The answer is already elsewhere in CARE's own model, fully validated and
native to FHIR R4: a **repeating group** (`repeats: true`), where each repeat
is a small set of sub-questions and the concept bearing one is a bound coding.

| Field | Each repeat carries | Becomes |
|---|---|---|
| diagnosis | code (clinical finding), verification status, clinical status, onset, severity | `Condition` |
| medications | drug (CDCI), dose, frequency, duration, route | `MedicationRequest` |
| investigations | test (LOINC) | `ServiceRequest` |
| dispense | drug (CDCI), quantity, batch | `MedicationDispense` |

One repeat is one resource, one repeat is one codification call, and every
repeat is validated. `structured` is then unused by the PHC bundle.

**Favourites and recents.** CARE keeps up to 50 favourite codes per user plus
recent views. A SNOMED branch holds about 100,000 concepts and a PHC medical
officer uses roughly forty. This is not a nicety; it is the difference between
a usable picker and an unusable one in a four minute consultation.

## 5. What each station becomes

| Station | Coding shape | Confirmed by |
|---|---|---|
| Reception, register | none; demographics are not clinical concepts | n/a |
| Nurse, vitals | 6 fixed `code` bindings, LOINC, type `quantity` with a bound UCUM unit | typed or device, already range checked; a tick if heard |
| Doctor, consultation | `answer_value_set` on diagnosis; narrative stays narrative | reading the note, plus a pick where unlinked |
| Doctor, prescription | `answer_value_set`, medication ontology | pick |
| Lab, result | 1 fixed `code` per analyte, plus a bound UCUM unit | typed |
| Pharmacy, dispense | `answer_value_set`, medication ontology, same codes as prescription | pick |

The count that matters: about **7 fixed codes and 4 valueset bindings** across
the whole PHC bundle. Not 41 of anything.

**Confirmation by exception, because sixty patients a day.** Per entity
confirmation is dead on arrival in an OPD. The rule:

- `linked` and not negated and above threshold: prefill, visible in the note
  the doctor reads anyway, committed with the note.
- unlinked, ambiguous, or any of the I6 statuses: surfaced for a pick or a
  tick. These are the only stops.
- Numbers keep their per field tick regardless. That rule is older than this
  document and is not relaxed by it.

## 6. Sequence

- [x] **1. Terminology seam with the local cache.** Done. Four methods now
      (`validate`, `bound`, `expand`, `concepts`), three generated files, and
      `scripts/seed_terminology.py` to generate them from a terminology server
      at design time so that "confirmed against LOINC 2.83" is reproducible
      rather than a claim. The script is deliberately not in the gate: it
      needs a network, and nothing at the point of care does.
- [ ] **2. Bind the 7 fixed codes.** Batch them through Eka codification with
      unit as context, confirm the list once by hand, write them into the
      cache. This is design time work; it never runs at the point of care.
- [x] **3. Bind the unit, and leave the question's type alone.** Done
      2026-10-31, and **narrowed from the original step**, which was to switch
      the 6 vitals and the lab result to `quantity`.
      What was built: every unit in both shipped bundles, nine of them, is now
      bound to the UCUM valueset at build time, read from the
      `styling_metadata.phc.unit` where it already lived next to the range that
      validates it. Nothing moved and nothing is duplicated.
      **The six vitals keep their `integer` and `decimal` types.** The reason
      is evidence rather than preference: an `integer` with a bound unit
      already produces a correct FHIR `valueQuantity` carrying the UCUM
      system, which the ABDM tier one validator confirms with zero findings on
      the generated WellnessRecord. Switching the type would change
      `api/fill.py` coercion, the voice grammar's number handling and the
      renderer's field, so it costs three layers of change for no difference at
      ABDM.
      **The lab result, which was what was left of this step, is done.** Done
      2026-10-31. The unit genuinely was an answer there rather than a
      property of the question, and the analyte was too: both now bind their
      ANSWER to a value set, which is the third binding form. The question
      types still did not change. What made the laboratory result different
      was never the type, it was that the concept and the unit are answers,
      and binding an answer is a different mechanism from switching a type.
      Check: `scripts/check_vitals.py`, and the tier one validation recorded in
      `docs/superpowers/plans/2026-10-31-application-architecture.md` section 3.
- [ ] **4. Replace `structured` with repeating groups** for diagnosis,
      medications, investigations and dispense, per the table in 4. Check: a
      repeat whose coding is outside its bound valueset is refused. Mutation:
      bind diagnosis to the observation valueset instead and confirm FAIL.
      **The binding half of this step is already built**, 2026-10-31:
      `answer_value_set` works, resolves at write time through the one
      validating constructor, and has three mapping sources and twenty nine
      checks behind it, driven by the laboratory result's analyte. What is
      left is the repeating group itself, which is the part that turns one
      repeat into one resource. A repeat's bound coding uses the form that now
      exists rather than needing a new one.
- [ ] **5. Codification seam plus stub.** Check: the whole PHC flow passes with
      the stub returning nothing.
- [ ] **6. Proposal and confirmation path.** I4 and I6 as checks. Mutation:
      make a suggestion commit without a person and confirm FAIL.
- [ ] **7. Bundle seam for `OPConsultRecord`**, validated against the NRCES
      profile.
- [ ] **8. Doctor templates**, assembled from the catalogue, only now.

Steps 1 to 3 are the Monday path and need no terminology server. Steps 5 to 7
are the ABDM path.

## 7. Decisions, settled 2026-10-30, with what the build changed

Three amendments were raised by the implementation on 2026-10-31 and accepted:
I1's wording now describes the unforgeable constructor plus the write path
re-check, `validate` takes a code rather than a coding, and step 3 is narrowed
to the lab result. Each is marked where it applies above. The four decisions
below are unchanged.

1. **Terminology.** We host it. Local file first, local index from the NRCeS
   release files second. See 2.1.
2. **`structured`.** Replaced by repeating groups of bound codings. See 4.
3. **Confirmation.** No queue and no human coding step. Confidence is carried
   as `verification_status` rather than enforced as a workflow. See I4.
4. **Eka's scribe output.** Both the bundle and the transcript. The bundle
   gives typed entities; the transcript is required anyway, because I2 needs
   the words an entity came from, and an entity we cannot trace is an entity
   we cannot defend.

**Still open, and the only one with a lead time.** Does Eka already hold a
SNOMED CT Affiliate License? If yes, step 2 is a download. If no, someone
starts the MLDS registration this week: it costs nothing and it gates ABDM
certification, though not Monday.

## 8. Known ceilings

- The local terminology cache cannot answer `expand` over a full SNOMED branch.
  Until a real server is behind the seam, diagnosis picking is limited to codes
  we have cached, and the doctor's fallback is narrative text. This is a
  degraded mode, not a broken one, and the note still reaches ABDM.
- Nothing here addresses who may edit a valueset. Step 1 treats the cache as
  read only and generated.
- `catalogue/vocab.py INSTRUMENTS` and `kernel/contracts.py INSTRUMENT_KINDS`
  still disagree on their fifth entry, recorded in the core and plugins plan.
  Unrelated to this work but touches the same declaration layer.
