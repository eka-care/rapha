package fill

// The transport scripts/check_go_parity.py asks this engine's fill through.
//
// WHY A TEST AND NOT A COMMAND OR A ROUTE
// ---------------------------------------
// api/fill.py is on no HTTP route until G8 serves the scribe, so the two
// engines' fill cannot be diffed over a socket the way everything else in
// this port is. Three ways out were available and two were worse:
//
//   - a third command under cmd/. The port plan takes a decision up front --
//     "One Go module, two commands" -- and a command that exists only to feed
//     a check is scaffolding the product does not use.
//   - a new route. Inventing one so a check can reach behind the service is
//     the opposite of what these checks are for.
//   - this: a test that ASSERTS NOTHING. It reads a file of inputs the Python
//     check wrote, runs them through this package, writes what came back, and
//     leaves every comparison to the check. No literal is written down here,
//     which is the rule scripts/check_go_parity.py is built on: a literal
//     would pass while both engines drifted from each other.
//
// Skipped, loudly, when the environment does not name a cases file, so
// `go test ./...` in scripts/check.sh is unaffected.
//
// WHAT IT CANNOT PROVE
// --------------------
// That fill is REACHED. Nothing in the Go service calls this package yet,
// because the one caller is the scribe and the scribe is G8. This proves the
// answers match; it does not prove anybody asks.

import (
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/terminology"
)

type parityCases struct {
	Questionnaires string   `json:"questionnaires"`
	Terminology    string   `json:"terminology"`
	Today          string   `json:"today"`
	Flatten        []string `json:"flatten"`
	Coerce         []struct {
		Slug   string `json:"slug"`
		LinkID string `json:"link_id"`
		Value  any    `json:"value"`
	} `json:"coerce"`
	Drafts []struct {
		Slug       string   `json:"slug"`
		Operation  string   `json:"operation"`
		Instrument string   `json:"instrument"`
		Transcript string   `json:"transcript"`
		Answers    []Answer `json:"answers"`
	} `json:"drafts"`
}

type coerced struct {
	OK    bool `json:"ok"`
	Value any  `json:"value"`
}

func TestFillAnswersForTheParityCheck(t *testing.T) {
	in := os.Getenv("PHC_FILL_CASES")
	out := os.Getenv("PHC_FILL_ANSWERS")
	if in == "" || out == "" {
		t.Skip("PHC_FILL_CASES and PHC_FILL_ANSWERS name the files " +
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
	schemas, err := questionnaire.Load(cases.Questionnaires)
	if err != nil {
		t.Fatal(err)
	}
	terms, err := terminology.Load(cases.Terminology)
	if err != nil {
		t.Fatal(err)
	}
	today, err := time.Parse("2006-01-02", cases.Today)
	if err != nil {
		t.Fatal(err)
	}

	answers := map[string]any{}

	flattened := map[string][]Field{}
	for _, slug := range cases.Flatten {
		schema, err := schemas.Get(slug)
		if err != nil {
			t.Fatal(err)
		}
		flattened[slug] = Flatten(schema, terms)
	}
	answers["flatten"] = flattened

	coercions := []coerced{}
	for _, one := range cases.Coerce {
		schema, err := schemas.Get(one.Slug)
		if err != nil {
			t.Fatal(err)
		}
		var found *Field
		for _, f := range Flatten(schema, terms) {
			if f.LinkID == one.LinkID {
				copied := f
				found = &copied
				break
			}
		}
		if found == nil {
			t.Fatalf("%s has no answerable question %s", one.Slug, one.LinkID)
		}
		value, ok := Coerce(*found, one.Value, today)
		coercions = append(coercions, coerced{OK: ok, Value: value})
	}
	answers["coerce"] = coercions

	drafts := []*Draft{}
	for _, one := range cases.Drafts {
		schema, err := schemas.Get(one.Slug)
		if err != nil {
			t.Fatal(err)
		}
		drafts = append(drafts, BuildDraft(one.Operation, schema, one.Answers,
			one.Transcript, one.Instrument, today, terms))
	}
	answers["drafts"] = drafts

	blob, err := json.Marshal(answers)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, blob, 0o644); err != nil {
		t.Fatal(err)
	}
}
