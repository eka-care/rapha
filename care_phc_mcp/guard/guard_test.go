// The guard's own properties, against the compiled catalogue.
//
// WHY THESE ARE GO TESTS AND NOT PARITY COMPARISONS
// -------------------------------------------------
// scripts/check_go_parity.py is the measure for this slice, and it is a
// differential check on purpose: a literal written into it would pass while
// both engines drifted together. The four properties below cannot be reached
// that way, and each one says which reason applies rather than being quietly
// moved here:
//
//  1. A missing validator fails closed. No socket can produce one: every
//     declared operation names a questionnaire that exists, so the only way
//     to a nil validator is to break a file, and a check that breaks a file
//     in the tree is not a check the gate can run.
//  2. An `actor of` precondition, and the agent prefix that must not launder
//     around it. bundles/phc declares no such precondition — bundles/lab
//     does — and the Go engine serves one bundle (cmd/api's own note), so the
//     socket cannot reach it from either side.
//  3. The precondition kind. It is on the Decision and NOT on the wire: the
//     only route that would carry it is POST /khoj, whose planner is
//     agent/turn.py and is not ported. So the parity check cannot compare it
//     and this is what holds it instead.
//  4. The guard's step ORDER, where two steps would both refuse. The wire
//     carries whichever sentence came first and the parity check compares it,
//     which proves the two engines agree; it does not prove the order is the
//     Python's. These do.
//
// Everything here is a property over the compiled declarations rather than a
// shape written down: the operations come from catalogue.json, so a bundle
// that grows is covered without this file being edited.
package guard

import (
	"strings"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
)

func load(t *testing.T) *carephc.Catalogue {
	t.Helper()
	cat, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := cat.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	return cat
}

func opOf(t *testing.T, cat *carephc.Catalogue, id string) Op {
	t.Helper()
	op, declared := cat.Operations[id]
	if !declared {
		t.Fatalf("the compiled catalogue has no %s", id)
	}
	qualifier := ""
	if op.ScopeQualifier != nil {
		qualifier = *op.ScopeQualifier
	}
	return Op{ID: op.ID, Kind: op.Kind, Capability: op.Capability,
		ScopeQualifier: qualifier, Preconditions: op.Preconditions,
		Irreversibility: op.Irreversibility}
}

func passes(Op, map[string]any) []string { return nil }

func set(names ...string) map[string]bool {
	out := map[string]bool{}
	for _, name := range names {
		out[name] = true
	}
	return out
}

// Every write operation in the catalogue, with everything the guard could
// want satisfied, so a test that means to exercise one step is not quietly
// stopped by an earlier one.
func wide(op Op) Input {
	state := map[string]bool{}
	for _, pre := range op.Preconditions {
		kind, name, negated := ParsePrecondition(pre)
		if kind == "flag" && !negated {
			state[name] = true
		}
	}
	return Input{
		Caps: set(op.Capability), State: state, Payload: map[string]any{},
		Surface: Rendered, Confirmed: true, Scopes: set(op.ScopeQualifier),
		Validate: passes, Actor: "user:someone", ActorGiven: true,
		Performers: map[string]map[string]bool{}, PerformersGiven: true,
	}
}

// A MISSING VALIDATOR FAILS CLOSED, for every write the catalogue declares,
// and it fails before the capability check so a caller holding everything is
// still refused.
func TestAMissingValidatorFailsClosedForEveryWrite(t *testing.T) {
	cat := load(t)
	writes := 0
	for id, declared := range cat.Operations {
		if declared.Kind != "write" {
			continue
		}
		writes++
		op := opOf(t, cat, id)
		in := wide(op)
		in.Validate = nil
		if d := Evaluate(op, in); d.Allowed {
			t.Fatalf("%s: a nil validator was allowed", id)
		} else if !strings.Contains(d.Reason, "no validator") {
			t.Fatalf("%s: a nil validator was refused for another reason: %s", id, d.Reason)
		}
		// And the same with nothing else satisfied, which is what proves the
		// validator is step ONE: the refusal is still the validator's and not
		// the capability's.
		bare := Input{Surface: Rendered, Payload: map[string]any{}}
		d := Evaluate(op, bare)
		if d.Allowed || !strings.Contains(d.Reason, "no validator") {
			t.Fatalf("%s: with nothing held, the refusal was %q rather than the "+
				"validator's, so the validator is not step one", id, d.Reason)
		}
		// A refusal is audited whatever its reason.
		if outcome, _ := d.Audit["outcome"].(string); !strings.HasPrefix(outcome, "denied: ") {
			t.Fatalf("%s: a refusal was not audited: %v", id, d.Audit)
		}
	}
	if writes == 0 {
		t.Fatal("the catalogue declares no write operation, so this proves nothing")
	}
}

// A VALIDATOR THAT FINDS PROBLEMS DENIES, and the problems reach the sentence.
func TestAnInvalidPayloadIsRefusedBeforeTheCapability(t *testing.T) {
	cat := load(t)
	op := opOf(t, cat, pickWrite(t, cat))
	in := wide(op)
	in.Caps = map[string]bool{}
	in.Validate = func(Op, map[string]any) []string {
		return []string{"first thing", "second thing"}
	}
	d := Evaluate(op, in)
	if d.Allowed {
		t.Fatal("an invalid payload was allowed")
	}
	for _, problem := range []string{"first thing", "second thing"} {
		if !strings.Contains(d.Reason, problem) {
			t.Fatalf("the denial dropped %q: %s", problem, d.Reason)
		}
	}
	if strings.Contains(d.Reason, "capability") {
		t.Fatalf("the capability was checked before the payload: %s", d.Reason)
	}
}

func pickWrite(t *testing.T, cat *carephc.Catalogue) string {
	t.Helper()
	for id, op := range cat.Operations {
		if op.Kind == "write" && len(op.Preconditions) > 0 {
			return id
		}
	}
	t.Fatal("no write operation with a precondition in the catalogue")
	return ""
}

// AN AGENT INHERITS THE EXCLUSIONS OF THE PERSON IT ACTS FOR.
//
// The hole this closes: api/main.py proposes as `agent:<caller id>`, so
// without stripping the prefix the account that keyed a result could get the
// verify proposed for itself by dictating the sentence instead of tapping the
// button. The precondition is declared in bundles/lab and the Go engine
// serves one bundle, so the rule is exercised against a precondition built
// here rather than read from the loaded catalogue — and the predicate under
// test is the real one.
func TestAnAgentInheritsTheExclusionsOfThePersonItActsFor(t *testing.T) {
	op := Op{ID: "x.op.verify", Kind: "write", Capability: "verify",
		Preconditions: []string{"not actor of x.op.enter"},
		Irreversibility: "correctable"}
	entered := map[string]map[string]bool{"x.op.enter": {"user:tech": true}}

	for _, actor := range []string{"user:tech", "agent:user:tech",
		"agent:agent:user:tech"} {
		in := Input{Caps: set("verify"), State: map[string]bool{},
			Payload: map[string]any{}, Surface: Rendered, Validate: passes,
			Actor: actor, ActorGiven: true, Performers: entered,
			PerformersGiven: true}
		if d := Evaluate(op, in); d.Allowed {
			t.Fatalf("%s: the person who entered the result was allowed to "+
				"verify it", actor)
		}
		if Visible(op, set("verify"), map[string]bool{}, true, actor, true, entered) {
			t.Fatalf("%s: the action was drawn for the person it excludes", actor)
		}
	}
	// Somebody else may.
	other := Input{Caps: set("verify"), State: map[string]bool{},
		Payload: map[string]any{}, Surface: Rendered, Validate: passes,
		Actor: "agent:user:incharge", ActorGiven: true, Performers: entered,
		PerformersGiven: true}
	if d := Evaluate(op, other); !d.Allowed {
		t.Fatalf("a different person was refused the verify: %s", d.Reason)
	}
}

// AN UNANSWERED SEPARATION OF DUTIES RULE IS A DENIAL, NEVER A PASS, and the
// denial leaks neither the prefix nor the operation it is about.
func TestAnUnevaluableActorRuleDeniesAndSaysSo(t *testing.T) {
	op := Op{ID: "x.op.verify", Kind: "write", Capability: "verify",
		Preconditions: []string{"not actor of x.op.enter"},
		Irreversibility: "correctable"}
	in := Input{Caps: set("verify"), State: map[string]bool{},
		Payload: map[string]any{}, Surface: Rendered, Validate: passes}
	d := Evaluate(op, in)
	if d.Allowed {
		t.Fatal("a rule the guard could not evaluate read as satisfied")
	}
	if d.Kind != "unevaluable" {
		t.Fatalf("the kind was %q", d.Kind)
	}
	for _, leak := range []string{ActorOf, "x.op.enter", "not "} {
		if strings.Contains(d.Reason, leak) {
			t.Fatalf("the denial leaked %q: %s", leak, d.Reason)
		}
	}
	// A surface deciding what to DRAW makes the opposite choice, and the tap
	// is then refused with the sentence above. That asymmetry is the design.
	if !Visible(op, set("verify"), map[string]bool{}, false, "", false, nil) {
		t.Fatal("the action was hidden when nobody said who was looking")
	}
}

// THE PRECONDITION KIND IS STABLE REGARDLESS OF THE SENTENCE, and is carried
// on the Decision for a precondition denial only.
func TestThePreconditionKindIsStableRegardlessOfTheSentence(t *testing.T) {
	for _, c := range []struct{ pre, kind string }{
		{"not registered", "flag_negated"},
		{"rx.confirmed", "flag_required"},
		{"not actor of lab.op.result-enter", "actor_negated"},
		{"actor of lab.op.result-enter", "actor_required"},
	} {
		if got := PreconditionKind(c.pre, false); got != c.kind {
			t.Fatalf("%s: kind %q, want %q", c.pre, got, c.kind)
		}
	}
	if got := PreconditionKind("lab.op.result-enter", true); got != "unevaluable" {
		t.Fatalf("unevaluable: %q", got)
	}
	// Renaming the flag changes the sentence and not the kind, which is the
	// whole point of having both.
	a, b := "not vitals.recorded", "not something.else.entirely"
	if DescribePrecondition(a, false) == DescribePrecondition(b, false) {
		t.Fatal("two different flags wrote the same sentence")
	}
	if PreconditionKind(a, false) != PreconditionKind(b, false) {
		t.Fatal("renaming a flag changed the kind")
	}

	// And Evaluate carries it for a precondition denial ONLY.
	cat := load(t)
	op := opOf(t, cat, "phc.op.patient-register")
	in := wide(op)
	in.State = set("registered")
	d := Evaluate(op, in)
	if d.Allowed || d.Kind != "flag_negated" {
		t.Fatalf("a precondition denial carried kind %q", d.Kind)
	}
	in = wide(op)
	in.Caps = map[string]bool{}
	if d := Evaluate(op, in); d.Allowed || d.Kind != "" {
		t.Fatalf("missing capability carried a precondition kind: %q", d.Kind)
	}
	if d := Evaluate(op, wide(op)); !d.Allowed || d.Kind != "" {
		t.Fatalf("an allow carried a precondition kind: %q", d.Kind)
	}
}

// EVERY WRITE OPERATION IS A PROPOSAL ON MCP, and an irreversible one is not
// even that.
func TestAMachineSurfaceNeverCommits(t *testing.T) {
	cat := load(t)
	writes, irreversible := 0, 0
	for id, declared := range cat.Operations {
		if declared.Kind != "write" {
			continue
		}
		writes++
		if !strings.HasPrefix(declared.Tool, "propose_") {
			t.Fatalf("%s exposes %q, which is not a propose verb", id, declared.Tool)
		}
		op := opOf(t, cat, id)
		in := wide(op)
		in.Surface = MCP
		d := Evaluate(op, in)
		if declared.Irreversibility == "irreversible" {
			irreversible++
			// Confirmed is true in `wide`, and it changes nothing: step 4
			// denies on the SURFACE before it looks at the flag at all.
			if d.Allowed {
				t.Fatalf("%s: an irreversible write was allowed from the "+
					"machine surface with confirmed asserted", id)
			}
			continue
		}
		if !d.Allowed {
			t.Fatalf("%s: a write was refused on the machine surface: %s", id, d.Reason)
		}
		if d.Reason != "proposed" {
			t.Fatalf("%s: the machine surface got %q rather than a proposal", id, d.Reason)
		}
		if outcome, _ := d.Audit["outcome"].(string); outcome != "proposed" {
			t.Fatalf("%s: the audit says %q", id, outcome)
		}
	}
	if writes == 0 || irreversible == 0 {
		t.Fatalf("%d writes and %d irreversible: this proves less than it says",
			writes, irreversible)
	}
}

// AN IRREVERSIBLE OPERATION NEEDS AN EXPLICIT CONFIRM FROM A PERSON.
func TestAnIrreversibleWriteNeedsAPersonAndAnExplicitConfirm(t *testing.T) {
	cat := load(t)
	found := 0
	for id, declared := range cat.Operations {
		if declared.Irreversibility != "irreversible" {
			continue
		}
		found++
		op := opOf(t, cat, id)
		in := wide(op)
		in.Confirmed = false
		d := Evaluate(op, in)
		if d.Allowed {
			t.Fatalf("%s: an irreversible write went through with no confirm", id)
		}
		if d := Evaluate(op, wide(op)); !d.Allowed {
			t.Fatalf("%s: an explicit confirm on the rendered surface was "+
				"refused: %s", id, d.Reason)
		}
	}
	if found == 0 {
		t.Fatal("the catalogue declares no irreversible operation")
	}
}

// THE KERNEL NAMES THE SURFACE, NOT THE CALLER: the audit line carries the
// surface the kernel passed, and there are two.
func TestTheAuditLineCarriesTheSurfaceTheKernelPassed(t *testing.T) {
	cat := load(t)
	op := opOf(t, cat, "phc.op.vitals-record")
	for _, surface := range []string{Rendered, MCP} {
		in := wide(op)
		in.Surface = surface
		d := Evaluate(op, in)
		if got, _ := d.Audit["surface"].(string); got != surface {
			t.Fatalf("the audit says %q for %q", got, surface)
		}
		if got, _ := d.Audit["actor"].(string); got != in.Actor {
			t.Fatalf("the audit says actor %q", got)
		}
	}
	// With no actor the line says null rather than the empty string, which is
	// what kernel/contracts.AuditRecord declares (Optional[str]).
	in := wide(op)
	in.ActorGiven, in.Actor = false, ""
	if d := Evaluate(op, in); d.Audit["actor"] != nil {
		t.Fatalf("an absent actor was audited as %#v", d.Audit["actor"])
	}
}

// A WITHHELD CAPABILITY NAMES BOTH THE CAPABILITY AND THE PLUGIN, and changes
// no decision: it is already out of Caps, so step 2 denies either way.
func TestAWithheldCapabilityNamesTheCapabilityAndThePlugin(t *testing.T) {
	cat := load(t)
	op := opOf(t, cat, "phc.op.lab-order")
	in := wide(op)
	in.Caps = map[string]bool{}
	plain := Evaluate(op, in)
	in.Withheld = map[string]string{op.Capability: "orders"}
	named := Evaluate(op, in)
	if plain.Allowed || named.Allowed {
		t.Fatal("a capability nobody holds was allowed")
	}
	if plain.Reason == named.Reason {
		t.Fatal("the plugin did not reach the sentence")
	}
	for _, wanted := range []string{op.Capability, "orders"} {
		if !strings.Contains(named.Reason, wanted) {
			t.Fatalf("the denial dropped %q: %s", wanted, named.Reason)
		}
	}
}
