// Package kstate is kernel/state.py in Go: thread state, declared instead of
// coded.
//
// WHY THIS IS IN THE GUARD'S SLICE AND NOT IN G6'S
// ------------------------------------------------
// Guard step 3 is "preconditions over thread state", so the flags are not a
// view's convenience, they are an input to every refusal. The parts of
// kernel/state.py that only a screen needs — the station line, the quick
// action row and the thread panel — are here too, and that IS pulling some of
// G6 forward. It is pulled rather than stubbed because api/main.py answers
// POST /operations/{op}/commit and POST /proposals/{id}/confirm with the
// thread panel, so there is no way to compare the guard's answers between the
// two engines without it. The DECLARED views (GET /queue, GET /views/{id})
// and the metrics stay in G6, which is where kernel/views.py is.
//
// THE DECLARATION ORDER OF THE STATE RULES IS LOAD BEARING
// --------------------------------------------------------
// flags() walks the rules in the order the workflow declared them and an
// `all_of` reads the flags already known. catalogue.json is written with
// sorted keys, so the order is NOT the dict's and is carried separately as
// `state_order` (see kernel/declarations.compile_json). Alphabetically
// `abha.pending` cannot see `registered` and `capture.consented` cannot see
// `capture.declined`, which would make a declined visit read as consented to
// ambient capture.
package kstate

import (
	"fmt"
	"sort"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/guard"
	"github.com/eka-care/care_phc_mcp/store"
)

// Reader is the part of the store this package needs. Narrow on purpose: the
// state of a thread is derived from counts, from the stored flags and from
// the audit trail, and nothing here may write.
type Reader interface {
	Count(resource string, thread *string, where store.Query) (int, error)
	StoredFlags(thread string) (map[string]bool, error)
	Audit(thread string) ([]store.AuditRecord, error)
	Proposals(thread, status string) ([]store.Proposal, error)
}

// Query turns the compiled `where` of a state rule into the store's query
// grammar: a plain value is an equality, "*" is present-and-not-empty, and a
// mapping is a range.
func Query(where map[string]any) (store.Query, error) {
	out := store.Query{}
	for field, cond := range where {
		switch t := cond.(type) {
		case string:
			if t == "*" {
				out[field] = store.Cond{Present: true}
				continue
			}
			out[field] = store.Cond{Equals: t}
		case map[string]any:
			c := store.Cond{}
			for op, value := range t {
				text, ok := store.Text(value)
				if !ok {
					return nil, fmt.Errorf("%s %s: %v is not a value a column holds",
						field, op, value)
				}
				switch op {
				case "gte":
					c.Gte = text
				case "gt":
					c.Gt = text
				case "lte":
					c.Lte = text
				case "lt":
					c.Lt = text
				default:
					return nil, fmt.Errorf("%s: unknown comparison %q", field, op)
				}
			}
			out[field] = c
		default:
			text, ok := store.Text(cond)
			if !ok {
				return nil, fmt.Errorf("%s: %v is not a value a column holds", field, cond)
			}
			out[field] = store.Cond{Equals: text}
		}
	}
	return out, nil
}

func count(s Reader, thread string, q carephc.StateQuery) (int, error) {
	where, err := Query(q.Where)
	if err != nil {
		return 0, err
	}
	return s.Count(q.Resource, &thread, where)
}

// ruleTrue is kernel/state._true: one state rule, in one of its four forms.
func ruleTrue(s Reader, thread string, rule carephc.StateRule,
	known, stored map[string]bool, flag string) (bool, error) {
	switch rule.Form {
	case "stored":
		return stored[flag], nil
	case "exists":
		n, err := count(s, thread, rule.Exists)
		return n > 0, err
	case "gte":
		a, err := count(s, thread, rule.Gte[0])
		if err != nil {
			return false, err
		}
		b, err := count(s, thread, rule.Gte[1])
		if err != nil {
			return false, err
		}
		// Partial dispense is a normal outcome, so this is a comparison and
		// not a boolean, and an empty denominator is never "complete".
		return b > 0 && a >= b, nil
	case "all_of":
		for _, item := range rule.AllOf {
			if item.Flag != "" {
				if item.Negated {
					if known[item.Flag] {
						return false, nil
					}
					continue
				}
				if !known[item.Flag] {
					return false, nil
				}
				continue
			}
			held, err := ruleTrue(s, thread, *item.Rule, known, stored, flag)
			if err != nil || !held {
				return false, err
			}
		}
		return true, nil
	}
	return false, fmt.Errorf("unknown state rule form '%s'", rule.Form)
}

// Flags is the flags true for this thread right now, in declaration order.
//
// A stored flag the workflow does not declare stored is dropped, the way the
// Python drops one: a stored copy of a derived fact desyncs, and a desynced
// copy shows a pharmacist a Dispense button that should not exist.
func Flags(s Reader, thread string, wf *carephc.Workflow) (map[string]bool, error) {
	held, err := s.StoredFlags(thread)
	if err != nil {
		return nil, err
	}
	declared := map[string]bool{}
	for _, flag := range wf.Stored {
		declared[flag] = true
	}
	stored := map[string]bool{}
	for flag := range held {
		if declared[flag] {
			stored[flag] = true
		}
	}
	known := map[string]bool{}
	for _, flag := range wf.StateOrder {
		rule, declaredRule := wf.States[flag]
		if !declaredRule {
			continue
		}
		on, err := ruleTrue(s, thread, rule, known, stored, flag)
		if err != nil {
			return nil, err
		}
		if on {
			known[flag] = true
		}
	}
	return known, nil
}

// performed are the outcomes on an audit line that mean "this actor performed
// this operation on this thread". A proposal is a request and not a
// performance; a denial is the opposite of one.
var performed = map[string]bool{"allowed": true, "confirmed": true}

// Performers is {operation id: the actors who have performed it on this
// thread}, read from the audit trail, which is the only record that carries
// an actor per decision.
func Performers(s Reader, thread string) (map[string]map[string]bool, error) {
	trail, err := s.Audit(thread)
	if err != nil {
		return nil, err
	}
	out := map[string]map[string]bool{}
	for _, record := range trail {
		if !performed[record.Outcome] || record.Actor == "" {
			continue
		}
		if out[record.Operation] == nil {
			out[record.Operation] = map[string]bool{}
		}
		out[record.Operation][record.Actor] = true
	}
	return out, nil
}

// Station is where this thread is, or "" once the line is complete.
//
// A step whose applies_when is false is skipped, not pending: a patient
// nobody ordered a test for is not waiting at the lab.
func Station(wf *carephc.Workflow, known map[string]bool) string {
	for _, step := range wf.Steps {
		if step.AppliesWhen != "" && !known[step.AppliesWhen] {
			continue
		}
		if !known[step.DoneWhen] {
			return step.Station
		}
	}
	return ""
}

// StepStatus is kernel/contracts.StepStatus.
type StepStatus struct {
	Station string `json:"station"`
	Label   string `json:"label"`
	Status  string `json:"status"`
}

// Line is the workflow's steps as StepStatus, for the renderer to draw.
func Line(wf *carephc.Workflow, known map[string]bool) []StepStatus {
	here := Station(wf, known)
	out := make([]StepStatus, 0, len(wf.Steps))
	currentTaken := false
	for _, step := range wf.Steps {
		var status string
		switch {
		case step.AppliesWhen != "" && !known[step.AppliesWhen]:
			status = "skipped"
		case known[step.DoneWhen]:
			status = "done"
		case !currentTaken && step.Station == here:
			status, currentTaken = "now", true
		default:
			status = "pending"
		}
		out = append(out, StepStatus{Station: step.Station, Label: step.DoneWhen,
			Status: status})
	}
	return out
}

// DrawnBy answers whether any step of this workflow puts this operation on a
// thread.
//
// catalogue/ops is shared between bundles, and a manifest may list an atom no
// step draws. phc.op.household-visit is one: it stands at `community`, which
// the outpatient line has no station for. Nothing stopped it, so once the
// demo account held visit.household it appeared as a button on every clinic
// encounter and wrote a household questionnaire onto it. A thread belongs to
// a workflow, so an operation that workflow never draws has no place on that
// thread, from any surface.
func DrawnBy(wf *carephc.Workflow, opID string) bool {
	for _, step := range wf.Steps {
		for _, id := range step.Operations {
			if id == opID {
				return true
			}
		}
	}
	return false
}

// LoopCloser is the operation at `station` that ends this role's task there.
//
// A step declares done_when, and exactly one of its operations emits that
// flag. Returns "" for a station this workflow has no step for, and for a
// step whose done_when no operation at that station emits — a bundle may
// declare a flag raised somewhere else, and that is a line with no close, not
// a crash.
func LoopCloser(wf *carephc.Workflow, operations map[string]carephc.Operation,
	station string) string {
	for _, step := range wf.Steps {
		if step.Station != station {
			continue
		}
		for _, opID := range step.Operations {
			op, declared := operations[opID]
			if !declared {
				continue
			}
			for _, emitted := range op.Emits {
				if emitted == step.DoneWhen {
					return opID
				}
			}
		}
	}
	return ""
}

// Actions is the quick actions to draw, ordered. Addendum SSD.2: a table, not
// a model.
//
// Ordering is by the declared line, so the next thing to do at this thread's
// current station sorts first. Inside one station it is the order the step
// declares its operations in, because a bundle writing that list down is a
// bundle saying which of the things at this station is the point.
func Actions(wf *carephc.Workflow, operations map[string]carephc.Operation,
	known, caps map[string]bool, stationFilter string, actorGiven bool,
	actor string, performersGiven bool,
	performers map[string]map[string]bool) []carephc.Operation {
	// LAST step wins for a station, FIRST for an operation's seat, and that
	// asymmetry is the Python's: kernel/state.actions builds `order` with a
	// dict comprehension, which overwrites, and `seat` with setdefault, which
	// does not. bundles/phc gives every station one step so nothing turns on
	// it here, and a bundle that draws one station twice would sort
	// differently in the two engines if this were tidied up.
	order := map[string]int{}
	for i, step := range wf.Steps {
		order[step.Station] = i
	}
	seat := map[string]int{}
	for _, step := range wf.Steps {
		for i, opID := range step.Operations {
			if _, seen := seat[opID]; !seen {
				seat[opID] = i
			}
		}
	}
	here := Station(wf, known)
	var picked []carephc.Operation
	for _, op := range operations {
		if !DrawnBy(wf, op.ID) {
			continue
		}
		if !guard.Visible(GuardOp(op), caps, known, actorGiven, actor,
			performersGiven, performers) {
			continue
		}
		if stationFilter != "" && op.Station != stationFilter {
			continue
		}
		picked = append(picked, op)
	}
	rank := func(op carephc.Operation) (bool, int, int, string) {
		at, placed := order[op.Station]
		if !placed {
			at = 99
		}
		s, placed := seat[op.ID]
		if !placed {
			s = 99
		}
		return op.Station != here, at, s, op.ID
	}
	sort.Slice(picked, func(i, j int) bool {
		ai, bi, ci, di := rank(picked[i])
		aj, bj, cj, dj := rank(picked[j])
		if ai != aj {
			return !ai
		}
		if bi != bj {
			return bi < bj
		}
		if ci != cj {
			return ci < cj
		}
		return di < dj
	})
	return picked
}

// GuardOp narrows a compiled operation to the fields the guard reads.
func GuardOp(op carephc.Operation) guard.Op {
	qualifier := ""
	if op.ScopeQualifier != nil {
		qualifier = *op.ScopeQualifier
	}
	return guard.Op{ID: op.ID, Kind: op.Kind, Capability: op.Capability,
		ScopeQualifier: qualifier, Preconditions: op.Preconditions,
		Irreversibility: op.Irreversibility}
}

// ThreadView is kernel/contracts.ThreadView, field for field and in the
// Python's own JSON order where that is visible.
type ThreadView struct {
	ID           string            `json:"id"`
	Workflow     string            `json:"workflow"`
	Subject      map[string]any    `json:"subject"`
	Flags        []string          `json:"flags"`
	Station      any               `json:"station"`
	Line         []StepStatus      `json:"line"`
	Closes       any               `json:"closes"`
	Actions      []map[string]any  `json:"actions"`
	Proposals    []store.Proposal  `json:"proposals"`
	Audit        []store.AuditRecord `json:"audit"`
	Capabilities []string          `json:"capabilities"`
	Held         []string          `json:"held"`
	Nudge        string            `json:"nudge"`
}

// View is kernel/state.thread_view for one thread. One read pass, no writes.
//
// `actorGiven` and the actor make an action whose precondition names an actor
// ABSENT for the person it excludes. Without one such an action is still
// drawn and the guard refuses the tap with the reason, which is the fail-safe
// rather than the intended shape.
func View(s Reader, ref store.ThreadRef, wf *carephc.Workflow,
	operations map[string]carephc.Operation, atoms map[string]map[string]any,
	caps map[string]bool, vocabularyCaps []string, actorGiven bool, actor string,
	nudge string) (*ThreadView, error) {
	known, err := Flags(s, ref.ID, wf)
	if err != nil {
		return nil, err
	}
	var performers map[string]map[string]bool
	if actorGiven {
		if performers, err = Performers(s, ref.ID); err != nil {
			return nil, err
		}
	}
	proposals, err := s.Proposals(ref.ID, "pending")
	if err != nil {
		return nil, err
	}
	trail, err := s.Audit(ref.ID)
	if err != nil {
		return nil, err
	}
	station := Station(wf, known)
	actions := Actions(wf, operations, known, caps, "", actorGiven, actor,
		actorGiven, performers)
	// The operations go out as the compiled atoms themselves, from the
	// embedded JSON rather than from the Go struct, for the reason
	// cmd/api/main.go serves the manifest that way: an atom field added in
	// the Python reaches the renderer without being retyped here.
	drawn := make([]map[string]any, 0, len(actions))
	for _, op := range actions {
		drawn = append(drawn, atoms[op.ID])
	}
	subject := map[string]any{}
	for k, v := range ref.Subject {
		subject[k] = v
	}
	return &ThreadView{
		ID: ref.ID, Workflow: wf.ID, Subject: subject,
		Flags: guard.SortedKeys(known), Station: nullIfEmpty(station),
		Line: Line(wf, known),
		Closes: nullIfEmpty(LoopCloser(wf, operations, station)),
		Actions: drawn, Proposals: proposals, Audit: trail,
		Capabilities: sortedCopy(vocabularyCaps), Held: guard.SortedKeys(caps),
		Nudge: nudge,
	}, nil
}

func sortedCopy(in []string) []string {
	out := append([]string(nil), in...)
	sort.Strings(out)
	if out == nil {
		out = []string{}
	}
	return out
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

// Nudge is api/main.py's _nudge: one line of wayfinding. The renderer may
// ignore it.
func Nudge(view *ThreadView) string {
	if view.Station == nil {
		return "Line complete."
	}
	station, _ := view.Station.(string)
	for _, op := range view.Actions {
		if at, _ := op["station"].(string); at == station {
			title, _ := op["title"].(string)
			return station + ": " + title
		}
	}
	return "Waiting at " + station + ". Nobody with your capabilities can act here."
}
