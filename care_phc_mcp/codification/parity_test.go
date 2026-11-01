package codification_test

// The transport scripts/check_go_parity.py asks this engine's codification
// seam through.
//
// WHY A TEST AND NOT A ROUTE
// --------------------------
// kernel/codification.py is on no HTTP route in either engine. The stub is
// what the gate runs and what a health centre with no line has, and a
// candidate's only path to a record is through a screen, so there is nothing
// for the socket checks to compare. Same position as the projection and the
// outbox, and fhir/parity_test.go is the precedent.
//
// A test THAT ASSERTS NOTHING: it reads a file of inputs the Python check
// wrote, runs them through this package, writes what came back, and leaves
// every comparison to the check. No literal is written down here.
//
// WHAT IS COMPARED, AND WHAT CANNOT BE
// ------------------------------------
// Compared: every candidate's public shape, every refusal SENTENCE, and
// whether the whole asking failed. The sentences matter as much as the
// candidates, because a refusal a doctor cannot read is a refusal that gets
// routed around.
//
// Not compared: the error TEXT when a value set is uncached. Both engines fail
// there and the check asserts that both fail, which is the decision this slice
// made; the Python raises UnboundCoding from inside its cache loader and the
// Go builds the same sentence from its own, and the two spell the directory
// differently because one is an absolute path and the other is what it was
// given.

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/eka-care/care_phc_mcp/codification"
	"github.com/eka-care/care_phc_mcp/terminology"
)

type parityCases struct {
	Cases []struct {
		What string `json:"what"`
		// The value set cache this case is resolved against. Empty means the
		// tree's own, which is what almost every case uses; a path is a
		// crafted one the Python wrote, which is the only way the wrong-branch
		// rule can be reached at all.
		CacheDir string                `json:"cache_dir"`
		ValueSet string                `json:"valueset"`
		Results  []codification.Result `json:"results"`
		// pyval would turn a JSON number into a float64 either way; the score
		// is carried and compared against nothing, so what matters is only
		// that both engines hand back what they were given.
		Transcript string `json:"transcript"`
		Span       string `json:"span"`
		Text       string `json:"text"`
	} `json:"cases"`
	// The slugs AcceptedTags is asked about on its own, so the tag reading is
	// compared apart from the whole resolve.
	Tags []struct {
		CacheDir string `json:"cache_dir"`
		ValueSet string `json:"valueset"`
	} `json:"tags"`
}

// answer is what came back, or that it would not come back. `Failed` carries
// whether the asking failed rather than the sentence: see the file comment.
type answer struct {
	Failed     bool             `json:"failed"`
	Candidates []map[string]any `json:"candidates"`
	Refused    []string         `json:"refused"`
	Asked      string           `json:"asked"`
	Reachable  bool             `json:"reachable"`
}

type tagAnswer struct {
	Failed bool     `json:"failed"`
	Tags   []string `json:"tags"`
}

func TestTheCodificationSeamAnswersForTheParityCheck(t *testing.T) {
	in := os.Getenv("PHC_CODIFICATION_CASES")
	out := os.Getenv("PHC_CODIFICATION_ANSWERS")
	if in == "" || out == "" {
		t.Skip("PHC_CODIFICATION_CASES and PHC_CODIFICATION_ANSWERS name the " +
			"files scripts/check_go_parity.py drives this package through")
	}
	raw, err := os.ReadFile(in)
	if err != nil {
		t.Fatal(err)
	}
	var cases parityCases
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}

	caches := map[string]*terminology.Cache{}
	load := func(dir string) *terminology.Cache {
		if dir == "" {
			dir = filepath.Join("..", "..", "terminology")
		}
		if held, done := caches[dir]; done {
			return held
		}
		terms, err := terminology.Load(dir)
		if err != nil {
			t.Fatal(err)
		}
		caches[dir] = terms
		return terms
	}

	answers := map[string]any{}

	resolved := []answer{}
	for _, one := range cases.Cases {
		got, err := codification.Resolve(one.Results, one.ValueSet,
			load(one.CacheDir), one.Transcript, one.Span, one.Text)
		if err != nil {
			resolved = append(resolved, answer{Failed: true,
				Candidates: []map[string]any{}, Refused: []string{}})
			continue
		}
		public := []map[string]any{}
		for _, candidate := range got.Candidates {
			public = append(public, candidate.Public())
		}
		refused := got.Refused
		if refused == nil {
			refused = []string{}
		}
		resolved = append(resolved, answer{Candidates: public,
			Refused: refused, Asked: got.Asked, Reachable: got.Reachable})
	}
	answers["cases"] = resolved

	tagged := []tagAnswer{}
	for _, one := range cases.Tags {
		got, err := codification.AcceptedTags(load(one.CacheDir), one.ValueSet)
		if err != nil {
			tagged = append(tagged, tagAnswer{Failed: true, Tags: []string{}})
			continue
		}
		names := []string{}
		for tag := range got {
			names = append(names, tag)
		}
		// Sorted, because what is compared is the SET: the Python's own
		// accepted_tags returns a set and its one caller reads it as one.
		sortStrings(names)
		tagged = append(tagged, tagAnswer{Tags: names})
	}
	answers["tags"] = tagged

	blob, err := json.MarshalIndent(answers, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, append(blob, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
}

func sortStrings(names []string) {
	for i := 1; i < len(names); i++ {
		for j := i; j > 0 && names[j-1] > names[j]; j-- {
			names[j-1], names[j] = names[j], names[j-1]
		}
	}
}
