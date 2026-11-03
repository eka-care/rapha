// Package store is the Go side of kernel/contracts.py's Store protocol, over
// a SQLite file, with modernc.org/sqlite as the driver.
//
// THE DRIVER IS PURE GO ON PURPOSE. Not mattn/go-sqlite3, which needs cgo.
// The whole deployment argument for Go here is one file copied to a clinic
// PC, and cgo breaks cross-compiling that file. If this driver ever proves
// unworkable the answer is to stop and report, not to reach for cgo
// (docs/superpowers/plans/2026-10-31-go-backend-port.md, "Decisions taken up
// front").
//
// THE PROTOCOL IS ONE METHOD WIDER THAN IT READS
// ----------------------------------------------
// kernel/contracts.py declares ELEVEN methods since 2026-11-01, when
// issue_token joined it and closed the token race. The kernel calls twelve:
// kernel/directory.py calls store.record_directory_id(...), which the
// protocol never declares, and scripts/check_queues.py pins the list of
// off-protocol Store calls in the kernel at exactly that one so a second
// fails the gate. That is contradiction 29, and it is known rather than
// fixed: fixing it is a change to the protocol and to the adapter test that
// pins its names.
//
// issue_token is NOT one of those gaps and is the difference worth noting. It
// was added to the protocol rather than bolted onto an adapter, because what
// it promises is a property every adapter must hold and an optional method
// cannot promise anything.
//
// So RecordDirectoryID is on this interface, named as what it is. An
// interface that declared ten and served eleven would reproduce in Go the
// exact gap the Python is already pinned at.
//
// OpenThread is here for the same reason and is the second gap: it is not on
// the protocol either, api/main.py calls it, and adapters/local/store.py's own
// docstring says so. Both are declared because this interface's rule is that
// it declares every method it serves.
//
// EVERY COLUMN IS TEXT, AND THAT IS COPIED RATHER THAN IMPROVED
// -------------------------------------------------------------
// adapters/local/store.py creates every column TEXT, so a systolic of 140
// reads back as the string "140", which is why kernel/fhir.py has a _number()
// at all. A Go store returning typed numbers would diverge silently from
// every expectation downstream, so Text() below is a transcription of that
// file's _text() and nothing more.
//
// THE SEED AND THE DEMO DAY ARE IN seed.go
// ----------------------------------------
// seed() and roll_seed_forward() were deliberately absent until the slice
// that serves a queue, because a seeded demo day is only observable through a
// view and writing them earlier would have been a second unproven
// implementation. They arrived with the views slice (G4). Open() now moves a
// stale demo day forward exactly as the Python constructor does.
package store

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"github.com/eka-care/care_phc_mcp/pyval"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

// Tables is one table per resource this bundle's operations read or write,
// plus the kernel's own three. Columns are query grammar field names,
// verbatim, and they are adapters/local/store.py's TABLES in the same order.
// adapters/local/tests/test_store.py holds the two against each other, so a
// column added on one side and not the other fails the gate rather than
// drifting until a mapped clinical value lands nowhere.
var Tables = map[string][]string{
	"patient": {"id", "name", "age", "sex", "phone", "village", "category", "abha_number", "directory_id", "directory_synced", "operation", "created_by", "created_date"},
	// `arrival` is how the person reached the queue: at the desk, or by
	// themselves at the printed poster. A fact about THIS visit, so it sits
	// on the encounter beside the number that was issued in the same moment.
	"encounter":              {"id", "patient", "status", "token", "arrival", "operation", "created_by", "created_date"},
	"observation":            {"id", "encounter", "category", "code", "code_system", "code_display", "value", "unit", "unit_system", "status", "operation", "created_by", "created_date"},
	"condition":              {"id", "encounter", "code", "code_system", "code_display", "clinical_status", "clinical_status_system", "verification_status", "verification_status_system", "onset", "operation", "created_by", "created_date"},
	"notes":                  {"id", "encounter", "text", "operation", "created_by", "created_date"},
	"medication_request":     {"id", "encounter", "medication", "medication_system", "medication_display", "dose", "dose_unit", "dose_unit_system", "route", "route_system", "route_display", "frequency", "frequency_system", "frequency_display", "duration", "duration_unit", "duration_unit_system", "intent", "status", "operation", "created_by", "created_date"},
	"medication_dispense":    {"id", "encounter", "medication", "quantity", "status", "operation", "created_by", "created_date"},
	"service_request":        {"id", "encounter", "code", "status", "operation", "created_by", "created_date"},
	"diagnostic_report":      {"id", "encounter", "code", "code_system", "conclusion", "status", "operation", "created_by", "created_date"},
	"specimen":               {"id", "encounter", "code", "status", "operation", "created_by", "created_date"},
	"inventory_item":         {"id", "encounter", "code", "quantity", "status", "operation", "created_by", "created_date"},
	"questionnaire_response": {"id", "encounter", "questionnaire", "payload", "operation", "created_by", "created_date"},
	"token_booking":          {"id", "encounter", "patient", "status", "operation", "created_by", "created_date"},
	// FHIR R4 EpisodeOfCare: the level between a person and a visit, insert
	// only like every other clinical table, so an episode ENDS BY GAINING A
	// SECOND ROW rather than by having its first rewritten. Generic on
	// purpose -- `type` is the bundle's word and no column here is
	// obstetric. adapters/local/store.py TABLES is the Python half.
	"episode_of_care":        {"id", "patient", "type", "status", "anchor_date", "anchor_basis", "outcome", "operation", "created_by", "created_date"},
	"thread_flag":            {"id", "thread", "flag", "created_by", "created_date"},
	"proposal":               {"id", "thread", "operation", "payload", "proposed_by", "surface", "status", "created_at", "flags_raised", "decided_by", "decided_at", "final_payload"},
	"audit":                  {"id", "thread", "operation", "actor", "surface", "payload", "outcome", "at", "proposal"},
}

// ThreadColumn is the adapter's private knowledge: which column ties a row to
// its thread. "encounter" is the thread itself; a patient is reached through
// it, so its entry is empty rather than absent and the lookup below says
// which.
// An empty entry means the row is reached through the thread's PATIENT
// rather than through the thread: asking a visit for "the episodes" means
// this person's, the same way asking it for "the patient" does.
var ThreadColumn = map[string]string{"encounter": "id", "thread_flag": "thread",
	"patient": "", "episode_of_care": ""}

// DefaultThreadColumn is what every clinical resource not named above joins on.
const DefaultThreadColumn = "encounter"

// KernelRecord: the kernel's own two records join and date themselves
// differently from a clinical resource. thread_flag does not, so it stays in
// ThreadColumn above.
var KernelRecord = map[string][2]string{
	"proposal": {"thread", "created_at"},
	"audit":    {"thread", "at"},
}

// SeedActor is what the seed writes as the author of a thread it opened.
const SeedActor = "seed"

var ident = regexp.MustCompile(`^[a-z_][a-z0-9_]*$`)

// ---------------------------------------------------------------------------
// the records the kernel passes across the seam
// ---------------------------------------------------------------------------

// ThreadRef mirrors kernel/contracts.py ThreadRef.
//
// Subject is map[string]any and not map[string]string because the Python's
// threads() builds it from dict(patient_row), which carries None for an
// unfilled column, and the subject goes on the wire: a queue row drawing "no
// ABHA number yet" sees the difference between null and "". Same reason
// SelectNullable exists; see that method.
type ThreadRef struct {
	ID       string         `json:"id"`
	Workflow string         `json:"workflow"`
	Subject  map[string]any `json:"subject"`
	OpenedAt string         `json:"opened_at"`
}

// Proposal mirrors kernel/contracts.py Proposal. Payload and FlagsRaised are
// stored as JSON in TEXT columns, exactly as the Python stores them.
type Proposal struct {
	ID           string         `json:"id"`
	Thread       string         `json:"thread"`
	Operation    string         `json:"operation"`
	Payload      map[string]any `json:"payload"`
	ProposedBy   string         `json:"proposed_by"`
	Surface      string         `json:"surface"`
	Status       string         `json:"status"`
	CreatedAt    string         `json:"created_at"`
	FlagsRaised  []string       `json:"flags_raised"`
	DecidedBy    string         `json:"decided_by"`
	DecidedAt    string         `json:"decided_at"`
	FinalPayload map[string]any `json:"final_payload"`
}

// AuditRecord mirrors kernel/contracts.py AuditRecord.
type AuditRecord struct {
	ID        string         `json:"id"`
	Thread    string         `json:"thread"`
	Operation string         `json:"operation"`
	Actor     string         `json:"actor"`
	Surface   string         `json:"surface"`
	Payload   map[string]any `json:"payload"`
	Outcome   string         `json:"outcome"`
	At        string         `json:"at"`
	Proposal  string         `json:"proposal"`
}

// MarshalJSON writes an AuditRecord as kernel/contracts.AuditRecord's
// asdict() does. The two Optional fields go out as null rather than as the
// empty string: `actor` is None on a line the guard filled with no actor, and
// `proposal` is None on a decision that came from no proposal. An engine
// answering "" where the reference answers null is a difference a renderer
// can see, so the difference does not exist.
func (r AuditRecord) MarshalJSON() ([]byte, error) {
	return json.Marshal(struct {
		ID        string         `json:"id"`
		Thread    string         `json:"thread"`
		Operation string         `json:"operation"`
		Actor     *string        `json:"actor"`
		Surface   string         `json:"surface"`
		Payload   map[string]any `json:"payload"`
		Outcome   string         `json:"outcome"`
		At        string         `json:"at"`
		Proposal  *string        `json:"proposal"`
	}{r.ID, r.Thread, r.Operation, nullable(r.Actor), r.Surface,
		orEmptyObject(r.Payload), r.Outcome, r.At, nullable(r.Proposal)})
}

// MarshalJSON writes a Proposal as kernel/contracts.Proposal's asdict() does:
// three Optional fields as null, and `flags_raised` as an empty list rather
// than null, which is what field(default_factory=list) gives.
func (p Proposal) MarshalJSON() ([]byte, error) {
	flags := p.FlagsRaised
	if flags == nil {
		flags = []string{}
	}
	return json.Marshal(struct {
		ID           string         `json:"id"`
		Thread       string         `json:"thread"`
		Operation    string         `json:"operation"`
		Payload      map[string]any `json:"payload"`
		ProposedBy   *string        `json:"proposed_by"`
		Surface      string         `json:"surface"`
		Status       string         `json:"status"`
		CreatedAt    string         `json:"created_at"`
		FlagsRaised  []string       `json:"flags_raised"`
		DecidedBy    *string        `json:"decided_by"`
		DecidedAt    *string        `json:"decided_at"`
		FinalPayload map[string]any `json:"final_payload"`
	}{p.ID, p.Thread, p.Operation, orEmptyObject(p.Payload),
		nullable(p.ProposedBy), p.Surface, p.Status, p.CreatedAt, flags,
		nullable(p.DecidedBy), nullable(p.DecidedAt), p.FinalPayload})
}

// nullable is the empty string as None, for a field the Python declares
// Optional.
func nullable(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// Cond is one condition in the query grammar: either an equality, the "*"
// present-and-not-empty form, or a range. kernel/contracts.py owns the
// grammar; this is the Go spelling of what adapters/local/store.py._where
// accepts, and nothing wider.
type Cond struct {
	Equals  string // the plain form, already text
	Present bool   // the "*" form
	Gte     string
	Gt      string
	Lte     string
	Lt      string
}

// Query is {field: condition}.
type Query map[string]Cond

// ---------------------------------------------------------------------------
// the interface
// ---------------------------------------------------------------------------

// Store is every method this package serves, and the comment on each of the
// last two says why it is here when the protocol does not declare it.
type Store interface {
	// reads that feed state derivation, views and metrics
	Count(resource string, thread *string, where Query) (int, error)
	Select(resource string, thread *string, where Query, fields []string, limit int) ([]map[string]string, error)
	Threads(workflow, scope string) ([]ThreadRef, error)
	StoredFlags(thread string) (map[string]bool, error)

	// writes, one per resource kind, by name
	Write(resource string, record map[string]any, thread string) (string, error)
	RaiseFlag(thread, flag, actor string) error

	// proposals and audit
	PutProposal(p Proposal) error
	Proposals(thread, status string) ([]Proposal, error)
	AppendAudit(r AuditRecord) error
	Audit(thread string) ([]AuditRecord, error)

	Proposal(id string) (*Proposal, bool, error)

	// The fourteenth. Select without the NULL flattening, for the one row
	// that goes on the wire; see the method.
	SelectNullable(resource string, thread *string, where Query, fields []string, limit int) ([]map[string]any, error)

	// The eleventh. kernel/directory.py calls it; the protocol in
	// kernel/contracts.py never declares it, and scripts/check_queues.py pins
	// the kernel's off-protocol Store calls at exactly this one. Declared
	// because this interface serves it. Contradiction 29.
	RecordDirectoryID(patientID, directoryID, at string, profile map[string]any) (string, error)

	// The twelfth, and the other gap adapters/local/store.py already names in
	// its own docstring: the protocol has no way to say "open a thread". It is
	// api/main.py that calls this one rather than the kernel, which is why
	// check_queues' count of the KERNEL's off-protocol calls stays at one.
	OpenThread(token, actor string) (string, error)

	// IssueToken is the ELEVENTH METHOD ON THE PROTOCOL ITSELF, added
	// 2026-11-01 when the token race was closed. Unlike the two above it is
	// not a gap: kernel/contracts.py declares it.
	//
	// The one method on this interface that must be ATOMIC against every
	// other caller, including callers in other processes against the same
	// file. Two arrivals racing must come back with two different numbers,
	// and a set of them must have no hole: a waiting room is one room, and a
	// number nobody was issued is a number nobody answers to.
	//
	// `floor` is the lowest number that may be handed out and it is the
	// KERNEL's arithmetic, package tokens here and kernel/tokens.py there:
	// one past the highest already issued, skipping tokens that are not on
	// the sequence. The store does not second-guess it. What the store owns
	// is only the atomicity, which is the half no pure package can provide.
	//
	// The contract is exactly: return a number not less than floor, never
	// return the same number twice for one (workflow, scope, day), and do it
	// in one indivisible step. An implementation that reads and then writes
	// has not implemented this method.
	IssueToken(workflow, scope string, floor int) (int, error)
}

// ---------------------------------------------------------------------------
// the SQLite implementation
// ---------------------------------------------------------------------------

// SQLite is a Store over one file. Pass ":memory:" for a test.
type SQLite struct {
	Path string
	db   *sql.DB
}

var _ Store = (*SQLite)(nil)

// Open creates the tables if they are not there and returns the store.
//
// One *sql.DB and not one connection per thread. database/sql owns a pool and
// serialises use of each connection, which is the problem
// adapters/local/store.py solves with thread-local connections because
// python's sqlite3 cannot do that. The pool is capped at one for a file so
// that two writers cannot meet inside SQLite: modernc's driver is safe to use
// concurrently, but WAL plus two writers still returns SQLITE_BUSY, and a
// busy error on a clinical write is not a thing to discover in a clinic.
// sequenceDDL is the facility's day sequence counter, and the one table here
// whose key is not a single `id` column. It is created by hand rather than
// through the Tables loop for exactly that reason: the whole point of it is a
// UNIQUE key on (workflow, scope, day), because that uniqueness is what makes
// issuing a number atomic. A table keyed by a generated row id would let two
// writers both insert and both believe they were first.
//
// It is not a resource. No declaration can name it, no metric can count it,
// and it holds no fact about anybody: four values and a high water mark.
// Byte for byte the schema adapters/local/store.py creates, because the two
// engines open the same file and a column either of them did not expect is a
// clinic's database that one of them cannot read.
const sequenceDDL = "CREATE TABLE IF NOT EXISTS day_sequence (" +
	" workflow TEXT NOT NULL," +
	" scope TEXT NOT NULL," +
	" day TEXT NOT NULL," +
	" last INTEGER NOT NULL," +
	" PRIMARY KEY (workflow, scope, day))"

func Open(path string) (*SQLite, error) {
	dsn := path
	if path == ":memory:" {
		// A plain ":memory:" is private to one connection, and the pool may
		// open more than one, so name it and share the cache. Same reason
		// adapters/local/store.py does.
		dsn = "file:mem?mode=memory&cache=shared"
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	s := &SQLite{Path: path, db: db}
	if path != ":memory:" {
		if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
			return nil, err
		}
	}
	for table, columns := range Tables {
		cols := make([]string, 0, len(columns))
		for _, c := range columns {
			if c == "id" {
				cols = append(cols, c+" TEXT PRIMARY KEY")
			} else {
				cols = append(cols, c+" TEXT")
			}
		}
		stmt := fmt.Sprintf("CREATE TABLE IF NOT EXISTS %s (%s)", table, strings.Join(cols, ", "))
		if _, err := db.Exec(stmt); err != nil {
			return nil, fmt.Errorf("creating %s: %w", table, err)
		}
	}
	if _, err := db.Exec(sequenceDDL); err != nil {
		return nil, fmt.Errorf("creating day_sequence: %w", err)
	}
	// The constructor's own job in adapters/local/store.py, and here for the
	// same reason: every queue view is `scope: today`, so a file seeded
	// yesterday draws an empty workspace this morning. Every process that
	// opens the file gets the roll forward, including the ones this adapter
	// does not own. See RollSeedForward in seed.go.
	if _, err := s.RollSeedForward(); err != nil {
		return nil, err
	}
	return s, nil
}

// DB is the handle, for a check that wants to read the file directly.
func (s *SQLite) DB() *sql.DB { return s.db }

// Close releases the pool.
func (s *SQLite) Close() error { return s.db.Close() }

// Now is the timestamp every row is dated with: ISO 8601 UTC to the second,
// the spelling adapters/local/store.py.now() produces, because everything that
// compares these columns compares strings.
func Now() string {
	return time.Now().UTC().Format("2006-01-02T15:04:05+00:00")
}

// NewID mirrors adapters/local/store.py.new_id: the resource's first four
// letters and eight hex digits.
func NewID(prefix string) string {
	if len(prefix) > 4 {
		prefix = prefix[:4]
	}
	return prefix + "-" + randomHex(8)
}

// Text is adapters/local/store.py._text, transcribed. Everything is TEXT:
// numbers keep their ordering because the columns compared with gte or lt are
// ISO dates, which sort as strings.
//
// Copied rather than improved. A systolic of 140 goes in as "140" and comes
// back as "140", which is why kernel/fhir.py has a _number().
func Text(value any) (string, bool) {
	switch v := value.(type) {
	case nil:
		return "", false // NULL, the way Python's None is
	case string:
		return v, true
	case bool:
		if v {
			return "true", true
		}
		return "false", true
	case int:
		return strconv.Itoa(v), true
	case int64:
		return strconv.FormatInt(v, 10), true
	case float64:
		// Python's str() of a float that is integral keeps a ".0", and of an
		// int keeps none. A JSON number arrives here as float64 whichever it
		// was written as, so an integral value is spelled without the ".0" to
		// match what the Python writes for an integer answer: that is the
		// case every questionnaire integer takes.
		if v == float64(int64(v)) {
			return strconv.FormatInt(int64(v), 10), true
		}
		return strconv.FormatFloat(v, 'g', -1, 64), true
	default:
		b, err := json.Marshal(value)
		if err != nil {
			return fmt.Sprint(value), true
		}
		return string(b), true
	}
}

func table(resource string) (string, error) {
	if _, ok := Tables[resource]; !ok {
		return "", fmt.Errorf("no table for resource %q", resource)
	}
	if !ident.MatchString(resource) {
		return "", fmt.Errorf("bad resource name %q", resource)
	}
	return resource, nil
}

func hasColumn(resource, field string) bool {
	for _, c := range Tables[resource] {
		if c == field {
			return true
		}
	}
	return false
}

// where turns (thread, query grammar where) into a SQL fragment and params.
// A transcription of adapters/local/store.py._where, including that a patient
// is reached through its encounter rather than joined directly.
func (s *SQLite) where(resource string, thread *string, q Query) (string, []any, error) {
	var clauses []string
	var params []any
	if thread != nil {
		column, named := ThreadColumn[resource]
		if !named {
			column = DefaultThreadColumn
		}
		if resource == "patient" {
			clauses = append(clauses, "id IN (SELECT patient FROM encounter WHERE id = ?)")
		} else if column == "" {
			// Reached through the thread's patient. `patient` above is the
			// special case of this where the key column IS `id`; everything
			// else joining this way carries a `patient` column.
			clauses = append(clauses,
				"patient IN (SELECT patient FROM encounter WHERE id = ?)")
		} else {
			clauses = append(clauses, column+" = ?")
		}
		params = append(params, *thread)
	}
	// Sorted so one query is one SQL string between runs, which a Go map
	// iteration would not give.
	fields := make([]string, 0, len(q))
	for f := range q {
		fields = append(fields, f)
	}
	sort.Strings(fields)
	for _, field := range fields {
		if !hasColumn(resource, field) {
			return "", nil, fmt.Errorf("%s has no field %q", resource, field)
		}
		cond := q[field]
		switch {
		case cond.Present:
			clauses = append(clauses, fmt.Sprintf("(%s IS NOT NULL AND %s != '')", field, field))
		case cond.Gte != "" || cond.Gt != "" || cond.Lte != "" || cond.Lt != "":
			for _, pair := range [][2]string{
				{cond.Gte, ">="}, {cond.Lt, "<"}, {cond.Gt, ">"}, {cond.Lte, "<="},
			} {
				if pair[0] != "" {
					clauses = append(clauses, field+" "+pair[1]+" ?")
					params = append(params, pair[0])
				}
			}
		default:
			clauses = append(clauses, field+" = ?")
			params = append(params, cond.Equals)
		}
	}
	if len(clauses) == 0 {
		return "1=1", params, nil
	}
	return strings.Join(clauses, " AND "), params, nil
}

// Count is the Store protocol's count.
func (s *SQLite) Count(resource string, thread *string, q Query) (int, error) {
	name, err := table(resource)
	if err != nil {
		return 0, err
	}
	clause, params, err := s.where(resource, thread, q)
	if err != nil {
		return 0, err
	}
	var n int
	row := s.db.QueryRow(fmt.Sprintf("SELECT COUNT(*) FROM %s WHERE %s", name, clause), params...)
	return n, scanInto(row, &n)
}

// Select is the Store protocol's select. Every value comes back as a string,
// because every column is TEXT.
func (s *SQLite) Select(resource string, thread *string, q Query, fields []string, limit int) ([]map[string]string, error) {
	name, err := table(resource)
	if err != nil {
		return nil, err
	}
	for _, f := range fields {
		if !hasColumn(resource, f) {
			return nil, fmt.Errorf("%s has no field %q", resource, f)
		}
	}
	clause, params, err := s.where(resource, thread, q)
	if err != nil {
		return nil, err
	}
	cols := "*"
	if len(fields) > 0 {
		cols = strings.Join(fields, ", ")
	}
	stmt := fmt.Sprintf("SELECT %s FROM %s WHERE %s ORDER BY created_date, id LIMIT ?", cols, name, clause)
	rows, err := s.db.Query(stmt, append(params, limit)...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanRows(rows)
}

// SelectNullable is Select with the NULLs kept rather than flattened to "".
//
// THE FOURTEENTH METHOD, and the fourth the protocol does not declare. It
// exists for one caller: a thread's `subject` goes out over HTTP, and
// adapters/local/store.py's select() answers None for an unfilled column
// while scanRows here answers "". Those are different facts to a renderer
// drawing "no ABHA number yet", so the lossy read stays for everything
// internal and this is what the wire gets.
func (s *SQLite) SelectNullable(resource string, thread *string, q Query, fields []string, limit int) ([]map[string]any, error) {
	name, err := table(resource)
	if err != nil {
		return nil, err
	}
	for _, f := range fields {
		if !hasColumn(resource, f) {
			return nil, fmt.Errorf("%s has no field %q", resource, f)
		}
	}
	clause, params, err := s.where(resource, thread, q)
	if err != nil {
		return nil, err
	}
	cols := "*"
	if len(fields) > 0 {
		cols = strings.Join(fields, ", ")
	}
	stmt := fmt.Sprintf("SELECT %s FROM %s WHERE %s ORDER BY created_date, id LIMIT ?", cols, name, clause)
	rows, err := s.db.Query(stmt, append(params, limit)...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return scanNullableRows(rows)
}

// Threads is the Store protocol's threads: every encounter in scope, newest
// first, with its subject fields.
func (s *SQLite) Threads(workflow, scope string) ([]ThreadRef, error) {
	stmt := "SELECT * FROM encounter"
	var params []any
	switch scope {
	case "today":
		stmt += " WHERE created_date >= ?"
		params = append(params, StartOf("day"))
	case "open":
		stmt += " WHERE status != 'completed'"
	}
	stmt += " ORDER BY created_date DESC, id"
	rows, err := s.db.Query(stmt, params...)
	if err != nil {
		return nil, err
	}
	encounters, err := scanNullableRows(rows)
	rows.Close()
	if err != nil {
		return nil, err
	}
	out := make([]ThreadRef, 0, len(encounters))
	for _, row := range encounters {
		id, _ := row["id"].(string)
		subject := map[string]any{
			"encounter": id, "token": row["token"], "status": row["status"],
			"arrival": row["arrival"],
		}
		if patient, _ := row["patient"].(string); patient != "" {
			pr, err := s.db.Query("SELECT * FROM patient WHERE id = ?", patient)
			if err != nil {
				return nil, err
			}
			found, err := scanNullableRows(pr)
			pr.Close()
			if err != nil {
				return nil, err
			}
			// One row, as the Python's fetchone() is: `if patient:` there is a
			// single row or nothing, so a second would be ignored either way.
			if len(found) == 1 {
				for k, v := range found[0] {
					// WITHOUT `operation`. It is this adapter's own
					// bookkeeping -- which form opened the row, so a
					// correction can find it -- and not a fact about the
					// person. It reached the context rail as a line reading
					// "Operation: phc.op.patient-register" beside somebody's
					// village, which is our schema printed at a clinician.
					if k == "operation" {
						continue
					}
					subject[k] = v
				}
			}
		}
		opened, _ := row["created_date"].(string)
		out = append(out, ThreadRef{
			ID: id, Workflow: workflow, Subject: subject, OpenedAt: opened,
		})
	}
	return out, nil
}

// StoredFlags is the Store protocol's stored_flags.
func (s *SQLite) StoredFlags(thread string) (map[string]bool, error) {
	rows, err := s.db.Query("SELECT flag FROM thread_flag WHERE thread = ?", thread)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]bool{}
	for rows.Next() {
		var flag sql.NullString
		if err := rows.Scan(&flag); err != nil {
			return nil, err
		}
		out[flag.String] = true
	}
	return out, rows.Err()
}

// Write is the Store protocol's write: one row of `resource`, returning its id.
//
// The fan-out happens above this line, as in the Python: three vitals are
// three calls. What is here is this adapter's own schema, which is the thread
// join and the fact that a second patient row on a thread is an update of the
// first person rather than a second person.
func (s *SQLite) Write(resource string, record map[string]any, thread string) (string, error) {
	row := map[string]any{}
	for k, v := range record {
		row[k] = v
	}
	if resource == "patient" {
		if _, given := row["id"]; !given {
			existing, err := s.Select("patient", &thread, nil, []string{"id"}, 1)
			if err != nil {
				return "", err
			}
			if len(existing) == 0 {
				if did, _ := Text(row["directory_id"]); strings.TrimSpace(did) != "" {
					// The same person, on a second visit. Scoped to a
					// thread=nil lookup on purpose: it is a question about a
					// person across visits, not within one.
					same, err := s.Select("patient", nil,
						Query{"directory_id": {Equals: did}}, []string{"id"}, 1)
					if err != nil {
						return "", err
					}
					existing = same
				}
			}
			if len(existing) > 0 {
				row["id"] = existing[0]["id"]
			}
		}
	}
	written, err := s.put(resource, row, thread)
	if err != nil {
		return "", err
	}
	if resource == "patient" {
		// The adapter owns the join, so it maintains it: a patient registered
		// against an empty thread is attached to it here.
		var patient sql.NullString
		err := s.db.QueryRow("SELECT patient FROM encounter WHERE id = ?", thread).Scan(&patient)
		if err == nil && patient.String == "" {
			if _, err := s.put("encounter", map[string]any{"id": thread, "patient": written}, thread); err != nil {
				return "", err
			}
		}
	}
	return written, nil
}

// put inserts, or updates the named columns when the id already exists.
//
// Authorship and the moment a row was opened are written once, both for the
// reason adapters/local/store.py gives at length: linking an ABHA updates the
// patient row registration created, and re-putting the encounter row to join a
// person to it used to reset opened_at to the moment the person was ATTACHED
// rather than the moment the thread was OPENED.
func (s *SQLite) put(resource string, record map[string]any, thread string) (string, error) {
	name, err := table(resource)
	if err != nil {
		return "", err
	}
	// A column this table does not have is refused, not filtered away.
	// Silently dropping a mapped clinical value is the worst failure this file
	// could have, and a mapping typo is exactly how it would happen.
	var unknown []string
	for k := range record {
		if !hasColumn(name, k) {
			unknown = append(unknown, k)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return "", fmt.Errorf("%s has no column %s", resource, strings.Join(unknown, ", "))
	}

	row := map[string]any{}
	for k, v := range record {
		if text, keep := Text(v); keep {
			row[k] = text
		} else {
			row[k] = nil
		}
	}
	column, named := ThreadColumn[name]
	if !named {
		column = DefaultThreadColumn
	}
	if column != "" && column != "id" {
		if _, set := row[column]; !set {
			row[column] = thread
		}
	} else if name == "encounter" {
		if _, set := row["id"]; !set {
			row["id"] = thread
		}
	} else if column == "" && name != "patient" && hasColumn(name, "patient") {
		// REACHED THROUGH THE THREAD'S PATIENT, so the join is filled from
		// it: an episode belongs to a person and outlives the visit it was
		// opened at. Without this the row lands with a null patient, every
		// read comes back empty, and the pregnancy does not exist on any
		// screen. adapters/local/store._put is the Python half, and the
		// parity check is what caught this engine lacking it.
		if _, set := row["patient"]; !set {
			var owner sql.NullString
			err := s.db.QueryRow(
				"SELECT patient FROM encounter WHERE id = ?", thread).Scan(&owner)
			if err != nil && err != sql.ErrNoRows {
				return "", err
			}
			if owner.Valid && owner.String != "" {
				row["patient"] = owner.String
			}
		}
	}
	if _, set := row["id"]; !set {
		row["id"] = NewID(name)
	}
	if _, set := row["created_date"]; !set {
		row["created_date"] = Now()
	}
	rid, _ := row["id"].(string)

	var exists int
	err = s.db.QueryRow(fmt.Sprintf("SELECT 1 FROM %s WHERE id = ?", name), rid).Scan(&exists)
	if err != nil && err != sql.ErrNoRows {
		return "", err
	}
	if err == nil {
		var sets []string
		var params []any
		for _, key := range Tables[name] { // declaration order, so one row is one statement
			// `operation` joins the write-once pair for the same reason
			// they are there: it is WHICH FORM OPENED this row, and
			// linking an ABHA re-writes the patient row registration
			// created. Letting it move would mean a clerk correcting a
			// misspelt name found nothing to correct.
			if key == "id" || key == "created_by" || key == "created_date" ||
				key == "operation" {
				continue
			}
			if value, set := row[key]; set {
				sets = append(sets, key+" = ?")
				params = append(params, value)
			}
		}
		if len(sets) == 0 {
			return rid, nil
		}
		_, err := s.db.Exec(fmt.Sprintf("UPDATE %s SET %s WHERE id = ?", name, strings.Join(sets, ", ")),
			append(params, rid)...)
		return rid, err
	}
	var keys []string
	var params []any
	for _, key := range Tables[name] {
		if value, set := row[key]; set {
			keys = append(keys, key)
			params = append(params, value)
		}
	}
	_, err = s.db.Exec(fmt.Sprintf("INSERT INTO %s (%s) VALUES (%s)",
		name, strings.Join(keys, ", "), marks(len(keys))), params...)
	return rid, err
}

// OpenThread starts an empty visit and returns its thread id. Off-protocol;
// see the Store interface above.
//
// NO TOKEN IS INVENTED HERE ANY MORE. This used to fall back to the last three
// characters of the generated row id whenever the caller passed none, so an
// arrival that reached the store without a number got one that was on no
// sequence, was issued to nobody, and was not a number at all. A visit with no
// token now has none, visibly, rather than a plausible one nobody ever called
// out. adapters/local/store.py removed the same fallback and says the same
// thing; this engine had kept it.
//
// Issuing a number is IssueToken's, and choosing one is nobody's.
func (s *SQLite) OpenThread(token, actor string) (string, error) {
	thread := NewID("enc")
	return s.put("encounter", map[string]any{
		"id": thread, "status": "in_progress", "token": token, "created_by": actor,
	}, thread)
}

// IssueToken hands out one number, and never hands the same one out twice.
//
// ONE SQL STATEMENT, and that is the whole of the fix. The upsert below is
// indivisible: SQLite takes a write lock for the duration of a single
// statement, so of two callers arriving in the same instant exactly one
// inserts the row and the other is made to take the UPDATE branch and
// increment what the first one wrote. Neither can read a counter, be
// overtaken, and write back a number the other already has, because neither
// reads it at all. There is no SELECT here on purpose.
//
// `floor` is the kernel's arithmetic (package tokens: one past the highest
// number already issued, skipping tokens that are not on the sequence) and
// this method does not second-guess it. MAX(last + 1, excluded.last) is why
// it is passed at all: the counter alone would be wrong the first time a day
// is issued against rows that already carry numbers, which is every day a
// seed has been rolled forward into. The counter supplies the atomicity and
// the floor supplies the starting point, and a number below the floor can
// never come back.
//
// Line for line what adapters/local/store.py issue_token does, against the
// same table and the same key, because the two engines open the same file.
func (s *SQLite) IssueToken(workflow, scope string, floor int) (int, error) {
	day := StartOf("day")
	if len(day) >= 10 {
		day = day[:10]
	}
	var last int
	err := s.db.QueryRow(
		"INSERT INTO day_sequence (workflow, scope, day, last) VALUES (?, ?, ?, ?)"+
			" ON CONFLICT(workflow, scope, day)"+
			" DO UPDATE SET last = MAX(last + 1, excluded.last)"+
			" RETURNING last",
		workflow, scope, day, floor).Scan(&last)
	if err != nil {
		return 0, err
	}
	return last, nil
}

// RaiseFlag is the Store protocol's raise_flag. Idempotent: raising a flag
// twice is one row, not two. The kernel checks the flag is one the workflow
// declares stored; this does not, because the adapter has never read a
// workflow.
func (s *SQLite) RaiseFlag(thread, flag, actor string) error {
	held, err := s.StoredFlags(thread)
	if err != nil {
		return err
	}
	if held[flag] {
		return nil
	}
	_, err = s.db.Exec(
		"INSERT INTO thread_flag (id, thread, flag, created_by, created_date) VALUES (?, ?, ?, ?, ?)",
		NewID("flag"), thread, flag, nullIfEmpty(actor), Now())
	return err
}

// RecordDirectoryID records that the patient directory knows this person, and
// when. Off-protocol; see the Store interface above.
//
// Deliberately narrow, as in the Python: it writes the identifier, the moment
// we agreed, and optionally the handful of profile columns a refresh may
// rewrite, on a row that must already exist. It cannot create a patient, it
// cannot touch an encounter and it raises no flag, so it is not a path to a
// clinical write and the guard stays the only one.
func (s *SQLite) RecordDirectoryID(patientID, directoryID, at string, profile map[string]any) (string, error) {
	row := map[string]any{"directory_id": directoryID, "directory_synced": at}
	for key, value := range profile {
		if !hasColumn("patient", key) {
			return "", fmt.Errorf("patient has no column %q", key)
		}
		switch key {
		case "id", "directory_id", "created_by", "created_date":
			return "", fmt.Errorf("%q is not a profile column a refresh may rewrite", key)
		}
		if text, keep := Text(value); keep && text != "" {
			row[key] = text
		}
	}
	var found int
	err := s.db.QueryRow("SELECT 1 FROM patient WHERE id = ?", patientID).Scan(&found)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("no patient %q to record a directory id against", patientID)
	}
	if err != nil {
		return "", err
	}
	var sets []string
	var params []any
	for _, key := range Tables["patient"] {
		if value, set := row[key]; set {
			sets = append(sets, key+" = ?")
			params = append(params, value)
		}
	}
	_, err = s.db.Exec("UPDATE patient SET "+strings.Join(sets, ", ")+" WHERE id = ?",
		append(params, patientID)...)
	return patientID, err
}

// PutProposal is the Store protocol's put_proposal: insert or replace by id.
func (s *SQLite) PutProposal(p Proposal) error {
	payload, err := json.Marshal(orEmptyObject(p.Payload))
	if err != nil {
		return err
	}
	flags, err := json.Marshal(orEmptyList(p.FlagsRaised))
	if err != nil {
		return err
	}
	var final any
	if p.FinalPayload != nil {
		b, err := json.Marshal(p.FinalPayload)
		if err != nil {
			return err
		}
		final = string(b)
	}
	_, err = s.db.Exec(
		"INSERT OR REPLACE INTO proposal (id, thread, operation, payload, proposed_by,"+
			" surface, status, created_at, flags_raised, decided_by, decided_at,"+
			" final_payload) VALUES ("+marks(12)+")",
		p.ID, p.Thread, p.Operation, string(payload), nullIfEmpty(p.ProposedBy),
		p.Surface, p.Status, p.CreatedAt, string(flags), nullIfEmpty(p.DecidedBy),
		nullIfEmpty(p.DecidedAt), final)
	return err
}

// Proposals is the Store protocol's proposals.
//
// The tiebreak is rowid and not id, for the reason the Python's audit()
// docstring gives: created_at is ISO 8601 to the second, so two proposals on
// one thread inside the same second tie, and id is random hex.
// Proposal is one proposal by id, and whether it was found. api/main.py's
// proposal_or_404 calls it, and confirm's first refusal is built on it: an id
// propose never issued is a 404, not a write.
//
// THE THIRTEENTH METHOD, and the third one the protocol does not declare.
// kernel/contracts.py's Store declares ten and this is not among them, yet
// adapters/local/store.py serves it and api/main.py calls it. Same family as
// contradiction 29 and the same treatment: declared here, named as what it
// is, because this interface's rule is that it declares every method it
// serves. scripts/check_queues.py pins the KERNEL's off-protocol calls at one
// and stays right, because this caller is the service rather than the kernel.
func (s *SQLite) Proposal(id string) (*Proposal, bool, error) {
	found, err := s.proposalsWhere("id = ?", []any{id}, "")
	if err != nil || len(found) == 0 {
		return nil, false, err
	}
	return &found[0], true, nil
}

func (s *SQLite) Proposals(thread, status string) ([]Proposal, error) {
	clause := "thread = ?"
	params := []any{thread}
	if status != "" {
		clause += " AND status = ?"
		params = append(params, status)
	}
	return s.proposalsWhere(clause, params, " ORDER BY created_at, rowid")
}

func (s *SQLite) proposalsWhere(clause string, params []any, order string) ([]Proposal, error) {
	rows, err := s.db.Query("SELECT * FROM proposal WHERE "+clause+order, params...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	found, err := scanRows(rows)
	if err != nil {
		return nil, err
	}
	out := make([]Proposal, 0, len(found))
	for _, r := range found {
		p := Proposal{
			ID: r["id"], Thread: r["thread"], Operation: r["operation"],
			ProposedBy: r["proposed_by"], Surface: r["surface"], Status: r["status"],
			CreatedAt: r["created_at"], DecidedBy: r["decided_by"],
			DecidedAt: r["decided_at"],
		}
		// pyval.Decode and not json.Unmarshal: a payload read back out
		// of the file is a clinical answer, and a decimal one must keep the
		// spelling the Python gives it. encoding/json's default narrows every
		// number to float64, so 37.0 came back as 37 and the renderer
		// prefilled a form with a value the clinician had not typed. See
		// package pyval's own note on why numbers arrive as json.Number.
		if err := pyval.Decode([]byte(orDefault(r["payload"], "{}")), &p.Payload); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(orDefault(r["flags_raised"], "[]")), &p.FlagsRaised); err != nil {
			return nil, err
		}
		if r["final_payload"] != "" {
			if err := pyval.Decode([]byte(r["final_payload"]), &p.FinalPayload); err != nil {
				return nil, err
			}
		}
		out = append(out, p)
	}
	return out, nil
}

// AppendAudit is the Store protocol's append_audit.
func (s *SQLite) AppendAudit(r AuditRecord) error {
	payload, err := json.Marshal(orEmptyObject(r.Payload))
	if err != nil {
		return err
	}
	_, err = s.db.Exec(
		"INSERT INTO audit (id, thread, operation, actor, surface, payload, outcome,"+
			" at, proposal) VALUES ("+marks(9)+")",
		r.ID, r.Thread, r.Operation, nullIfEmpty(r.Actor), r.Surface,
		string(payload), r.Outcome, r.At, nullIfEmpty(r.Proposal))
	return err
}

// Audit is the Store protocol's audit: oldest first, as ThreadView promises,
// tiebroken on rowid. The Python's own docstring says why that is not
// cosmetic: an audit panel showing a refusal after the write it refused reads
// as a different sequence of events from the one that happened.
func (s *SQLite) Audit(thread string) ([]AuditRecord, error) {
	rows, err := s.db.Query("SELECT * FROM audit WHERE thread = ? ORDER BY at, rowid", thread)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	found, err := scanRows(rows)
	if err != nil {
		return nil, err
	}
	out := make([]AuditRecord, 0, len(found))
	for _, r := range found {
		a := AuditRecord{
			ID: r["id"], Thread: r["thread"], Operation: r["operation"],
			Actor: r["actor"], Surface: r["surface"], Outcome: r["outcome"],
			At: r["at"], Proposal: r["proposal"],
		}
		// pyval.Decode, for the reason proposals above give: an audit
		// row's payload is the answer as it was judged, and a decimal keeps
		// its spelling.
		if err := pyval.Decode([]byte(orDefault(r["payload"], "{}")), &a.Payload); err != nil {
			return nil, err
		}
		out = append(out, a)
	}
	return out, nil
}

// StartOf is adapters/local/store.py._start_of: the first instant of a metric
// window, as an ISO string to compare with. A week and a month are rolling,
// not calendar.
func StartOf(window string) string {
	day := time.Now().UTC().Truncate(24 * time.Hour)
	if window == "all" {
		return "0000-01-01T00:00:00+00:00"
	}
	back := map[string]int{"day": 0, "week": 6, "month": 29}[window]
	return day.AddDate(0, 0, -back).Format("2006-01-02T15:04:05+00:00")
}
