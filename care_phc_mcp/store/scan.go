package store

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"strings"
)

// Everything in this file is plumbing. It holds no knowledge about a
// resource, a thread or a clinical value, and nothing here decides anything:
// store.go is where the adapter's own knowledge lives.

// scanRows reads every column of every row as a string, because every column
// is TEXT. A NULL comes back as "", which is the one place this is lossy
// against the Python's None, and it is lossy in the same direction the
// Python's own callers already are: adapters/local/store.py returns dicts
// whose None values every reader treats as absent-or-empty, and
// `where {field: "*"}` is spelled as "not null AND not empty" for that reason.
func scanRows(rows *sql.Rows) ([]map[string]string, error) {
	columns, err := rows.Columns()
	if err != nil {
		return nil, err
	}
	var out []map[string]string
	for rows.Next() {
		cells := make([]any, len(columns))
		holders := make([]sql.NullString, len(columns))
		for i := range holders {
			cells[i] = &holders[i]
		}
		if err := rows.Scan(cells...); err != nil {
			return nil, err
		}
		row := make(map[string]string, len(columns))
		for i, name := range columns {
			row[name] = holders[i].String
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

func scanInto(row *sql.Row, into *int) error {
	if err := row.Scan(into); err == sql.ErrNoRows {
		return nil
	} else if err != nil {
		return err
	}
	return nil
}

func marks(n int) string {
	return strings.TrimSuffix(strings.Repeat("?, ", n), ", ")
}

// nullIfEmpty keeps an absent value NULL rather than "". The Python writes
// None for an actor nobody supplied, and a check that reads created_by back
// should not be told the empty string was recorded.
func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func orDefault(s, fallback string) string {
	if s == "" {
		return fallback
	}
	return s
}

func orEmptyObject(m map[string]any) map[string]any {
	if m == nil {
		return map[string]any{}
	}
	return m
}

func orEmptyList(l []string) []string {
	if l == nil {
		return []string{}
	}
	return l
}

func randomHex(n int) string {
	b := make([]byte, (n+1)/2)
	if _, err := rand.Read(b); err != nil {
		// crypto/rand on a supported platform does not fail, and an id that
		// is not unique is worse than a crash in a clinic.
		panic("care-phc: no randomness for an id: " + err.Error())
	}
	return hex.EncodeToString(b)[:n]
}
