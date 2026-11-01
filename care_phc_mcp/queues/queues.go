// Package queues is kernel/queues.py: audio and national records wait for the
// line, and never drop.
//
// The problem, in one paragraph
// -----------------------------
// A primary health centre's internet comes and goes. A consultation is
// recorded while the line is down and the recording must still reach the
// speech service. A visit ends while the line is down and its national
// document must still reach ABDM. The product's premise is that the point of
// care keeps working, so this is not a convenience bolted on at the end: it is
// what makes the rest true.
//
// Four properties, each one separate
// ----------------------------------
//  1. DURABLE. The claim is on disk before Claim returns, so the outbox
//     survives the process. That is the spool's and it is proved against a
//     real file by a real process killed with SIGKILL.
//  2. NOTHING IS LOST. An attempt is claimed durably BEFORE it is sent, so a
//     crash mid-send leaves the item in `sending` rather than back in `ready`
//     or gone. Recover picks those up.
//  3. NOTHING IS SENT TWICE. Every item carries a Key WE supply, not one the
//     remote mints, so one item asked for twice is one job on their side. And
//     recovery never resends blind: it asks the remote what it already has
//     (Sender.Delivered), and an item the remote cannot speak for is parked in
//     `held` for a person rather than guessed about.
//  4. NOTHING IS REPORTED AS SENT WHEN IT WAS NOT. `sent` is written only
//     after a receipt comes back, and if the receipt cannot be written down
//     the item stays `sending` and is reported as a failure of that sweep. It
//     does not become `sent` on the strength of a send nobody recorded.
//
// Where the bodies come from, and why documents keep none here
// ------------------------------------------------------------
//   - A DOCUMENT keeps no body. The rows in the Store are the record, and the
//     bundle is re-projected at the moment of sending, through the bundle's own
//     `documents:` declaration. So there is no second copy to drift, nothing
//     clinical is written to the outbox, and a correction made while the item
//     waited is in the document that finally leaves.
//   - AUDIO keeps its bytes, because they exist nowhere else. A recording is
//     not derivable from anything, which is exactly why losing it is
//     unrecoverable.
//
// What is in the outbox row, which is the privacy decision
// --------------------------------------------------------
// Identifiers and state. No name, no mobile number, no Aadhaar number, no OTP,
// no answer a clinician typed, and for a document no body at all. The one free
// text field is LastError and Scrubbed is the only writer of it.
//
// THAT DECISION IS READ FROM kernel/queues.py's OWN PROSE AND CARRIED. It is
// not re-derived here and this package is not the place it is argued.
//
// Still switched off by default, and that is not this package's call
// -----------------------------------------------------------------
// kernel/queues.py is complete and proved and api/scribe.py does not call it,
// because wiring it in contradicts three sentences that file states as rules
// and because surviving an outage MEANS holding the recording. The retention
// window that would make it safe is unsigned. The Go side is wired in exactly
// as far: nothing in cmd/api calls Pump, no route reaches this package, and
// flipping that over is a person's decision in the order the Python names,
// which is sign the retention window and then wire the route.
//
// Pure: everything takes a Spool, a Sender and a clock, and returns values.
// Opens no socket, reads no environment except the spool root, imports no
// connector.
package queues

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// --------------------------------------------------------------------------
// Settings. Every number here is a guess and is labelled as one, exactly as
// kernel/queues.py labels its own.
// --------------------------------------------------------------------------

// MaxAttempts is how many times an item is tried before it stops in `failed`.
// Six, so that with the backoff below an item queued at the start of a clinic
// session is still being tried at the end of it and has stopped long before a
// week of them pile up. NOT MEASURED against a real primary health centre's
// line. A deployment that has measured one should raise or lower it and say
// what it measured.
const MaxAttempts = 6

// BackoffSeconds is the wait before attempt n, by how many attempts have
// already been made. Doubling, with a ceiling, so a dead line is not hammered
// and a line that flickers back is used within a minute. AGAIN, NOT MEASURED.
var BackoffSeconds = []int{0, 30, 120, 600, 1800, 3600}

// InFlightSeconds is how long an item may sit in `sending` before Recover
// considers it abandoned rather than in flight. Longer than any single send
// should take and shorter than a clinic session. A GUESS.
const InFlightSeconds = 900

// SpoolEnv and SpoolDefault are where the audio waits. Outside the repository,
// deliberately and not incidentally: a consultation recording is identifiable
// health data and a source tree is copied, zipped and pushed. Overridden per
// deployment, which is where the answer actually belongs, because a facility's
// disk encryption and its backup policy are the things that make this safe and
// neither is ours to choose.
const (
	SpoolEnv     = "PHC_SPOOL"
	SpoolDefault = "~/.local/share/phc/spool"
)

// SpoolDirMode and SpoolFileMode are the owner only. A clinic machine has more
// than one account on it.
const (
	SpoolDirMode  os.FileMode = 0o700
	SpoolFileMode os.FileMode = 0o600
)

// SpoolRoot is where recordings wait. Never under the repository.
func SpoolRoot() string {
	where := os.Getenv(SpoolEnv)
	if where == "" {
		where = SpoolDefault
	}
	if where == "~" || (len(where) > 1 && where[:2] == "~"+string(os.PathSeparator)) {
		if home, err := os.UserHomeDir(); err == nil {
			where = filepath.Join(home, where[1:])
		}
	}
	out, err := filepath.Abs(where)
	if err != nil {
		return where
	}
	return out
}

// --------------------------------------------------------------------------
// The seam: what sends one item
// --------------------------------------------------------------------------

// Unsendable is the line was down, the remote refused, or the body would not
// build.
//
// Scrubbed by Pump before it is written down, never before: a sender returns
// whatever sentence it has and this package is the one filter, so a new sender
// cannot forget to scrub.
type Unsendable struct{ Why string }

func (u *Unsendable) Error() string { return u.Why }

// Unsendablef is the one constructor, so a call site cannot build one with a
// sentence it has already written somewhere else.
func Unsendablef(format string, args ...any) *Unsendable {
	return &Unsendable{Why: fmt.Sprintf(format, args...)}
}

func asUnsendable(err error) (*Unsendable, bool) {
	var u *Unsendable
	if errors.As(err, &u) {
		return u, true
	}
	return nil, false
}

// Delivery is what a remote can tell us about something we may already have
// sent.
//
// THREE ANSWERS AND NOT TWO, and the third is why this is a struct rather than
// a string. Known=false means the remote could not be asked or could not say,
// which is NOT the same as "it does not have it": acting on that confusion is
// how a national record gets filed twice. It is the same distinction
// DirectoryError.reachable draws and for the same reason.
//
//	Delivery{Known: false}                    cannot say. Nobody resends.
//	Delivery{Known: true, Receipt: ""}        definitely does not have it.
//	Delivery{Known: true, Receipt: "abc"}     has it, and calls it abc.
type Delivery struct {
	Known   bool
	Receipt string
}

// Delivered is true only when the remote both answered and named a receipt.
func (d Delivery) Delivered() bool { return d.Known && d.Receipt != "" }

// Sender is what the queue needs from whatever carries one kind of item away.
//
// Two methods, and the second is the one that makes property 3 provable. A
// sender with no Delivered can only guess after a crash, and a guess either
// loses the item or files it twice.
type Sender interface {
	// Send hands one item over and returns the remote's receipt, which must be
	// a non-empty string: a receipt is the evidence for writing `sent`, so an
	// empty one is treated as a failure rather than as a success nobody can
	// point at. Returns an *Unsendable for every failure.
	Send(item Item, body any) (string, error)

	// Delivered is what the remote already has under item.Key.
	//
	// For audio this is the scribe's own status endpoint on the transaction id
	// api/scribe.py supplies, so it is answerable today. FOR A NATIONAL
	// DOCUMENT IT IS NOT KNOWN what the equivalent is, and a sender that
	// cannot answer must return Delivery{Known: false} rather than a guess.
	// The item then waits in `held` for a person. That is a gap in what we
	// know about ABDM, not a gap in this design.
	Delivered(item Item) (Delivery, error)
}

// Decision is catalogue.guard.Decision's shape as this package needs it: the
// two fields Pump reads. Given rather than built here so this package imports
// no guard, no bundle and no store, and so the audit row the guard writes is
// written by whoever owns the audit trail.
type Decision interface {
	Allowed() bool
	Reason() string
}

// Permit is the authorisation question, asked once per item at the moment of
// sending. See PermitWithGuard in permit.go for the one that re-runs the
// guard.
type Permit func(item Item) Decision

// Bodies builds what is sent for one item, returning an *Unsendable when it
// cannot.
type Bodies func(item Item) (any, error)

// --------------------------------------------------------------------------
// Admission: a centre holds nothing for a plugin it does not run
// --------------------------------------------------------------------------

// Refusal is why this item may not be queued here, or "" if it may.
//
// Called at admission AND again inside the permit, which is not belt and
// braces: a facility's shape is read at start-up and an item can outlive the
// process that admitted it. An item admitted last week for a plugin this
// centre has since switched off must stop, and the only place that can be
// noticed is the moment somebody looks at it again.
func Refusal(kind, operation, capability string, withheld map[string]string) string {
	if !IsKind(kind) {
		return fmt.Sprintf("'%s' is not a kind of queued work", kind)
	}
	if plugin := withheld[capability]; plugin != "" {
		return fmt.Sprintf("capability %s withheld by plugin '%s': this "+
			"facility does not run it, so nothing is held for it",
			capability, plugin)
	}
	return ""
}

// Enqueued is what Enqueue needs told about one new item. A struct rather than
// eleven positional arguments, because the Python's call is all keywords and a
// Go call with eleven strings in a row is one transposition away from filing a
// capability as an operation.
type Enqueued struct {
	Kind       string
	Key        string
	Thread     string
	Operation  string
	Capability string
	Facility   string
	At         string
	Actor      string
	Blob       string
	Withheld   map[string]string
}

// NewID is how an item is named. Opaque, because the name reaches a directory
// listing: see Spool.Keep.
var NewID = func() string {
	return "q-" + randomHex(12)
}

// Enqueue puts one item in the outbox, or refuses it and keeps nothing.
//
// Refusing means refusing to HOLD it, which is stronger than refusing to send
// it: an item for a plugin this centre does not run leaves no row, no
// recording on disk and nothing for a person to wonder about. Returns an error
// rather than a zero item, because a caller that drops a recording on the
// floor without noticing is the failure this package exists to prevent.
func Enqueue(spool Spool, in Enqueued) (Item, error) {
	if why := Refusal(in.Kind, in.Operation, in.Capability, in.Withheld); why != "" {
		return Item{}, &Unsendable{Why: why}
	}
	if trimmed(in.Key) == "" {
		// The key is the whole of the not-sent-twice property, so an item
		// without one is refused rather than given a generated one: a key we
		// minted here and the remote never saw deduplicates nothing.
		return Item{}, Unsendablef("a queued item needs the key the remote " +
			"will know it by, and this one has none")
	}
	item := Item{ID: NewID(), Kind: in.Kind, Key: in.Key, Thread: in.Thread,
		Operation: in.Operation, Capability: in.Capability,
		Facility: in.Facility, CreatedAt: in.At, Actor: in.Actor,
		Blob: in.Blob, State: "ready"}
	if err := spool.Put(item); err != nil {
		return Item{}, err
	}
	return item, nil
}

// --------------------------------------------------------------------------
// What is due, and what is stuck
// --------------------------------------------------------------------------

// moment parses one of the row's timestamps, or reports that it cannot.
func moment(text string) (time.Time, bool) {
	for _, layout := range []string{
		time.RFC3339Nano, time.RFC3339,
		"2006-01-02T15:04:05.999999999", "2006-01-02T15:04:05",
		"2006-01-02 15:04:05.999999999-07:00", "2006-01-02 15:04:05-07:00",
		"2006-01-02 15:04:05.999999999", "2006-01-02 15:04:05",
		"2006-01-02",
	} {
		if when, err := time.Parse(layout, text); err == nil {
			// datetime.fromisoformat gives a naive moment when the string
			// carries no offset, and kernel/queues._moment then calls it UTC.
			// time.Parse on a layout with no offset gives UTC already, so the
			// two agree without a special case.
			return when, true
		}
	}
	return time.Time{}, false
}

// waited reports whether `seconds` passed between these two moments. An
// unreadable or missing timestamp counts as long enough: an item whose clock we
// cannot read must still move, and the alternative is an item that waits
// forever because of a bad string.
func waited(since, now string, seconds int) bool {
	start, okStart := moment(since)
	end, okEnd := moment(now)
	if !okStart || !okEnd {
		return true
	}
	return end.Sub(start) >= time.Duration(seconds)*time.Second
}

// Backoff is the wait owed after this many attempts. A guess; see the
// constant.
func Backoff(attempts int) int {
	if attempts <= 0 {
		return 0
	}
	n := attempts
	if n > len(BackoffSeconds) {
		n = len(BackoffSeconds)
	}
	return BackoffSeconds[n-1]
}

// Due is the items ready to try, oldest first. Two reasons one is not: it has
// had its limit of attempts, or it is still inside its backoff.
//
// DELIBERATELY NOT A PLACE THAT ASKS WHETHER THIS CENTRE MAY SEND THE ITEM.
// Dropping a withheld item here was the first shape of the Python's own
// function and it was wrong: a plugin that is off DENIES AND DOES NOT HIDE,
// with the capability and the plugin named in an audit row. An item filtered
// out here would instead sit in `ready` forever with nothing written down,
// which is both hiding and the silent giving up that this package is supposed
// to make impossible. So authorisation happens in exactly one place, the
// permit, and this function only answers "is a try owed yet".
func Due(spool Spool, now string, limit, maxAttempts int) ([]Item, error) {
	ask := limit * 4
	if ask < limit {
		ask = limit
	}
	ready, err := spool.Items("ready", "", ask)
	if err != nil {
		return nil, err
	}
	var out []Item
	for _, item := range ready {
		if item.Attempts >= maxAttempts {
			continue
		}
		if !IsKind(item.Kind) {
			continue
		}
		if item.Attempts > 0 && !waited(item.ClaimedAt, now, Backoff(item.Attempts)) {
			continue
		}
		out = append(out, item)
		if len(out) >= limit {
			break
		}
	}
	return out, nil
}

// Stuck is the items claimed and never settled: every crash mid-send lands
// here.
func Stuck(spool Spool, now string, seconds, limit int) ([]Item, error) {
	sending, err := spool.Items("sending", "", limit)
	if err != nil {
		return nil, err
	}
	var out []Item
	for _, item := range sending {
		if waited(item.ClaimedAt, now, seconds) {
			out = append(out, item)
		}
	}
	return out, nil
}

// --------------------------------------------------------------------------
// The pump
// --------------------------------------------------------------------------

// Outcome is one item's line in a Sweep: which item, and why.
type Outcome struct {
	Item string
	Why  string
}

// Sweep is what one pass did. `Failed` is not an error: an item that could not
// be sent stays in the answer and is tried again. `Unrecorded` is the dangerous
// one and is listed on its own, because an item the remote accepted and we
// could not write down is neither a success nor an ordinary failure.
type Sweep struct {
	Sent       []Outcome // Why is the receipt
	Failed     []Outcome
	Refused    []Outcome
	Stopped    []Outcome // reached the limit
	Held       []Outcome // nobody may guess
	Unrecorded []Outcome // accepted, not written
}

// Count is how many actually went.
func (s Sweep) Count() int { return len(s.Sent) }

// Pump is one pass over what is due. THE ORDER OF THE STEPS IS THE DESIGN.
//
// `senders` is kind -> Sender. There is no `withheld` argument: which plugins
// this centre runs is a question for the permit, and one authorisation check in
// one place is the whole reason the permit exists. `delete` removes a sent
// recording's bytes.
//
// Per item, in this order and not another:
//
//  1. THE GUARD, BEFORE THE CLAIM. An item the guard now denies becomes
//     `refused` without ever entering `sending`, so a denial costs no attempt
//     and leaves no in-flight row for Recover to reason about. A proposal is
//     judged against the world as it is when it is acted on, not as it was when
//     it was made; a queue is that problem with a longer gap.
//  2. CLAIM, durably. After this returns, a crash leaves `sending`.
//  3. Build the body. For a document this projects the visit as it stands.
//  4. Send.
//  5. Write the receipt. Only now is anything `sent`.
//  6. Delete the recording, after the receipt and never before.
func Pump(spool Spool, senders map[string]Sender, permit Permit, bodies Bodies,
	now string, limit, maxAttempts int, delete func(string) error) (Sweep, error) {

	report := Sweep{}
	due, err := Due(spool, now, limit, maxAttempts)
	if err != nil {
		return report, err
	}
	for _, item := range due {
		decision := permit(item)
		if decision == nil || !decision.Allowed() {
			reason := "refused"
			if decision != nil && decision.Reason() != "" {
				reason = decision.Reason()
			}
			if err := spool.Settle(item.ID, "refused", now, "", Scrubbed(reason)); err != nil {
				return report, err
			}
			report.Refused = append(report.Refused, Outcome{item.ID, Scrubbed(reason)})
			continue
		}

		claimed, took, err := spool.Claim(item.ID, now)
		if err != nil {
			return report, err
		}
		if !took {
			continue // another pump took it
		}

		sender, configured := senders[claimed.Kind]
		if !configured || sender == nil {
			if err := giveUp(spool, &report, claimed, now,
				fmt.Sprintf("nothing is configured to send a %s item", claimed.Kind),
				maxAttempts); err != nil {
				return report, err
			}
			continue
		}

		body, err := bodies(claimed)
		if err == nil {
			var receipt string
			receipt, err = sender.Send(claimed, body)
			if err == nil {
				if trimmed(receipt) == "" {
					// Property 4, at its sharpest. A send that came back with
					// nothing to point at is not a success: there is no
					// evidence, so there is no `sent`.
					if err := giveUp(spool, &report, claimed, now,
						"the service accepted nothing and returned no receipt",
						maxAttempts); err != nil {
						return report, err
					}
					continue
				}
				if err := spool.Settle(claimed.ID, "sent", now, receipt, ""); err != nil {
					// THE DANGEROUS CASE, and the reason this is not a bare
					// call. The remote has it and we could not write down that
					// it does. It is NOT reported as sent, and the row stays
					// `sending`, which is exactly where Recover looks and where
					// Delivered will settle it without a second send. Reported
					// rather than returned: returning would also throw away the
					// record of everything this sweep already sent.
					report.Unrecorded = append(report.Unrecorded, Outcome{
						claimed.ID,
						Scrubbed(fmt.Sprintf("the service accepted it as %s and "+
							"the receipt could not be written: %s", receipt, err)),
					})
					continue
				}
				report.Sent = append(report.Sent, Outcome{claimed.ID, receipt})
				if claimed.Blob != "" && delete != nil {
					// After the receipt, never before. A recording deleted
					// before the receipt is written is a recording lost to a
					// crash in between.
					_ = delete(claimed.Blob)
				}
				continue
			}
		}
		// One failure path for the body and the send, because the Python has
		// one: both are inside the same try and both end in _give_up.
		why := ""
		if unsendable, is := asUnsendable(err); is {
			why = unsendable.Why
		} else {
			why = fmt.Sprintf("the service failed with %s", typeName(err))
		}
		if err := giveUp(spool, &report, claimed, now, why, maxAttempts); err != nil {
			return report, err
		}
	}
	return report, nil
}

// giveUp ends one failed attempt: back to `ready`, or stop in `failed`.
//
// Stopping is a state, not a silence. The item stays in the outbox with its
// attempt count and its last reason on it, so Status can say that one recording
// has failed six times and stopped, which is the whole of the "visible, not
// forever" requirement.
func giveUp(spool Spool, report *Sweep, item Item, now, why string,
	maxAttempts int) error {

	text := Scrubbed(why)
	if item.Attempts >= maxAttempts {
		if err := spool.Settle(item.ID, "failed", now, "", Scrubbed(why)); err != nil {
			return err
		}
		report.Stopped = append(report.Stopped, Outcome{item.ID, text})
		return nil
	}
	if err := spool.Settle(item.ID, "ready", now, "", Scrubbed(why)); err != nil {
		return err
	}
	report.Failed = append(report.Failed, Outcome{item.ID, text})
	return nil
}

// --------------------------------------------------------------------------
// Recovery: what a crash left behind
// --------------------------------------------------------------------------

// Recover settles everything a crash left in `sending`, by asking the remote.
//
// THIS IS THE WHOLE OF PROPERTY 3. The naive recovery is to put a stuck item
// back in `ready`, and that sends anything the remote already took a second
// time, which for a national health record means a duplicate document about a
// real person. So nothing is resent on the strength of our own ignorance:
//
//	the remote has it        -> `sent`, with the receipt it gives
//	the remote does not      -> `ready`, to be tried again
//	the remote cannot say    -> `held`. Not retried, not discarded, visible.
//
// `held` is the honest third answer and the only one that is not automatic. It
// means a person has to look, and for a national document that is the right
// answer today, because what ABDM's equivalent of "do you already have this?"
// is has not been established here.
func Recover(spool Spool, senders map[string]Sender, now string,
	seconds, maxAttempts int) (Sweep, error) {

	report := Sweep{}
	stuck, err := Stuck(spool, now, seconds, 200)
	if err != nil {
		return report, err
	}
	for _, item := range stuck {
		sender, configured := senders[item.Kind]
		if !configured || sender == nil {
			why := fmt.Sprintf("nothing is configured to say whether a %s item "+
				"was delivered, so nobody may resend it", item.Kind)
			if err := spool.Settle(item.ID, "held", now, "", Scrubbed(why)); err != nil {
				return report, err
			}
			report.Held = append(report.Held, Outcome{item.ID, Scrubbed(why)})
			continue
		}
		answer, askErr := sender.Delivered(item)
		why := "the service cannot say whether it already has this"
		if askErr != nil {
			answer = Delivery{}
			why = fmt.Sprintf("asking whether it was delivered failed with %s",
				typeName(askErr))
		}
		switch {
		case !answer.Known:
			if err := spool.Settle(item.ID, "held", now, "", Scrubbed(why)); err != nil {
				return report, err
			}
			report.Held = append(report.Held, Outcome{item.ID, Scrubbed(why)})
		case answer.Delivered():
			if err := spool.Settle(item.ID, "sent", now, answer.Receipt, ""); err != nil {
				return report, err
			}
			report.Sent = append(report.Sent, Outcome{item.ID, answer.Receipt})
		case item.Attempts >= maxAttempts:
			if err := spool.Settle(item.ID, "failed", now, "",
				Scrubbed("the service does not have it and the attempt limit "+
					"is spent")); err != nil {
				return report, err
			}
			report.Stopped = append(report.Stopped, Outcome{item.ID,
				"the attempt limit is spent"})
		default:
			if err := spool.Settle(item.ID, "ready", now, "",
				Scrubbed("interrupted before the service answered; it does "+
					"not have it")); err != nil {
				return report, err
			}
			report.Failed = append(report.Failed, Outcome{item.ID,
				"interrupted before it was sent"})
		}
	}
	return report, nil
}

// --------------------------------------------------------------------------
// Retention: audio that nobody ever came back for
// --------------------------------------------------------------------------

// AudioMaxHoldSeconds is care_phc/connectors/scribe/base.AUDIO_MAX_HOLD_SECONDS,
// carried here because this package has no connector to import and may not grow
// one. SIX HOURS, AND UNSIGNED: that file's own sentence is that how long
// unconfirmed consultation audio may be kept has no clinical or legal sign-off,
// and copying the number does not sign it.
const AudioMaxHoldSeconds = 6 * 60 * 60

// SweepAudio deletes recordings held longer than the retention backstop allows.
//
// An item whose bytes are deleted this way is NOT marked sent, because it was
// not. It stops in `failed` saying the recording aged out, which is the honest
// record: the audio is gone, nobody got a transcript, and the note was typed or
// it was not.
func SweepAudio(spool Spool, now string, delete func(string) error,
	maxHold int) ([]string, error) {

	if maxHold <= 0 {
		maxHold = AudioMaxHoldSeconds
	}
	// EVERY CANDIDATE IS LISTED BEFORE ANY OF THEM IS SETTLED. Settling moves
	// an item into `failed`, which is one of the states being walked, so
	// listing and settling in the same loop found the same recording twice and
	// reported it deleted twice. The Python's check caught exactly that.
	var waiting []Item
	for _, state := range []string{"ready", "held", "failed"} {
		rows, err := spool.Items(state, "audio", 500)
		if err != nil {
			return nil, err
		}
		for _, item := range rows {
			if item.Blob != "" && waited(item.CreatedAt, now, maxHold) {
				waiting = append(waiting, item)
			}
		}
	}
	gone := []string{}
	for _, item := range waiting {
		if delete != nil {
			if err := delete(item.Blob); err != nil {
				continue
			}
		}
		if item.State != "failed" {
			if err := spool.Settle(item.ID, "failed", now, "",
				"the recording was held longer than the retention backstop "+
					"allows and was deleted without being transcribed"); err != nil {
				return nil, err
			}
		}
		gone = append(gone, item.ID)
	}
	return gone, nil
}

// --------------------------------------------------------------------------
// Legibility: somebody can see that twelve recordings are waiting
// --------------------------------------------------------------------------

// Nouns is what one item of each kind is called in a sentence, singular and
// plural. Here and not in a renderer, because the renderer may never name one
// of this bundle's words and these are the queue's own words, not the
// bundle's.
var Nouns = map[string][2]string{
	"audio":    {"recording", "recordings"},
	"document": {"national record", "national records"},
}

func plural(kind string, n int) string {
	words, named := Nouns[kind]
	if !named {
		words = [2]string{"item", "items"}
	}
	if n == 1 {
		return words[0]
	}
	return words[1]
}

type countKey struct{ Kind, State string }

// Worst is the item of one kind that has been tried most.
type Worst struct {
	Item     string
	Attempts int
}

// Standing is the outbox as counts, per kind and state, plus the worst
// offender. A value and not a printed report, so the one caller that needs to
// render it can and nothing here draws anything. Lines is the plain English,
// and it is correct at nought and at one as well as at twelve.
type Standing struct {
	Counts map[countKey]int
	Worst  map[string]Worst
}

// Total counts the rows matching a kind, a state, or both. An empty string does
// not narrow.
func (s Standing) Total(kind, state string) int {
	n := 0
	for key, count := range s.Counts {
		if kind != "" && key.Kind != kind {
			continue
		}
		if state != "" && key.State != state {
			continue
		}
		n += count
	}
	return n
}

// Lines is one sentence per thing a person needs to know, or one saying there
// is nothing. No prose beyond a count and a state.
func (s Standing) Lines() []string {
	out := []string{}
	for _, kind := range Kinds {
		waiting := s.Total(kind, "ready") + s.Total(kind, "sending")
		if waiting > 0 {
			out = append(out, fmt.Sprintf("%d %s waiting for the line",
				waiting, plural(kind, waiting)))
		}
		for _, pair := range [][2]string{
			{"failed", "failed and stopped"},
			{"refused", "refused by the guard"},
			{"held", "waiting for somebody to decide"},
		} {
			n := s.Total(kind, pair[0])
			if n == 0 {
				continue
			}
			said := fmt.Sprintf("%d %s %s", n, plural(kind, n), pair[1])
			worst, named := s.Worst[kind]
			if pair[0] == "failed" && named && worst.Attempts > 0 {
				attempt := "attempts"
				if worst.Attempts == 1 {
					attempt = "attempt"
				}
				said += fmt.Sprintf(" after %d %s", worst.Attempts, attempt)
			}
			out = append(out, said)
		}
	}
	if len(out) == 0 {
		return []string{"nothing is waiting to be sent"}
	}
	return out
}

// Status is the whole outbox, counted. The one read a person's view would make.
func Status(spool Spool, limit int) (Standing, error) {
	out := Standing{Counts: map[countKey]int{}, Worst: map[string]Worst{}}
	for _, state := range States {
		rows, err := spool.Items(state, "", limit)
		if err != nil {
			return out, err
		}
		for _, item := range rows {
			key := countKey{item.Kind, state}
			out.Counts[key]++
			if state == "failed" {
				best, named := out.Worst[item.Kind]
				if !named || item.Attempts > best.Attempts {
					out.Worst[item.Kind] = Worst{item.ID, item.Attempts}
				}
			}
		}
	}
	return out, nil
}

// SortedKinds is the kinds a Standing mentions, for a caller that renders one.
func SortedKinds(s Standing) []string {
	seen := map[string]bool{}
	var out []string
	for key := range s.Counts {
		if !seen[key.Kind] {
			seen[key.Kind] = true
			out = append(out, key.Kind)
		}
	}
	sort.Strings(out)
	return out
}
