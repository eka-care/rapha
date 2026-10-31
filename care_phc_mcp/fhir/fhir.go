// Package fhir is the bundle seam: rows in, an ABDM document out. It is the
// Go spelling of kernel/fhir.py and nothing more.
//
// WHY A PROJECTION AND NOT A STORAGE FORMAT
// -----------------------------------------
// We store flat rows and generate the document at the edge. Flat rows,
// because a district count is `WHERE code = '8480-6'` and a trend is an
// `ORDER BY`. A document at the edge, because that is what ABDM consumes: a
// DocumentBundle is an envelope for sending, not a record for keeping.
//
// THE RULE THIS FILE MUST NOT BREAK
// ---------------------------------
// It may not name a clinical concept. There is no `if code == "29463-7"` here
// and there must never be one. What a resource knows about itself comes from
// the row, and which section of which profile it lands in is DECLARED on the
// bundle and passed in by the caller. The only clinical vocabulary here is
// ABDM's own profile table, which is the standard's and not a facility's.
// scripts/check_go_parity.py holds this file to that rule with the same word
// list scripts/check_rx.py holds kernel/fhir.py to.
//
// WHY THIS DOES NOT USE terminology.Coding.ToFHIR()
// -------------------------------------------------
// It goes the same way the Python does, and the way is deliberate. A coding
// here is built from stored COLUMNS, which are text read back out of SQLite,
// and a `Coding` cannot be constructed from text without re-resolving it
// through a value set. Doing that at projection time would change behaviour
// rather than port it: a row whose code its value set no longer holds is
// published by the Python as what the row says, and a Coding-based path would
// refuse to publish it at all. The write path is where a code is vouched for
// (mapping.boundFact and terminology.AnswerCoding, invariant I1); by the time
// a row is read back, the proof has already been made and the row is the
// record of it. So ToFHIR keeps the one caller G5 found for it, its own test,
// and this is reported rather than quietly resolved either way.
//
// WHAT IS HERE AND WHAT IS NOT
// ----------------------------
// Here: the WellnessRecord and OPConsultRecord profiles, and the Observation,
// Condition, MedicationRequest, DocumentReference, Patient, Encounter and
// Practitioner projections those two need.
//
// Not here, and each a named plan step rather than an omission: the
// ServiceRequest projection an investigation needs, the gateway call that
// sends a bundle, and the ECDH encryption M2 wraps one in.
//
// WHAT NO GO CALLER CAN DO YET, AND WHY THAT IS NOT THIS PACKAGE'S DOING
// ----------------------------------------------------------------------
// `Document` takes the section placement as an argument, exactly as the
// Python does, because where a row goes in a published document is a
// declaration and not this file's business. The Python caller reads it from
// `documents` in bundles/<id>/bundle.yaml. That declaration is NOT in
// catalogue.json: it is absent from kernel/contracts.BUNDLE_KEYS, so the word
// "documents" does not appear in the compiled artifact at all, and no Go
// process can read it. The production caller is the outbox (G8), which is
// where that seam has to be closed; this package is held to the Python's
// behaviour by scripts/check_go_parity.py, which passes it the Python
// bundle's own declaration.
package fhir

import (
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"
)

// ---------------------------------------------------------------------------
// ABDM's grammar. Not a facility's words: these come from the NRCeS India
// profiles and a bundle declaring something else is not an ABDM bundle.
// ---------------------------------------------------------------------------

const (
	NRCES       = "https://nrces.in/ndhm/fhir/r4/StructureDefinition"
	LOINC       = "http://loinc.org"
	UCUM        = "http://unitsofmeasure.org"
	SNOMED      = "http://snomed.info/sct"
	HL7Category = "http://terminology.hl7.org/CodeSystem/observation-category"
)

// How a narrative row travels. text/plain because what is stored is the
// note's own words and not a rendered document, and a content type that
// promised markup would be a claim about the text. The language is the
// Composition's own, which is the only language this product writes a note in
// today.
const (
	NarrativeType     = "text/plain"
	NarrativeLanguage = "en-IN"
)

// DocumentBundle is the envelope profile every document carries.
var DocumentBundle = NRCES + "/DocumentBundle"

// Section is one of a profile's Composition.section slices.
//
// Code "" is not a placeholder to be tidied away later; it is a gap being
// reported. NRCeS discriminates a section slice by its code, and for
// WellnessRecord no section code is published anywhere this build can read, so
// a section is emitted with its title and its entries and no code. Inventing
// a SNOMED code to fill the hole would be worse than leaving it visible: a
// wrong section code is a record filed under the wrong heading, which reads
// as correct everywhere it is read.
type Section struct {
	Title   string `json:"title"`
	Code    string `json:"code"`
	Display string `json:"display"`
}

// DocumentType is a profile's own Composition.type.
type DocumentType struct {
	Code string `json:"code"`
	Text string `json:"text"`
}

// Profile is one ABDM hiType this build emits.
type Profile struct {
	Profile string       `json:"profile"`
	Title   string       `json:"title"`
	Type    DocumentType `json:"type"`
	// Every path the NRCeS digest for this profile requires on the
	// Composition, so a check can assert the document fills them instead of
	// asserting a list somebody typed twice.
	Required []string           `json:"required"`
	Sections map[string]Section `json:"sections"`
}

// Profiles is one entry per ABDM hiType we emit.
var Profiles = map[string]Profile{
	"WellnessRecord": {
		Profile: NRCES + "/WellnessRecord",
		Title:   "Wellness Record",
		// Composition.type, which the digest requires (min 1) while fixing no
		// value, unlike OPConsultRecord where it fixes a SNOMED code. The
		// digest requires Composition.type and not Composition.type.coding
		// for this profile, so a CodeableConcept carrying only `text`
		// satisfies it, and that is what is emitted while the code is absent.
		Type:     DocumentType{Code: "", Text: "Wellness record"},
		Required: []string{"status", "type", "subject", "date", "author", "title", "section"},
		Sections: map[string]Section{
			"VitalSigns":        {Title: "Vital signs"},
			"BodyMeasurement":   {Title: "Body measurement"},
			"PhysicalActivity":  {Title: "Physical activity"},
			"GeneralAssessment": {Title: "General assessment"},
			"WomenHealth":       {Title: "Women health"},
			"Lifestyle":         {Title: "Lifestyle"},
			"OtherObservations": {Title: "Other observations"},
			"DocumentReference": {Title: "Document reference"},
		},
	},
	// Read off NRCeS's own Bundle-OPConsultNote-example-05 and recorded in
	// docs/superpowers/specs/2026-10-30-nrces-section-codes.md. Unlike
	// WellnessRecord above, every section here HAS a published SNOMED code,
	// and Composition.type is fixed by the profile digest to 371530004.
	//
	// Four of the profile's twelve slices are absent, and absent on purpose:
	// PhysicalExamination, FamilyHistory, Referral and OtherObservations are
	// not populated by the example, so no code for them was published
	// anywhere this build could read. They are min 0, so omitting them is
	// valid, and reusing a code from the table below because it looks close
	// is how a record gets filed under the wrong heading.
	"OPConsultRecord": {
		Profile:  NRCES + "/OPConsultRecord",
		Title:    "OP Consultation Record",
		Type:     DocumentType{Code: "371530004", Text: "Clinical consultation report"},
		Required: []string{"status", "type", "subject", "encounter", "date", "author", "title", "section"},
		Sections: map[string]Section{
			"ChiefComplaints":     {Title: "Chief complaints", Code: "422843007", Display: "Chief complaint section"},
			"Allergies":           {Title: "Allergies", Code: "722446000", Display: "Allergy record"},
			"MedicalHistory":      {Title: "Medical History", Code: "371529009", Display: "History and physical report"},
			"InvestigationAdvice": {Title: "Investigation Advice", Code: "721963009", Display: "Order document"},
			"Medications":         {Title: "Medications", Code: "721912009", Display: "Medication summary document"},
			"Procedure":           {Title: "Procedure", Code: "371525003", Display: "Clinical procedure report"},
			"FollowUp":            {Title: "Follow Up", Code: "736271009", Display: "Outpatient care plan"},
			// The example publishes the Composition's own type code here.
			// That is what it publishes; it is not a transcription slip.
			"DocumentReference": {Title: "Document Reference", Code: "371530004", Display: "Clinical consultation report"},
		},
	},
}

// ResourceType is which resource a row of each table becomes. A table name,
// not a concept: this says "an observation row is a FHIR Observation", which
// is true of every bundle, and says nothing about what any particular
// observation means.
var ResourceType = map[string]string{
	"observation":        "Observation",
	"notes":              "DocumentReference",
	"patient":            "Patient",
	"encounter":          "Encounter",
	"condition":          "Condition",
	"medication_request": "MedicationRequest",
}

// The columns a coding spans, by prefix. The adapter owns its schema, so
// these are the query grammar's field names, which the adapter stores
// verbatim.
const (
	ColCode        = "code"
	ColCodeSystem  = "code_system"
	ColCodeDisplay = "code_display"
	ColUnit        = "unit"
	ColUnitSystem  = "unit_system"
)

// The columns a Condition's two status codings span, and the three each of a
// MedicationRequest's coded dosage parts spans.
const (
	ColClinical           = "clinical_status"
	ColClinicalSystem     = "clinical_status_system"
	ColVerification       = "verification_status"
	ColVerificationSystem = "verification_status_system"
)

var (
	medication = [3]string{"medication", "medication_system", "medication_display"}
	route      = [3]string{"route", "route_system", "route_display"}
	frequency  = [3]string{"frequency", "frequency_system", "frequency_display"}
)

// StatusBinding is every stored column a projection below copies VERBATIM
// into a FHIR `code` element, and the value set R4 binds that element to.
//
// `code` in the FHIR sense, not a CodeableConcept: a bare token from a fixed
// list, with no system column beside it, so none of the three binding forms
// in the terminology package applies and nothing validated these.
//
// A column is here because a projection copies it, which is why
// encounter.status and diagnostic_report.status are NOT: Encounter translates
// its stored workflow state into an R4 code rather than copying it, and no
// projection reads a diagnostic_report row at all.
//
// Keyed by table and column rather than by column, because `status` means a
// different list on each resource.
var StatusBinding = map[[2]string]string{
	{"observation", "status"}:        "observation-status",
	{"medication_request", "status"}: "medicationrequest-status",
	{"medication_request", "intent"}: "medicationrequest-intent",
}

// TranslatedStatus is the columns a projection reads from a row and does NOT
// copy into a FHIR `code` element, so that a check can tell "no binding was
// declared" from "this is deliberately not a FHIR code". encounter.status is
// this build's own workflow state, translated by Encounter below.
var TranslatedStatus = map[[2]string]bool{{"encounter", "status"}: true}

// CodedStatus is the statuses that are a CodeableConcept rather than a bare
// code, so they were already bound and by a stronger mechanism than the table
// above: each carries its code system in a column beside the code, which
// means the answer went through the one validating constructor of a Coding.
// These are ANSWERS a clinician gave; everything in StatusBinding is a
// literal an operation declared.
var CodedStatus = map[[2]string]string{
	{"condition", "clinicalStatus"}:     ColClinical,
	{"condition", "verificationStatus"}: ColVerification,
}

// Sections is the section slices this profile declares. A caller may not
// invent one.
func Sections(profile string) map[string]Section { return Profiles[profile].Sections }

// ---------------------------------------------------------------------------
// the small conversions
// ---------------------------------------------------------------------------

// namespaceURL is RFC 4122's URL namespace, which is what uuid.NAMESPACE_URL
// is in Python.
var namespaceURL = [16]byte{0x6b, 0xa7, 0xb8, 0x11, 0x9d, 0xad, 0x11, 0xd1,
	0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30, 0xc8}

// URN is a stable urn:uuid for a row id.
//
// Stable, because a bundle regenerated from the same rows must be the same
// bundle: ABDM deduplicates on the bundle identifier and a fresh uuid4 per
// projection would publish the same visit twice under two identities. A
// version 5 uuid over the row id does that with no state to keep.
//
// Written out here rather than taken from a uuid library, because the whole
// deployment argument for Go is one file copied to a clinic PC and a third
// party dependency for twenty lines of SHA-1 is not worth the supply chain.
func URN(seed string) string {
	sum := sha1.Sum(append(namespaceURL[:], []byte("phc:"+seed)...))
	var id [16]byte
	copy(id[:], sum[:16])
	id[6] = (id[6] & 0x0f) | 0x50 // version 5
	id[8] = (id[8] & 0x3f) | 0x80 // RFC 4122 variant
	hexed := hex.EncodeToString(id[:])
	return fmt.Sprintf("urn:uuid:%s-%s-%s-%s-%s", hexed[0:8], hexed[8:12],
		hexed[12:16], hexed[16:20], hexed[20:32])
}

// pythonFloat is Python's float(str) grammar, which is wider than Go's
// strconv.ParseFloat in two ways that matter only because a column is text
// and text is whatever was written into it: Python strips surrounding
// whitespace, and it allows single underscores between digits. Copied rather
// than narrowed, so that a value the Python turns into a FHIR decimal is not
// published by the Go as a quoted string.
var pythonFloat = regexp.MustCompile(
	`^[+-]?(?:(?:[0-9](?:_?[0-9])*(?:\.(?:[0-9](?:_?[0-9])*)?)?|\.[0-9](?:_?[0-9])*)(?:[eE][+-]?[0-9](?:_?[0-9])*)?|[iI][nN][fF](?:[iI][nN][iI][tT][yY])?|[nN][aA][nN])$`)

func parseFloat(text string) (float64, bool) {
	trimmed := strings.Trim(text, " \t\n\r\v\f")
	if !pythonFloat.MatchString(trimmed) {
		return 0, false
	}
	f, err := strconv.ParseFloat(strings.ReplaceAll(trimmed, "_", ""), 64)
	if err != nil {
		return 0, false
	}
	return f, true
}

// Number is a stored value as a JSON number where it is one, else as given.
//
// Every column in the SQLite adapter is TEXT, so a systolic of 140 reads back
// as "140". FHIR's Quantity.value is a decimal and a quoted number fails
// validation, so the cast happens here, at the one place that turns a row
// into FHIR, rather than in the adapter where it would have to guess which
// columns are numeric.
//
// One limit, stated rather than hidden: a value whose magnitude is beyond an
// int64 is published as a float where the Python publishes an exact integer,
// because Python's int is arbitrary precision and Go's is not. No column in
// this build can hold such a number, the questionnaire ranges being what they
// are, so this is a difference recorded and not a difference measured.
func Number(value any) any {
	switch t := value.(type) {
	case int:
		return t
	case int64:
		return t
	case float64:
		return t
	}
	text, isText := value.(string)
	if !isText {
		return value
	}
	f, held := parseFloat(text)
	if !held {
		return value
	}
	if math.IsInf(f, 0) || math.IsNaN(f) {
		return f
	}
	if f == math.Trunc(f) && math.Abs(f) <= 1<<62 {
		return int64(f)
	}
	return f
}

// Coding is a FHIR Coding from the three columns one coding spans, or nil.
//
// No system means no coding. A code without a system is meaningless in FHIR
// R4 and unexportable to ABDM, so an uncoded row is projected without a
// code.coding rather than with a bare code nobody can resolve.
//
// An empty `display` argument means the caller is reading a coding that has
// no display column, which is not the same as a row whose display is blank.
func Coding(row map[string]string, code, system, display string) map[string]any {
	if row[code] == "" || row[system] == "" {
		return nil
	}
	out := map[string]any{"system": row[system], "code": row[code]}
	if display != "" && row[display] != "" {
		out["display"] = row[display]
	}
	return out
}

// Concept is a CodeableConcept from those columns, or nil.
//
// A coding where the row has a system, and {"text": ...} where it has only a
// code. The second is not a fallback worth being proud of; it is how an
// uncoded row stays readable instead of becoming an unresolvable code, and it
// is the shape a diagnosis this build cannot code would take if one ever
// reached a column.
func Concept(row map[string]string, code, system, display string) map[string]any {
	found := Coding(row, code, system, display)
	if found != nil {
		out := map[string]any{"coding": []any{found}}
		if shown, has := found["display"]; has {
			out["text"] = shown
		}
		return out
	}
	if row[code] != "" {
		return map[string]any{"text": row[code]}
	}
	return nil
}

// Quantity is a FHIR Quantity from a value column and its unit columns, or
// nil.
//
// A value with no unit is not a Quantity: a dose of 500 is a different thing
// in milligrams and in millilitres, so an unmeasured number is dropped here
// rather than published as if the reader could guess.
func Quantity(row map[string]string, value, unit, system string) map[string]any {
	if row[value] == "" || row[unit] == "" {
		return nil
	}
	out := map[string]any{"value": Number(row[value]), "unit": row[unit]}
	if row[system] != "" {
		// For UCUM the printable symbol IS the code, which is why the adapter
		// keeps one column: see Observation below.
		out["system"] = row[system]
		out["code"] = row[unit]
	}
	return out
}
