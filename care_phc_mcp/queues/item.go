package queues

// What a queued item is for. `audio` is a consultation recording owed to a
// speech service; `document` is a visit owed to a national record. Two kinds
// and not one because the bodies come from different places: audio's bytes are
// held by the spool, a document's body is re-projected from the Store.
//
// kernel/contracts.QUEUE_KINDS, in that order.
var Kinds = []string{"audio", "document"}

// An item's life. Every one of these is a state somebody can be shown.
//
//	ready     waiting for a line
//	sending   claimed, and the outcome is not yet known
//	sent      the remote acknowledged it, and said so with a receipt
//	failed    tried the limit and stopped. Visible, not retried, not lost.
//	refused   the guard denied it at the moment it would have been sent
//	held      the remote cannot say whether it already has this, so nobody may
//	          resend it and nobody may throw it away. A person decides.
//
// kernel/contracts.QUEUE_STATES, in that order.
var States = []string{"ready", "sending", "sent", "failed", "refused", "held"}

// IsKind and IsState are the closed-list checks the Python spells with `in`.
// Here rather than in the adapter because the vocabulary is the kernel's: an
// adapter that decided for itself what a state was could make an item
// invisible to every read.
func IsKind(kind string) bool { return inList(Kinds, kind) }

// IsState reports whether this outbox knows that state.
func IsState(state string) bool { return inList(States, state) }

func inList(all []string, want string) bool {
	for _, one := range all {
		if one == want {
			return true
		}
	}
	return false
}

// Item is one thing this facility owes a remote service:
// kernel/contracts.QueueItem.
//
// WHAT THIS ROW HOLDS, which is the most sensitive decision in the module:
// identifiers and state, never content. No name, no mobile number, no Aadhaar
// number, no OTP, no answer a clinician typed, and for a document no body at
// all. `Blob` is a path to bytes for an `audio` item and empty otherwise, and
// the file it names is called after `ID`, which is opaque. `LastError` is the
// one free text field and it is scrubbed before it is written; this package is
// the only writer of it.
//
// That decision is READ FROM kernel/queues.py's own prose and carried, not
// re-derived. It is the Python's and it stays the Python's.
//
// `Key` is what the remote is asked under, and it is the whole of the
// not-sent-twice property: it is supplied by us rather than minted by them, so
// the same item asked for twice is one job on their side. For audio it is the
// scribe transaction id; for a document it is the encounter id, which
// kernel/fhir.py already writes as identifier.value. Neither is invented here.
//
// EVERY FIELD IS TEXT except Attempts, which is the Python's own note: every
// field on this row persists as text and a nil that reads back as "" is a
// field whose type lies about the table.
//
// THE FIELD ORDER IS LOAD BEARING. adapters/local/spool.COLUMNS is asserted
// against dataclasses.fields(QueueItem) by name AND by order, because a field
// added there and forgotten here is a column that silently never persists.
// Columns below holds the same rule on this side.
type Item struct {
	ID         string
	Kind       string // Kinds
	Key        string // the idempotency key the remote is asked under
	Thread     string
	Operation  string // the operation this item belongs to
	Capability string // what the guard re-judges at send time
	Facility   string // the shape this was admitted under
	CreatedAt  string
	Actor      string
	Blob       string // audio only: the path to the bytes
	State      string // States
	Attempts   int
	LastError  string // scrubbed by this package, never raw
	ClaimedAt  string
	SentAt     string
	Receipt    string // what the remote called it
}

// Columns is the row, in order, by the column name the adapter persists it
// under. The names are adapters/local/spool.COLUMNS verbatim and the order is
// kernel/contracts.QueueItem's field order, which is the same list the Python
// asserts against its own dataclass.
//
// Here in the kernel half rather than in the adapter, because what a queued
// item IS is not an adapter's choice; a spool over object storage would read
// this list rather than keep its own.
var Columns = []string{"id", "kind", "key", "thread", "operation", "capability",
	"facility", "created_at", "actor", "blob", "state", "attempts",
	"last_error", "claimed_at", "sent_at", "receipt"}

// Ints is which of those columns is a number. One, and the Python says the
// same.
var Ints = []string{"attempts"}

// Spool is a facility's outbox: kernel/contracts.Spool. Five methods, and
// Claim is the only subtle one.
//
// Nothing here decides anything. It does not know what a plugin is, what the
// guard is, or when to retry: this package owns all of that, exactly as
// kstate owns what a flag means and the store only stores.
type Spool interface {
	// Put inserts or replaces by item.ID.
	Put(item Item) error

	// Get is the row, or false when there is none.
	Get(id string) (Item, bool, error)

	// Items is the rows in a state and of a kind, oldest first. An empty
	// string for either does not narrow.
	Items(state, kind string, limit int) ([]Item, error)

	// Claim moves ready -> sending and adds one to attempts, ATOMICALLY, and
	// returns the item as it now stands. false if it was not ready any more,
	// which is how two pumps running at once cannot both take one item.
	//
	// THE WRITE MUST BE DURABLE BEFORE THIS RETURNS: a crash one instruction
	// later has to leave the item in `sending`, because an item that is still
	// `ready` after a crash mid-send is an item a recovery will send a second
	// time.
	Claim(id string, at string) (Item, bool, error)

	// Settle is the one write that ends an attempt. `state` is one of States.
	Settle(id string, state string, at string, receipt string, errText string) error
}
