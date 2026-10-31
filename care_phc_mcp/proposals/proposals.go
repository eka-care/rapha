// Package proposals is kernel/proposals.py in Go: the write path, and the
// audit log.
//
// THERE IS ONE RULE AND THIS PACKAGE IS IT
// ----------------------------------------
// Nothing reaches Store.Write without a guard.Evaluate that allowed it, and
// confirming a proposal is a SECOND guard pass on the rendered surface with
// the payload as it stands after a person edited it. So a proposal is not a
// stored permission: it is a stored request, re-judged at the moment it is
// accepted, against the thread state as it is then. A proposal made when a
// precondition held is denied at confirm if the precondition has since gone.
//
// Commit hard codes the rendered surface rather than taking one, because a
// surface argument is a hole: a caller that could pass Rendered could pass it
// from a machine. The MCP server has Propose and nothing else.
//
// EVERY DECISION IS AUDITED, DENIALS INCLUDED, AND BEFORE THE WRITE
// -----------------------------------------------------------------
// An audit line that only appears when a write succeeded is a log of what
// worked, not of what was tried. And the order is not cosmetic: the row goes
// on the trail BEFORE execute, so a process killed between the two leaves a
// record of an attempt rather than a clinical fact nobody asked for.
//
// THE SEVEN STEPS, AND WHERE EACH ONE IS
// --------------------------------------
//  1. schema          guard.Evaluate step 1, through Validator below
//  2. capability       guard.Evaluate step 2
//  3. preconditions    guard.Evaluate step 3, over kstate.Flags and kstate.Performers
//  4. irreversibility  guard.Evaluate step 4
//  5. audit persist    audit() below, before anything is written
//  6. the CARE write   write() below, through the compiled mapping
//  7. the state emit   write() below, raising the flags the payload raised
package proposals

import (
	"fmt"
	"sort"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/guard"
	"github.com/eka-care/care_phc_mcp/kstate"
	"github.com/eka-care/care_phc_mcp/mapping"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/store"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// Store is every method the write path uses. Wider than kstate.Reader by the
// four writes, and no wider: a package that can open a thread could open one
// without a guard pass.
type Store interface {
	kstate.Reader
	Write(resource string, record map[string]any, thread string) (string, error)
	RaiseFlag(thread, flag, actor string) error
	PutProposal(p store.Proposal) error
	AppendAudit(r store.AuditRecord) error
	Proposal(id string) (*store.Proposal, bool, error)
}

// Bundle is the loaded declarations the write path reads. Assembled once at
// startup, so nothing here opens a file.
type Bundle struct {
	Catalogue  *carephc.Catalogue
	Operations map[string]carephc.Operation
	Workflow   *carephc.Workflow
	Schemas    *questionnaire.Set
	Terms      *terminology.Cache
	// Withheld is {capability: the plugin id that withholds it} for the
	// facility this kernel runs. It changes no decision; see guard.Input.
	Withheld map[string]string
}

// Now is the audit and proposal timestamp format, which is the Python's
// strftime("%Y-%m-%dT%H:%M:%SZ") in UTC.
//
// NOT store.Now(), which spells the same moment "+00:00". The two spellings
// are kernel/proposals.now() and adapters/local/store.now() and they really
// are different in the Python: the kernel's stamps an audit row and a
// proposal, the adapter's stamps a clinical row's created_date. Copied rather
// than unified, because unifying them would change what a stored row looks
// like and that is not this slice's call.
func Now() string {
	return time.Now().UTC().Format("2006-01-02T15:04:05Z")
}

// newID is kernel/proposals._id: the WHOLE prefix and twelve hex digits.
//
// Also not store.NewID, which is adapters/local/store.new_id: four letters of
// the prefix and eight digits. Two id shapes, one per layer, and a proposal
// carries the kernel's.
func newID(prefix string) string {
	return prefix + "-" + store.RandomHex(12)
}

// Validator is the same validator every surface uses, loaded from the
// questionnaire the operation names, so there is one definition of a valid
// payload.
//
// Two halves, composed here and nowhere else. The schema rules are the
// catalogue's (required, types, choices, the range rule) and the terminology
// rules are the kernel's (an answer is a code its value set holds, and a unit
// is the one its analyte is reported in). They are composed rather than
// merged because the catalogue layer may not import the kernel and the value
// sets are the kernel's, and composing them here keeps the property that
// matters: there is still exactly one validator per operation and every
// surface uses it.
//
// Both halves run, and the problems are concatenated, so a technician with a
// bad number and a bad unit is told about both at once rather than fixing one
// and discovering the other. That is CARE's all-or-nothing submission rule,
// which is the right one.
//
// Returns nil for an operation whose questionnaire cannot be loaded, and that
// nil is a DENIAL at guard step 1, not a pass. See the package comment on
// guard.
func (b *Bundle) Validator(op carephc.Operation) guard.Validator {
	schema, err := b.Schemas.Get(op.Input)
	if err != nil {
		return nil
	}
	terms := b.Terms
	return func(_ guard.Op, payload map[string]any) []string {
		return append(schema.Validate(payload), terms.AnswerProblems(schema, payload)...)
	}
}

// Raised is the stored flags this payload raises. A critical but in-range
// value flags; an out of range value never gets this far, the validator
// blocks it.
func (b *Bundle) Raised(op carephc.Operation, payload map[string]any) []string {
	schema, err := b.Schemas.Get(op.Input)
	if err != nil {
		return []string{}
	}
	declared := map[string]bool{}
	for _, flag := range b.Workflow.Stored {
		declared[flag] = true
	}
	out := []string{}
	for flag := range schema.Flags(payload) {
		if declared[flag] {
			out = append(out, flag)
		}
	}
	sort.Strings(out)
	return out
}

// audit writes one audit record from a guard decision's audit dict. Public as
// AuditRow, because the queue slice (G8) writes the queue's own audit rows
// and there must be exactly one builder of an audit record. A second one
// would be a second place for the id prefix, the field order and the guard's
// dict shape to drift, which is the whole reason this helper exists.
func AuditRow(s Store, decision map[string]any, thread, at, proposal string) (store.AuditRecord, error) {
	record := store.AuditRecord{
		ID:        newID("aud"),
		Thread:    thread,
		Operation: str(decision["operation"]),
		Actor:     str(decision["actor"]),
		Surface:   str(decision["surface"]),
		Outcome:   str(decision["outcome"]),
		At:        at,
		Proposal:  proposal,
	}
	if payload, ok := decision["payload"].(map[string]any); ok {
		record.Payload = payload
	} else {
		record.Payload = map[string]any{}
	}
	return record, s.AppendAudit(record)
}

func str(v any) string {
	if v == nil {
		return ""
	}
	s, _ := v.(string)
	return s
}

// decide is kernel/proposals._decide: the workflow check that comes BEFORE
// the guard, then the guard.
func (b *Bundle) decide(s Store, op carephc.Operation, thread string,
	payload map[string]any, caps map[string]bool, surface, actor string,
	confirmed bool, scopes map[string]bool) (guard.Decision, error) {
	if !kstate.DrawnBy(b.Workflow, op.ID) {
		// Before the guard, because this is not a judgement about this
		// thread's state: the operation is not part of this line at all.
		return guard.Decision{
			Allowed: false,
			Reason: fmt.Sprintf("%s is not a step of %s: no station in this "+
				"workflow draws it", op.ID, b.Workflow.ID),
			Audit: map[string]any{
				"operation": op.ID, "actor": actor, "surface": surface,
				"payload": copyPayload(payload),
				"outcome": "denied: not in this workflow",
			},
		}, nil
	}
	flags, err := kstate.Flags(s, thread, b.Workflow)
	if err != nil {
		return guard.Decision{}, err
	}
	performers, err := kstate.Performers(s, thread)
	if err != nil {
		return guard.Decision{}, err
	}
	// Which plugins this facility runs is the bundle's own answer and never a
	// caller's argument: a surface that could pass one could widen it. It
	// changes no decision, only the sentence.
	withheld := map[string]string{}
	for cap, plugin := range b.Withheld {
		withheld[cap] = plugin
	}
	return guard.Evaluate(kstate.GuardOp(op), guard.Input{
		Caps: caps, State: flags, Payload: payload, Surface: surface,
		Confirmed: confirmed, Scopes: scopes, Validate: b.Validator(op),
		Actor: actor, ActorGiven: true, Performers: performers,
		PerformersGiven: true, Withheld: withheld,
	}), nil
}

// write is guard steps 6 and 7: the CARE write, then the state emit.
//
// Which answer becomes which column is declared on the operation atom and
// compiled by kernel/mapping.py, so the store is handed rows and not the
// payload. Every adapter inherits the one mapping; none of them re-derives
// what a blood pressure is.
//
// One record in, one Store.Write out. A payload fans out, so three vitals are
// three observation rows and two medicines are two medication_request rows,
// which is what dispensed.complete counts.
//
// `actor` is what the mapping's {actor: id} source reads, so every row a
// declaration writes carries its author. Rows used to land with created_by
// null, which made "who did this" a question only the audit could answer.
func (b *Bundle) write(s Store, op carephc.Operation, thread string,
	payload map[string]any, actor string) ([]string, error) {
	var records []mapping.Record
	if _, err := b.Catalogue.Mapping(op.ID, &records); err != nil {
		return nil, err
	}
	built, err := mapping.Records(records, payload, actor, b.Terms)
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, row := range built {
		id, err := s.Write(row.Resource, row.Columns, thread)
		if err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	for _, flag := range b.Raised(op, payload) {
		if err := s.RaiseFlag(thread, flag, actor); err != nil {
			return nil, err
		}
	}
	return ids, nil
}

func copyPayload(in map[string]any) map[string]any {
	out := map[string]any{}
	for k, v := range in {
		out[k] = v
	}
	return out
}

// Propose queues a write for a person to accept. A denial writes an audit
// line and no proposal.
//
// Used by the MCP surface and by an instrument that captured a draft.
func (b *Bundle) Propose(s Store, op carephc.Operation, thread string,
	payload map[string]any, caps, scopes map[string]bool, actor, surface, at string,
) (guard.Decision, *store.Proposal, error) {
	if at == "" {
		at = Now()
	}
	if surface == "" {
		surface = guard.MCP
	}
	decision, err := b.decide(s, op, thread, payload, caps, surface, actor, false, scopes)
	if err != nil {
		return guard.Decision{}, nil, err
	}
	if !decision.Allowed {
		if _, err := AuditRow(s, decision.Audit, thread, at, ""); err != nil {
			return decision, nil, err
		}
		return decision, nil, nil
	}
	proposal := store.Proposal{
		ID: newID("prop"), Thread: thread, Operation: op.ID,
		Payload: copyPayload(payload), ProposedBy: actor, Surface: surface,
		Status: "pending", CreatedAt: at, FlagsRaised: b.Raised(op, payload),
	}
	if err := s.PutProposal(proposal); err != nil {
		return decision, nil, err
	}
	if _, err := AuditRow(s, decision.Audit, thread, at, proposal.ID); err != nil {
		return decision, &proposal, err
	}
	return decision, &proposal, nil
}

// Commit is a person, on the rendered surface, writing directly. The surface
// is not a parameter on purpose.
func (b *Bundle) Commit(s Store, op carephc.Operation, thread string,
	payload map[string]any, caps, scopes map[string]bool, actor string,
	confirmed bool, at string) (guard.Decision, error) {
	if at == "" {
		at = Now()
	}
	decision, err := b.decide(s, op, thread, payload, caps, guard.Rendered,
		actor, confirmed, scopes)
	if err != nil {
		return guard.Decision{}, err
	}
	// Step 5 before step 6, and that order is the property: the row is on the
	// trail before a clinical fact exists.
	if _, err := AuditRow(s, decision.Audit, thread, at, ""); err != nil {
		return decision, err
	}
	if decision.Allowed {
		if _, err := b.write(s, op, thread, payload, actor); err != nil {
			return decision, err
		}
	}
	return decision, nil
}

// Confirm accepts a queued write: the second guard pass, on the rendered
// surface, with the payload as the person edited it.
func (b *Bundle) Confirm(s Store, proposal store.Proposal, caps, scopes map[string]bool,
	actor string, payload map[string]any, given bool, confirmed bool, at string,
) (guard.Decision, store.Proposal, error) {
	if at == "" {
		at = Now()
	}
	use := proposal.Payload
	if given {
		use = payload
	}
	use = copyPayload(use)

	op, declared := b.Operations[proposal.Operation]
	if !declared {
		// A proposal outlived the bundle that queued it: one SQLite file
		// opened under PHC_BUNDLE=lab still holds the health centre's rows.
		// Refuse it like any other denial rather than failing on the tap.
		// Nothing was ever written either way; a 500 on a confirm button is
		// still the wrong answer.
		decision := guard.Decision{
			Allowed: false,
			Reason: fmt.Sprintf("%s is not an operation this facility declares",
				proposal.Operation),
			Audit: map[string]any{
				"operation": proposal.Operation, "actor": actor,
				"surface": guard.Rendered, "payload": use,
				"outcome": "denied: not in this bundle",
			},
		}
		_, err := AuditRow(s, decision.Audit, proposal.Thread, at, proposal.ID)
		return decision, proposal, err
	}

	if proposal.Status != "pending" {
		decision := guard.Decision{
			Allowed: false,
			Reason:  "proposal is already " + proposal.Status,
			Audit: map[string]any{
				"operation": proposal.Operation, "actor": actor,
				"surface": guard.Rendered, "payload": use,
				"outcome": "denied: already " + proposal.Status,
			},
		}
		_, err := AuditRow(s, decision.Audit, proposal.Thread, at, proposal.ID)
		return decision, proposal, err
	}

	decision, err := b.decide(s, op, proposal.Thread, use, caps, guard.Rendered,
		actor, confirmed, scopes)
	if err != nil {
		return guard.Decision{}, proposal, err
	}
	if !decision.Allowed {
		_, err := AuditRow(s, decision.Audit, proposal.Thread, at, proposal.ID)
		return decision, proposal, err
	}
	decision.Audit["outcome"] = "confirmed"
	if _, err := AuditRow(s, decision.Audit, proposal.Thread, at, proposal.ID); err != nil {
		return decision, proposal, err
	}
	if _, err := b.write(s, op, proposal.Thread, use, actor); err != nil {
		return decision, proposal, err
	}
	decided := proposal
	decided.Status = "confirmed"
	decided.DecidedBy = actor
	decided.DecidedAt = at
	decided.FinalPayload = use
	decided.FlagsRaised = b.Raised(op, use)
	if err := s.PutProposal(decided); err != nil {
		return decision, decided, err
	}
	return decision, decided, nil
}

// Reject declines a queued write. Nothing is written; the request stays on
// the record, because what was refused is as interesting as what was done.
func (b *Bundle) Reject(s Store, proposal store.Proposal, actor, reason, at string,
) (store.Proposal, error) {
	if at == "" {
		at = Now()
	}
	decided := proposal
	decided.Status = "rejected"
	decided.DecidedBy = actor
	decided.DecidedAt = at
	if err := s.PutProposal(decided); err != nil {
		return decided, err
	}
	outcome := "rejected"
	if reason != "" {
		outcome = "rejected: " + reason
	}
	_, err := AuditRow(s, map[string]any{
		"operation": proposal.Operation, "actor": actor,
		"surface": guard.Rendered, "payload": copyPayload(proposal.Payload),
		"outcome": outcome,
	}, proposal.Thread, at, proposal.ID)
	return decided, err
}
