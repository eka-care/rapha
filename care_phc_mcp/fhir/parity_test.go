package fhir

// The transport scripts/check_go_parity.py asks this engine's projection
// through.
//
// WHY A TEST AND NOT A COMMAND OR A ROUTE
// ---------------------------------------
// kernel/fhir.py is on no HTTP route in either engine, and it never will be:
// a document is not something a clinic asks for over the wire, it is what the
// outbox sends to ABDM. api/main.py serves no route that returns one, so
// there is nothing for the socket checks to compare and no route may be
// invented so that a check can reach behind the service. The same three ways
// out fill/parity_test.go names were available and the same two were worse.
//
// So this is a test THAT ASSERTS NOTHING. It reads a file of inputs the
// Python check wrote, runs them through this package, writes what came back,
// and leaves every comparison to the check. No literal is written down here,
// which is the rule scripts/check_go_parity.py is built on: a literal would
// pass while both engines drifted from each other.
//
// Skipped, loudly, when the environment does not name a cases file, so
// `go test ./...` in scripts/check.sh is unaffected.
//
// WHAT IT CANNOT PROVE
// --------------------
// That the projection is REACHED. Nothing in the Go service calls this
// package, because the one production caller is the outbox (G8) and the
// placement declaration it would need is not in catalogue.json at all. This
// proves the documents match; it does not prove anybody asks for one.

import (
	"encoding/json"
	"os"
	"sort"
	"testing"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/store"
)

type parityCases struct {
	Rows      map[string]map[string][]map[string]string `json:"rows"`
	Documents []struct {
		Case             string `json:"case"`
		Thread           string `json:"thread"`
		Profile          string `json:"profile"`
		IdentifierSystem string `json:"identifier_system"`
		Now              string `json:"now"`
		Sections         []struct {
			Slice   string `json:"slice"`
			Queries []struct {
				Resource string            `json:"resource"`
				Where    map[string]string `json:"where"`
			} `json:"queries"`
		} `json:"sections"`
	} `json:"documents"`
	Projections []struct {
		Resource     string            `json:"resource"`
		Row          map[string]string `json:"row"`
		Subject      string            `json:"subject"`
		Encounter    string            `json:"encounter"`
		Performer    string            `json:"performer"`
		DocumentType *DocumentType     `json:"document_type"`
	} `json:"projections"`
	Patients   []map[string]string `json:"patients"`
	Encounters []struct {
		Row     map[string]string `json:"row"`
		Subject string            `json:"subject"`
	} `json:"encounters"`
	Practitioners []string `json:"practitioners"`
	Numbers       []any    `json:"numbers"`
	URNs          []string `json:"urns"`
}

// answer is what came back, or why it would not come back. `Refused` carries
// the sentence rather than a flag, because the sentence is one of the things
// the check compares: a refusal whose wording drifted is a refusal a reader
// cannot act on.
type answer struct {
	OK       bool           `json:"ok"`
	Resource map[string]any `json:"resource"`
	Refused  string         `json:"refused"`
}

// stub is the Rows seam over the case file's own rows, in the order the file
// lists them.
//
// WHAT IT DOES AND DOES NOT DECIDE. Row ORDER is the store's (`ORDER BY
// created_date, id`) and is not re-implemented here: the case file lists rows
// already in that order, so order is an input to this comparison rather than
// a thing it compares. What it does implement is the `where` grammar's
// equality and present forms, which is the whole of what a section query uses,
// and the Python half of the check implements the same two. That pair is the
// one place this harness could agree with itself while both engines were
// wrong; a Document that dropped its `where` instead of passing it through
// would still show up, because only one engine would drop it.
type stub struct {
	tables map[string][]map[string]string
	thread string
}

func (s stub) Select(resource string, thread *string, where store.Query,
	fields []string, limit int) ([]map[string]string, error) {
	// THE THREAD HAS TO BE PASSED, AND IT HAS TO BE THIS ONE. Not a join:
	// this stub implements none, and the join is the adapter's. It is the
	// narrower fact that a document is about ONE VISIT, and a Document that
	// read the store without saying which visit would publish one patient's
	// rows inside another patient's record. Found by mutation: this check
	// ignored the argument, and a Go Document that passed nothing passed the
	// whole gate.
	if thread == nil || *thread != s.thread {
		return nil, nil
	}
	var out []map[string]string
	for _, row := range s.tables[resource] {
		keep := true
		for field, cond := range where {
			switch {
			case cond.Present:
				keep = keep && row[field] != ""
			default:
				keep = keep && row[field] == cond.Equals
			}
		}
		if !keep {
			continue
		}
		out = append(out, row)
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

func TestTheProjectionAnswersForTheParityCheck(t *testing.T) {
	in := os.Getenv("PHC_FHIR_CASES")
	out := os.Getenv("PHC_FHIR_ANSWERS")
	if in == "" || out == "" {
		t.Skip("PHC_FHIR_CASES and PHC_FHIR_ANSWERS name the files " +
			"scripts/check_go_parity.py drives this package through")
	}
	raw, err := os.ReadFile(in)
	if err != nil {
		t.Fatal(err)
	}
	var cases parityCases
	if err := pyval.Decode(raw, &cases); err != nil {
		t.Fatal(err)
	}

	answers := map[string]any{}

	documents := []answer{}
	for _, one := range cases.Documents {
		wanted := make([]Want, 0, len(one.Sections))
		for _, section := range one.Sections {
			want := Want{Slice: section.Slice}
			for _, query := range section.Queries {
				where := store.Query{}
				for field, value := range query.Where {
					if value == "*" {
						where[field] = store.Cond{Present: true}
						continue
					}
					where[field] = store.Cond{Equals: value}
				}
				want.Queries = append(want.Queries, Query{Resource: query.Resource, Where: where})
			}
			wanted = append(wanted, want)
		}
		made, err := Document(stub{cases.Rows[one.Case], one.Thread}, one.Thread, one.Profile,
			wanted, one.Now, one.IdentifierSystem)
		documents = append(documents, held(made, err))
	}
	answers["documents"] = documents

	projections := []answer{}
	for _, one := range cases.Projections {
		project, has := Projections[one.Resource]
		if !has {
			projections = append(projections, answer{Refused: "no projection"})
			continue
		}
		made, err := project(one.Row, one.Subject, one.Encounter, one.Performer,
			one.DocumentType)
		projections = append(projections, held(made, err))
	}
	answers["projections"] = projections

	patients := []map[string]any{}
	for _, row := range cases.Patients {
		patients = append(patients, Patient(row))
	}
	answers["patients"] = patients

	encounters := []map[string]any{}
	for _, one := range cases.Encounters {
		encounters = append(encounters, Encounter(one.Row, one.Subject))
	}
	answers["encounters"] = encounters

	practitioners := []map[string]any{}
	for _, actor := range cases.Practitioners {
		practitioners = append(practitioners, Practitioner(actor))
	}
	answers["practitioners"] = practitioners

	numbers := []any{}
	for _, value := range cases.Numbers {
		numbers = append(numbers, Number(value))
	}
	answers["numbers"] = numbers

	urns := []string{}
	for _, seed := range cases.URNs {
		urns = append(urns, URN(seed))
	}
	answers["urns"] = urns

	answers["tables"] = tables()

	blob, err := json.Marshal(answers)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, blob, 0o644); err != nil {
		t.Fatal(err)
	}
}

// held is one projection's answer: what it made, or the sentence it refused
// with. A nil resource and no error is a projection that declined this
// particular row, which is the narrative fallback's empty note and is a third
// outcome rather than a failure.
func held(made map[string]any, err error) answer {
	if err != nil {
		return answer{Refused: err.Error()}
	}
	return answer{OK: true, Resource: made}
}

// tables is every declaration this package holds, flattened so that the
// Python's own tables can be diffed against it. Nothing is asserted: which
// profile declares which section, which column is a verbatim FHIR code and
// which is translated, are facts the Python owns and this engine copies, and a
// copy that drifted is exactly what the check is for.
func tables() map[string]any {
	profiles := map[string]any{}
	for name, spec := range Profiles {
		sections := map[string]any{}
		for slice, section := range spec.Sections {
			sections[slice] = map[string]any{"title": section.Title,
				"code": section.Code, "display": section.Display}
		}
		profiles[name] = map[string]any{
			"profile": spec.Profile, "title": spec.Title,
			"type":     map[string]any{"code": spec.Type.Code, "text": spec.Type.Text},
			"required": spec.Required, "sections": sections,
		}
	}
	return map[string]any{
		"profiles":          profiles,
		"document_bundle":   DocumentBundle,
		"resource_type":     ResourceType,
		"status_binding":    pairs(StatusBinding),
		"translated_status": pairKeys(TranslatedStatus),
		"coded_status":      pairs(CodedStatus),
		"projections":       keys(Projections),
		"typed_by_profile":  keys(TypedByProfile),
		"narrative":         map[string]any{"type": NarrativeType, "language": NarrativeLanguage},
		"systems": map[string]any{"nrces": NRCES, "loinc": LOINC, "ucum": UCUM,
			"snomed": SNOMED, "hl7_category": HL7Category},
	}
}

// pairs renders a table keyed by (table, column) as the check can read it:
// "table.column" to the value. The Python's key is a tuple, which JSON has no
// spelling for, so both sides join it.
func pairs[V any](table map[[2]string]V) map[string]any {
	out := map[string]any{}
	for key, value := range table {
		out[key[0]+"."+key[1]] = value
	}
	return out
}

// pairKeys is the same join over a table that is only its keys.
func pairKeys[V any](table map[[2]string]V) []string {
	out := make([]string, 0, len(table))
	for key := range table {
		out = append(out, key[0]+"."+key[1])
	}
	sort.Strings(out)
	return out
}

func keys[V any](table map[string]V) []string {
	out := make([]string, 0, len(table))
	for key := range table {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}
