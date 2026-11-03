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
	"strings"
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
	// Select is here for one caller: WrittenBy, which has to find the rows a
	// given operation wrote before a correction can replace them.
	Select(resource string, thread *string, q store.Query, fields []string,
		limit int) ([]map[string]string, error)
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

// Auditable is all AuditRow needs, which is the one append. Narrower than
// Store on purpose: the outbox (G8) writes the queue's own audit rows and
// reaches a store through which nothing clinical can be written, so a builder
// that demanded the whole write path would have forced that caller to hold a
// wider handle than it uses. Every Store satisfies this.
type Auditable interface {
	AppendAudit(r store.AuditRecord) error
}

// audit writes one audit record from a guard decision's audit dict. Public as
// AuditRow, because the queue slice (G8) writes the queue's own audit rows
// and there must be exactly one builder of an audit record. A second one
// would be a second place for the id prefix, the field order and the guard's
// dict shape to drift, which is the whole reason this helper exists.
func AuditRow(s Auditable, decision map[string]any, thread, at, proposal string) (store.AuditRecord, error) {
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
	return b.decideWith(s, op, thread, payload, caps, surface, actor, confirmed,
		scopes, false)
}

func (b *Bundle) decideWith(s Store, op carephc.Operation, thread string,
	payload map[string]any, caps map[string]bool, surface, actor string,
	confirmed bool, scopes map[string]bool, correcting bool) (guard.Decision, error) {
	if !kstate.DrawnBy(b.Workflow, op.ID) {
		// Before the guard, because this is not a judgement about this
		// thread's state: the operation is not part of this line at all.
		return guard.Decision{
			Allowed: false,
			// In the workflow's own words and the operation's own title:
			// the ids are on the audit line below, where an auditor can
			// find them. Parity with kernel/proposals.py.
			Reason: fmt.Sprintf("%s is not a step of %s: no station in this "+
				"line draws it", op.Title, b.Workflow.Title),
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
	if correcting {
		// A CORRECTION IS EVALUATED AS IF ITS OWN RECORD WERE NOT THERE.
		// `phc.op.vitals-record` declares `not vitals.recorded`, so a nurse
		// fixing a pulse she keyed as 85 and meant as 58 would be told the
		// vitals are already recorded, which is both true and useless. A
		// precondition of that shape says when a step may first be TAKEN;
		// a correction is not taking it again. Only this operation's own
		// negative terms are lifted; everything else about the guard runs
		// exactly as it does on a commit.
		lifted := map[string]bool{}
		for flag, known := range flags {
			lifted[flag] = known
		}
		for _, term := range op.Preconditions {
			if strings.HasPrefix(term, "not ") {
				delete(lifted, strings.TrimSpace(term[4:]))
			}
		}
		flags = lifted
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
	payload map[string]any, actor string, reuse map[string][]string) ([]string, error) {
	var records []mapping.Record
	if _, err := b.Catalogue.Mapping(op.ID, &records); err != nil {
		return nil, err
	}
	built, err := mapping.Records(records, payload, actor, b.Terms)
	if err != nil {
		return nil, err
	}
	// WHICH OPERATION WROTE THIS ROW, stamped here because it is the
	// kernel's fact and not the mapping's: a declaration says what a blood
	// pressure is, not which form it arrived on. Without it a correction
	// could not find its own rows -- a consultation and a nurse's vitals
	// both write `observation` on one thread. `reuse` is the ids of the
	// rows a correction is replacing, per resource and in order; nil on a
	// first commit, which is an insert.
	spare := map[string][]string{}
	for res, had := range reuse {
		spare[res] = append([]string(nil), had...)
	}
	var ids []string
	for _, row := range built {
		columns := map[string]any{}
		for k, v := range row.Columns {
			columns[k] = v
		}
		columns["operation"] = op.ID
		if left := spare[row.Resource]; len(left) > 0 {
			columns["id"] = left[0]
			spare[row.Resource] = left[1:]
		}
		id, err := s.Write(row.Resource, columns, thread)
		if err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	for _, flag := range b.Raised(op, payload) {
		// NO ACTOR, and that is copied rather than improved.
		// kernel/proposals._write calls store.raise_flag(thread, flag) with
		// two arguments, so every flag the guard raises lands with created_by
		// NULL. The adapter's own seed passes one (adapters/local/store.py
		// seed()), and the `{actor: id}` mapping source exists precisely
		// because rows landing with created_by null made "who did this" a
		// question only the audit could answer. The same gap is open on this
		// path and closing it here would be this engine inventing an answer
		// the reference does not give.
		if err := s.RaiseFlag(thread, flag, ""); err != nil {
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
		if _, err := b.write(s, op, thread, payload, actor, nil); err != nil {
			return decision, err
		}
	}
	return decision, nil
}

// WrittenBy is the rows this operation already wrote on this visit, keyed by
// resource and ordered by when each row was opened, so a correction replaces
// the first medicine with the first medicine. `operation` is the column
// write() stamps; a row written before that column existed has none and
// comes back in no list, which is why Amend refuses rather than guessing
// which row a clinician meant.
func (b *Bundle) WrittenBy(s Store, op carephc.Operation, thread string) (map[string][]string, error) {
	var records []mapping.Record
	if _, err := b.Catalogue.Mapping(op.ID, &records); err != nil {
		return nil, err
	}
	found := map[string][]string{}
	for _, record := range records {
		if _, seen := found[record.Resource]; seen {
			continue
		}
		rows, err := s.Select(record.Resource, &thread,
			store.Query{"operation": {Equals: op.ID}}, []string{"id", "created_date"}, 200)
		if err != nil {
			return nil, err
		}
		sort.SliceStable(rows, func(i, j int) bool {
			if rows[i]["created_date"] != rows[j]["created_date"] {
				return rows[i]["created_date"] < rows[j]["created_date"]
			}
			return rows[i]["id"] < rows[j]["id"]
		})
		ids := []string{}
		for _, row := range rows {
			ids = append(ids, row["id"])
		}
		found[record.Resource] = ids
	}
	for res, ids := range found {
		if len(ids) == 0 {
			delete(found, res)
		}
	}
	return found, nil
}

// Amend corrects what was already recorded, while the visit is still open.
//
// THE CASE THIS EXISTS FOR. A nurse keys a pulse of 85 and means 58. The
// only answers before it were a second contradictory reading or leaving the
// wrong one standing, and a clinician who cannot fix an obvious slip keeps a
// paper copy.
//
// ONLY WHILE THE VISIT IS OPEN. A workflow out of stations is a visit that
// is over, its document may already have gone to ABDM, and a record changed
// after publication is a different problem with a different answer: a new
// bundle that relatesTo the old one. So this refuses in those words.
//
// THE GUARD RUNS AGAIN, less this operation's own negative preconditions.
// Same capability, same scope, same separation of duties, same validator,
// same audit line. Nothing here is a shortcut past the guard.
func (b *Bundle) Amend(s Store, op carephc.Operation, thread string,
	payload map[string]any, caps, scopes map[string]bool, actor string,
	confirmed bool, at string) (guard.Decision, error) {
	if at == "" {
		at = Now()
	}
	refuse := func(reason, outcome string) (guard.Decision, error) {
		decision := guard.Decision{Allowed: false, Reason: reason, Audit: map[string]any{
			"operation": op.ID, "actor": actor, "surface": guard.Rendered,
			"payload": copyPayload(payload), "outcome": outcome,
		}}
		if _, err := AuditRow(s, decision.Audit, thread, at, ""); err != nil {
			return decision, err
		}
		return decision, nil
	}

	flags, err := kstate.Flags(s, thread, b.Workflow)
	if err != nil {
		return guard.Decision{}, err
	}
	if kstate.Station(b.Workflow, flags) == "" {
		return refuse("this visit is over, so its records can no longer be "+
			"edited here", "denied: the visit is over")
	}
	if op.Irreversibility == "irreversible" {
		return refuse("this cannot be edited: it was an irreversible action "+
			"and it has already left this facility", "denied: irreversible")
	}
	reuse, err := b.WrittenBy(s, op, thread)
	if err != nil {
		return guard.Decision{}, err
	}
	if len(reuse) == 0 {
		return refuse("nothing recorded by this operation was found on this "+
			"visit, so there is nothing to edit", "denied: nothing to edit")
	}

	decision, err := b.decideWith(s, op, thread, payload, caps, guard.Rendered,
		actor, confirmed, scopes, true)
	if err != nil {
		return guard.Decision{}, err
	}
	if decision.Allowed {
		decision.Audit["outcome"] = "amended"
	}
	if _, err := AuditRow(s, decision.Audit, thread, at, ""); err != nil {
		return decision, err
	}
	if decision.Allowed {
		if _, err := b.write(s, op, thread, payload, actor, reuse); err != nil {
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
			Reason: "that is not an action this facility offers",
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
	if _, err := b.write(s, op, proposal.Thread, use, actor, nil); err != nil {
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
