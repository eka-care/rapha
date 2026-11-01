package spool

import (
	"crypto/rand"
	"encoding/hex"
)

// randomName names a private in-memory database so two of them in one process
// are two databases. Only ever used for ":memory:".
func randomName() string {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		panic("could not name an in-memory spool: " + err.Error())
	}
	return hex.EncodeToString(raw)
}
