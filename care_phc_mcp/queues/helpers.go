package queues

import (
	"crypto/rand"
	"encoding/hex"
	"strings"
)

// trimmed is the Python's `str(x or "").strip()`, which both the key check and
// the receipt check are spelled with. A receipt of three spaces is no receipt.
func trimmed(text string) string { return strings.TrimSpace(text) }

// randomHex is uuid4().hex[:n]. crypto/rand rather than math/rand: the id names
// a file holding a consultation recording, and a guessable name in a shared
// spool directory is a worse property than a slow one.
func randomHex(n int) string {
	raw := make([]byte, (n+1)/2)
	if _, err := rand.Read(raw); err != nil {
		// crypto/rand does not fail on any platform this runs on, and a queue
		// that carried on with a predictable id would be worse than one that
		// stops. There is no caller that can do anything useful with an error
		// here, so this is the one panic in the package and it is unreachable.
		panic("the outbox could not name an item: " + err.Error())
	}
	return hex.EncodeToString(raw)[:n]
}
