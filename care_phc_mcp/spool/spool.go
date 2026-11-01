// Package spool is queues.Spool over a SQLite file, and a directory of
// recordings: adapters/local/spool.py.
//
// Its own package and its own database, beside the store adapter rather than
// inside it. Three reasons, in increasing order of how much they matter:
//
//   - A recording is a blob and the store's write takes a mapping.
//   - An outbox row is not clinical state, so it would need a CARE resource
//     name for a thing no CARE resource corresponds to.
//   - An outbox must survive the system of record being unreachable, which is
//     the whole point of having one. Keeping it inside somebody else's record
//     makes it empty exactly when it is needed.
//
// THE ONE SUBTLE METHOD IS Claim, AND THE SUBTLETY IS DURABILITY RATHER THAN
// LOCKING. `UPDATE ... WHERE state = 'ready'` is a single statement and
// database/sql runs it outside a transaction, so the move from ready to sending
// is on disk before the method returns. That is what makes "a crash between
// taking an item and sending it loses nothing" true: the row is `sending` and
// nothing can mistake it for untried work. With WAL and the default
// synchronous=NORMAL a committed transaction survives a process crash, which is
// the failure this guards against; it is a power cut that needs
// synchronous=FULL, and that is a deployment's decision about its own hardware
// rather than this file's.
//
// RowsAffected on that UPDATE is also the compare-and-set: two pumps racing for
// one item both run the statement, and exactly one of them changes a row. The
// loser is told false and moves on.
//
// THE DRIVER IS PURE GO, for the reason the store's is: the whole deployment
// argument is one file copied to a clinic PC, and cgo breaks cross-compiling
// that file.
package spool

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/eka-care/care_phc_mcp/queues"

	_ "modernc.org/sqlite"
)

// Table is the one table. `key` and `state` are not SQL keywords in SQLite but
// `key` reads badly unquoted, and every identifier here is quoted for the same
// reason the store adapter validates its own: a column name that reaches SQL
// unchecked is one edit away from being a caller's string.
const Table = "outbox"

// SQLite is queues.Spool over a file. ":memory:" for a test.
type SQLite struct {
	Path string
	db   *sql.DB
}

// Open creates the table and the one index if they are not there.
func Open(path string) (*SQLite, error) {
	dsn := path
	if path == ":memory:" {
		// A plain ":memory:" database is private to one connection, so a
		// second connection would open an empty one and a race check would
		// pass for the wrong reason. Same trick, and same reason, as the store
		// adapter and adapters/local/spool.py.
		dsn = "file:spool-" + randomName() + "?mode=memory&cache=shared"
	}
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	if path != ":memory:" {
		if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
			return nil, err
		}
	}
	cols := make([]string, 0, len(queues.Columns))
	for _, c := range queues.Columns {
		kind := "TEXT"
		if isInt(c) {
			kind = "INTEGER"
		}
		if c == "id" {
			kind += " PRIMARY KEY"
		}
		cols = append(cols, fmt.Sprintf("%q %s", c, kind))
	}
	if _, err := db.Exec(fmt.Sprintf(
		"CREATE TABLE IF NOT EXISTS %q (%s)", Table, strings.Join(cols, ", "))); err != nil {
		return nil, err
	}
	// Every read is by state, and a clinic's outbox after a bad week is the one
	// table here that grows without being cleared.
	if _, err := db.Exec(fmt.Sprintf(
		"CREATE INDEX IF NOT EXISTS outbox_state ON %q (state, created_at)",
		Table)); err != nil {
		return nil, err
	}
	return &SQLite{Path: path, db: db}, nil
}

// Close releases the handle. A test that reopens the same file to prove
// durability needs this.
func (s *SQLite) Close() error { return s.db.Close() }

// DB is the handle, for a check that wants to read the file directly.
func (s *SQLite) DB() *sql.DB { return s.db }

func isInt(column string) bool {
	for _, one := range queues.Ints {
		if one == column {
			return true
		}
	}
	return false
}

// ----------------------------------------------------------------- reads

// Get is the row, or false when there is none.
func (s *SQLite) Get(id string) (queues.Item, bool, error) {
	rows, err := s.db.Query(fmt.Sprintf(
		"SELECT %s FROM %q WHERE id = ?", selectList(), Table), id)
	if err != nil {
		return queues.Item{}, false, err
	}
	defer rows.Close()
	if !rows.Next() {
		return queues.Item{}, false, rows.Err()
	}
	item, err := scan(rows)
	if err != nil {
		return queues.Item{}, false, err
	}
	return item, true, nil
}

// Items is the rows in a state and of a kind, oldest first. An empty string for
// either does not narrow, and a value neither knows is refused rather than
// silently matching nothing.
func (s *SQLite) Items(state, kind string, limit int) ([]queues.Item, error) {
	var where []string
	var params []any
	if state != "" {
		if !queues.IsState(state) {
			return nil, unknown(state, queues.States, "state")
		}
		where = append(where, "state = ?")
		params = append(params, state)
	}
	if kind != "" {
		if !queues.IsKind(kind) {
			return nil, unknown(kind, queues.Kinds, "kind")
		}
		where = append(where, "kind = ?")
		params = append(params, kind)
	}
	clause := "1=1"
	if len(where) > 0 {
		clause = strings.Join(where, " AND ")
	}
	params = append(params, limit)
	rows, err := s.db.Query(fmt.Sprintf(
		"SELECT %s FROM %q WHERE %s ORDER BY created_at, id LIMIT ?",
		selectList(), Table, clause), params...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []queues.Item{}
	for rows.Next() {
		item, err := scan(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

// ---------------------------------------------------------------- writes

// Put inserts or replaces by item.ID.
func (s *SQLite) Put(item queues.Item) error {
	if !queues.IsKind(item.Kind) {
		return unknown(item.Kind, queues.Kinds, "kind")
	}
	if !queues.IsState(item.State) {
		return unknown(item.State, queues.States, "state")
	}
	names := make([]string, 0, len(queues.Columns))
	marks := make([]string, 0, len(queues.Columns))
	for _, c := range queues.Columns {
		names = append(names, fmt.Sprintf("%q", c))
		marks = append(marks, "?")
	}
	_, err := s.db.Exec(fmt.Sprintf("INSERT OR REPLACE INTO %q (%s) VALUES (%s)",
		Table, strings.Join(names, ", "), strings.Join(marks, ", ")),
		values(item)...)
	return err
}

// Claim is ready -> sending and one more attempt, atomically and durably.
//
// One statement, so it either happened or it did not, and it is on disk when
// this returns. RowsAffected is the compare-and-set: the pump that changed a
// row owns the item and every other one is told false.
func (s *SQLite) Claim(id string, at string) (queues.Item, bool, error) {
	done, err := s.db.Exec(fmt.Sprintf(
		"UPDATE %q SET state = ?, attempts = attempts + 1, claimed_at = ? "+
			"WHERE id = ? AND state = ?", Table), "sending", at, id, "ready")
	if err != nil {
		return queues.Item{}, false, err
	}
	changed, err := done.RowsAffected()
	if err != nil {
		return queues.Item{}, false, err
	}
	if changed == 0 {
		return queues.Item{}, false, nil
	}
	item, found, err := s.Get(id)
	return item, found, err
}

// Settle ends an attempt. `sent_at` is set only by reaching `sent`, so a row
// carrying one is a row something acknowledged; an item that goes back to
// `ready` keeps the previous reason until the next attempt replaces it, which
// is what lets Status say why the last one failed.
func (s *SQLite) Settle(id, state, at, receipt, errText string) error {
	if !queues.IsState(state) {
		return unknown(state, queues.States, "state")
	}
	_, err := s.db.Exec(fmt.Sprintf(
		"UPDATE %q SET state = ?, last_error = ?, receipt = ?, "+
			"sent_at = CASE WHEN ? = 'sent' THEN ? ELSE sent_at END "+
			"WHERE id = ?", Table),
		state, errText, receipt, state, at, id)
	return err
}

// ------------------------------------------------------- the bytes
// Not part of the interface. The kernel is handed paths and a delete callable
// and never opens a directory itself, so these two are this adapter's own and a
// spool over object storage would replace them without the kernel noticing.

// Keep writes one recording where it waits, owner readable only.
//
// THE FILENAME IS THE ITEM'S OPAQUE ID AND NOTHING ELSE. A name carrying a
// patient, a thread or a time of day would put identifiable information in a
// directory listing, which is the one place in this design where a file name is
// as readable as a log line.
func Keep(itemID string, audio []byte, root string) (string, error) {
	if err := os.MkdirAll(root, queues.SpoolDirMode); err != nil {
		return "", err
	}
	// MkdirAll applies the mode only to directories it CREATES, and umask
	// takes bits off even then, so the mode is set again rather than assumed:
	// a spool directory that came out group readable is a consultation
	// readable by every account on a clinic machine.
	if err := os.Chmod(root, queues.SpoolDirMode); err != nil {
		return "", err
	}
	path := filepath.Join(root, itemID+".bin")
	handle, err := os.OpenFile(path,
		os.O_WRONLY|os.O_CREATE|os.O_TRUNC, queues.SpoolFileMode)
	if err != nil {
		return "", err
	}
	if _, err := handle.Write(audio); err != nil {
		handle.Close()
		return "", err
	}
	// The recording is the one copy there is, so it is on the platter before
	// this returns: the row that names it is about to be written, and a row
	// pointing at a file the page cache lost is exactly the loss this package
	// exists to prevent.
	if err := handle.Sync(); err != nil {
		handle.Close()
		return "", err
	}
	if err := handle.Close(); err != nil {
		return "", err
	}
	return path, nil
}

// Drop removes one recording. Missing is success: the only thing this is asked
// for is that the bytes are gone.
func Drop(path string) error {
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// --------------------------------------------------------------- plumbing

func unknown(value string, allowed []string, what string) error {
	return fmt.Errorf("%q is not a %s this outbox knows: %v", value, what, allowed)
}

func selectList() string {
	names := make([]string, 0, len(queues.Columns))
	for _, c := range queues.Columns {
		names = append(names, fmt.Sprintf("%q", c))
	}
	return strings.Join(names, ", ")
}

// values is the item in Columns order. Written against the column list rather
// than as a literal, so a column added to queues.Columns and not handled here
// fails to compile instead of persisting as empty.
func values(item queues.Item) []any {
	byName := map[string]any{
		"id": item.ID, "kind": item.Kind, "key": item.Key,
		"thread": item.Thread, "operation": item.Operation,
		"capability": item.Capability, "facility": item.Facility,
		"created_at": item.CreatedAt, "actor": item.Actor, "blob": item.Blob,
		"state": item.State, "attempts": item.Attempts,
		"last_error": item.LastError, "claimed_at": item.ClaimedAt,
		"sent_at": item.SentAt, "receipt": item.Receipt,
	}
	out := make([]any, 0, len(queues.Columns))
	for _, c := range queues.Columns {
		out = append(out, byName[c])
	}
	return out
}

func scan(rows *sql.Rows) (queues.Item, error) {
	cells := make([]any, len(queues.Columns))
	texts := make([]sql.NullString, len(queues.Columns))
	numbers := make([]sql.NullInt64, len(queues.Columns))
	for i, c := range queues.Columns {
		if isInt(c) {
			cells[i] = &numbers[i]
		} else {
			cells[i] = &texts[i]
		}
	}
	if err := rows.Scan(cells...); err != nil {
		return queues.Item{}, err
	}
	var item queues.Item
	for i, c := range queues.Columns {
		text := texts[i].String
		switch c {
		case "id":
			item.ID = text
		case "kind":
			item.Kind = text
		case "key":
			item.Key = text
		case "thread":
			item.Thread = text
		case "operation":
			item.Operation = text
		case "capability":
			item.Capability = text
		case "facility":
			item.Facility = text
		case "created_at":
			item.CreatedAt = text
		case "actor":
			item.Actor = text
		case "blob":
			item.Blob = text
		case "state":
			item.State = text
		case "attempts":
			item.Attempts = int(numbers[i].Int64)
		case "last_error":
			item.LastError = text
		case "claimed_at":
			item.ClaimedAt = text
		case "sent_at":
			item.SentAt = text
		case "receipt":
			item.Receipt = text
		default:
			return queues.Item{}, fmt.Errorf(
				"the outbox has a column %q that nothing reads back, so it "+
					"would silently never persist", c)
		}
	}
	return item, nil
}
