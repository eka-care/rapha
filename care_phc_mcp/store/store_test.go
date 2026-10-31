package store

import (
	"path/filepath"
	"reflect"
	"sort"
	"testing"
)

// What is proved here is the storage BEHAVIOUR that downstream code already
// depends on, not that SQLite works. Each of these was chosen because a Go
// store that got it wrong would diverge from the Python silently, which is
// the one failure mode the port cannot afford.

func open(t *testing.T) *SQLite {
	t.Helper()
	s, err := Open(filepath.Join(t.TempDir(), "test.sqlite3"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// The reason kernel/fhir.py has a _number() at all. A systolic of 140 is
// written as a number and read back as the string "140", and a Go store that
// returned a typed 140 would make every downstream expectation wrong in a way
// no check would catch until a document was already published.
func TestANumberReadsBackAsAString(t *testing.T) {
	s := open(t)
	thread, err := s.OpenThread("T-1", "nurse")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.Write("observation", map[string]any{
		"category": "vital-signs", "code": "8480-6", "code_system": "http://loinc.org",
		"value": 140, "unit": "mm[Hg]", "status": "final", "created_by": "nurse",
	}, thread); err != nil {
		t.Fatal(err)
	}
	rows, err := s.Select("observation", &thread, nil, []string{"value", "code"}, 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(rows) != 1 {
		t.Fatalf("expected one observation, got %d", len(rows))
	}
	if rows[0]["value"] != "140" {
		t.Fatalf("value is %q, want the string \"140\"", rows[0]["value"])
	}
	// A decimal keeps its point, and an integral float does not grow one: a
	// questionnaire integer arrives as a JSON number either way.
	for value, want := range map[any]string{36.8: "36.8", 98.0: "98", 61: "61", true: "true"} {
		if got, _ := Text(value); got != want {
			t.Errorf("Text(%v) = %q, want %q", value, got, want)
		}
	}
}

// A column this table does not have is refused, not filtered away. Silently
// dropping a mapped clinical value is the worst failure this file could have,
// and a mapping typo is exactly how it would happen.
func TestAnUnknownColumnIsRefusedRatherThanDropped(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-2", "nurse")
	_, err := s.Write("observation", map[string]any{"systolic": 140}, thread)
	if err == nil {
		t.Fatal("writing a column the table does not have was accepted")
	}
	if n, _ := s.Count("observation", &thread, nil); n != 0 {
		t.Fatalf("a refused write left %d rows", n)
	}
}

// Linking an ABHA updates the patient row registration created, and the person
// linking is not the person who registered. Both created_by and created_date
// are written once for that reason: the Python's own comment says resetting
// created_date is what made a seeded thread's declared age vanish.
func TestAuthorshipAndTheMomentARowWasOpenedAreWrittenOnce(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-3", "frontdesk")
	id, err := s.Write("patient", map[string]any{
		"name": "Asha", "age": 44, "created_by": "user:frontdesk",
		"created_date": "2026-01-01T09:00:00+00:00",
	}, thread)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := s.Write("patient", map[string]any{
		"id": id, "abha_number": "12-3456-7890-1234", "created_by": "user:nurse",
		"created_date": Now(),
	}, thread); err != nil {
		t.Fatal(err)
	}
	rows, _ := s.Select("patient", &thread, nil, nil, 10)
	if len(rows) != 1 {
		t.Fatalf("linking an ABHA made %d patient rows, want 1", len(rows))
	}
	if rows[0]["created_by"] != "user:frontdesk" {
		t.Errorf("created_by is %q: the registrar was overwritten", rows[0]["created_by"])
	}
	if rows[0]["created_date"] != "2026-01-01T09:00:00+00:00" {
		t.Errorf("created_date is %q: the moment the thread opened was reset", rows[0]["created_date"])
	}
	if rows[0]["abha_number"] != "12-3456-7890-1234" {
		t.Errorf("the ABHA number did not land: %q", rows[0]["abha_number"])
	}
}

// A patient registered against an empty thread is attached to it. The adapter
// owns the join, so it maintains it.
func TestRegisteringAPatientJoinsItToTheOpenThread(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-4", "frontdesk")
	id, _ := s.Write("patient", map[string]any{"name": "Ravi"}, thread)
	rows, _ := s.Select("encounter", &thread, nil, []string{"patient"}, 1)
	if len(rows) != 1 || rows[0]["patient"] != id {
		t.Fatalf("the encounter was not joined to the patient: %v", rows)
	}
}

// Raising a flag twice is one row, not two.
func TestRaisingAFlagTwiceIsOneRow(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-5", "nurse")
	for i := 0; i < 3; i++ {
		if err := s.RaiseFlag(thread, "registered", "user:nurse"); err != nil {
			t.Fatal(err)
		}
	}
	flags, err := s.StoredFlags(thread)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(flags, map[string]bool{"registered": true}) {
		t.Fatalf("flags are %v", flags)
	}
	if n, _ := s.Count("thread_flag", &thread, nil); n != 1 {
		t.Fatalf("three raises wrote %d rows", n)
	}
}

// The eleventh method. It writes an identifier and a moment on a row that must
// already exist, it cannot create a patient, and it refuses a profile column a
// refresh may not rewrite.
func TestRecordDirectoryIDIsNarrow(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-6", "frontdesk")
	if _, err := s.RecordDirectoryID("no-such-patient", "oid-1", Now(), nil); err == nil {
		t.Fatal("recorded a directory id against a patient that does not exist")
	}
	id, _ := s.Write("patient", map[string]any{"name": "Meena", "created_by": "user:frontdesk"}, thread)
	if _, err := s.RecordDirectoryID(id, "oid-1", "2026-03-04T05:06:07+00:00",
		map[string]any{"village": "Kolar"}); err != nil {
		t.Fatal(err)
	}
	rows, _ := s.Select("patient", &thread, nil, nil, 1)
	if rows[0]["directory_id"] != "oid-1" || rows[0]["directory_synced"] != "2026-03-04T05:06:07+00:00" {
		t.Fatalf("the receipt did not land: %v", rows[0])
	}
	if rows[0]["village"] != "Kolar" {
		t.Fatalf("the profile column did not land: %v", rows[0])
	}
	for _, forbidden := range []string{"id", "directory_id", "created_by", "created_date"} {
		if _, err := s.RecordDirectoryID(id, "oid-1", Now(),
			map[string]any{forbidden: "x"}); err == nil {
			t.Errorf("a refresh was allowed to rewrite %q", forbidden)
		}
	}
	if _, err := s.RecordDirectoryID(id, "oid-1", Now(),
		map[string]any{"systolic": "140"}); err == nil {
		t.Error("a column the patient table does not have was accepted")
	}
}

// The same person on a second visit is one patient row, found by the
// directory's identifier. Without one, "the same person" is a question this
// adapter cannot answer and a returning patient has no history.
func TestTheDirectoryIdentifierMakesAReturningPatientOneRow(t *testing.T) {
	s := open(t)
	first, _ := s.OpenThread("T-7", "frontdesk")
	a, _ := s.Write("patient", map[string]any{"name": "Sita", "directory_id": "oid-9"}, first)
	second, _ := s.OpenThread("T-8", "frontdesk")
	b, _ := s.Write("patient", map[string]any{"name": "Sita", "directory_id": "oid-9"}, second)
	if a != b {
		t.Fatalf("two visits made two patient rows: %s and %s", a, b)
	}
	if n, _ := s.Count("patient", nil, nil); n != 1 {
		t.Fatalf("%d patient rows, want 1", n)
	}
}

// Oldest first, tiebroken on rowid. ISO timestamps are to the second, so two
// decisions inside one second tie on `at`, and the id is random hex: an audit
// panel showing a refusal after the write it refused reads as a different
// sequence of events from the one that happened.
func TestTheAuditTrailIsInsertionOrderWithinOneSecond(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-9", "nurse")
	at := "2026-10-31T10:00:00+00:00"
	for _, outcome := range []string{"denied: first", "allowed", "proposed"} {
		if err := s.AppendAudit(AuditRecord{
			ID: NewID("aud"), Thread: thread, Operation: "phc.op.vitals-record",
			Surface: "RENDERED", Outcome: outcome, At: at,
			Payload: map[string]any{"systolic": 140},
		}); err != nil {
			t.Fatal(err)
		}
	}
	trail, err := s.Audit(thread)
	if err != nil {
		t.Fatal(err)
	}
	var order []string
	for _, r := range trail {
		order = append(order, r.Outcome)
	}
	if !reflect.DeepEqual(order, []string{"denied: first", "allowed", "proposed"}) {
		t.Fatalf("the trail reordered itself: %v", order)
	}
	if trail[0].Payload["systolic"] != float64(140) {
		t.Fatalf("the payload did not round-trip: %v", trail[0].Payload)
	}
}

// A proposal is stored by id and replaced by id, so a double tap or a retry is
// one row. Payload and flags round-trip through their TEXT columns.
func TestAProposalIsReplacedByIDAndRoundTrips(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-10", "nurse")
	p := Proposal{
		ID: "prop-1", Thread: thread, Operation: "phc.op.vitals-record",
		Payload: map[string]any{"systolic": 140}, ProposedBy: "agent:test",
		Surface: "MCP", Status: "pending", CreatedAt: "2026-10-31T10:00:00+00:00",
		FlagsRaised: []string{"vitals.flagged"},
	}
	if err := s.PutProposal(p); err != nil {
		t.Fatal(err)
	}
	p.Status = "confirmed"
	p.FinalPayload = map[string]any{"systolic": 138}
	if err := s.PutProposal(p); err != nil {
		t.Fatal(err)
	}
	found, err := s.Proposals(thread, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(found) != 1 {
		t.Fatalf("%d proposals, want 1", len(found))
	}
	if found[0].Status != "confirmed" || found[0].FinalPayload["systolic"] != float64(138) {
		t.Fatalf("the replacement did not land: %+v", found[0])
	}
	if !reflect.DeepEqual(found[0].FlagsRaised, []string{"vitals.flagged"}) {
		t.Fatalf("flags did not round-trip: %v", found[0].FlagsRaised)
	}
	pending, _ := s.Proposals(thread, "pending")
	if len(pending) != 0 {
		t.Fatalf("a confirmed proposal still answers a pending query: %v", pending)
	}
}

// The query grammar, including the "*" form, which means present AND not
// empty. Written out because an empty-string column is how a patient with no
// ABHA number is stored, and `abha_number: "*"` is the metric that counts
// coverage.
func TestThePresentFormMeansNotNullAndNotEmpty(t *testing.T) {
	s := open(t)
	thread, _ := s.OpenThread("T-11", "frontdesk")
	id, _ := s.Write("patient", map[string]any{"name": "Nobody"}, thread)
	if n, _ := s.Count("patient", nil, Query{"abha_number": {Present: true}}); n != 0 {
		t.Fatalf("a patient with no ABHA number counted as having one")
	}
	if _, err := s.Write("patient", map[string]any{"id": id, "abha_number": ""}, thread); err != nil {
		t.Fatal(err)
	}
	if n, _ := s.Count("patient", nil, Query{"abha_number": {Present: true}}); n != 0 {
		t.Fatalf("an empty ABHA number counted as present")
	}
	if _, err := s.Write("patient", map[string]any{"id": id, "abha_number": "12-3456-7890-1234"}, thread); err != nil {
		t.Fatal(err)
	}
	if n, _ := s.Count("patient", nil, Query{"abha_number": {Present: true}}); n != 1 {
		t.Fatalf("a recorded ABHA number did not count")
	}
}

// A field the resource does not have is refused on a read too, not ignored: a
// declaration whose `where` names a column that moved must fail loudly rather
// than quietly matching every row.
func TestAQueryOnAFieldThatDoesNotExistIsRefused(t *testing.T) {
	s := open(t)
	if _, err := s.Count("observation", nil, Query{"systolic": {Equals: "140"}}); err == nil {
		t.Fatal("a query on a column the table does not have was accepted")
	}
	if _, err := s.Select("observation", nil, nil, []string{"systolic"}, 1); err == nil {
		t.Fatal("selecting a column the table does not have was accepted")
	}
	if _, err := s.Count("nonsense", nil, nil); err == nil {
		t.Fatal("a resource with no table was accepted")
	}
}

// Every method on the interface is implemented, and the interface declares the
// eleventh and twelfth the Python's protocol does not. The assertion is on the
// interface's own method set so a method added to the interface and not the
// struct does not compile rather than failing here, and the names are listed
// so a method SERVED and not DECLARED is visible.
func TestTheInterfaceDeclaresEveryMethodItServes(t *testing.T) {
	declared := reflect.TypeOf((*Store)(nil)).Elem()
	var names []string
	for i := 0; i < declared.NumMethod(); i++ {
		names = append(names, declared.Method(i).Name)
	}
	sort.Strings(names)
	want := []string{
		"AppendAudit", "Audit", "Count", "OpenThread", "Proposals",
		"PutProposal", "RaiseFlag", "RecordDirectoryID", "Select",
		"StoredFlags", "Threads", "Write",
	}
	if !reflect.DeepEqual(names, want) {
		t.Fatalf("the interface declares %v, want %v", names, want)
	}
	// Ten of these are kernel/contracts.py's Store protocol. The two that are
	// not are named in the interface's own comments and in the port plan:
	// RecordDirectoryID (contradiction 29, called by kernel/directory.py) and
	// OpenThread (called by api/main.py).
	if len(names) != 12 {
		t.Fatalf("%d methods: the protocol is ten and this serves two more", len(names))
	}
}
