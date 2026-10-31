package plugins

// The transport scripts/check_go_parity.py asks this engine's plugin lint
// through.
//
// WHY A TEST AND NOT A ROUTE
// --------------------------
// A lint is what stops a kernel STARTING, so the only thing it can be asked
// over a socket is whether this one bundle is sound, which it is. Every
// refusal worth proving needs a declaration bent on purpose, and a bundle bent
// on purpose never gets as far as a port. So the same shape G6 used for the
// record projection is used here: a test that ASSERTS NOTHING. It reads a file
// of bent declarations the Python check wrote, runs each through Lint, writes
// back what came out, and leaves every comparison to the check. No sentence is
// written down here, which is the rule scripts/check_go_parity.py is built on:
// a literal copied from whichever engine was read last would pass while both
// drifted.
//
// The one refusal that IS reachable over a socket is the misspelt
// PHC_FACILITY, because that one needs no bent bundle: the check launches both
// engines with a shape neither declares and both must refuse to start. That
// is asserted there, not here.
//
// Skipped, loudly, when the environment does not name a cases file, so
// `go test ./...` in scripts/check.sh is unaffected.

import (
	"encoding/json"
	"os"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
)

type lintCase struct {
	Name         string                       `json:"name"`
	Plugins      map[string]carephc.Plugin    `json:"plugins"`
	Facilities   carephc.Facilities           `json:"facilities"`
	Capabilities []string                     `json:"capabilities"`
	Operations   map[string]carephc.Operation `json:"operations"`
	Workflows    []*carephc.Workflow          `json:"workflows"`
	Asked        string                       `json:"asked"`
}

func TestTheLintAnswersForTheParityCheck(t *testing.T) {
	in := os.Getenv("PHC_PLUGIN_CASES")
	out := os.Getenv("PHC_PLUGIN_ANSWERS")
	if in == "" || out == "" {
		t.Skip("PHC_PLUGIN_CASES and PHC_PLUGIN_ANSWERS name the files " +
			"scripts/check_go_parity.py drives this package through")
	}
	raw, err := os.ReadFile(in)
	if err != nil {
		t.Fatal(err)
	}
	var cases []lintCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	answers := map[string][]string{}
	for _, one := range cases {
		bad := Lint(Shape{
			Plugins:      one.Plugins,
			Facilities:   one.Facilities,
			Capabilities: one.Capabilities,
			Operations:   one.Operations,
			Workflows:    one.Workflows,
			Asked:        one.Asked,
		})
		if bad == nil {
			bad = []string{}
		}
		answers[one.Name] = bad
	}
	blob, err := json.Marshal(answers)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, blob, 0o644); err != nil {
		t.Fatal(err)
	}
}
