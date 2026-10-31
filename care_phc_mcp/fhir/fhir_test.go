package fhir

// The Go spelling of kernel/fhir.py's own demo(), which the port plan counts
// among the files that import the Python kernel directly and must be
// rewritten as Go tests.
//
// This file DOES write literals down, unlike parity_test.go beside it, and
// the difference is deliberate. A demo has to name a concrete code and a
// concrete unit or it is not a test of anything; the Python's own docstring
// says so, which is why scripts/engine_code.py exempts everything from
// `demo(` onward when it checks that no engine module types a clinical word.
// What holds the two engines to EACH OTHER is the parity check, not this.

import (
	"encoding/json"
	"testing"

	"github.com/eka-care/care_phc_mcp/store"
)

func TestAnObservationCarriesItsOwnCodeUnitAndStatus(t *testing.T) {
	row := map[string]string{"id": "obs-1", "category": "vital-signs",
		"code": "8480-6", "code_system": LOINC,
		"code_display": "Systolic blood pressure", "value": "140",
		"unit": "mm[Hg]", "unit_system": UCUM, "status": "final",
		"created_by": "user:nurse", "created_date": "2026-10-31T09:14:00+00:00"}
	obs, err := Observation(row, "urn:uuid:p", "urn:uuid:e", "urn:uuid:n")
	if err != nil {
		t.Fatal(err)
	}
	coded := obs["code"].(map[string]any)["coding"].([]any)[0]
	want := map[string]any{"system": LOINC, "code": "8480-6",
		"display": "Systolic blood pressure"}
	if !same(coded, want) {
		t.Fatalf("code.coding is %v, not the row's own %v", coded, want)
	}
	quantity := obs["valueQuantity"].(map[string]any)
	if !same(quantity, map[string]any{"value": int64(140), "unit": "mm[Hg]",
		"system": UCUM, "code": "mm[Hg]"}) {
		t.Fatalf("valueQuantity is %v", quantity)
	}
	// A quoted number is not a FHIR decimal, which is the whole of why
	// Number() exists: every column in the store is text.
	if _, quoted := quantity["value"].(string); quoted {
		t.Fatal("a quoted number is not a FHIR decimal")
	}
	if obs["status"] != "final" {
		t.Fatalf("status is %v", obs["status"])
	}
	category := obs["category"].([]any)[0].(map[string]any)["coding"].([]any)[0]
	if category.(map[string]any)["code"] != "vital-signs" {
		t.Fatalf("the category is the row's own column, got %v", category)
	}
	if _, err := json.Marshal(obs); err != nil {
		t.Fatal(err)
	}
}

func TestACodeWithNoSystemIsTextAndNeverAResolvableCoding(t *testing.T) {
	uncoded, err := Observation(map[string]string{"id": "o2", "code": "Haemoglobin",
		"value": "9.4", "unit": "g/dL", "status": "preliminary"},
		"urn:uuid:p", "urn:uuid:e", "")
	if err != nil {
		t.Fatal(err)
	}
	code := uncoded["code"].(map[string]any)
	if _, resolvable := code["coding"]; resolvable {
		t.Fatal("a code with no system is text, never a resolvable coding")
	}
	if code["text"] != "Haemoglobin" {
		t.Fatalf("code is %v", code)
	}
	if !same(uncoded["valueQuantity"], map[string]any{"value": 9.4, "unit": "g/dL"}) {
		t.Fatalf("valueQuantity is %v", uncoded["valueQuantity"])
	}
	// The status is the row's, not this package's. A keyed laboratory value
	// that nobody has verified is `preliminary` and is published as
	// `preliminary`.
	if uncoded["status"] != "preliminary" {
		t.Fatalf("status is %v", uncoded["status"])
	}
}

func TestAnObservationWithNoStatusIsRefusedRatherThanGivenOne(t *testing.T) {
	_, err := Observation(map[string]string{"id": "o3", "code": "x", "value": "1"},
		"urn:uuid:p", "urn:uuid:e", "")
	if err == nil {
		t.Fatal("an observation with no status was given one here")
	}
}

func TestAnObservationCarryingCertaintyIsRefused(t *testing.T) {
	// R4's Observation has nowhere to put the doubt, so the row goes nowhere
	// rather than being published as a fact.
	for _, column := range []string{ColVerification, ColClinical} {
		_, err := Observation(map[string]string{"id": "o4", "status": "final",
			column: "refuted"}, "urn:uuid:p", "urn:uuid:e", "")
		if err == nil {
			t.Fatalf("a row carrying %s was published as an Observation", column)
		}
	}
}

func TestAUrnIsStablePerRowAndDiffersBetweenRows(t *testing.T) {
	if URN("obs-1") != URN("obs-1") {
		t.Fatal("a bundle regenerated from the same rows must be the same bundle")
	}
	if URN("obs-1") == URN("obs-2") {
		t.Fatal("two rows share one identity")
	}
}

func TestAnAbhaNumberIsAnIdentifierAndNotOurRowId(t *testing.T) {
	pat := Patient(map[string]string{"id": "pat-1", "name": "Sunita Devi",
		"sex": "female", "abha_number": "12-3456-7890-1234"})
	identifier := pat["identifier"].([]any)[0].(map[string]any)
	if identifier["value"] != "12-3456-7890-1234" {
		t.Fatalf("identifier is %v", identifier)
	}
	if pat["id"] != "pat-1" {
		t.Fatal("an ABHA number is an identifier, not our row id")
	}
}

func TestAnEmptyNarrativeIsNoDocumentReference(t *testing.T) {
	// A narrative row with nothing in it is not a degraded document, it is an
	// empty attachment under a heading claiming there is a note.
	made, err := DocumentReference(map[string]string{"id": "n1", "text": "   "},
		"urn:uuid:p", "urn:uuid:e", "", nil)
	if err != nil {
		t.Fatal(err)
	}
	if made != nil {
		t.Fatalf("an empty note was published as %v", made)
	}
}

func TestEverySectionACallerMayAskForIsDeclaredByItsProfile(t *testing.T) {
	rows := stub{map[string][]map[string]string{
		"encounter": {{"id": "enc-1", "status": "completed",
			"created_date": "2026-10-31T09:00:00+00:00"}},
		"patient": {{"id": "pat-1", "name": "Sunita Devi"}},
		"notes": {{"id": "n1", "text": "seen and advised",
			"created_by": "user:ravi", "created_date": "2026-10-31T09:20:00+00:00"}},
	}}
	_, err := Document(rows, "enc-1", "OPConsultRecord",
		[]Want{{Slice: "NotASlice", Queries: []Query{{Resource: "notes"}}}},
		"2026-10-31T10:05:00+00:00", "")
	if err == nil {
		t.Fatal("a section the profile does not declare was emitted")
	}
	// And the narrative really does become a document, which is the fallback
	// that was a sentence rather than a path until it was measured.
	made, err := Document(rows, "enc-1", "OPConsultRecord",
		[]Want{{Slice: "DocumentReference", Queries: []Query{{Resource: "notes"}}}},
		"2026-10-31T10:05:00+00:00", "")
	if err != nil {
		t.Fatal(err)
	}
	entries := made["entry"].([]any)
	kinds := map[string]bool{}
	for _, one := range entries {
		resource := one.(map[string]any)["resource"].(map[string]any)
		kinds[resource["resourceType"].(string)] = true
	}
	for _, needed := range []string{"Composition", "Practitioner", "Patient",
		"Encounter", "DocumentReference"} {
		if !kinds[needed] {
			t.Fatalf("a consultation this build cannot code published no %s: %v",
				needed, kinds)
		}
	}
	if _, err := json.Marshal(made); err != nil {
		t.Fatal(err)
	}
}

func TestADocumentAboutNobodyIsRefused(t *testing.T) {
	rows := stub{map[string][]map[string]string{
		"encounter": {{"id": "enc-2"}},
		"notes":     {{"id": "n2", "text": "a note"}},
	}}
	_, err := Document(rows, "enc-2", "WellnessRecord",
		[]Want{{Slice: "DocumentReference", Queries: []Query{{Resource: "notes"}}}},
		"2026-10-31T10:05:00+00:00", "")
	if err == nil {
		t.Fatal("a document with no Composition.subject was published")
	}
}

func TestASectionWithNoProjectionIsRefusedRatherThanServedByTheNearestOne(t *testing.T) {
	rows := stub{map[string][]map[string]string{
		"encounter":       {{"id": "enc-3"}},
		"patient":         {{"id": "pat-3"}},
		"service_request": {{"id": "sr-1"}},
	}}
	if _, has := Projections["service_request"]; has {
		t.Skip("pick a resource with no projection")
	}
	_, err := Document(rows, "enc-3", "OPConsultRecord",
		[]Want{{Slice: "InvestigationAdvice",
			Queries: []Query{{Resource: "service_request", Where: store.Query{}}}}},
		"2026-10-31T10:05:00+00:00", "")
	if err == nil {
		t.Fatal("a row with no projection was published as something else")
	}
}

// same is a deep compare over what the projections return, which is plain
// JSON data and nothing else.
func same(a, b any) bool {
	left, err := json.Marshal(a)
	if err != nil {
		return false
	}
	right, err := json.Marshal(b)
	if err != nil {
		return false
	}
	return string(left) == string(right)
}
