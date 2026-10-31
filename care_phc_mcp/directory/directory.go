// Package directory is the LOCAL HALF of kernel/directory.py in Go: who the
// clerk at the desk might be, answered from this facility's own register.
//
// WHAT IS HERE AND WHAT IS DELIBERATELY NOT
// -----------------------------------------
// kernel/directory.py has two halves. The local half always runs and never
// needs a socket: a scan of the patient rows this store already holds, and a
// list of the ones no registry has seen. That is this file.
//
// The other half asks Eka's patient directory, and it is NOT here. There is
// no vendor connector in Go, no credential is read, and nothing in this
// package opens a socket. What it serves instead is the kernel's own
// AbsentDirectory: every lookup reports that the directory could not be
// ASKED, which is the designed degraded path rather than a stub. The Python
// reaches the same answer by the ordinary route whenever EKA_ACCESS_TOKEN and
// EKA_CLIENT_ID are unset, which is how every check in this repository runs,
// and PHC_DIRECTORY=absent makes it the answer on purpose.
//
// So: a facility with a credential configured gets suggestions from the
// Python and none from the Go. That is a real gap, it is this slice's and not
// a defect, and the differential check sets PHC_DIRECTORY=absent so the two
// engines are compared where they can honestly be compared rather than where
// one of them would have to invent a vendor.
//
// REACHABLE AND "NOBODY MATCHED" ARE DIFFERENT FACTS
// --------------------------------------------------
// `reachable` is false only when the directory could not be asked. A
// directory that answered and refused is reachable and `reason` says what it
// said. A clerk needs those apart: one means "nobody matched", the other
// means "I could not look", and a clerk who cannot tell them apart registers
// a duplicate.
package directory

import (
	"regexp"
	"sort"
	"strings"

	"github.com/eka-care/care_phc_mcp/store"
)

// Reader is the part of the store this package needs: one read, nullable,
// because the rows go on the wire and an unfilled column is null and not "".
type Reader interface {
	SelectNullable(resource string, thread *string, where store.Query, fields []string, limit int) ([]map[string]any, error)
}

// AbsentReason is kernel/directory.AbsentDirectory.reason, word for word. It
// is what every lookup reports here, because there is no vendor behind this
// seam in Go.
const AbsentReason = "no patient directory is configured or reachable"

// scan is the ceiling kernel/directory.cached and .pending both read to: every
// patient row this store has ever cached. Honest about being a scan: the query
// grammar in kernel/contracts.py has equality, presence, gte and lt and no
// prefix condition. Right for a health centre's own register, which is
// thousands of rows at the outside, and wrong for a district. The fix when it
// matters is a `prefix` condition in the grammar, in one place, and not a
// cache in front of this.
const scan = 5000

var notDigits = regexp.MustCompile(`\D`)

// RowMatches is kernel/directory._row_matches: name prefix, or phone
// substring.
//
// Name is a prefix match because that is what the directory does and two
// search boxes that behave differently is one search box too many. Phone is a
// substring match on the digits, because a clerk types the last few.
func RowMatches(row map[string]any, query string) bool {
	want := strings.ToLower(strings.TrimSpace(query))
	if want == "" {
		return false
	}
	name, _ := row["name"].(string)
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(name)), want) {
		return true
	}
	digits := notDigits.ReplaceAllString(want, "")
	phoneText, _ := row["phone"].(string)
	phone := notDigits.ReplaceAllString(phoneText, "")
	return digits != "" && len(digits) >= 4 && strings.Contains(phone, digits)
}

// Cached is kernel/directory.cached: rows this facility already holds that
// match, newest first.
func Cached(s Reader, query string, limit int) ([]map[string]any, error) {
	rows, err := s.SelectNullable("patient", nil, nil, nil, scan)
	if err != nil {
		return nil, err
	}
	hits := []map[string]any{}
	for _, row := range rows {
		if RowMatches(row, query) {
			hits = append(hits, row)
		}
	}
	// Stable and reversed, which is what Python's sort(reverse=True) is: two
	// rows created in the same second keep the order the select answered in,
	// and that order is created_date then id.
	sort.SliceStable(hits, func(i, j int) bool {
		a, _ := hits[i]["created_date"].(string)
		b, _ := hits[j]["created_date"].(string)
		return a > b
	})
	if len(hits) > limit {
		hits = hits[:limit]
	}
	return hits, nil
}

// Resolution is kernel/directory.Resolution, in the Python's own field order.
// Suggestions is always empty here; see the package comment.
type Resolution struct {
	Query       string           `json:"query"`
	Local       []map[string]any `json:"local"`
	Suggestions []any            `json:"suggestions"`
	Reachable   bool             `json:"reachable"`
	Reason      string           `json:"reason"`
}

// Resolve is kernel/directory.resolve against the kernel's AbsentDirectory.
//
// The local half runs and answers. The directory half raises
// DirectoryError(reachable=False) on every method of AbsentDirectory, which
// the Python catches and reports, so the answer is the local rows, no
// suggestions, reachable false and the reason. A failure is REPORTED and
// never raised, because a clerk with a reachable patient in today's line must
// not be shown an error about a patient they were not looking for.
func Resolve(s Reader, query string, limit int) (*Resolution, error) {
	local, err := Cached(s, query, limit)
	if err != nil {
		return nil, err
	}
	return &Resolution{Query: query, Local: local, Suggestions: []any{},
		Reachable: false, Reason: AbsentReason}, nil
}

// Pending is kernel/directory.pending: patients registered here that the
// directory does not know about.
//
// Not a queue and not a table: a query over rows we already keep. A
// registration taken while the line was down is in this answer by virtue of
// having no directory id, so nothing had to be enqueued and nothing can fall
// out of sync with the record it is about.
func Pending(s Reader, limit int) ([]map[string]any, error) {
	rows, err := s.SelectNullable("patient", nil, nil, nil, scan)
	if err != nil {
		return nil, err
	}
	unpublished := []map[string]any{}
	for _, row := range rows {
		id, _ := row["directory_id"].(string)
		if strings.TrimSpace(id) == "" {
			unpublished = append(unpublished, row)
		}
	}
	sort.SliceStable(unpublished, func(i, j int) bool {
		a, _ := unpublished[i]["created_date"].(string)
		b, _ := unpublished[j]["created_date"].(string)
		return a < b
	})
	if len(unpublished) > limit {
		unpublished = unpublished[:limit]
	}
	return unpublished, nil
}
