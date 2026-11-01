package queues_test

import (
	"errors"
	"fmt"
	"reflect"
	"regexp"
	"strings"
	"testing"

	"github.com/eka-care/care_phc_mcp/queues"
	"github.com/eka-care/care_phc_mcp/spool"
)

// An EXTERNAL test package, for the reason the terminology slice gives for its
// own: a test inside the package could reach past the one constructor and the
// one scrubber and prove the opposite of what it claims.

const now = "2026-11-01T10:00:00+00:00"
const later = "2026-11-01T14:00:00+00:00"

func newSpool(t *testing.T) *spool.SQLite {
	t.Helper()
	s, err := spool.Open(":memory:")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { s.Close() })
	return s
}

// ---------------------------------------------------------------- senders

// counting is a remote that remembers what it took, which is what makes the
// not-sent-twice property observable at all.
type counting struct{ sent []string }

func (c *counting) Send(item queues.Item, body any) (string, error) {
	c.sent = append(c.sent, item.Key)
	return "r-" + item.Key, nil
}

func (c *counting) Delivered(item queues.Item) (queues.Delivery, error) {
	for _, key := range c.sent {
		if key == item.Key {
			return queues.Delivery{Known: true, Receipt: "r-" + item.Key}, nil
		}
	}
	return queues.Delivery{Known: true, Receipt: ""}, nil
}

// dead is a line that is down.
type dead struct{}

func (dead) Send(queues.Item, any) (string, error) {
	return "", queues.Unsendablef("there is no line")
}
func (dead) Delivered(queues.Item) (queues.Delivery, error) {
	return queues.Delivery{Known: true, Receipt: ""}, nil
}

// mute accepted something and named nothing.
type mute struct{}

func (mute) Send(queues.Item, any) (string, error) { return "   ", nil }
func (mute) Delivered(queues.Item) (queues.Delivery, error) {
	return queues.Delivery{Known: true, Receipt: ""}, nil
}

// silent cannot say whether it already has this.
type silent struct{}

func (silent) Send(queues.Item, any) (string, error) {
	return "", queues.Unsendablef("no")
}
func (silent) Delivered(queues.Item) (queues.Delivery, error) {
	return queues.Delivery{Known: false}, nil
}

// leaky raises something that is not an Unsendable, carrying a response body.
// What reaches the row must be the TYPE and never the sentence.
type leaky struct{}

type bodyCarrying struct{ body string }

func (b *bodyCarrying) Error() string { return b.body }

func (leaky) Send(queues.Item, any) (string, error) {
	return "", &bodyCarrying{body: "patient Asha Devi, mobile 9876543210, " +
		"diagnosis hypertension"}
}
func (leaky) Delivered(queues.Item) (queues.Delivery, error) {
	return queues.Delivery{Known: true, Receipt: ""}, nil
}

// ------------------------------------------------------------- the permits

func yes(queues.Item) queues.Decision { return queues.Allowed() }
func no(queues.Item) queues.Decision {
	return queues.Denied("missing capability encounter.document")
}

func bodies(queues.Item) (any, error) { return map[string]any{"body": true}, nil }

func enqueueOne(t *testing.T, s queues.Spool, key, thread string) queues.Item {
	t.Helper()
	item, err := queues.Enqueue(s, queues.Enqueued{
		Kind: "document", Key: key, Thread: thread,
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", At: now, Actor: "user:mo"})
	if err != nil {
		t.Fatal(err)
	}
	return item
}

// ---------------------------------------------------------------- admission

// kernel/plugins.py's doctrine is that a plugin that is off DENIES AND DOES NOT
// HIDE. At admission that means refusing to HOLD the item, which is stronger
// than refusing to send it: no row, no recording on disk, and nothing for a
// person to wonder about.
func TestACentreHoldsNothingForAPluginItDoesNotRun(t *testing.T) {
	s := newSpool(t)
	_, err := queues.Enqueue(s, queues.Enqueued{
		Kind: "audio", Key: "t-1", Thread: "enc-1",
		Operation: "phc.op.household-visit", Capability: "visit.household",
		Facility: "consulting-room-only", At: now,
		Withheld: map[string]string{"visit.household": "outreach"}})
	if err == nil {
		t.Fatal("an item was held for a plugin this centre is not running")
	}
	if !strings.Contains(err.Error(), "outreach") {
		t.Errorf("the refusal does not name the plugin: %v", err)
	}
	rows, _ := s.Items("", "", 500)
	if len(rows) != 0 {
		t.Errorf("a refused item left %d rows behind", len(rows))
	}
}

// The key is the whole of the not-sent-twice property, so an item without one
// is refused rather than given a generated one: a key we minted here and the
// remote never saw deduplicates nothing.
func TestAnItemWithNoKeyIsRefused(t *testing.T) {
	s := newSpool(t)
	for _, key := range []string{"", "   "} {
		_, err := queues.Enqueue(s, queues.Enqueued{
			Kind: "audio", Key: key, Thread: "enc-1",
			Operation:  "phc.op.consult-document",
			Capability: "encounter.document", Facility: "all-plugins", At: now})
		if err == nil {
			t.Fatalf("an item with the key %q was accepted", key)
		}
		if !strings.Contains(err.Error(), "key") {
			t.Errorf("the refusal does not say what is missing: %v", err)
		}
	}
	if rows, _ := s.Items("", "", 500); len(rows) != 0 {
		t.Errorf("a keyless item left %d rows behind", len(rows))
	}
}

func TestAKindThisOutboxDoesNotKnowIsRefused(t *testing.T) {
	s := newSpool(t)
	_, err := queues.Enqueue(s, queues.Enqueued{
		Kind: "video", Key: "t-1", Thread: "enc-1",
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", At: now})
	if err == nil {
		t.Fatal("an item of an unknown kind was accepted")
	}
}

// ------------------------------------------------------- the guard at send

// PROPERTY: the guard is re-run at the moment of sending. A proposal is judged
// against the world as it is when it is acted on, and a queue is that problem
// with a longer gap. An item the guard now denies becomes `refused` WITHOUT
// ever entering `sending`, so a denial costs no attempt.
func TestTheGuardRefusesAtSendTimeAndNothingGoes(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-1", "enc-1")
	sender := &counting{}

	report, err := queues.Pump(s, map[string]queues.Sender{"document": sender},
		no, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Sent) != 0 || len(report.Refused) != 1 {
		t.Fatalf("a refused item produced %+v", report)
	}
	if len(sender.sent) != 0 {
		t.Error("a refused item was sent anyway")
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "refused" {
		t.Errorf("a denied item is in %q, want refused", row.State)
	}
	if row.Attempts != 0 {
		t.Errorf("a guard denial cost %d attempts, so a denial can exhaust an "+
			"item that was never tried", row.Attempts)
	}
}

func TestAnAllowedItemGoesOnceWithAReceipt(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-1", "enc-1")
	sender := &counting{}

	report, err := queues.Pump(s, map[string]queues.Sender{"document": sender},
		yes, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	want := []queues.Outcome{{Item: item.ID, Why: "r-enc-1"}}
	if !reflect.DeepEqual(report.Sent, want) {
		t.Fatalf("sent %+v, want %+v", report.Sent, want)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "sent" || row.Receipt != "r-enc-1" {
		t.Errorf("after a receipt the row is %+v", row)
	}
	// And a second sweep does not send it again: `sent` is not `ready`.
	if _, err := queues.Pump(s, map[string]queues.Sender{"document": sender},
		yes, bodies, now, 50, queues.MaxAttempts, nil); err != nil {
		t.Fatal(err)
	}
	if len(sender.sent) != 1 {
		t.Errorf("the remote was asked %d times for one item", len(sender.sent))
	}
}

// ------------------------------------------------- nothing reported as sent

func TestAFailedSendIsNotRecordedAsASuccess(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-2", "enc-2")
	report, err := queues.Pump(s, map[string]queues.Sender{"document": dead{}},
		yes, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Sent) != 0 || len(report.Failed) != 1 {
		t.Fatalf("a dead line produced %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "ready" || row.Attempts != 1 || row.Receipt != "" {
		t.Errorf("after a failed send the row is %+v", row)
	}
	if row.SentAt != "" {
		t.Error("a row that was never sent carries a sent_at")
	}
}

// Property 4 at its sharpest: a send that came back with nothing to point at is
// not a success. There is no evidence, so there is no `sent`.
func TestAnEmptyReceiptIsAFailureNotASuccess(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-3", "enc-3")
	report, err := queues.Pump(s, map[string]queues.Sender{"document": mute{}},
		yes, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Sent) != 0 {
		t.Fatalf("an empty receipt was reported as sent: %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "ready" {
		t.Errorf("after an empty receipt the row is %q", row.State)
	}
	if row.Receipt != "" {
		t.Errorf("a row carries the receipt %q, which the service never gave",
			row.Receipt)
	}
}

// breakingSettle is a spool that cannot write the receipt down. THE DANGEROUS
// CASE: the remote has it and we could not record that it does. It must not be
// reported as sent, and the row must stay `sending`, which is exactly where
// Recover looks.
type breakingSettle struct {
	queues.Spool
	breakOn string
}

func (b *breakingSettle) Settle(id, state, at, receipt, errText string) error {
	if state == b.breakOn {
		return errors.New("the disk is full")
	}
	return b.Spool.Settle(id, state, at, receipt, errText)
}

func TestAnAcceptedItemWhoseReceiptCannotBeWrittenIsNotReportedAsSent(t *testing.T) {
	inner := newSpool(t)
	s := &breakingSettle{Spool: inner, breakOn: "sent"}
	item := enqueueOne(t, s, "enc-4", "enc-4")
	sender := &counting{}

	report, err := queues.Pump(s, map[string]queues.Sender{"document": sender},
		yes, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Sent) != 0 {
		t.Fatalf("an item nobody could record was reported as sent: %+v", report)
	}
	if len(report.Unrecorded) != 1 {
		t.Fatalf("the dangerous case was not reported on its own: %+v", report)
	}
	row, _, _ := inner.Get(item.ID)
	if row.State != "sending" {
		t.Errorf("the row is %q; it must stay `sending`, because that is where "+
			"recovery looks and where the remote's own answer settles it "+
			"without a second send", row.State)
	}

	// And recovery completes it from the remote's own answer, ONCE. This is the
	// whole of the not-sent-twice property: the remote is asked rather than
	// guessed about.
	rec, err := queues.Recover(inner, map[string]queues.Sender{"document": sender},
		later, queues.InFlightSeconds, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(rec.Sent) != 1 {
		t.Fatalf("recovery did not settle it: %+v", rec)
	}
	if len(sender.sent) != 1 {
		t.Errorf("the item was handed over %d times; a national record filed "+
			"twice is about a real person", len(sender.sent))
	}
	row, _, _ = inner.Get(item.ID)
	if row.State != "sent" || row.Receipt != "r-enc-4" {
		t.Errorf("after recovery the row is %+v", row)
	}
}

// ------------------------------------------------------------- recovery

// `held` is the honest third answer and the only one that is not automatic. A
// remote that CANNOT SAY is not a remote that says no: acting on that confusion
// is how a national record gets filed twice.
func TestARemoteThatCannotSayHoldsTheItemInsteadOfGuessing(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-5", "enc-5")
	if err := s.Settle(item.ID, "sending", now, "", ""); err != nil {
		t.Fatal(err)
	}
	report, err := queues.Recover(s, map[string]queues.Sender{"document": silent{}},
		later, queues.InFlightSeconds, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Held) != 1 || report.Held[0].Item != item.ID {
		t.Fatalf("a remote that cannot say produced %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "held" {
		t.Errorf("the row is %q, want held: not retried, not discarded, visible",
			row.State)
	}
}

func TestARemoteThatDoesNotHaveItTriesAgainRatherThanHolding(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-6", "enc-6")
	if err := s.Settle(item.ID, "sending", now, "", ""); err != nil {
		t.Fatal(err)
	}
	report, err := queues.Recover(s, map[string]queues.Sender{"document": &counting{}},
		later, queues.InFlightSeconds, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Sent) != 0 || len(report.Failed) != 1 {
		t.Fatalf("a remote that does not have it must try again, not hold: %+v",
			report)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "ready" {
		t.Errorf("the row is %q, want ready", row.State)
	}
}

// A sender that cannot be asked at all is the same answer as one that cannot
// say: nobody may resend it.
func TestWithNoSenderToAskNobodyMayResend(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-7", "enc-7")
	if err := s.Settle(item.ID, "sending", now, "", ""); err != nil {
		t.Fatal(err)
	}
	report, err := queues.Recover(s, nil, later, queues.InFlightSeconds,
		queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Held) != 1 {
		t.Fatalf("with nothing to ask, the item went %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "held" {
		t.Errorf("the row is %q, want held", row.State)
	}
}

// ------------------------------------------------- bounded, and visible

func TestAnItemOnADeadLineStopsVisiblyRatherThanRetryingForever(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-8", "enc-8")
	senders := map[string]queues.Sender{"document": dead{}}

	// Each sweep is told a moment far enough past the last claim that the
	// backoff is spent, so what is being measured is the attempt limit and not
	// the clock.
	clock := []string{
		"2026-11-01T10:00:00+00:00", "2026-11-01T11:00:00+00:00",
		"2026-11-01T12:00:00+00:00", "2026-11-01T13:00:00+00:00",
		"2026-11-01T14:00:00+00:00", "2026-11-01T15:00:00+00:00",
		"2026-11-01T16:00:00+00:00", "2026-11-01T17:00:00+00:00",
	}
	stopped := false
	for _, at := range clock {
		report, err := queues.Pump(s, senders, yes, bodies, at, 50,
			queues.MaxAttempts, nil)
		if err != nil {
			t.Fatal(err)
		}
		if len(report.Stopped) > 0 {
			stopped = true
			break
		}
	}
	if !stopped {
		t.Fatalf("an item on a dead line never stopped in %d sweeps", len(clock))
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "failed" {
		t.Errorf("a stopped item is in %q, want failed", row.State)
	}
	if row.Attempts != queues.MaxAttempts {
		t.Errorf("it stopped after %d attempts, want %d", row.Attempts,
			queues.MaxAttempts)
	}
	if row.LastError == "" {
		t.Error("a stopped item carries no reason, so stopping is a silence " +
			"rather than a state")
	}
	// And a stopped item stays stopped: neither retried nor thrown away.
	before := row.Attempts
	if _, err := queues.Pump(s, senders, yes, bodies,
		"2026-11-02T10:00:00+00:00", 50, queues.MaxAttempts, nil); err != nil {
		t.Fatal(err)
	}
	after, found, _ := s.Get(item.ID)
	if !found {
		t.Fatal("a stopped item was thrown away")
	}
	if after.State != "failed" || after.Attempts != before {
		t.Errorf("a stopped item was tried again: %+v", after)
	}
}

func TestTheFirstRetryIsImmediateAndLaterOnesWaitOutABackoff(t *testing.T) {
	if queues.Backoff(0) != 0 {
		t.Errorf("Backoff(0) = %d, want 0", queues.Backoff(0))
	}
	if queues.Backoff(1) != 0 {
		t.Errorf("the first retry is not immediate: %d", queues.Backoff(1))
	}
	last := 0
	for n := 2; n <= len(queues.BackoffSeconds); n++ {
		got := queues.Backoff(n)
		if got <= last {
			t.Errorf("Backoff(%d) = %d, which does not grow past %d", n, got, last)
		}
		last = got
	}
	// Past the table it is the ceiling, not an index out of range.
	if queues.Backoff(99) != queues.BackoffSeconds[len(queues.BackoffSeconds)-1] {
		t.Errorf("Backoff(99) = %d, want the ceiling", queues.Backoff(99))
	}

	// And an item inside its backoff is not due. TWO sweeps, because the first
	// retry is immediate: Backoff(1) is 0, so an item that has been tried once
	// is due again at once and the gate only exists from the second attempt.
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-9", "enc-9")
	for n := 0; n < 2; n++ {
		if _, err := queues.Pump(s, map[string]queues.Sender{"document": dead{}},
			yes, bodies, now, 50, queues.MaxAttempts, nil); err != nil {
			t.Fatal(err)
		}
	}
	row, _, _ := s.Get(item.ID)
	if row.Attempts != 2 {
		t.Fatalf("two sweeps produced %d attempts, so the first retry was not "+
			"immediate", row.Attempts)
	}
	// One second later the third attempt's backoff has not been waited out.
	due, err := queues.Due(s, "2026-11-01T10:00:01+00:00", 50, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 0 {
		t.Errorf("an item inside its backoff was due: %+v", due)
	}
	due, err = queues.Due(s, "2026-11-01T10:05:00+00:00", 50, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 1 {
		t.Errorf("an item past its backoff was not due")
	}
}

// Deliberately NOT a place that asks whether this centre may send the item: a
// plugin that is off denies and does not hide, and an item filtered out here
// would sit in `ready` forever with nothing written down.
func TestDueDoesNotFilterOnAuthorisation(t *testing.T) {
	s := newSpool(t)
	enqueueOne(t, s, "enc-10", "enc-10")
	due, err := queues.Due(s, now, 50, queues.MaxAttempts)
	if err != nil {
		t.Fatal(err)
	}
	if len(due) != 1 {
		t.Fatalf("Due returned %d items", len(due))
	}
	// The one place authorisation happens is the permit, and when it denies,
	// the denial is WRITTEN DOWN.
	report, err := queues.Pump(s, map[string]queues.Sender{"document": &counting{}},
		no, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Refused) != 1 || report.Refused[0].Why == "" {
		t.Errorf("a denial was not written down with a reason: %+v", report)
	}
}

// ------------------------------------------------------------- the row

// The privacy decision, read from kernel/queues.py's own prose and carried: a
// failure sentence reaching this row carries no Aadhaar number, no OTP, and no
// mobile number beyond its last four digits.
func TestAFailureSentenceCarriesNoIdentifier(t *testing.T) {
	cases := []struct {
		label     string
		raw       string
		forbidden []string
		expected  string
	}{
		{"aadhaar", "Aadhaar 1234 5678 9012 is already linked",
			[]string{"1234 5678 9012", "123456789012"}, queues.AadhaarMark},
		{"aadhaar, unspaced", "linking 123456789012 failed",
			[]string{"123456789012"}, queues.AadhaarMark},
		{"mobile", "no profile for mobile 9876543210",
			[]string{"9876543210"}, "ending 3210"},
		{"mobile with a country code", "+91 98765 43210 is unknown",
			[]string{"9876543210", "98765 43210"}, "ending 3210"},
		{"otp", "OTP 123456 has expired, request another",
			[]string{"123456"}, queues.OTPMark},
		{"one time password", "the one-time password 4821 was wrong",
			[]string{"4821"}, queues.OTPMark},
	}
	for _, one := range cases {
		out := queues.Scrubbed(one.raw)
		for _, bad := range one.forbidden {
			if strings.Contains(out, bad) {
				t.Errorf("%s: %q survived the scrubber in %q", one.label, bad, out)
			}
		}
		if !strings.Contains(out, one.expected) {
			t.Errorf("%s: %q does not carry %q", one.label, out, one.expected)
		}
	}

	// An Aadhaar number is removed WHOLE, not reduced to four digits: four
	// digits of an Aadhaar number is still four digits of an Aadhaar number.
	// This is why the Aadhaar rule runs before the mobile one.
	out := queues.Scrubbed("Aadhaar 1234 5678 9012 refused")
	if strings.Contains(out, "ending 9012") {
		t.Errorf("an Aadhaar number was treated as a phone number and kept "+
			"its last four: %q", out)
	}

	// A long remote body cannot arrive whole through the error field.
	if n := len(queues.Scrubbed(strings.Repeat("x", 5000))); n > queues.ErrorChars {
		t.Errorf("a response body of %d characters reached the row", n)
	}

	// A number that is not ten digits is not a mobile and is left alone,
	// because a redactor that eats identifiers a person needs to read is a
	// redactor people route around.
	for _, keep := range []string{"status 404 on session scr-1",
		"token 12345678", "systolic 140"} {
		if queues.Scrubbed(keep) != keep {
			t.Errorf("%q was changed to %q", keep, queues.Scrubbed(keep))
		}
	}
}

// The Python's mobile pattern has a lookbehind and a lookahead and Go's RE2 has
// neither. They are dropped rather than approximated, and the reasoning that
// makes that sound is asserted here rather than left in a comment, because the
// reasoning is the thing most likely to be wrong.
func TestTheMobileRuleIsNotTrickedByAdjacentDigits(t *testing.T) {
	// THE PROPERTY THE TWO LOOKAROUNDS PROTECT, stated as the thing that must
	// be true of the OUTPUT rather than as the thing the pattern does: no run
	// of ten or more digits survives anywhere in a scrubbed sentence. A match
	// that began or ended in the middle of a digit run would leave one, which
	// is exactly what (?<!\d) and (?!\d) are there to stop.
	tenPlus := regexp.MustCompile(`\d{10,}`)
	for _, raw := range []string{
		"no profile for mobile 9876543210",
		"+91 98765 43210 is unknown",
		"id 123456789012345 refused",
		"ref 98765432109876543210 refused",
		"x9876543210y",
		"9876543210",
		"call 9876543210 or 9123456780 back",
		"Aadhaar 1234 5678 9012 is already linked",
		"linking 123456789012 failed",
	} {
		out := queues.Scrubbed(raw)
		// The digits of the output with the separators taken out, because the
		// Python's pattern treats "98765 43210" as one number and so does
		// this one: a run broken only by spaces is still a run.
		runs := strings.NewReplacer(" ", "", "-", "", "+", "").Replace(out)
		if found := tenPlus.FindString(runs); found != "" {
			t.Errorf("scrubbing %q left the %d digit run %q in %q",
				raw, len(found), found, out)
		}
	}

	// And a number too short to be a mobile is left alone, so the rule has not
	// simply been widened until it eats everything.
	for _, keep := range []string{"token 12345678", "year 2026", "systolic 140"} {
		if queues.Scrubbed(keep) != keep {
			t.Errorf("%q was changed to %q", keep, queues.Scrubbed(keep))
		}
	}
}

// A sender that fails with something that is not an Unsendable is still just a
// failure, and THE TYPE NAME IS ALL THAT IS KEPT: an arbitrary failure's text
// on this path is a response body, and a response body here is a consultation.
func TestAnUnexpectedFailureIsRecordedByTypeAloneAndCarriesNoBody(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-11", "enc-11")
	report, err := queues.Pump(s, map[string]queues.Sender{"document": leaky{}},
		yes, bodies, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Failed) != 1 {
		t.Fatalf("an unexpected failure produced %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	for _, leaked := range []string{"Asha Devi", "hypertension", "9876543210"} {
		if strings.Contains(row.LastError, leaked) {
			t.Errorf("%q reached the outbox row: %q", leaked, row.LastError)
		}
	}
	if !strings.Contains(row.LastError, "the service failed with") {
		t.Errorf("the row does not name a kind of failure: %q", row.LastError)
	}
}

// A body that will not build is not a line failure: no number of retries fixes
// it, so it comes back as an Unsendable and the attempt counter stops it.
func TestABodyThatWillNotBuildIsAFailureAndNothingIsSent(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-12", "enc-12")
	sender := &counting{}
	report, err := queues.Pump(s, map[string]queues.Sender{"document": sender},
		yes, func(queues.Item) (any, error) {
			return nil, queues.Unsendablef("this visit cannot be published: " +
				"it has no subject")
		}, now, 50, queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Failed) != 1 || len(report.Sent) != 0 {
		t.Fatalf("a body that would not build produced %+v", report)
	}
	if len(sender.sent) != 0 {
		t.Error("the remote was handed an item whose body did not build")
	}
	row, _, _ := s.Get(item.ID)
	if !strings.Contains(row.LastError, "no subject") {
		t.Errorf("the row does not say why: %q", row.LastError)
	}
}

func TestNothingConfiguredToSendAKindIsAFailureAndNotASilence(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-13", "enc-13")
	report, err := queues.Pump(s, nil, yes, bodies, now, 50,
		queues.MaxAttempts, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Failed) != 1 {
		t.Fatalf("with nothing configured the item went %+v", report)
	}
	row, _, _ := s.Get(item.ID)
	if !strings.Contains(row.LastError, "nothing is configured") {
		t.Errorf("the row does not say why: %q", row.LastError)
	}
}

// ---------------------------------------------- the recording's own bytes

// After the receipt, NEVER BEFORE. A recording deleted before the receipt is
// written is a recording lost to a crash in between.
func TestARecordingIsDeletedAfterTheReceiptAndNotBefore(t *testing.T) {
	s := newSpool(t)
	item, err := queues.Enqueue(s, queues.Enqueued{
		Kind: "audio", Key: "t-20", Thread: "enc-20",
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", At: now, Blob: "/tmp/phc-test-recording.bin"})
	if err != nil {
		t.Fatal(err)
	}

	// A line that is down must not delete anything.
	var dropped []string
	drop := func(path string) error { dropped = append(dropped, path); return nil }
	if _, err := queues.Pump(s, map[string]queues.Sender{"audio": dead{}},
		yes, bodies, now, 50, queues.MaxAttempts, drop); err != nil {
		t.Fatal(err)
	}
	if len(dropped) != 0 {
		t.Fatalf("a recording was deleted after a FAILED send: %v", dropped)
	}

	// And a receipt deletes it, once.
	if err := s.Settle(item.ID, "ready", now, "", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := queues.Pump(s, map[string]queues.Sender{"audio": &counting{}},
		yes, bodies, "2026-11-01T12:00:00+00:00", 50, queues.MaxAttempts,
		drop); err != nil {
		t.Fatal(err)
	}
	if len(dropped) != 1 || dropped[0] != "/tmp/phc-test-recording.bin" {
		t.Errorf("after a receipt the recording was dropped %v", dropped)
	}
}

// An item whose bytes are deleted by the retention backstop is NOT marked
// sent, because it was not. It stops in `failed` saying the recording aged out,
// which is the honest record.
func TestARecordingHeldPastTheBackstopIsDeletedAndNotCalledSent(t *testing.T) {
	s := newSpool(t)
	item, err := queues.Enqueue(s, queues.Enqueued{
		Kind: "audio", Key: "t-21", Thread: "enc-21",
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", At: now, Blob: "/tmp/phc-old-recording.bin"})
	if err != nil {
		t.Fatal(err)
	}
	var dropped []string
	drop := func(path string) error { dropped = append(dropped, path); return nil }

	// Not yet.
	gone, err := queues.SweepAudio(s, "2026-11-01T11:00:00+00:00", drop,
		queues.AudioMaxHoldSeconds)
	if err != nil {
		t.Fatal(err)
	}
	if len(gone) != 0 || len(dropped) != 0 {
		t.Fatalf("a recording was swept before the backstop: %v", gone)
	}

	// Past it.
	gone, err = queues.SweepAudio(s, "2026-11-02T10:00:00+00:00", drop,
		queues.AudioMaxHoldSeconds)
	if err != nil {
		t.Fatal(err)
	}
	if len(gone) != 1 || gone[0] != item.ID {
		t.Fatalf("the swept items are %v", gone)
	}
	row, _, _ := s.Get(item.ID)
	if row.State != "failed" {
		t.Errorf("an aged out recording is in %q, want failed: nobody got a "+
			"transcript, so it was not sent", row.State)
	}
	if row.Receipt != "" {
		t.Error("an aged out recording carries a receipt")
	}
	if !strings.Contains(row.LastError, "retention backstop") {
		t.Errorf("the row does not say why: %q", row.LastError)
	}

	// AND IT IS NOT REPORTED TWICE. Settling moves an item into `failed`,
	// which is one of the states the sweep walks, so listing and settling in
	// one loop found the same recording twice. The Python's check caught that;
	// this is what fails if it comes back.
	dropped = nil
	gone, err = queues.SweepAudio(s, "2026-11-02T11:00:00+00:00", drop,
		queues.AudioMaxHoldSeconds)
	if err != nil {
		t.Fatal(err)
	}
	if len(gone) > 1 {
		t.Errorf("one recording was reported deleted %d times: %v", len(gone), gone)
	}
}

// ------------------------------------------------------------ legibility

// A queue that retries forever is a defect and so is one that gives up
// quietly, so the whole outbox reads as sentences a person can act on. Correct
// at nought and at one as well as at twelve.
func TestTheOutboxReadsAsSentencesAtNoughtOneAndTwelve(t *testing.T) {
	empty := newSpool(t)
	standing, err := queues.Status(empty, 2000)
	if err != nil {
		t.Fatal(err)
	}
	if got := standing.Lines(); !reflect.DeepEqual(got,
		[]string{"nothing is waiting to be sent"}) {
		t.Errorf("an empty outbox reads %q", got)
	}

	one := newSpool(t)
	if _, err := queues.Enqueue(one, queues.Enqueued{
		Kind: "audio", Key: "t-1", Thread: "enc-1",
		Operation: "phc.op.consult-document", Capability: "encounter.document",
		Facility: "all-plugins", At: now}); err != nil {
		t.Fatal(err)
	}
	standing, _ = queues.Status(one, 2000)
	if got := standing.Lines(); !reflect.DeepEqual(got,
		[]string{"1 recording waiting for the line"}) {
		t.Errorf("one recording reads %q", got)
	}

	for n := 0; n < 11; n++ {
		if _, err := queues.Enqueue(one, queues.Enqueued{
			Kind: "audio", Key: fmt.Sprintf("t-%d", n+2), Thread: "enc-1",
			Operation:  "phc.op.consult-document",
			Capability: "encounter.document", Facility: "all-plugins",
			At: now}); err != nil {
			t.Fatal(err)
		}
	}
	standing, _ = queues.Status(one, 2000)
	if got := standing.Lines(); !reflect.DeepEqual(got,
		[]string{"12 recordings waiting for the line"}) {
		t.Errorf("twelve recordings read %q", got)
	}
}

// A stopped item says how many times it was tried, which is the whole of the
// "visible, not forever" requirement.
func TestAStoppedItemSaysHowManyTimesItWasTried(t *testing.T) {
	s := newSpool(t)
	item := enqueueOne(t, s, "enc-30", "enc-30")
	// Straight to the end, so what is measured is the sentence rather than the
	// clock.
	for n := 0; n < queues.MaxAttempts; n++ {
		if _, _, err := s.Claim(item.ID, now); err != nil {
			t.Fatal(err)
		}
		if err := s.Settle(item.ID, "ready", now, "", "there is no line"); err != nil {
			t.Fatal(err)
		}
	}
	if err := s.Settle(item.ID, "failed", now, "", "there is no line"); err != nil {
		t.Fatal(err)
	}
	standing, err := queues.Status(s, 2000)
	if err != nil {
		t.Fatal(err)
	}
	lines := strings.Join(standing.Lines(), " | ")
	if !strings.Contains(lines, "failed and stopped") {
		t.Errorf("a stopped national record does not read as stopped: %q", lines)
	}
	if !strings.Contains(lines, fmt.Sprintf("after %d attempts", queues.MaxAttempts)) {
		t.Errorf("it does not say how many times it was tried: %q", lines)
	}
}

func TestOneOfEachStateReadsInItsOwnWords(t *testing.T) {
	s := newSpool(t)
	for i, state := range []string{"refused", "held"} {
		item := enqueueOne(t, s, fmt.Sprintf("enc-4%d", i), fmt.Sprintf("enc-4%d", i))
		if err := s.Settle(item.ID, state, now, "", "a reason"); err != nil {
			t.Fatal(err)
		}
	}
	standing, _ := queues.Status(s, 2000)
	lines := strings.Join(standing.Lines(), " | ")
	for _, want := range []string{"refused by the guard", "waiting for somebody to decide"} {
		if !strings.Contains(lines, want) {
			t.Errorf("the outbox does not say %q: %q", want, lines)
		}
	}
}
