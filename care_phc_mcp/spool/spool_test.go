package spool

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sync"
	"syscall"
	"testing"

	"github.com/eka-care/care_phc_mcp/queues"
)

// The child half of TestAClaimIsOnDiskBeforeItReturns. This test binary
// re-executes itself with PHC_SPOOL_CRASH_DB set, claims the item, and then
// kills itself with SIGKILL between claiming and sending. That is the crash
// the durability property is about, and it is MADE TO HAPPEN rather than
// asserted, which is the discipline scripts/check_queues.py already holds the
// Python to.
func TestMain(m *testing.M) {
	if path := os.Getenv("PHC_SPOOL_CRASH_DB"); path != "" {
		crashAfterClaiming(path, os.Getenv("PHC_SPOOL_CRASH_ITEM"))
		return // unreachable: crashAfterClaiming does not come back
	}
	os.Exit(m.Run())
}

func crashAfterClaiming(path, id string) {
	s, err := Open(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, "child could not open the spool:", err)
		os.Exit(2)
	}
	if _, took, err := s.Claim(id, "2026-11-01T10:01:00+00:00"); err != nil || !took {
		fmt.Fprintln(os.Stderr, "child could not claim:", err, took)
		os.Exit(3)
	}
	// Not Close(), not Exit(): the whole point is that nothing runs after the
	// claim. A graceful exit would flush something and prove less.
	syscall.Kill(os.Getpid(), syscall.SIGKILL)
	os.Exit(4) // if SIGKILL did not land, say so rather than passing
}

func item(id string) queues.Item {
	return queues.Item{ID: id, Kind: "audio", Key: "t-" + id, Thread: "enc-1",
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", CreatedAt: "2026-11-01T10:00:00+00:00",
		// Spelled out, because Go has no field defaults and Put refuses a row
		// whose state this outbox does not know. See the note on queues.Item.
		State: "ready"}
}

func open(t *testing.T) *SQLite {
	t.Helper()
	s, err := Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// queues.Item is the authority on what a queued item is. A field added there
// and not here is a column that silently never persists, which is the worst
// bug this package could have, so the list is held against it by NAME and by
// ORDER rather than maintained beside it. adapters/local/spool.py's own demo
// asserts exactly this against its dataclass.
func TestColumnsAndTheItemHaveNotDrifted(t *testing.T) {
	fields := reflect.TypeOf(queues.Item{})
	if fields.NumField() != len(queues.Columns) {
		t.Fatalf("Item has %d fields and Columns has %d",
			fields.NumField(), len(queues.Columns))
	}
	// The column name is the field name in snake case, which is the mapping
	// the Python gets for free from its dataclass. Spelled out so that a
	// rename on either side is a failure rather than a silent empty column.
	want := []string{"ID", "Kind", "Key", "Thread", "Operation", "Capability",
		"Facility", "CreatedAt", "Actor", "Blob", "State", "Attempts",
		"LastError", "ClaimedAt", "SentAt", "Receipt"}
	for i, name := range want {
		if fields.Field(i).Name != name {
			t.Errorf("field %d is %s, and the column list expects %s at that "+
				"position (%s)", i, fields.Field(i).Name, name, queues.Columns[i])
		}
	}
}

func TestARowRoundTripsWithEveryField(t *testing.T) {
	s := open(t)
	// Every field set to something distinguishable, so a column written into
	// the wrong slot is a failure rather than two empty strings agreeing.
	full := queues.Item{ID: "q-1", Kind: "document", Key: "k-1",
		Thread: "enc-7", Operation: "phc.op.consult-document",
		Capability: "encounter.document", Facility: "all-plugins",
		CreatedAt: "2026-11-01T10:00:00+00:00", Actor: "user:mo",
		Blob: "/tmp/nothing.bin", State: "held", Attempts: 3,
		LastError: "a reason", ClaimedAt: "2026-11-01T10:01:00+00:00",
		SentAt: "2026-11-01T10:02:00+00:00", Receipt: "txn-9"}
	if err := s.Put(full); err != nil {
		t.Fatal(err)
	}
	back, found, err := s.Get("q-1")
	if err != nil || !found {
		t.Fatalf("get: %v %v", found, err)
	}
	if !reflect.DeepEqual(back, full) {
		t.Errorf("round trip lost a field:\n got %+v\nwant %+v", back, full)
	}
}

func TestReadsNarrowByStateAndKind(t *testing.T) {
	s := open(t)
	for _, one := range []queues.Item{item("q-1"), item("q-2")} {
		if err := s.Put(one); err != nil {
			t.Fatal(err)
		}
	}
	doc := item("q-3")
	doc.Kind = "document"
	if err := s.Put(doc); err != nil {
		t.Fatal(err)
	}
	ready, err := s.Items("ready", "", 500)
	if err != nil || len(ready) != 3 {
		t.Fatalf("ready: %d %v", len(ready), err)
	}
	audio, err := s.Items("ready", "audio", 500)
	if err != nil || len(audio) != 2 {
		t.Fatalf("ready audio: %d %v", len(audio), err)
	}
	sent, err := s.Items("sent", "", 500)
	if err != nil || len(sent) != 0 {
		t.Fatalf("sent: %d %v", len(sent), err)
	}
	// A state or a kind this outbox does not know is REFUSED rather than
	// matching nothing: a typo in a state name that read as "no rows" would
	// make an item invisible to every read, which is the silent giving up the
	// outbox exists to prevent.
	if _, err := s.Items("done", "", 10); err == nil {
		t.Error("an unknown state was accepted as a filter")
	}
	if _, err := s.Items("", "video", 10); err == nil {
		t.Error("an unknown kind was accepted as a filter")
	}
}

func TestOneItemClaimsOnceHoweverManyAsk(t *testing.T) {
	s := open(t)
	if err := s.Put(item("q-1")); err != nil {
		t.Fatal(err)
	}
	// Eight at once, which is what scripts/check_queues.py runs at the Python.
	// RowsAffected on a single UPDATE is the compare-and-set, so exactly one
	// of these may come back with the item.
	const racers = 8
	var wg sync.WaitGroup
	took := make([]bool, racers)
	errs := make([]error, racers)
	for i := 0; i < racers; i++ {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			_, got, err := s.Claim("q-1", "2026-11-01T10:01:00+00:00")
			took[n], errs[n] = got, err
		}(i)
	}
	wg.Wait()
	wins := 0
	for i := range took {
		if errs[i] != nil {
			t.Fatalf("racer %d: %v", i, errs[i])
		}
		if took[i] {
			wins++
		}
	}
	if wins != 1 {
		t.Fatalf("%d of %d pumps claimed one item, so %d could both send it",
			wins, racers, wins)
	}
	row, _, err := s.Get("q-1")
	if err != nil {
		t.Fatal(err)
	}
	if row.State != "sending" || row.Attempts != 1 {
		t.Errorf("after eight racing claims the row is %s with %d attempts, "+
			"want sending with 1", row.State, row.Attempts)
	}
}

func TestSettleOnlyStampsSentAtOnSent(t *testing.T) {
	s := open(t)
	if err := s.Put(item("q-1")); err != nil {
		t.Fatal(err)
	}
	if err := s.Settle("q-1", "ready", "2026-11-01T10:05:00+00:00", "",
		"there is no line"); err != nil {
		t.Fatal(err)
	}
	row, _, _ := s.Get("q-1")
	if row.SentAt != "" {
		t.Errorf("a row that was never sent carries sent_at %q", row.SentAt)
	}
	if row.LastError != "there is no line" {
		t.Errorf("last_error is %q", row.LastError)
	}
	if err := s.Settle("q-1", "sent", "2026-11-01T10:06:00+00:00", "txn-9", ""); err != nil {
		t.Fatal(err)
	}
	row, _, _ = s.Get("q-1")
	if row.State != "sent" || row.Receipt != "txn-9" ||
		row.SentAt != "2026-11-01T10:06:00+00:00" {
		t.Errorf("after a receipt the row is %+v", row)
	}
	// A state the outbox does not know is refused rather than written.
	for _, bad := range []string{"done", ""} {
		if err := s.Settle("q-1", bad, "now", "", ""); err == nil {
			t.Errorf("settle accepted the unknown state %q", bad)
		}
	}
}

// PROPERTY 1, MADE TO HAPPEN. A real process, against a real file, killed with
// SIGKILL between claiming an item and sending it. The claim must be on disk,
// because an item that is still `ready` after a crash mid-send is an item a
// recovery will send a second time.
func TestAClaimIsOnDiskBeforeItReturns(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "spool.sqlite3")
	parent, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := parent.Put(item("q-1")); err != nil {
		t.Fatal(err)
	}
	// Closed so the child is the only writer, which is what makes the reopen
	// below a read of what actually reached the platter.
	if err := parent.Close(); err != nil {
		t.Fatal(err)
	}

	child := exec.Command(os.Args[0], "-test.run=TestMain")
	child.Env = append(os.Environ(),
		"PHC_SPOOL_CRASH_DB="+path, "PHC_SPOOL_CRASH_ITEM=q-1")
	child.Stderr = os.Stderr
	runErr := child.Run()
	if runErr == nil {
		t.Fatal("the child exited cleanly, so it was not killed mid-send and " +
			"this proves nothing")
	}
	state, ok := child.ProcessState.Sys().(syscall.WaitStatus)
	if !ok || !state.Signaled() || state.Signal() != syscall.SIGKILL {
		t.Fatalf("the child did not die of SIGKILL (%v), so the crash this "+
			"test is about did not happen", runErr)
	}

	again, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer again.Close()
	row, found, err := again.Get("q-1")
	if err != nil || !found {
		t.Fatalf("after the crash the row is gone: %v %v", found, err)
	}
	if row.State != "sending" {
		t.Errorf("a process killed between claiming and sending left the item "+
			"in %q. In `ready` a recovery resends it; anything else loses it.",
			row.State)
	}
	if row.Attempts != 1 {
		t.Errorf("the crashed attempt was not counted: attempts = %d", row.Attempts)
	}
	if row.ClaimedAt == "" {
		t.Error("the claim was not stamped, so nothing can tell how long it " +
			"has been in flight")
	}
}

// The bytes wait OUTSIDE the repository, owner readable only, under a name
// that is the item's opaque id and nothing else. A name carrying a patient, a
// thread or a time of day would put identifiable information in a directory
// listing, which is the one place in this design where a file name is as
// readable as a log line.
func TestARecordingWaitsUnderItsOpaqueIdAndIsReadableOnlyByItsOwner(t *testing.T) {
	root := filepath.Join(t.TempDir(), "spool")
	path, err := Keep("q-abc123", []byte("not really audio"), root)
	if err != nil {
		t.Fatal(err)
	}
	if base := filepath.Base(path); base != "q-abc123.bin" {
		t.Errorf("a recording is named %q", base)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if mode := info.Mode().Perm(); mode != 0o600 {
		t.Errorf("a consultation recording is mode %o, want 600: a clinic "+
			"machine has more than one account on it", mode)
	}
	dir, err := os.Stat(root)
	if err != nil {
		t.Fatal(err)
	}
	if mode := dir.Mode().Perm(); mode != 0o700 {
		t.Errorf("the spool directory is mode %o, want 700", mode)
	}
	raw, err := os.ReadFile(path)
	if err != nil || string(raw) != "not really audio" {
		t.Errorf("the bytes did not survive: %q %v", raw, err)
	}
	// Missing is success: the only thing Drop is asked for is that the bytes
	// are gone.
	if err := Drop(path); err != nil {
		t.Fatal(err)
	}
	if err := Drop(path); err != nil {
		t.Errorf("dropping an already gone recording failed: %v", err)
	}
}
