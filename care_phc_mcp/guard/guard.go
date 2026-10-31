// Package guard is catalogue/guard.py in Go. Every operation, from every
// surface, passes through Evaluate.
//
// A TRANSCRIPTION, NOT A REINTERPRETATION
// ---------------------------------------
// This is the most safety-critical code in the product and the reason the
// architecture exists, so the Python is the specification down to the wording
// of each denial. Where the Python phrases a refusal a particular way, the
// same sentence is produced here, because a denial is read by a clerk and by
// agent/turn.py and both of them are part of the contract.
//
// Steps 5 to 7 of the write path (audit persist, CARE write, state emit)
// belong to the caller, exactly as they do in Python. Evaluate decides, and
// hands back the audit record to write.
//
// WHAT IS DELIBERATELY ABSENT
// ---------------------------
// There is no default validator. A nil Validate is a denial, never a pass:
// that is the "missing validator fails closed" property, and it is the one
// place where writing the obvious convenience would be the bug.
package guard

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// Surfaces an operation can be invoked from. There is no third.
const (
	Rendered = "rendered"
	MCP      = "mcp"
)

// ActorOf is the precondition prefix for a fact about who acted on this
// thread before, rather than about a flag.
//
//	registered                           the flag is true
//	not dispensed.complete               the flag is false
//	actor of phc.op.lab-order            this caller performed that operation here
//	not actor of lab.op.result-enter     this caller did NOT perform it
//
// The second pair is separation of duties: a laboratory refuses the person
// who keyed a result the right to verify it, whatever capabilities they hold.
const ActorOf = "actor of "

// AgentPrefix is how api/main.py names an agent acting FOR somebody, so a
// card can say a machine asked rather than a colleague. For a separation of
// duties rule the prefix has to come off: the person who keyed a result must
// not be able to verify it by dictating the sentence instead of tapping the
// button. Stripped in the one predicate both enforcement and visibility read,
// because a rule an agent can launder around is not a rule.
const AgentPrefix = "agent:"

// Person is the human behind an actor string. `agent:user:x` and `user:x` are
// the same person for every rule about who did what.
func Person(actor string) string {
	for strings.HasPrefix(actor, AgentPrefix) {
		actor = actor[len(AgentPrefix):]
	}
	return actor
}

// ParsePrecondition returns (kind, name, negated). kind is "flag" or "actor".
// One definition, so lint and enforcement cannot drift.
func ParsePrecondition(pre string) (kind, name string, negated bool) {
	negated = strings.HasPrefix(pre, "not ")
	term := pre
	if negated {
		term = pre[4:]
	}
	if strings.HasPrefix(term, ActorOf) {
		return "actor", strings.TrimSpace(term[len(ActorOf):]), negated
	}
	return "flag", term, negated
}

var punctuation = regexp.MustCompile(`[._-]+`)

// words renders a flag or operation id as words. `rx.confirmed` becomes "rx
// confirmed" and `lab.op.result-enter` becomes "lab op result enter". No
// lookup table: this is the catalogue's own punctuation, split apart, so any
// bundle's flags read the same way PHC's do.
func words(name string) string {
	return strings.TrimSpace(punctuation.ReplaceAllString(name, " "))
}

// DescribePrecondition is a sentence a clerk reads correctly, never the
// literal precondition string. `not registered` unmet means the flag IS
// present, which is "Already registered.", not something that sounds like its
// opposite. `unevaluable` is the separation-of-duties case where nobody said
// who is acting, so it is neither confirmed nor denied by the flag or the
// actor; it says that.
func DescribePrecondition(pre string, unevaluable bool) string {
	kind, name, negated := ParsePrecondition(pre)
	w := words(name)
	if unevaluable {
		return fmt.Sprintf("Needs to know who is acting, to check whether they performed %s.", w)
	}
	if kind == "actor" {
		if negated {
			return fmt.Sprintf("Already performed %s.", w)
		}
		return fmt.Sprintf("Must be the person who performed %s.", w)
	}
	if negated {
		return fmt.Sprintf("Already %s.", w)
	}
	return fmt.Sprintf("Requires %s.", w)
}

// PreconditionKind is a machine-stable label for a precondition denial,
// alongside the human sentence DescribePrecondition writes. One of
// "flag_negated", "flag_required", "actor_negated", "actor_required",
// "unevaluable" — never a specific flag or operation name, so a caller can
// react to the shape of the denial without parsing prose a copy pass is free
// to reword. Derived from the same parse the sentence is, so the two cannot
// drift apart.
func PreconditionKind(pre string, unevaluable bool) string {
	if unevaluable {
		return "unevaluable"
	}
	kind, _, negated := ParsePrecondition(pre)
	if negated {
		return kind + "_negated"
	}
	return kind + "_required"
}

// Decision mirrors catalogue/guard.Decision. Kind is set only for a
// precondition denial and is empty for every other denial and for an allow,
// so a caller that only cares about preconditions can test it for emptiness.
type Decision struct {
	Allowed bool
	Reason  string
	Audit   map[string]any
	Kind    string
}

// Op is the part of a compiled operation the guard reads. A struct rather
// than a map, because every field here is one the guard would fail closed
// without and a typo in a map key is a silent pass.
type Op struct {
	ID              string
	Kind            string
	Capability      string
	ScopeQualifier  string
	Preconditions   []string
	Irreversibility string
}

// Validator is callable(op, payload) -> the problems. Required: see the
// package comment.
type Validator func(op Op, payload map[string]any) []string

// Input is Evaluate's keyword arguments, named rather than positional because
// the Python's are and because a positional caps/state pair is two sets of
// strings that would silently swap.
type Input struct {
	Caps       map[string]bool
	State      map[string]bool
	Payload    map[string]any
	Surface    string
	Confirmed  bool
	Scopes     map[string]bool
	Validate   Validator
	Actor      string
	Performers map[string]map[string]bool
	// Withheld is {capability: the plugin id that withholds it} for the
	// facility this kernel is running. It changes NO decision: the capability
	// has already been subtracted from Caps before this is called, so step 2
	// denies either way. What it changes is the sentence, which names both the
	// capability and the plugin. Naming only the plugin leaves an audit line
	// nobody can reconstruct against a bundle.yaml that has since been
	// edited; naming only the capability lies to a clinician whose role
	// plainly holds it.
	Withheld map[string]string
	// ActorGiven says whether an actor was supplied at all, as distinct from
	// an actor that is the empty string. Python passes `actor=None` and tests
	// `actor is None`; Go has no such distinction on a string, so the caller
	// says. kernel/state.actions passes no actor when it was not given one.
	ActorGiven bool
	// PerformersGiven is the same fact about the thread's audit having been
	// read. Python tests `performers is None`, and a nil map and an empty map
	// mean different things to this guard: nobody read the audit, versus
	// nobody has acted.
	PerformersGiven bool
}

// preconditionsMet walks the operation's preconditions over this thread's
// flags and over who has already acted here.
//
// unknownActor says what to do when nobody supplied an actor: the guard
// passes true and denies, because a rule it cannot evaluate must never read
// as satisfied; a surface deciding what to draw passes false and shows the
// action, and the tap is refused.
func preconditionsMet(op Op, state map[string]bool, actorGiven bool, actor string,
	performersGiven bool, performers map[string]map[string]bool,
	unknownActor bool) (met bool, missing string, unevaluable bool) {
	for _, pre := range op.Preconditions {
		kind, name, negated := ParsePrecondition(pre)
		var held bool
		switch {
		case kind == "flag":
			held = state[name]
		case !actorGiven || !performersGiven:
			// Not evaluable: either nobody said who is acting, or nobody read
			// the thread's audit to find out who acted before.
			if unknownActor {
				return false, pre, true
			}
			continue
		default:
			who := Person(actor)
			for a := range performers[name] {
				if Person(a) == who {
					held = true
					break
				}
			}
		}
		if held == negated {
			return false, pre, false
		}
	}
	return true, "", false
}

// Visible answers whether this action should be drawn at all.
//
// Addendum SSD.1: an action does not appear before its precondition. Not
// greyed out, not erroring on tap. Absent. This is the same predicate the
// guard enforces, so the surface cannot drift from the rule.
//
// With no actor an `actor of` precondition cannot be evaluated and the action
// stays drawn; the guard then refuses the tap and says why.
func Visible(op Op, caps, state map[string]bool, actorGiven bool, actor string,
	performersGiven bool, performers map[string]map[string]bool) bool {
	if !caps[op.Capability] {
		return false
	}
	met, _, _ := preconditionsMet(op, state, actorGiven, actor, performersGiven,
		performers, false)
	return met
}

// PreconditionsHoldAgainstNothing is kernel/state.loop_opener reaching for
// the underscore-prefixed predicate: a property of the workflow alone, with
// no capability and no actor in it.
func PreconditionsHoldAgainstNothing(op Op) bool {
	met, _, _ := preconditionsMet(op, nil, false, "", false, nil, false)
	return met
}

// Evaluate is guard steps 1 to 4. Returns a Decision carrying the audit
// record.
func Evaluate(op Op, in Input) Decision {
	audit := map[string]any{
		"operation": op.ID,
		"actor":     actorOrNil(in),
		"surface":   in.Surface,
		"payload":   in.Payload,
		"outcome":   nil,
	}
	deny := func(reason, kind string) Decision {
		audit["outcome"] = "denied: " + reason
		return Decision{Allowed: false, Reason: reason, Audit: audit, Kind: kind}
	}

	// 1. schema. Fail closed: no validator is a denial, never a pass.
	if in.Validate == nil {
		return deny("no validator registered for this operation", "")
	}
	if problems := in.Validate(op, in.Payload); len(problems) > 0 {
		return deny("payload invalid: "+strings.Join(problems, "; "), "")
	}

	// 2. capability, then its scope qualifier. A CHO's rx.prescribe is not an
	//    MO's.
	if !in.Caps[op.Capability] {
		if plugin, withheld := in.Withheld[op.Capability]; withheld {
			return deny(fmt.Sprintf("capability %s withheld by plugin %s: this "+
				"facility does not run it", op.Capability, pyRepr(plugin)), "")
		}
		return deny("missing capability "+op.Capability, "")
	}
	if op.ScopeQualifier != "" && !in.Scopes[op.ScopeQualifier] {
		return deny("outside scope of practice: "+op.ScopeQualifier, "")
	}

	// 3. preconditions over thread state, and over who has already acted here.
	met, missing, unevaluable := preconditionsMet(op, in.State, in.ActorGiven,
		in.Actor, in.PerformersGiven, in.Performers, true)
	if !met {
		return deny(DescribePrecondition(missing, unevaluable),
			PreconditionKind(missing, unevaluable))
	}

	// 4. irreversibility. v0.1 SS5 and addendum SSB.2: the confirm for an
	//    irreversible operation is explicit and un-prefilled, and an agent can
	//    never satisfy it. Note this denies on surface before it looks at
	//    `confirmed` at all, so a machine caller asserting confirmation gets
	//    nowhere.
	if op.Irreversibility == "irreversible" {
		if in.Surface != Rendered {
			return deny("irreversible operations require a human confirmation "+
				"on the rendered surface", "")
		}
		if !in.Confirmed {
			return deny("irreversible operation needs an explicit confirm", "")
		}
	}

	// A write from the machine surface is a proposal, never a commit.
	outcome := "allowed"
	if in.Surface == MCP && op.Kind == "write" {
		outcome = "proposed"
	}
	audit["outcome"] = outcome
	return Decision{Allowed: true, Reason: outcome, Audit: audit}
}

// actorOrNil puts null on the audit line for an actor nobody supplied, which
// is what the Python's `actor=None` serialises to. An empty string would be a
// different answer on the wire.
func actorOrNil(in Input) any {
	if !in.ActorGiven {
		return nil
	}
	return in.Actor
}

// pyRepr is Python's %r for a plain string, which is what the withheld-plugin
// denial sentence contains. Reproduced rather than approximated: the sentence
// is compared between the two engines, and single quotes are part of it.
func pyRepr(s string) string {
	if !strings.Contains(s, "'") {
		return "'" + s + "'"
	}
	return `"` + s + `"`
}

// SortedKeys is a small shared helper: the true keys of a set, sorted. Used
// wherever the Python hands back `sorted(...)` of a set.
func SortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for k, v := range set {
		if v {
			out = append(out, k)
		}
	}
	sort.Strings(out)
	return out
}
