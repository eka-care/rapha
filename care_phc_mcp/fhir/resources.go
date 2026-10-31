package fhir

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
)

// Refusal is a projection or a document refusing to be built. It is the Go
// spelling of the KeyError kernel/fhir.py raises, and the message is the
// Python's word for word, because a refusal sentence is one of the things the
// two engines are compared on.
type Refusal struct{ Why string }

func (r *Refusal) Error() string { return r.Why }

func refuse(format string, args ...any) error {
	return &Refusal{Why: fmt.Sprintf(format, args...)}
}

// Observation is one observation row as a FHIR R4 Observation.
//
// `status` is the row's own answer and never a literal here. It used to be
// `final`, on the argument that there is one path to a stored row and it goes
// through the guard with a person's tap on it. That argument is about whether
// a row EXISTS, and Observation.status is about whether its value is settled,
// which is a different question with a different answer.
//
// The two come apart in the laboratory, where this build already has the
// second pair of eyes: the operation that writes the values writes a report
// saying `preliminary`, and verifying it is a separate operation a separate
// person performs. So between those two taps every keyed value would be
// published as `final` while the report carrying them said `preliminary`. R4
// has the word for that state.
//
// A row with no status is REFUSED rather than given one. R4 makes the element
// required (1..1) and this file may not decide how settled somebody else's
// measurement is; the operation that writes the row declares it.
func Observation(row map[string]string, subject, encounter, performer string) (map[string]any, error) {
	if row[ColVerification] != "" || row[ColClinical] != "" {
		// R4's Observation has no verificationStatus and no clinicalStatus.
		// It has no negation element either: there is no way in this resource
		// to say that a finding was denied, hypothetical, a family member's
		// or historical. FHIR's answer is that such a finding is a Condition,
		// and invariant I6 is held there.
		//
		// So a row carrying one is refused rather than projected without it.
		// Dropping it would be the one failure this whole package exists to
		// prevent: a value whose certainty was recorded, published as a fact
		// because the resource it landed in had nowhere to put the doubt.
		return nil, refuse("observation row %s carries a clinical or verification "+
			"status, and R4's Observation has neither element. A finding whose "+
			"certainty matters is a Condition; publishing this as an Observation "+
			"would drop the doubt and keep the value.", idOf(row))
	}
	status := row["status"]
	if status == "" {
		return nil, refuse("observation row %s carries no status, and R4 requires "+
			"Observation.status. The operation that writes the row declares it; "+
			"this file may not choose how settled a measurement is.", idOf(row))
	}
	out := map[string]any{
		"resourceType": "Observation",
		"id":           row["id"],
		"status":       status,
		"subject":      map[string]any{"reference": subject},
		"encounter":    map[string]any{"reference": encounter},
	}
	if row["category"] != "" {
		// The row's own column. A bundle choosing a category is a bundle
		// declaring it in a mapping's {const: ...}, which is why this file
		// does not have to know what a vital sign is.
		out["category"] = []any{map[string]any{"coding": []any{
			map[string]any{"system": HL7Category, "code": row["category"]}}}}
	}
	if coding := Coding(row, ColCode, ColCodeSystem, ColCodeDisplay); coding != nil {
		code := map[string]any{"coding": []any{coding}}
		if shown, has := coding["display"]; has {
			code["text"] = shown
		}
		out["code"] = code
	} else if row[ColCode] != "" {
		out["code"] = map[string]any{"text": row[ColCode]}
	}
	if row["created_date"] != "" {
		out["effectiveDateTime"] = row["created_date"]
	}
	if performer != "" {
		out["performer"] = []any{map[string]any{"reference": performer}}
	}
	if value := row["value"]; value != "" {
		switch {
		case row[ColUnit] != "" && row[ColUnitSystem] != "":
			// Quantity.unit is the printable symbol and Quantity.code is the
			// coded one. For UCUM they are the same string: the symbol IS the
			// code, which is why the adapter keeps one column and not two.
			out["valueQuantity"] = map[string]any{"value": Number(value),
				"unit": row[ColUnit], "system": row[ColUnitSystem], "code": row[ColUnit]}
		case row[ColUnit] != "":
			out["valueQuantity"] = map[string]any{"value": Number(value), "unit": row[ColUnit]}
		default:
			out["valueString"] = value
		}
	}
	return out, nil
}

// Condition is one condition row as a FHIR R4 Condition.
//
// `verificationStatus` is the row's own answer and never a default. That is
// invariant I6 held at the projection as well as at the write: a finding the
// patient denied is published as `refuted`, which records it without
// asserting it, and a row that says nothing about how sure anybody was
// publishes no verificationStatus rather than a confident one.
//
// NRCeS's own Condition examples carry a clinicalStatus and no
// verificationStatus, so neither is required and both are emitted from what
// the row holds.
func Condition(row map[string]string, subject, encounter, performer string) (map[string]any, error) {
	out := map[string]any{"resourceType": "Condition", "id": row["id"],
		"subject":   map[string]any{"reference": subject},
		"encounter": map[string]any{"reference": encounter}}
	if clinical := Concept(row, ColClinical, ColClinicalSystem, ""); clinical != nil {
		out["clinicalStatus"] = clinical
	}
	if verification := Concept(row, ColVerification, ColVerificationSystem, ""); verification != nil {
		out["verificationStatus"] = verification
	}
	if code := Concept(row, ColCode, ColCodeSystem, ColCodeDisplay); code != nil {
		out["code"] = code
	}
	if row["onset"] != "" {
		out["onsetDateTime"] = row["onset"]
	}
	if row["created_date"] != "" {
		out["recordedDate"] = row["created_date"]
	}
	if performer != "" {
		out["recorder"] = map[string]any{"reference": performer}
	}
	return out, nil
}

// MedicationRequest is one medicine row as a FHIR R4 MedicationRequest.
//
// The dosage is a Dosage element rather than a sentence, which is the point of
// the five columns behind it: a dose as a Quantity with its UCUM unit, a coded
// route, and a course length as a Duration. It used to be one
// dosage_instruction string, so nothing downstream could read the dose.
//
// The frequency is published as dosageInstruction.additionalInstruction,
// carrying the concept the answer named. That is what NRCeS's own
// OPConsultRecord example does, and it is deliberately NOT turned into
// timing.repeat.frequency: reading a number out of the words of a label would
// be this file inventing structured data from a label, which is the one thing
// it may not do.
func MedicationRequest(row map[string]string, subject, encounter, performer string) (map[string]any, error) {
	status := row["status"]
	if status == "" {
		status = "unknown"
	}
	out := map[string]any{"resourceType": "MedicationRequest", "id": row["id"],
		// Both required by R4, and both the row's own: `intent` is a
		// {const: ...} in the operation's mapping rather than a literal here,
		// so this file decides nothing about what a prescription is.
		"status":    status,
		"subject":   map[string]any{"reference": subject},
		"encounter": map[string]any{"reference": encounter}}
	if row["intent"] != "" {
		out["intent"] = row["intent"]
	}
	if named := Concept(row, medication[0], medication[1], medication[2]); named != nil {
		out["medicationCodeableConcept"] = named
	}
	if row["created_date"] != "" {
		out["authoredOn"] = row["created_date"]
	}
	if performer != "" {
		out["requester"] = map[string]any{"reference": performer}
	}

	dosage := map[string]any{}
	if taken := Concept(row, route[0], route[1], route[2]); taken != nil {
		dosage["route"] = taken
	}
	if often := Concept(row, frequency[0], frequency[1], frequency[2]); often != nil {
		dosage["additionalInstruction"] = []any{often}
	}
	if dose := Quantity(row, "dose", "dose_unit", "dose_unit_system"); dose != nil {
		dosage["doseAndRate"] = []any{map[string]any{"doseQuantity": dose}}
	}
	if length := Quantity(row, "duration", "duration_unit", "duration_unit_system"); length != nil {
		dosage["timing"] = map[string]any{"repeat": map[string]any{"boundsDuration": length}}
	}
	if len(dosage) > 0 {
		out["dosageInstruction"] = []any{dosage}
	}
	return out, nil
}

// DocumentReference is one narrative row as a FHIR R4 DocumentReference
// carrying its text.
//
// THIS IS THE DESIGNED FALLBACK, and on the Python side it was a sentence
// rather than a path until it was measured: the terminology module says an
// uncoded diagnosis travels as narrative text and the note still reaches
// ABDM, and the architecture document's ceilings say it twice. It was not
// true. A narrative row had no projection, every profile requires at least
// one section, so a consultation whose findings this build cannot code
// published NOTHING. The probe that proves it is in
// scripts/check_codification.py on the Python side and in
// scripts/check_go_parity.py for this one.
//
// The shape is the NRCeS implementation guide's own, read from the
// OPConsultRecord example, where a DocumentReference carries status,
// docStatus, a type with a coding, a subject and one content.attachment with
// a contentType, a language, base64 data, a title and a creation instant. The
// example's attachment is a PDF of a laboratory report; this one is the
// note's own text, which is the same element with a different content type
// and needs nothing invented.
//
// `documentType` is the profile's own document type, passed in by Document
// below, because what kind of document this is is the profile's fact and not
// this function's. Nothing here names a document type.
//
// `encounter` is accepted and unused: R4's DocumentReference has a `context`
// element whose shape is not in the example, so it is left out rather than
// guessed at from the signature.
func DocumentReference(row map[string]string, subject, encounter, performer string,
	documentType *DocumentType) (map[string]any, error) {
	text := row["text"]
	if strings.Trim(text, " \t\n\r\v\f") == "" {
		// A narrative row with nothing in it is not a degraded document, it
		// is an empty attachment under a heading claiming there is a note.
		return nil, nil
	}
	attachment := map[string]any{"contentType": NarrativeType,
		"language": NarrativeLanguage,
		"data":     base64.StdEncoding.EncodeToString([]byte(text))}
	out := map[string]any{"resourceType": "DocumentReference", "id": row["id"],
		"meta":      map[string]any{"profile": []any{NRCES + "/DocumentReference"}},
		"status":    "current",
		"docStatus": "final",
		"subject":   map[string]any{"reference": subject}}
	if documentType != nil && documentType.Code != "" {
		out["type"] = map[string]any{
			"coding": []any{map[string]any{"system": SNOMED,
				"code": documentType.Code, "display": documentType.Text}},
			"text": documentType.Text}
		attachment["title"] = documentType.Text
	}
	if row["created_date"] != "" {
		attachment["creation"] = row["created_date"]
	}
	if performer != "" {
		out["author"] = []any{map[string]any{"reference": performer}}
	}
	out["content"] = []any{map[string]any{"attachment": attachment}}
	return out, nil
}

// Patient is a patient row as a FHIR R4 Patient.
//
// The ABHA number becomes an identifier and not the resource id. A national
// identifier is a fact about a person, not our name for their row, and a
// patient with no ABHA yet is an ordinary patient rather than an
// unprojectable one.
func Patient(row map[string]string) map[string]any {
	out := map[string]any{"resourceType": "Patient", "id": row["id"]}
	if row["name"] != "" {
		out["name"] = []any{map[string]any{"text": row["name"]}}
	}
	if row["sex"] != "" {
		out["gender"] = row["sex"]
	}
	if row["phone"] != "" {
		out["telecom"] = []any{map[string]any{"system": "phone", "value": row["phone"]}}
	}
	if row["abha_number"] != "" {
		out["identifier"] = []any{map[string]any{
			"type": map[string]any{"coding": []any{map[string]any{
				"system": "http://terminology.hl7.org/CodeSystem/v2-0203",
				"code":   "MR"}}},
			"system": "https://healthid.ndhm.gov.in",
			"value":  row["abha_number"]}}
	}
	return out
}

// Practitioner is an actor string as a FHIR R4 Practitioner.
//
// Every row carries its author, because a mapping record with no {actor: id}
// field fails lint. So the document always has an author to name, which is
// what Composition.author requires. The id is hashed rather than the raw
// actor string, which may be a login name.
func Practitioner(actor string) map[string]any {
	sum := sha256.Sum256([]byte(actor))
	return map[string]any{
		"resourceType": "Practitioner",
		"id":           "prac-" + hex.EncodeToString(sum[:])[:12],
		"name":         []any{map[string]any{"text": actor}},
	}
}

// Encounter is an encounter row as a FHIR R4 Encounter. Its status is this
// build's own workflow state TRANSLATED, never copied: see TranslatedStatus.
func Encounter(row map[string]string, subject string) map[string]any {
	status := "in-progress"
	if row["status"] == "completed" {
		status = "finished"
	}
	out := map[string]any{"resourceType": "Encounter", "id": row["id"],
		"status": status,
		"class": map[string]any{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
			"code": "AMB", "display": "ambulatory"},
		"subject": map[string]any{"reference": subject}}
	if row["created_date"] != "" {
		out["period"] = map[string]any{"start": row["created_date"]}
	}
	return out
}

// Projections is which function turns a row of each table into a resource. A
// table name, not a concept, for the same reason ResourceType is.
//
// Document used to call the observation projection for every row of every
// section on the Python side, so a section carrying conditions would have
// published them as Observations with a diagnosis in the code field. Nothing
// caught it because nothing but vitals had a projection to call.
var Projections = map[string]func(row map[string]string, subject, encounter, performer string,
	documentType *DocumentType) (map[string]any, error){
	"observation": func(row map[string]string, s, e, p string, _ *DocumentType) (map[string]any, error) {
		return Observation(row, s, e, p)
	},
	"condition": func(row map[string]string, s, e, p string, _ *DocumentType) (map[string]any, error) {
		return Condition(row, s, e, p)
	},
	"medication_request": func(row map[string]string, s, e, p string, _ *DocumentType) (map[string]any, error) {
		return MedicationRequest(row, s, e, p)
	},
	"notes": DocumentReference,
}

// TypedByProfile is the resources whose projection needs to know what kind of
// document it is travelling in. One, and it is the narrative attachment: what
// a note IS is the profile's fact, so the projection is handed it rather than
// typing it. Every other projection describes something that means the same
// thing in any document and is given nothing.
var TypedByProfile = map[string]bool{"notes": true}

// idOf is a row's id as Python's %r of it renders it, which is how both
// engines' refusal sentences come out the same.
func idOf(row map[string]string) string {
	if value, has := row["id"]; has {
		return pyval.Repr(value)
	}
	// Python's row.get("id") is None for a row with no id column at all, and
	// %r of None is None.
	return "None"
}
