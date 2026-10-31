# NRCeS Composition section codes, read off NRCeS's own examples

**Status.** Fact, not a decision. Read on 2026-10-30 from the NRCeS
implementation guide's published example bundles, through the ABDM docs
server's `get_fhir_example`, catalogue version 2026.09.16.

**Why this file exists.** `Composition.section.code` is how a section slice is
discriminated, and the architecture document's open item 3 asked for the codes
rather than guessing them. Inventing a SNOMED code files a record under the
wrong heading, which reads as correct everywhere it is read and is therefore
the worst kind of wrong. The answer turned out to be different for the two
record types this product emits, which is why it is written down.

## WellnessRecord: there are no section codes, and that is not an omission

`Bundle-WellnessRecord-example-01`, profile
`https://nrces.in/ndhm/fhir/r4/StructureDefinition/WellnessRecord`.

Every section in NRCeS's own example carries exactly two keys, `title` and
`entry`. None carries a `code`. The seven are Vital Signs, Body Measurement,
Physical Activity, General Assessment, Women Health, Lifestyle and Document
Reference.

`Composition.type` is `{"text": "Wellness Record"}`: no `coding`, no system,
no code.

So a WellnessRecord section is identified by its title, and emitting a
CodeableConcept with text and no coding is what the publisher does. This
confirms what `kernel/fhir.py` already emits rather than changing it. **Do not
invent a SNOMED code for a WellnessRecord section or for its type.** A code
nobody published is a code no reader can resolve.

## OPConsultRecord: eight real codes, all SNOMED CT

`Bundle-OPConsultNote-example-05`. `Composition.type` is SNOMED CT
`371530004`, Clinical consultation report, under `http://snomed.info/sct`,
which matches the fixed value the profile digest already gives.

Every section code below is SNOMED CT under that same system URL.

| Section title | Code | Display |
|---|---|---|
| Chief complaints | `422843007` | Chief complaint section |
| Allergies | `722446000` | Allergy record |
| Medical History | `371529009` | History and physical report |
| Investigation Advice | `721963009` | Order document |
| Medications | `721912009` | Medication summary document |
| Procedure | `371525003` | Clinical procedure report |
| Follow Up | `736271009` | Outpatient care plan |
| Document Reference | `371530004` | Clinical consultation report |

Note that Document Reference repeats the Composition's own type code. That is
what the example publishes; it is not a transcription error here.

## The four slices with no code yet

The profile defines twelve slices. The example populates eight. These four are
left out of it entirely, so this file has no code for them:

PhysicalExamination, FamilyHistory, Referral, OtherObservations.

They are optional (`min: 0`), so a bundle omitting them is valid, and the PHC
bundle has no reason to emit one before the OPConsultRecord module. When one
is needed, read the slice's own fixed value out of the StructureDefinition
rather than reusing a code from the table above because it looks close.
`nrces.in` rejected a direct fetch with a certificate error on 2026-10-30, so
the route in is the docs server or the packaged guide `ndhm.in#6.5.0`.

## What this changes

- The vitals slice, which emits WellnessRecord, is correct as built. The gap
  recorded against it was a gap in our knowledge, not in the code.
- The OPConsultRecord module has its section codes and does not need to wait
  on anyone.
- Nothing here is a decision, so nothing here is the owner's to confirm.
