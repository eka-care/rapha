// Package tokens is the Go side of kernel/tokens.py: the facility's day
// sequence, the number the waiting area calls out.
//
// WHAT WAS HERE BEFORE THIS PACKAGE, WHICH IS NOTHING
// ---------------------------------------------------
// This engine had no day sequence at all. `POST /threads` read a `token` out
// of the request BODY and handed it to the store, and the store, when given
// none, made one up out of the last three characters of the generated row id.
// So a number came from whichever client asked, or from a row id, and in
// neither case from a sequence. cmd/api/main.go's route table said "the day
// sequence is ported but the arrival route is not", and the first half of that
// sentence was not true. It is true now.
//
// Both of those are gone. A client's token is ignored, exactly as
// api/main.py's own route ignores one, and for the reason that file gives: a
// number a client picks is a number nothing else knew it had given out, and
// two clients each picking their own is how one waiting room ends up with two
// people called seven.
//
// THE RULE AND THE LOCK ARE DIFFERENT HALVES
// ------------------------------------------
// The rule is here: one past the HIGHEST number already issued, skipping any
// token that is not on the sequence. The atomicity is the store's, behind
// Store.IssueToken, because a package of pure arithmetic cannot hold a lock.
// kernel/tokens.py splits it the same way and says why at length.
//
// Reading the day's numbers and then writing the next one is two steps, and
// two arrivals inside one instant were handed the same number. That race was
// closed on 2026-11-01 in both engines. scripts/check_tokens_race.py proves
// the Python's by racing real processes; tokens_race_test.go proves this one
// by racing real goroutines against a real file, and both assert no duplicate
// and no hole.
package tokens

import (
	"sort"
	"strconv"
	"strings"
)

// First is the first number of a facility's day. Not zero: nobody calls out
// "zero". kernel/tokens.FIRST.
const First = 1

// Numbers returns the tokens that are on this sequence, as integers, in order.
//
// A token that is not a plain number is not on the sequence and is SKIPPED
// rather than rejected, and kernel/tokens.py gives both reasons. A laboratory
// numbers its racks ("25-0414") and that is its own business, not a gap in
// anybody's queue. And a facility whose file still holds a pre-numeric token
// must still be able to open tomorrow: skipping it means the next arrival
// gets 1 and the day is countable again, where refusing would mean the desk
// cannot register anybody until somebody edits a database.
func Numbers(given []string) []int {
	out := []int{}
	for _, token := range given {
		text := strings.TrimSpace(token)
		if text == "" {
			continue
		}
		// strconv.Atoi accepts a leading sign and Python's str.isdigit() does
		// not, so "-3" is not on the sequence here either. Checked rather
		// than assumed, because a negative token would otherwise lower the
		// floor and reissue a number.
		if strings.IndexFunc(text, func(r rune) bool { return r < '0' || r > '9' }) >= 0 {
			continue
		}
		n, err := strconv.Atoi(text)
		if err != nil {
			continue
		}
		out = append(out, n)
	}
	sort.Ints(out)
	return out
}

// After returns the next number, given the ones already issued.
//
// One past the HIGHEST issued, not one past the count. A visit that was opened
// and closed still spent its number: counting instead would hand the next
// arrival a number somebody in the room was already answering to.
func After(given []string) int {
	issued := Numbers(given)
	if len(issued) == 0 {
		return First
	}
	return issued[len(issued)-1] + 1
}
