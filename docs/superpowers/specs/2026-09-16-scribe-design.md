# Scribe: record anywhere, fill any questionnaire

Status: draft for review · 2026-09-16 · decision A (questionnaire is the only template format)

## 1. Problem

Today the mic is bound to a form. `web/src/screens/Encounter.tsx:154` picks the
first operation whose instrument is `scribe`, opens its panel, and mounts the
`Recorder` above it (`web/src/form/Panel.tsx:285`). No scribe-enabled operation
at this step means the mic is disabled. The mapping from Eka's output to fields
is hand-written per link_id (`api/scribe.py:329 fill()`), so every new form needs
new code.

We want:

1. Recording and transcription that do not depend on persona or on an open form.
2. A template per station, chosen by default, changeable by the user.
3. One filling engine that fills **any** questionnaire from a transcript, so custom
   forms and assessments are scribe-fillable with no per-form code.
4. Clinically deep templates per specialty.

## 2. Decision

**Every template is a CARE-format questionnaire** (the shape already in
`questionnaires/*.json`: `slug`, `questions[]` with `link_id`, `type`,
`structured_type`, `answer_option`, `unit`, `enable_when`, nested `questions`).

Eka (or any speech service behind `care_phc/connectors/scribe/base.py`) is used
**only for audio → transcript**. EkaScribe templates are prose + markdown with no
typed fields (see research, §9), so they cannot carry VA per eye, FDI tooth
numbers or mg/kg doses. Structure lives on our side.

## 3. Flow

```
mic (any screen) ──► session {subject, actor, station, template_slug}
        │
        ▼
 speech connector ──► transcript            (existing eka.py, transcript only)
        │
        ▼
 flatten(questionnaire) ──► field list      (pure code)
        │
        ▼
 extract(field list, transcript) ──► {link_id: value, confidence, evidence}   (LLM)
        │
        ▼
 coerce/validate per field type ──► Draft   (pure code; drops what fails)
        │
        ▼
 renderer shows Draft in the template's form ──► human taps to commit (unchanged)
```

The commit and readback rules do not change: output is a `kernel.contracts.Draft`,
`commit: tap`, discrete values arrive unconfirmed.

## 4. Components

### 4.1 Recorder, decoupled (web)

- The mic in `Composer.tsx` is always enabled when a subject (patient or encounter)
  is in context. It no longer needs a scribe operation at this step.
- Pressing it starts recording immediately; **no form opens**. A slim recording bar
  shows elapsed time, the active template name, and a template switcher.
- On stop, the Draft opens in the template's form for review. If transcription
  succeeds but extraction yields nothing, show the transcript with "nothing to fill".

### 4.2 Station templates (config, not code)

In `bundles/phc/bundle.yaml`, per station:

```yaml
scribe:
  reception: { default: phc-register-v1 }
  nurse:     { default: phc-vitals-v1 }
  community: { default: null, choose: [asha-hbnc-v1, asha-cbac-v1, asha-anc-v1, phc-household-visit-v1] }
  doctor:    { default: rx-general-v1,
               choose: [rx-general-v1, soap-v1, rx-paeds-v1, rx-ophth-v1, rx-dental-v1, rx-anc-v1] }
```

- `default: null` + `choose` means the user picks before or after recording (ASHA
  has several surveys).
- A doctor's last choice is remembered per user (server-side preference) and
  becomes their default. Their specialty is set when they onboard.
- The template can be changed **after** recording: re-extraction reruns on the
  saved transcript, so no re-recording is needed. One recording can fill two
  templates (e.g. vitals + Rx), up to 2, matching Eka's per-session limit
  in spirit.

### 4.3 `flatten(questionnaire)` (pure)

Walks nested `questions`, returns an ordered list of:

```
{link_id, path, text, description, type, structured_type, required, repeats,
 unit, options: [value...], enable_when}
```

Groups become path prefixes (`right_eye.va_unaided`). Display items are dropped.

### 4.4 `extract(fields, transcript)` (LLM)

- Uses the Claude client pattern in `agent/planner.py` (`claude-opus-5`, env-key
  gated). One call per template, with tool/JSON output that must match the field list.
- For every field, the model returns `value | null`, `confidence 0–1`, and
  `evidence` (the transcript span it came from). **A field with no evidence is
  returned as null**, which stops the model filling in values nobody said.
- Choice fields: the model must pick from `options`; free text is rejected at
  coercion.
- Offline / no key: return an empty Draft with the transcript (the existing
  fail-closed "show the keypad" outcome). No regex fallback.

### 4.5 `coerce(field, value)` (pure)

Per `type`: `integer/decimal` parse + unit normalise (UCUM); `date` → ISO
`YYYY-MM-DD` (handles "15 August", "last Monday" relative to encounter date);
`boolean`; `choice` exact then case/space-insensitive match against options
(eka-relay's `generic.js:257` rule); `quantity` value+unit; `structured` via
per-type shapers for `medication_request` and `condition` (moved from
`api/scribe.py fill()`, which is deleted). Anything that fails coercion is
dropped and listed in the Draft as "heard but not filled".

`enable_when` is evaluated after coercion; values for disabled fields are dropped.

Confidence handed to the renderer = model confidence, capped at 0.89 for every
discrete value, so all discrete values still render unconfirmed (current rule).

### 4.6 API

- `POST /scribe/sessions` takes `{subject, templates: [slug]}` instead of deriving
  targets from operations. `templates` defaults from station config.
- `POST /scribe/sessions/{id}/extract` `{templates: [slug]}` reruns extraction on the
  held transcript (the template switch).
- Transcript is held for 24 hours (see §10), then dropped.

### 4.7 Custom forms

Any questionnaire with `styling_metadata.phc.scribe: true` appears in the
switcher for the stations it lists. Nothing else is needed: flatten + extract +
coerce is generic. This is the "algorithmic form filling" capability. It reads
the form's definition, not the page's DOM, so it is simpler than eka-relay.

## 5. Template content (v1)

New questionnaires under `questionnaires/`. Fields beyond generic SOAP:

| Slug | Must-have structure |
|---|---|
| `rx-general-v1` | complaints + duration, comorbidities (DM/HTN/TB), allergies, tobacco/alcohol, diagnosis (condition), medications (medication_request: drug, strength, dose, frequency 1-0-1, food relation, duration), investigations, follow-up date, referral |
| `soap-v1` | S / O / A / P text + diagnosis + medications |
| `rx-paeds-v1` | age in months, weight/length/HC/MUAC, birth weight, gestation, feeding, milestones, immunisation (UIP vaccine/dose/date/next due), IMNCI danger signs, meds with mg/kg (dose computed and capped by code, never by model) |
| `rx-ophth-v1` | groups `right_eye`/`left_eye`: VA unaided/pinhole/BCVA (6/x), near, IOP + method, lids, slit lamp (conj, cornea, AC, iris, pupil, lens + grade), fundus (disc, CDR, macula, DR grade), refraction (sph/cyl/axis/add), diagnosis per eye; PD |
| `rx-dental-v1` | repeating `tooth` group: FDI number (choice 11–48, 51–85), status, surfaces (M/O/D/B/L), mobility, procedure; CPI score, oral hygiene, oral cancer screen |
| `rx-anc-v1` | LMP, EDD (computed), GA weeks (computed), G/P/A/L, visit no., BP, weight, Hb, fundal height, FHR, presentation, oedema, urine alb/sugar, blood group, HIV/VDRL/HBsAg, Td doses, IFA/calcium, high-risk flags, RCH ID |
| `phc-vitals-v1` (extend) | temp, pulse, RR, BP sys/dia, SpO2, weight, height, BMI (computed), RBS, pain score |
| `phc-register-v1` (existing) | unchanged; confirm scribe flag |
| `asha-hbnc-v1` | visit day (3/7/14/21/28/42), newborn weight/temp/feeding/cord/jaundice/danger signs, mother bleeding/fever, refer |
| `asha-cbac-v1` | CBAC items as choices with scores; total score computed; ≥4 → refer flag; symptom checklist |
| `asha-anc-v1` | registration ≤12 wk, visit dates, IFA, danger signs, birth plan, JSY |

Rule: **derived values (EDD, GA, BMI, CBAC total, mg/kg dose) are computed by
code from extracted inputs, never extracted.** These fields carry
`read_only: true` and a `formula`.

Clinical review of each template by a practising clinician is a prerequisite to
marking it `active`; until then `status: draft`.

## 6. Error handling

| Failure | Result |
|---|---|
| Transcription fails | Session error; audio retained per retention rule; retry button |
| No LLM key / LLM error | Empty Draft + transcript (keypad) |
| Model returns a value with no evidence, off-option choice, or unparseable value | Field dropped, listed as "heard but not filled" |
| Template switched after commit | Not allowed; switcher is disabled once committed |

## 7. Testing

- `flatten` + `coerce`: one `scribe_fill.check.py` with asserts over the new
  templates (nested groups, choice matching, dates, enable_when, derived fields).
- `extract`: golden transcripts (one per template, English + Hinglish) with an
  expected-field set; run against the live model only when the key is present, and
  measure field precision and recall. Precision matters more: a wrong value is
  worse than an empty one.
- Web: extend `web/src/scribe/scribe.check.ts` for mic-enabled-without-operation
  and template switch → re-extract.

## 8. Out of scope (v1)

- Live streaming transcription / fill-as-you-speak.
- Form builder UI for custom questionnaires (authored as JSON for now).
- Filling third-party web forms by DOM (eka-relay's domain).
- Coding to ICD-10/SNOMED in extraction. The existing readback rule still
  applies: codes are only offered where a questionnaire asks for them explicitly.

## 9. Research notes

- **EkaScribe templates**: `{id, title, desc, section_ids, default}`, where `desc`
  is a prose instruction and output is markdown. A session takes at most 2 templates.
  No typed fields.
- **CARE questionnaire** (`care/emr/resources/questionnaire/spec.py`): types
  group/boolean/decimal/integer/string/text/display/date/dateTime/time/choice/url/
  quantity/structured; `enable_when` with 7 operators; `unit`, `formula`,
  `repeats`. MedicationRequest `dosage_instruction` carries timing, route, and
  dose_and_rate.
- **eka-relay**: no LLM. It scans the DOM, resolves each field's label, and fills
  by field_code with read-back. We reuse its choice-matching and verify-after-fill
  ideas; the transcript → values step is new.

## 10. Decisions (2026-09-16)

1. **Transcript retention: 24 hours**, independent of the audio window. Audio
   follows the existing `AudioRetention` rule; the transcript is deleted 24h after
   the session ends. §4.6 is superseded on this point.
2. **Clinical review**: templates are built now as `status: draft`. Doctors at Eka
   review each specialty template before it is flipped to `active`.
3. **Languages in v1**: en-IN, Hinglish, Hindi, Tamil, Telugu. Golden transcripts
   (§7) cover each language for at least `rx-general-v1` and `phc-vitals-v1`.
   Extraction works on the native-script transcript directly; field values are
   written in English except free-text fields, which keep the spoken language.
4. **Numbers may be filled by a recording, behind a per-field tick.** This
   reverses the "a recording never fills a number" rule
   (`web/src/scribe/session.ts narrative()`, `kernel/DECLARATIONS.md` §4, the
   `_lint_instrument` device rule). Every non-text value a recording fills
   (integer, decimal, quantity, date, choice, boolean) opens with the words it
   came from beside it, and Commit stays disabled until the person ticks each
   one. Text and structured rows keep today's treatment (unconfirmed highlight,
   no tick). `readback: required` and `commit: tap` are unchanged.
5. **A template is an operation.** A template is named by operation id, and
   the questionnaire it fills is that operation's `input`, because only an
   operation's mapping can write. Station config (§4.2) therefore lists
   operation ids (e.g. `phc.op.vitals-record`), not questionnaire slugs. The
   instrument's `operations` list is the allowlist of what a recording may fill.
   Specialty templates (Plan 2) each get an operation whose mapping writes
   their structured findings. Custom forms (Plan 2) get one generic operation
   that stores a questionnaire response.
6. **The last template a user chose is remembered in the browser**, keyed by
   role, until the kernel has real users (today it has an `X-PHC-Role`
   header, not accounts). §4.2's server-side preference waits for that.
7. **Delivery is split.** Plan 1 is the engine on the forms that exist today:
   decoupled mic, station defaults and switcher, flatten/extract/coerce,
   re-extract, 24h transcript, languages, number ticks. Plan 2 is the §5
   templates, their operations and mappings, and the generic custom-form
   operation.
