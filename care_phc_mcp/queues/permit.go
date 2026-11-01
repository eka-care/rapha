package queues

import (
	"fmt"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/guard"
	"github.com/eka-care/care_phc_mcp/kstate"
	"github.com/eka-care/care_phc_mcp/proposals"
	"github.com/eka-care/care_phc_mcp/store"
)

// QueueSurfaceNote is what a queue send is called on the audit line. The
// guard's own vocabulary has `allowed`, and that is the right word: steps 1 to
// 4 passed and the caller is about to do 5 to 7, which is exactly the
// situation. A new outcome word would be a sixth thing every reader of the
// audit trail has to learn.
const QueueSurfaceNote = "queued"

// decision is the Decision this package hands back to Pump. A small type rather
// than guard.Decision directly, because Pump's Decision is an interface of two
// methods and guard.Decision carries them as fields.
type decision struct {
	allowed bool
	reason  string
}

func (d decision) Allowed() bool  { return d.allowed }
func (d decision) Reason() string { return d.reason }

// Allowed and Denied build one, for a caller writing its own permit.
func Allowed() Decision          { return decision{true, "allowed"} }
func Denied(why string) Decision { return decision{false, why} }

// GuardStore is what PermitWithGuard needs: the reads the state derivation
// makes, and the one append that puts a decision on the trail. Narrowed to an
// interface so that nothing on this path can write a clinical row.
type GuardStore interface {
	kstate.Reader
	AppendAudit(record store.AuditRecord) error
}

// PermitWithGuard is a Permit for Pump: the guard, against the world as it is
// NOW.
//
// A proposal is judged against the world as it is when it is acted on, not as
// it was when it was made, and this is the same rule over a longer gap. The
// capabilities, the facility's shape and the thread's own flags are read at the
// moment of sending, not at the moment of queueing, so an item queued under
// capabilities somebody has since lost does not go out.
//
// WHICH GUARD STEPS THIS RE-RUNS, exactly, because overstating it would be
// worse than not doing it:
//
//   - step 2, capability, and step 3, preconditions. Through guard.Visible,
//     which is the ONE predicate both enforcement and the surfaces already
//     read, including the `actor of` separation of duties rule. Not
//     re-implemented here, so it cannot drift.
//   - the plugin subtraction, by naming the plugin in the sentence the same way
//     the guard does, so an audit line is reconstructable against a bundle.yaml
//     that has since been edited.
//
// What it does NOT re-run, and why:
//
//   - step 1, the payload schema. A queued item carries no payload. A
//     document's content is the rows in the store, which were validated by the
//     guard when they were committed, and re-validating a projection against a
//     questionnaire is not a thing that means anything. Audio has no payload at
//     all; what it produces is a Draft, and a Draft goes through the whole
//     guard when a person taps it.
//   - step 4, the irreversibility rule, and the scope qualifier. Both are about
//     who may invoke an operation on which surface, and sending is not invoking
//     it: the operation already happened. An irreversible operation that a
//     person performed on the rendered surface does not become un-performed
//     because its document waited for a line.
//
// THE AUDIT ROW IS WRITTEN BEFORE THE SEND, which is the guard's step order and
// is not relaxed for a queue: Pump calls this before it claims, and an allowed
// item is audited before a byte leaves. A denial is audited too, naming the
// capability and, where there is one, the plugin.
type GuardPermit struct {
	Store      GuardStore
	Operations map[string]carephc.Operation
	Workflow   *carephc.Workflow
	Caps       map[string]bool
	Withheld   map[string]string
	Actor      string
	At         string
	Surface    string
}

// Permit is the callable Pump takes.
func (g GuardPermit) Permit(item Item) Decision {
	op, loaded := g.Operations[item.Operation]
	if !loaded {
		return g.refuse(item, fmt.Sprintf("%s is not an operation this kernel "+
			"loads, so nothing may be sent for it", item.Operation))
	}
	// One sentence for a withheld plugin, from the same function Enqueue uses,
	// so admitting and sending cannot disagree about what this centre runs or
	// about how it says so.
	if why := Refusal(item.Kind, op.ID, op.Capability, g.Withheld); why != "" {
		return g.refuse(item, why)
	}
	if !g.Caps[op.Capability] {
		return g.refuse(item, "missing capability "+op.Capability)
	}
	flags, err := kstate.Flags(g.Store, item.Thread, g.Workflow)
	if err != nil {
		// A permit that cannot read the thread must not allow the send. Fail
		// closed, which is guard step 3's rule when a precondition cannot be
		// evaluated at all.
		return g.refuse(item, "the preconditions for "+op.ID+
			" could not be read, so nothing may be sent for it")
	}
	performers, err := kstate.Performers(g.Store, item.Thread)
	if err != nil {
		return g.refuse(item, "the preconditions for "+op.ID+
			" could not be read, so nothing may be sent for it")
	}
	who := item.Actor
	if who == "" {
		who = g.Actor
	}
	if !guard.Visible(guardOp(op), g.Caps, flags, true, who, true, performers) {
		return g.refuse(item, fmt.Sprintf("the preconditions for %s no longer "+
			"hold on this visit", op.ID))
	}
	// Allowed, and audited before anything is sent.
	if _, err := proposals.AuditRow(g.Store, map[string]any{
		"operation": op.ID, "actor": g.Actor,
		"surface": g.surface(),
		"payload": map[string]any{
			"queued": item.Kind, "item": item.ID, "key": item.Key},
		"outcome": "allowed",
	}, item.Thread, g.At, ""); err != nil {
		// An allow nobody could write down is not an allow. The guard's own
		// rule is that the record comes before the act.
		return decision{false, "the audit row for this send could not be " +
			"written, so nothing was sent"}
	}
	return decision{true, "allowed"}
}

func (g GuardPermit) surface() string {
	if g.Surface != "" {
		return g.Surface
	}
	return guard.Rendered
}

// refuse is one denial: the audit row first, then the decision.
//
// Written here and not left to the caller for the reason the guard gives for
// building the record itself: a denial nobody wrote down is a denial that did
// not happen as far as anybody reading the trail can tell.
func (g GuardPermit) refuse(item Item, reason string) Decision {
	_, _ = proposals.AuditRow(g.Store, map[string]any{
		"operation": item.Operation, "actor": g.Actor,
		"surface": guard.Rendered,
		"payload": map[string]any{
			"queued": item.Kind, "item": item.ID, "key": item.Key},
		"outcome": "denied: " + reason,
	}, item.Thread, g.At, "")
	return decision{false, reason}
}

// guardOp is the compiled atom as the guard reads it. The same reshaping
// cmd/api does, so the queue and the routes cannot disagree about which fields
// the guard is given.
func guardOp(op carephc.Operation) guard.Op {
	scope := ""
	if op.ScopeQualifier != nil {
		scope = *op.ScopeQualifier
	}
	return guard.Op{
		ID: op.ID, Kind: op.Kind, Capability: op.Capability,
		ScopeQualifier: scope, Preconditions: op.Preconditions,
		Irreversibility: op.Irreversibility,
	}
}
