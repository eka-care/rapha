package queues_test

// The transport scripts/check_go_parity.py asks this engine's outbox through.
//
// WHY A TEST AND NOT A COMMAND OR A ROUTE
// ---------------------------------------
// The outbox is SWITCHED ON since 2026-11-01 and is still on no HTTP ROUTE in
// either engine, which are different things. api/outbox.py holds a recording
// the line could not take and sweeps on a timer, and cmd/api/outbox.go sweeps
// the same spool; neither exposes a route, because an outbox is not something
// a caller asks for. So there is still nothing for the socket checks to
// compare, and no route may be invented so that a check can reach behind the
// service. That is the same position kernel/fhir.py is in, and
// fhir/parity_test.go is the precedent this file follows.
//
// What the socket checks still cannot see is the SWEEPER running, because it
// runs on a five minute timer rather than in answer to a request.
// scripts/check_audio_ceiling.py drives a pass with its own clock instead, and
// asserts against the source that both engines start one.
//
// So this is a test THAT ASSERTS NOTHING. It reads a file of inputs the
// Python check wrote, runs them through this package, writes what came back,
// and leaves every comparison to the check. No literal is written down here,
// which is the rule scripts/check_go_parity.py is built on: a literal would
// pass while both engines drifted from each other.
//
// Skipped, loudly, when the environment does not name a cases file, so
// `go test ./...` in scripts/check.sh is unaffected.
//
// WHAT IT CANNOT PROVE
// --------------------
// That the outbox is REACHED. Nothing in either service calls it, by
// decision and not by omission, so this proves the two outboxes answer alike
// and not that anybody asks them anything.
//
// And one thing it deliberately does NOT compare: the sentence a failure that
// is not an Unsendable leaves on the row. The Python writes
// `type(broke).__name__` and Go has no such name; what both hold is that the
// row names a KIND of failure and never the sentence that came with it, and
// the scrub cases are where that is compared.

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/eka-care/care_phc_mcp/queues"
	"github.com/eka-care/care_phc_mcp/spool"
)

type parityCases struct {
	Scrub   []string `json:"scrub"`
	Backoff []int    `json:"backoff"`
	Refusal []struct {
		Kind       string            `json:"kind"`
		Operation  string            `json:"operation"`
		Capability string            `json:"capability"`
		Withheld   map[string]string `json:"withheld"`
	} `json:"refusal"`
	Standing []struct {
		Case string `json:"case"`
		Rows []struct {
			Kind     string `json:"kind"`
			State    string `json:"state"`
			Attempts int    `json:"attempts"`
		} `json:"rows"`
	} `json:"standing"`
	Admit []struct {
		Case       string            `json:"case"`
		Kind       string            `json:"kind"`
		Key        string            `json:"key"`
		Operation  string            `json:"operation"`
		Capability string            `json:"capability"`
		Withheld   map[string]string `json:"withheld"`
	} `json:"admit"`
	Sweeps []struct {
		Case  string `json:"case"`
		Now   string `json:"now"`
		Items []struct {
			Key   string `json:"key"`
			Kind  string `json:"kind"`
			Blob  string `json:"blob"`
			Allow bool   `json:"allow"`
			Deny  string `json:"deny"`
		} `json:"items"`
		// One word per attempt, PER ITEM KEY, consumed in order: "receipt",
		// "unsendable", "empty" or "boom". A key that runs out of words gets
		// the last one again, which is what a line that stays down looks like.
		//
		// KEYED BY ITEM AND NOT POSITIONAL, because the order items are swept
		// in is not deterministic in EITHER engine: `due` reads them oldest
		// first and the tiebreak is the row id, which is a random hex string
		// on both sides. A positional script made the comparison depend on
		// that randomness rather than on the outbox.
		Send map[string][]string `json:"send"`
		// "known", "known-empty" or "unknown".
		Delivered string `json:"delivered"`
		// One pump sweep per moment, in order. A LIST AND NOT A COUNT,
		// because the backoff is a function of the clock: nine sweeps all told
		// the same moment are one sweep and eight items sitting inside their
		// backoff, which is how the attempt limit went unreached the first
		// time this was written.
		Clock []string `json:"clock"`
		// Whether to move everything still waiting into `sending` before
		// recovering. That is what a crash leaves behind, and without it there
		// is nothing in flight for recovery to find.
		Strand  bool `json:"strand"`
		Recover bool `json:"recover"`
		// The moment recovery is run at, which must be past the in-flight
		// window for anything to be stuck.
		RecoverAt string `json:"recover_at"`
	} `json:"sweeps"`

	// The owner's 24 hour ceiling on held audio, which is a CLAMP and not a
	// default, and which states a held recording is swept out of.
	Ceiling   []int    `json:"ceiling"`
	Retention []string `json:"retention"`
}

// sweepAnswer is one scenario's outcome: the sweep's own lists, and then the
// rows as they stand. The rows are the thing that matters most, because a row
// is what survives the process.
type sweepAnswer struct {
	Case       string     `json:"case"`
	Sent       []string   `json:"sent"`
	Failed     []string   `json:"failed"`
	Refused    []string   `json:"refused"`
	Stopped    []string   `json:"stopped"`
	Held       []string   `json:"held"`
	Unrecorded []string   `json:"unrecorded"`
	Rows       []rowState `json:"rows"`
	Handed     []string   `json:"handed"`
	Dropped    int        `json:"dropped"`
	Lines      []string   `json:"lines"`
}

// rowState is one outbox row as the comparison sees it. NO ITEM ID AND NO
// TIMESTAMP: the id is a random hex string and the claim stamp is the clock,
// so neither can be compared between two engines. The key is the stable name,
// which is the point of the key.
type rowState struct {
	Key       string `json:"key"`
	Kind      string `json:"kind"`
	State     string `json:"state"`
	Attempts  int    `json:"attempts"`
	Receipt   string `json:"receipt"`
	LastError string `json:"last_error"`
	// Whether a sent_at was stamped, rather than what it was: the moment is
	// the clock's, the fact that there is one is the design's.
	Stamped bool `json:"stamped"`
}

// scripted is a remote driven by a word list, so both engines face the same
// remote without either of them writing one down.
type scripted struct {
	words     map[string][]string
	at        map[string]int
	delivered string
	handed    []string
}

func (s *scripted) Send(item queues.Item, body any) (string, error) {
	word := "receipt"
	if list := s.words[item.Key]; len(list) > 0 {
		i := s.at[item.Key]
		if i < len(list) {
			word = list[i]
		} else {
			word = list[len(list)-1]
		}
	}
	if s.at == nil {
		s.at = map[string]int{}
	}
	s.at[item.Key]++
	s.handed = append(s.handed, item.Key)
	switch word {
	case "unsendable":
		return "", queues.Unsendablef("there is no line")
	case "empty":
		return "   ", nil
	case "boom":
		return "", &scriptedFailure{}
	default:
		return "r-" + item.Key, nil
	}
}

// scriptedFailure is a failure that is NOT an Unsendable, which is the case
// where only the kind of failure may reach the row.
type scriptedFailure struct{}

func (scriptedFailure) Error() string {
	return "patient Asha Devi, mobile 9876543210, diagnosis hypertension"
}

func (s *scripted) Delivered(item queues.Item) (queues.Delivery, error) {
	switch s.delivered {
	case "unknown":
		return queues.Delivery{Known: false}, nil
	case "known-empty":
		return queues.Delivery{Known: true, Receipt: ""}, nil
	default:
		return queues.Delivery{Known: true, Receipt: "r-" + item.Key}, nil
	}
}

// The two clocks the retention cases use. parityPastCeiling is two days on,
// past the owner's 24 hour ceiling; scripts/check_go_parity.py uses the same
// two instants and the pair must agree about what expired.
const (
	parityNow         = "2026-11-01T10:00:00+00:00"
	parityPastCeiling = "2026-11-03T10:00:00+00:00"
)

func TestTheOutboxAnswersForTheParityCheck(t *testing.T) {
	in := os.Getenv("PHC_QUEUE_CASES")
	out := os.Getenv("PHC_QUEUE_ANSWERS")
	if in == "" || out == "" {
		t.Skip("PHC_QUEUE_CASES and PHC_QUEUE_ANSWERS name the files " +
			"scripts/check_go_parity.py drives this package through")
	}
	raw, err := os.ReadFile(in)
	if err != nil {
		t.Fatal(err)
	}
	var cases parityCases
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}

	answers := map[string]any{}

	// The privacy decision, sentence by sentence. This is the one that matters
	// most: it is the only free text field on the row and the two engines must
	// remove the same things from the same strings.
	scrubbed := []string{}
	for _, one := range cases.Scrub {
		scrubbed = append(scrubbed, queues.Scrubbed(one))
	}
	answers["scrub"] = scrubbed

	backoff := []int{}
	for _, n := range cases.Backoff {
		backoff = append(backoff, queues.Backoff(n))
	}
	answers["backoff"] = backoff

	// The ceiling clamp, input for input.
	ceiling := []int{}
	for _, n := range cases.Ceiling {
		ceiling = append(ceiling, queues.HeldCeiling(n))
	}
	answers["ceiling"] = ceiling
	answers["swept_states"] = queues.SweptStates

	// One audio item in each state, swept past the ceiling: was its recording
	// deleted, and what state did the row end in. The delete RECORDS rather
	// than unlinking, so the two engines are compared on the decision and not
	// on two filesystems.
	retention := []map[string]any{}
	for _, state := range cases.Retention {
		box, err := spool.Open(":memory:")
		if err != nil {
			t.Fatal(err)
		}
		item, err := queues.Enqueue(box, queues.Enqueued{
			Kind: "audio", Key: "k-" + state, Thread: "enc-1",
			Operation:  "phc.op.consult-document",
			Capability: "encounter.document", Facility: "all-plugins",
			At: parityNow, Blob: "/held/" + state,
		})
		if err != nil {
			t.Fatal(err)
		}
		if state != "ready" {
			receipt := ""
			if state == "sent" {
				receipt = "r-1"
			}
			if err := box.Settle(item.ID, state, parityNow, receipt, ""); err != nil {
				t.Fatal(err)
			}
		}
		removed := []string{}
		gone, err := queues.SweepAudio(box, parityPastCeiling,
			func(path string) error {
				removed = append(removed, path)
				return nil
			}, queues.AudioMaxHoldSeconds)
		if err != nil {
			t.Fatal(err)
		}
		after, _, err := box.Get(item.ID)
		if err != nil {
			t.Fatal(err)
		}
		retention = append(retention, map[string]any{
			"state":   state,
			"swept":   len(gone) == 1 && gone[0] == item.ID,
			"deleted": removed,
			"final":   after.State,
			"says":    after.LastError,
		})
		box.Close()
	}
	answers["retention"] = retention

	refusal := []string{}
	for _, one := range cases.Refusal {
		refusal = append(refusal, queues.Refusal(one.Kind, one.Operation,
			one.Capability, one.Withheld))
	}
	answers["refusal"] = refusal

	// Admission: whether a row was kept, and what was said if it was not.
	admit := []map[string]any{}
	for _, one := range cases.Admit {
		s, err := spool.Open(":memory:")
		if err != nil {
			t.Fatal(err)
		}
		_, enqErr := queues.Enqueue(s, queues.Enqueued{
			Kind: one.Kind, Key: one.Key, Thread: "enc-1",
			Operation: one.Operation, Capability: one.Capability,
			Facility: "all-plugins", At: "2026-11-01T10:00:00+00:00",
			Withheld: one.Withheld})
		rows, _ := s.Items("", "", 500)
		why := ""
		if enqErr != nil {
			why = enqErr.Error()
		}
		admit = append(admit, map[string]any{
			"case": one.Case, "refused": why, "rows": len(rows)})
		s.Close()
	}
	answers["admit"] = admit

	// The outbox as sentences, over a hand built set of rows.
	standing := []map[string]any{}
	for _, one := range cases.Standing {
		s, err := spool.Open(":memory:")
		if err != nil {
			t.Fatal(err)
		}
		for n, row := range one.Rows {
			item := queues.Item{
				ID: idFor(one.Case, n), Kind: row.Kind, Key: keyFor(one.Case, n),
				Thread: "enc-1", Operation: "phc.op.consult-document",
				Capability: "encounter.document", Facility: "all-plugins",
				CreatedAt: "2026-11-01T10:00:00+00:00", State: row.State,
				Attempts: row.Attempts}
			if err := s.Put(item); err != nil {
				t.Fatal(err)
			}
		}
		got, err := queues.Status(s, 2000)
		if err != nil {
			t.Fatal(err)
		}
		standing = append(standing, map[string]any{
			"case": one.Case, "lines": got.Lines()})
		s.Close()
	}
	answers["standing"] = standing

	// And the pump itself, scripted.
	sweeps := []sweepAnswer{}
	for _, one := range cases.Sweeps {
		s, err := spool.Open(":memory:")
		if err != nil {
			t.Fatal(err)
		}
		verdict := map[string]bool{}
		deny := map[string]string{}
		byID := map[string]string{} // item id -> key, for naming outcomes
		for _, want := range one.Items {
			item, err := queues.Enqueue(s, queues.Enqueued{
				Kind: want.Kind, Key: want.Key, Thread: "enc-" + want.Key,
				Operation:  "phc.op.consult-document",
				Capability: "encounter.document", Facility: "all-plugins",
				At: one.Now, Actor: "user:mo", Blob: want.Blob})
			if err != nil {
				t.Fatal(err)
			}
			byID[item.ID] = want.Key
			verdict[want.Key] = want.Allow
			deny[want.Key] = want.Deny
		}
		sender := &scripted{words: one.Send, at: map[string]int{},
			delivered: one.Delivered}
		senders := map[string]queues.Sender{"document": sender, "audio": sender}
		permit := func(item queues.Item) queues.Decision {
			if verdict[item.Key] {
				return queues.Allowed()
			}
			return queues.Denied(deny[item.Key])
		}
		dropped := 0
		drop := func(string) error { dropped++; return nil }

		// Every list starts EMPTY and not nil. encoding/json writes a nil
		// slice as `null` and an empty one as `[]`, and the Python always has a
		// list, so a scenario in which nothing failed would otherwise differ
		// from the Python by the spelling of nothing.
		got := sweepAnswer{Case: one.Case,
			Sent: []string{}, Failed: []string{}, Refused: []string{},
			Stopped: []string{}, Held: []string{}, Unrecorded: []string{},
			Handed: []string{}}
		for _, at := range one.Clock {
			report, err := queues.Pump(s, senders, permit,
				func(queues.Item) (any, error) {
					return map[string]any{"body": true}, nil
				}, at, 50, queues.MaxAttempts, drop)
			if err != nil {
				t.Fatal(err)
			}
			got.Sent = append(got.Sent, named(report.Sent, byID)...)
			got.Failed = append(got.Failed, named(report.Failed, byID)...)
			got.Refused = append(got.Refused, named(report.Refused, byID)...)
			got.Stopped = append(got.Stopped, named(report.Stopped, byID)...)
			got.Held = append(got.Held, named(report.Held, byID)...)
			got.Unrecorded = append(got.Unrecorded, named(report.Unrecorded, byID)...)
		}
		if one.Strand {
			// What a crash leaves: claimed and never settled. The last reason
			// is cleared, because the Python's own settle writes an empty
			// error when it is not given one.
			waiting, err := s.Items("ready", "", 500)
			if err != nil {
				t.Fatal(err)
			}
			for _, row := range waiting {
				if err := s.Settle(row.ID, "sending", one.Now, "", ""); err != nil {
					t.Fatal(err)
				}
			}
		}
		if one.Recover {
			// Everything still in flight is made stuck by the clock, which is
			// what a crash plus a restart looks like.
			at := one.RecoverAt
			if at == "" {
				at = one.Now
			}
			report, err := queues.Recover(s, senders, at,
				queues.InFlightSeconds, queues.MaxAttempts)
			if err != nil {
				t.Fatal(err)
			}
			got.Sent = append(got.Sent, named(report.Sent, byID)...)
			got.Failed = append(got.Failed, named(report.Failed, byID)...)
			got.Held = append(got.Held, named(report.Held, byID)...)
			got.Stopped = append(got.Stopped, named(report.Stopped, byID)...)
		}
		if sender.handed != nil {
			got.Handed = sender.handed
		}
		got.Dropped = dropped
		got.Rows = rowsOf(t, s)
		standingNow, err := queues.Status(s, 2000)
		if err != nil {
			t.Fatal(err)
		}
		got.Lines = standingNow.Lines()
		sweeps = append(sweeps, got)
		s.Close()
	}
	answers["sweeps"] = sweeps

	blob, err := json.MarshalIndent(answers, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(out, append(blob, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
}

// named turns a sweep's outcomes into the stable keys, because the item id is
// random and cannot be compared between engines. The reason is kept with the
// outcome, because a refusal whose wording drifted is a refusal a reader
// cannot act on.
func named(outcomes []queues.Outcome, byID map[string]string) []string {
	out := []string{}
	for _, one := range outcomes {
		out = append(out, byID[one.Item]+" "+one.Why)
	}
	return out
}

func rowsOf(t *testing.T, s *spool.SQLite) []rowState {
	t.Helper()
	out := []rowState{}
	// Walked in the vocabulary's own order rather than by a bare read, so the
	// two engines list the rows the same way without either sorting them.
	for _, state := range queues.States {
		rows, err := s.Items(state, "", 500)
		if err != nil {
			t.Fatal(err)
		}
		for _, row := range rows {
			out = append(out, rowState{Key: row.Key, Kind: row.Kind,
				State: row.State, Attempts: row.Attempts,
				Receipt: row.Receipt, LastError: row.LastError,
				Stamped: row.SentAt != ""})
		}
	}
	return out
}

func idFor(prefix string, n int) string {
	return "q-" + prefix + "-" + itoa(n)
}

func keyFor(prefix string, n int) string {
	return prefix + "-" + itoa(n)
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var digits []byte
	for n > 0 {
		digits = append([]byte{byte('0' + n%10)}, digits...)
		n /= 10
	}
	return string(digits)
}
