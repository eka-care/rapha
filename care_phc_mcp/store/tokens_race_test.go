package store

import (
	"fmt"
	"path/filepath"
	"sort"
	"sync"
	"testing"

	"github.com/eka-care/care_phc_mcp/tokens"
)

// The Go half of the token race, and it is proved by racing rather than by
// inspection. scripts/check_tokens_race.py is the Python's and the reasoning
// is written out there; the short version is that a test issuing numbers one
// after another passed against the broken code for as long as the broken code
// shipped, because the arithmetic was never what was wrong.
//
// REAL GOROUTINES AGAINST A REAL FILE. Not ":memory:", because that is one
// SQLite instance behind one shared cache and the locking a file gets is the
// thing under test; a fix that worked only in memory would be a fix for
// nothing. Every goroutine does its reads, then waits on one barrier, so the
// issuing overlaps instead of queueing behind setup.
//
// Go's own race detector is not what this is for and would not catch it: the
// defect is not a data race in Go memory, it is two correct readers of a
// database agreeing on a stale answer. Only the outcome shows it.
const (
	raceWorkers   = 16
	racePerWorker = 6
	raceRounds    = 3
)

func TestIssueTokenHandsOutEachNumberOnceUnderRealConcurrency(t *testing.T) {
	for round := 1; round <= raceRounds; round++ {
		// A fresh file per round, so each round is a facility's own first
		// morning and the expected answer is exactly 1..n. Carrying the file
		// over would make the expected set depend on the previous round and
		// hide a duplicate inside a bigger range.
		path := filepath.Join(t.TempDir(), fmt.Sprintf("round-%d.sqlite3", round))
		s, err := Open(path)
		if err != nil {
			t.Fatalf("round %d: open: %v", round, err)
		}

		var (
			start sync.WaitGroup
			done  sync.WaitGroup
			mu    sync.Mutex
			got   []int
		)
		start.Add(1)
		for w := 0; w < raceWorkers; w++ {
			done.Add(1)
			go func() {
				defer done.Done()
				start.Wait()
				for i := 0; i < racePerWorker; i++ {
					// Exactly what the route does and in that order: read the
					// day, compute the floor, reserve a number, write the row.
					// Not a bare call to IssueToken, because the thing being
					// proved is the production path.
					refs, err := s.Threads("phc.wf.outpatient", "today")
					if err != nil {
						t.Errorf("threads: %v", err)
						return
					}
					seen := make([]string, 0, len(refs))
					for _, ref := range refs {
						text, _ := ref.Subject["token"].(string)
						seen = append(seen, text)
					}
					n, err := s.IssueToken("phc.wf.outpatient", "today", tokens.After(seen))
					if err != nil {
						t.Errorf("issue: %v", err)
						return
					}
					if _, err := s.OpenThread(fmt.Sprintf("%d", n), "race"); err != nil {
						t.Errorf("open thread: %v", err)
						return
					}
					mu.Lock()
					got = append(got, n)
					mu.Unlock()
				}
			}()
		}
		start.Done()
		done.Wait()
		if t.Failed() {
			return
		}

		want := raceWorkers * racePerWorker
		if len(got) != want {
			t.Fatalf("round %d: %d arrivals, want %d", round, len(got), want)
		}

		// The rows, not what the callers reported. What the waiting room has
		// is what the database has, and a caller that returned a number it
		// failed to store would otherwise read as a pass.
		rows, err := s.db.Query("SELECT token FROM encounter WHERE created_by = 'race'")
		if err != nil {
			t.Fatalf("round %d: read back: %v", round, err)
		}
		stored := []string{}
		for rows.Next() {
			var token string
			if err := rows.Scan(&token); err != nil {
				t.Fatalf("scan: %v", err)
			}
			stored = append(stored, token)
		}
		rows.Close()

		if len(stored) != want {
			t.Fatalf("round %d: %d rows for %d arrivals", round, len(stored), want)
		}

		numbers := tokens.Numbers(stored)
		if len(numbers) != want {
			t.Fatalf("round %d: %d of %d stored tokens are not on the sequence",
				round, want-len(numbers), want)
		}
		sort.Ints(numbers)

		seen := map[int]int{}
		repeated := []int{}
		for _, n := range numbers {
			seen[n]++
			if seen[n] == 2 {
				repeated = append(repeated, n)
			}
		}
		if len(repeated) > 0 {
			t.Fatalf("round %d: %d arrivals were handed a number somebody else "+
				"already had: %v. This is the race, and it is what two patients "+
				"holding the same slip looks like.", round, len(repeated), repeated)
		}

		// A hole is as much a defect as a duplicate and is asserted for its
		// own sake: a sequence that answers a collision by skipping a number
		// is a number called out to a room where nobody has it.
		for i, n := range numbers {
			if n != i+1 {
				t.Fatalf("round %d: the day is not 1..%d; position %d holds %d. "+
					"A hole is a number called out to a room where nobody has it.",
					round, want, i+1, n)
			}
		}
	}
}

// The floor, which the race above cannot see.
//
// A counter alone is not enough and this is the case that proves it. Rows can
// gain numbers without the counter being told: a seed rolled forward into
// today is exactly that, and so is any row written straight to the table. If
// issuing read only the counter, the next arrival would be handed a number a
// row in the room already wears.
//
// Sequential on purpose. It is not a race, it is the arithmetic the race test
// cannot reach, and it is the other half of one promise.
func TestIssueTokenNeverGoesBelowTheFloorTheRowsSet(t *testing.T) {
	path := filepath.Join(t.TempDir(), "floor.sqlite3")
	s, err := Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}

	first, err := s.IssueToken("phc.wf.outpatient", "today", 1)
	if err != nil || first != 1 {
		t.Fatalf("first number: %d, %v", first, err)
	}

	// A number arriving from outside the sequence, as a rolled-forward seed's
	// does. The counter still says 1.
	if _, err := s.OpenThread("50", "seed"); err != nil {
		t.Fatalf("open thread: %v", err)
	}
	refs, err := s.Threads("phc.wf.outpatient", "today")
	if err != nil {
		t.Fatalf("threads: %v", err)
	}
	seen := []string{}
	for _, ref := range refs {
		text, _ := ref.Subject["token"].(string)
		seen = append(seen, text)
	}
	floor := tokens.After(seen)
	if floor != 51 {
		t.Fatalf("floor: %d, want 51", floor)
	}

	next, err := s.IssueToken("phc.wf.outpatient", "today", floor)
	if err != nil {
		t.Fatalf("issue: %v", err)
	}
	if next < floor {
		t.Fatalf("the sequence handed out %d when a row in the room already wore "+
			"50. The counter was followed and the floor was ignored, which is how "+
			"a seeded demo day reissues a number somebody is answering to.", next)
	}
	if next != 51 {
		t.Fatalf("next: %d, want 51", next)
	}

	// And it does not go backwards afterwards either.
	again, err := s.IssueToken("phc.wf.outpatient", "today", 1)
	if err != nil || again != 52 {
		t.Fatalf("after the floor: %d, %v; want 52", again, err)
	}
}

// OpenThread invents no number. It used to fall back to the last three
// characters of the generated row id, so an arrival that reached the store
// without a number got one that was on no sequence and was issued to nobody.
// adapters/local/store.py removed that and said so; this engine had kept it.
func TestOpenThreadInventsNoTokenWhenGivenNone(t *testing.T) {
	path := filepath.Join(t.TempDir(), "no-token.sqlite3")
	s, err := Open(path)
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	thread, err := s.OpenThread("", "desk")
	if err != nil {
		t.Fatalf("open thread: %v", err)
	}
	var token any
	if err := s.db.QueryRow("SELECT token FROM encounter WHERE id = ?", thread).
		Scan(&token); err != nil {
		t.Fatalf("read back: %v", err)
	}
	text, _ := token.(string)
	if text != "" {
		t.Fatalf("a visit with no number was given %q, which is on no sequence "+
			"and was issued to nobody", text)
	}
}
