// The two write-path properties that are BELOW the socket, so neither the
// differential check nor any check driving a port can see them.
//
// Found by mutation, which is why they are here. Moving the audit row from
// before the write to after it changed nothing either engine answered: the
// row is on the trail either way by the time anybody can ask, so eleven
// comparisons and nine properties in scripts/check_go_parity.py all stayed
// green. The order is only observable from inside, and it matters for the one
// case nobody can arrange over HTTP, which is the process stopping between
// the two.
//
// The same for a record whose coded answer is absent: the validator refuses
// that payload at guard step 1, so the refusal in kernel/mapping is a SECOND
// line and the socket cannot reach it. It exists because a coded column that
// lands null is a clinical number with nothing saying what it measured, and
// the Python's own comment says it was found by mutation there too.
package proposals

import (
	"errors"
	"path/filepath"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/store"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// recorder is a Store that remembers the order it was called in, and can be
// told to fail the write.
type recorder struct {
	*store.SQLite
	calls     []string
	writeFail bool
}

func (r *recorder) Write(resource string, record map[string]any, thread string) (string, error) {
	r.calls = append(r.calls, "write")
	if r.writeFail {
		return "", errors.New("the store refused this row")
	}
	return r.SQLite.Write(resource, record, thread)
}

func (r *recorder) AppendAudit(record store.AuditRecord) error {
	r.calls = append(r.calls, "audit")
	return r.SQLite.AppendAudit(record)
}

func (r *recorder) RaiseFlag(thread, flag, actor string) error {
	r.calls = append(r.calls, "flag")
	return r.SQLite.RaiseFlag(thread, flag, actor)
}

// root is the repository, two directories up from this package.
func root() string { return filepath.Join("..", "..") }

func loaded(t *testing.T) (*Bundle, *recorder, string) {
	t.Helper()
	cat, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := cat.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	schemas, err := questionnaire.Load(filepath.Join(root(), "questionnaires"))
	if err != nil {
		t.Fatal(err)
	}
	terms, err := terminology.Load(filepath.Join(root(), "terminology"))
	if err != nil {
		t.Fatal(err)
	}
	rows, err := store.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { rows.Close() })
	s := &recorder{SQLite: rows}
	thread, err := rows.OpenThread("", "user:test")
	if err != nil {
		t.Fatal(err)
	}
	ops := cat.BundleOperations()
	b := &Bundle{Catalogue: cat, Operations: ops, Workflow: cat.Workflow,
		Schemas: schemas, Terms: terms, Withheld: map[string]string{}}
	return b, s, thread
}

func caps(names ...string) map[string]bool {
	out := map[string]bool{}
	for _, n := range names {
		out[n] = true
	}
	return out
}

var registration = map[string]any{
	"name": "A Patient", "age": 30, "sex": "female", "phone": "9000000000",
	"village": "Somewhere",
}

// THE AUDIT ROW IS WRITTEN BEFORE EXECUTE.
//
// Two halves, because either one alone passes a mutation that moves the call:
// the order of the calls, and that the row survives a write that failed.
func TestTheAuditRowIsOnTheTrailBeforeAnythingIsWritten(t *testing.T) {
	b, s, thread := loaded(t)
	op := b.Operations["phc.op.patient-register"]

	d, err := b.Commit(s, op, thread, registration, caps(op.Capability),
		caps(), "user:clerk", false, "")
	if err != nil {
		t.Fatal(err)
	}
	if !d.Allowed {
		t.Fatalf("the registration was refused: %s", d.Reason)
	}
	audit, write := -1, -1
	for i, call := range s.calls {
		if call == "audit" && audit < 0 {
			audit = i
		}
		if call == "write" && write < 0 {
			write = i
		}
	}
	if audit < 0 || write < 0 {
		t.Fatalf("expected an audit and a write, got %v", s.calls)
	}
	if audit > write {
		t.Fatalf("the write came before the audit row: %v", s.calls)
	}

	// And the half that says why the order is the property rather than a
	// style: a write that fails leaves the attempt on the trail. With the
	// audit row written afterwards this is an unrecorded attempt.
	b2, s2, thread2 := loaded(t)
	s2.writeFail = true
	op2 := b2.Operations["phc.op.patient-register"]
	if _, err := b2.Commit(s2, op2, thread2, registration, caps(op2.Capability),
		caps(), "user:clerk", false, ""); err == nil {
		t.Fatal("a store that refused the row reported success")
	}
	trail, err := s2.Audit(thread2)
	if err != nil {
		t.Fatal(err)
	}
	if len(trail) != 1 {
		t.Fatalf("a write that failed left %d audit rows", len(trail))
	}
	if trail[0].Operation != op2.ID || trail[0].Outcome != "allowed" {
		t.Fatalf("the trail says %q / %q", trail[0].Operation, trail[0].Outcome)
	}
	rows, err := s2.Count("patient", &thread2, nil)
	if err != nil {
		t.Fatal(err)
	}
	if rows != 0 {
		t.Fatalf("%d patient rows after a refused write", rows)
	}
}

// A REFUSAL IS AUDITED AND WRITES NOTHING, at the level the guard decides it
// rather than at the level a socket reports it.
func TestARefusalIsAuditedAndTouchesNothing(t *testing.T) {
	b, s, thread := loaded(t)
	op := b.Operations["phc.op.vitals-record"]
	// No capability, and the precondition does not hold either.
	d, err := b.Commit(s, op, thread, map[string]any{}, caps(), caps(),
		"user:clerk", false, "")
	if err != nil {
		t.Fatal(err)
	}
	if d.Allowed {
		t.Fatal("a caller with no capability was allowed")
	}
	for _, call := range s.calls {
		if call != "audit" {
			t.Fatalf("a refusal called %q: %v", call, s.calls)
		}
	}
	trail, err := s.Audit(thread)
	if err != nil {
		t.Fatal(err)
	}
	if len(trail) != 1 {
		t.Fatalf("a refusal left %d audit rows", len(trail))
	}
}

// ONE PROPOSAL WRITES ONE ROW. Counted at the store rather than inferred from
// a flag, which is all a panel can show.
func TestOneProposalWritesOneRow(t *testing.T) {
	b, s, thread := loaded(t)
	register := b.Operations["phc.op.patient-register"]
	if d, err := b.Commit(s, register, thread, registration,
		caps(register.Capability), caps(), "user:clerk", false, ""); err != nil || !d.Allowed {
		t.Fatalf("registration: %v %v", d.Reason, err)
	}
	op := b.Operations["phc.op.vitals-record"]
	payload := map[string]any{"systolic": 120, "diastolic": 80, "pulse": 72}
	_, proposal, err := b.Propose(s, op, thread, payload, caps(op.Capability),
		caps(), "user:nurse", "mcp", "")
	if err != nil || proposal == nil {
		t.Fatalf("propose: %v %v", err, proposal)
	}
	before, err := s.Count("observation", &thread, nil)
	if err != nil {
		t.Fatal(err)
	}
	if before != 0 {
		t.Fatalf("a pending proposal wrote %d rows", before)
	}
	d, decided, err := b.Confirm(s, *proposal, caps(op.Capability), caps(),
		"user:nurse", nil, false, false, "")
	if err != nil || !d.Allowed {
		t.Fatalf("confirm: %v %v", d.Reason, err)
	}
	after, err := s.Count("observation", &thread, nil)
	if err != nil {
		t.Fatal(err)
	}
	if after != 3 {
		t.Fatalf("three answered vitals became %d rows", after)
	}
	// And a replay writes none, because the proposal is no longer pending.
	d, _, err = b.Confirm(s, decided, caps(op.Capability), caps(),
		"user:nurse", nil, false, false, "")
	if err != nil {
		t.Fatal(err)
	}
	if d.Allowed {
		t.Fatal("a confirmed proposal was confirmed again")
	}
	replayed, err := s.Count("observation", &thread, nil)
	if err != nil {
		t.Fatal(err)
	}
	if replayed != after {
		t.Fatalf("a replayed confirm wrote %d more rows", replayed-after)
	}
}
