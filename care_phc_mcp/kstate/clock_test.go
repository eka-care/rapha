package kstate_test

// `now` in the query grammar, this engine's half.
//
// WHY A TEST AND NOT A SOCKET COMPARISON. scripts/check_go_parity.py is the
// right place to hold these two engines together and it cannot reach this
// yet: no shipped declaration uses `now`, so neither engine's HTTP answers
// differ whether this works or not. Same position as the projection and the
// codification seam, and fhir/parity_test.go is the precedent. The moment a
// bundle declares a date-relative rule, the parity check covers this for
// free and these literals stop being the only opinion.
//
// The Python half is kernel/tests/test_clock.py and asserts the same
// properties in the same order. Two copies of a literal is what the port's
// doctrine warns about, and it is accepted here only because this is a pure
// function over a map with no store behind it.

import (
	"testing"
	"time"

	"github.com/eka-care/care_phc_mcp/kstate"
)

var midday = time.Date(2026, 11, 4, 12, 0, 0, 0, time.UTC)

func TestInstantIsTheStoresOwnDateShape(t *testing.T) {
	// A string comparison is what makes `lt` work at all, so the format has
	// to be the adapter's own and has to sort as text.
	if got := kstate.Instant(midday); got != "2026-11-04T12:00:00Z" {
		t.Fatalf("instant = %q, want the adapter's date shape", got)
	}
	if kstate.Instant(time.Time{}) == "" {
		t.Fatal("a caller with no instant gets nothing instead of this machine's clock")
	}
}

func TestBindResolvesNow(t *testing.T) {
	out := kstate.Bind(map[string]any{
		"status": "open",
		"closes": map[string]any{"lt": "now"},
	}, midday)

	if out["status"] != "open" {
		t.Fatalf("a literal beside a symbol was changed: %v", out["status"])
	}
	closes, isMap := out["closes"].(map[string]any)
	if !isMap || closes["lt"] != "2026-11-04T12:00:00Z" {
		t.Fatalf("now inside a comparison did not resolve: %v", out["closes"])
	}

	// Legal wherever a literal is, not only inside a comparison.
	bare := kstate.Bind(map[string]any{"created_date": "now"}, midday)
	if bare["created_date"] != "2026-11-04T12:00:00Z" {
		t.Fatalf("a bare now did not resolve: %v", bare["created_date"])
	}
}

func TestBindLeavesEverythingElseAlone(t *testing.T) {
	in := map[string]any{"category": "vital-signs", "value": map[string]any{"gte": "140"}}
	out := kstate.Bind(in, midday)
	if out["category"] != "vital-signs" {
		t.Fatalf("category changed: %v", out["category"])
	}
	value, _ := out["value"].(map[string]any)
	if value["gte"] != "140" {
		t.Fatalf("a query with no now in it came back different: %v", out["value"])
	}
	if len(kstate.Bind(nil, midday)) != 0 {
		t.Fatal("an absent where should bind to an empty one")
	}
}

func TestBindDoesNotWriteIntoTheDeclaration(t *testing.T) {
	// The compiled catalogue is shared and read by every request. An
	// implementation that resolved in place would pass every assertion
	// above and would rewrite the declaration on first use.
	inner := map[string]any{"lt": "now"}
	kstate.Bind(map[string]any{"closes": inner}, midday)
	if inner["lt"] != "now" {
		t.Fatalf("binding rewrote the declaration: %v", inner["lt"])
	}
}
