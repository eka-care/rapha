package planner

import (
	"strings"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
)

// WHY THIS FILE EXISTS, AND WHAT THE SOCKET CHECKS CANNOT REACH
//
// scripts/check_go_parity.py drives this planner over a real socket against
// the Python's, which is the acceptance test for everything the route
// answers. Two of this package's rules cannot be reached that way, and the
// mutation ledger is how that was found rather than how it was argued:
//
//   - Typed() drops override_reason, and Extract() has ALREADY dropped the
//     field before any payload exists. So no utterance can make the router
//     answer override_reason, and a socket check asserting the card does not
//     carry one is true of every possible utterance for a reason that is not
//     Typed(). A mutation making Typed() accept the field survived the whole
//     gate. agent/turn.py's own demo() has the matching direct assertion, for
//     the same reason and in the same shape, and this package had no
//     equivalent until that mutation said so.
//
//     It is not dead code. Typed() is the trust boundary for a planner that
//     DOES answer freely, which is agent/planner.py's llm backend: it filters
//     the model's payload after the model answers. The Go has no llm backend
//     yet, so the guard here has nothing to guard today and everything to
//     guard the moment one lands.
//
//   - NextStep() dispatches on the guard's machine-stable kind BEFORE it
//     looks at the reason string, which is what keeps a copy pass over the
//     guard's clerk-facing sentences from silently changing the advice.
//     Comparing two engines proves they agree on the sentence; it does not
//     prove the dispatch happened on the kind.

func field(linkID string) carephc.Field {
	return carephc.Field{LinkID: linkID, Type: "integer", Text: linkID, Required: true}
}

// TestTypedRefusesTheOverride is the rule the whole machine surface rests on.
// override_reason waives the physiological range check, so a planner that
// could answer it could waive it, and no planner may. A person can still
// override at the rendered surface, by writing the reason themselves.
func TestTypedRefusesTheOverride(t *testing.T) {
	op := carephc.Operation{ID: "x.op.vitals", Fields: []carephc.Field{
		field("systolic"), field("override_reason")}}

	got := Typed(op, map[string]any{
		"systolic":        120,
		"override_reason": "because I said so",
	})
	if _, waived := got["override_reason"]; waived {
		t.Fatalf("a planner answered override_reason and it reached the guard: %v", got)
	}
	if got["systolic"] != 120 || len(got) != 1 {
		t.Fatalf("Typed kept %v, want only the declared systolic", got)
	}
}

// TestTypedDropsWhatTheFormDoesNotAsk is the other half: the validator ignores
// a key it does not know, so an invented key would ride along into a proposal
// a person then taps. A planner answers the questionnaire's questions and
// nothing else.
func TestTypedDropsWhatTheFormDoesNotAsk(t *testing.T) {
	op := carephc.Operation{ID: "x.op.vitals", Fields: []carephc.Field{field("systolic")}}

	got := Typed(op, map[string]any{"systolic": 120, "invented": 9, "confirmed": true})
	if len(got) != 1 || got["systolic"] != 120 {
		t.Fatalf("Typed kept %v, want only the declared systolic", got)
	}
	// `confirmed` in particular: there is no confirmed argument anywhere on
	// the propose path, and a payload key spelled like one must not be the
	// thing that invents it.
	if _, found := got["confirmed"]; found {
		t.Fatal("a payload key named confirmed survived the filter")
	}
}

// TestNextStepDispatchesOnTheKindNotTheSentence is agent/turn.py's own
// assertion, carried over. Rewording a clerk-facing sentence must not change
// the advice, and two different kinds must not collapse to the same advice
// just because a sentence was reused.
func TestNextStepDispatchesOnTheKindNotTheSentence(t *testing.T) {
	if NextStep("Patient is already registered.", "flag_negated") !=
		NextStep("Already registered.", "flag_negated") {
		t.Fatal("the sentence changed; the advice for the same kind must not")
	}
	if NextStep("Already registered.", "flag_negated") ==
		NextStep("Already registered.", "actor_negated") {
		t.Fatal("two kinds collapsed to the same advice because a sentence was reused")
	}
	// A separation of duties refusal must not share the plain-flag advice: it
	// is about who is asking, not about the state of the visit.
	duties := NextStep("Already performed lab op result enter.", "actor_negated")
	if !strings.Contains(duties, "Somebody else has to do this one") {
		t.Fatalf("a separation of duties refusal said %q", duties)
	}
	if strings.Contains(duties, "does not satisfy that") {
		t.Fatalf("a separation of duties refusal borrowed the plain-flag advice: %q", duties)
	}
	// And a denial that is not a precondition at all still gets advice, keyed
	// on the shape of the guard's own reason.
	if NextStep("payload invalid: pulse is required", "") == nextOtherwise {
		t.Fatal("a payload denial fell through to the catch-all advice")
	}
	// A kind the table does not know must not silently become a precondition
	// sentence: it falls through to the reason, and then to the catch-all.
	if NextStep("something new the guard learned to say", "") != nextOtherwise {
		t.Fatal("an unknown denial did not reach the catch-all advice")
	}
}
