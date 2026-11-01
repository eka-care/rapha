package main

// The outbox sweeper, switched on. api/outbox.py is the Python's half and the
// reasoning is argued there at length; this file carries the same schedule,
// the same order of a pass, and the same refusal to let a failed pass stop the
// next one.
//
// WHAT THIS CLOSES. package queues was complete, proved, and reached by
// nothing: no route touched it and nothing in cmd/api called Pump, so the
// retention ceiling was a constant nobody read. It was switched off for one
// reason, that holding consultation audio on a clinic's disk needed a signed
// retention window, and docs/DECISIONS-2026-11-01.md decision 2 signed it: 24
// hours, enforced rather than documented.
//
// WHAT THIS ENGINE DOES AND DOES NOT DO. It sweeps and it recovers. It does
// NOT hold new recordings, because this engine does not serve the scribe
// routes: POST /scribe/* is not in `served` and there is no scribe connector
// here. So `senders` is empty and the Pump below sends nothing.
//
// That is not a reason to leave the sweeper out, and it is the opposite. Both
// engines open the SAME spool, exactly as they open the same database, so a
// deployment running the Go kernel beside or instead of the Python's has a
// spool with real recordings in it that the Python put there. A Go-only
// process with no sweeper would be a clinic where the ceiling silently is not
// enforced, which is the failure this whole slice exists to remove. Sweeping
// needs no connector: deleting a file that is out of time is not sending it.
//
// Pump is still called rather than skipped, and with an empty sender map it
// moves an item toward `failed` saying nothing is configured to send it. That
// is the honest outcome and it is visible in the row; a queue that silently
// never tried is the thing that cannot be debugged.

import (
	"log"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/eka-care/care_phc_mcp/queues"
	"github.com/eka-care/care_phc_mcp/spool"
	"github.com/eka-care/care_phc_mcp/store"
)

// sweepSeconds is how often a pass happens. Five minutes, the same as
// api/outbox.py's, and a guess in exactly the sense that file labels it one.
//
// It also bounds how late a deletion can be: a recording goes within one pass
// of its window expiring, so the effective ceiling is 24 hours plus up to five
// minutes rather than 24 hours exactly. Said plainly because a ceiling that is
// quietly approximate is the sort of claim this work exists to stop.
const sweepSeconds = 300

// spoolDB is the outbox database's own file, under the spool root. The same
// name api/outbox.py uses, because the two engines share one spool.
const spoolDB = "outbox.sqlite3"

// startSweeper opens this process's outbox and sweeps it on a timer.
//
// Returns a function that stops it, for a caller that wants a clean shutdown.
// A failure to open the spool is logged and not fatal: the answer is a kernel
// that serves and sweeps nothing, with the reason on the log, rather than a
// clinic whose screens do not come up because an outbox could not be created.
func startSweeper(every time.Duration) func() {
	root := queues.SpoolRoot()
	if err := os.MkdirAll(root, queues.SpoolDirMode); err != nil {
		log.Printf("the outbox could not be opened, so nothing will be swept "+
			"and held audio will stay on this disk: %v", err)
		return func() {}
	}
	box, err := spool.Open(filepath.Join(root, spoolDB))
	if err != nil {
		log.Printf("the outbox could not be opened, so nothing will be swept "+
			"and held audio will stay on this disk: %v", err)
		return func() {}
	}

	if override := os.Getenv("PHC_SWEEP_SECONDS"); override != "" {
		if n, err := strconv.Atoi(override); err == nil {
			if n == 0 {
				// No timer. For a check that drives a pass with its own clock.
				// It does not switch the ceiling off: a process that is not
				// sweeping holds nothing new, and the next one to open this
				// spool sweeps on its first pass.
				log.Printf("the outbox sweeper is off (PHC_SWEEP_SECONDS=0)")
				return func() { box.Close() }
			}
			every = time.Duration(n) * time.Second
		}
	}

	stop := make(chan struct{})
	go func() {
		ticker := time.NewTicker(every)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				return
			case <-ticker.C:
				sweepOnce(box)
			}
		}
	}()
	log.Printf("care-phc: the outbox sweeper is running every %s; held audio "+
		"is deleted after at most %ds", every, queues.AudioCeilingSeconds)
	return func() { close(stop); box.Close() }
}

// sweepOnce is one pass: recover, pump, then sweep. The order is the design.
//
//  1. Recover first, because an item a crash left in `sending` must be asked
//     about before anything new is claimed. Resending blind is the one thing
//     an outbox may never do.
//  2. Pump, the sending pass. The guard runs again per item, before the claim.
//  3. SweepAudio last, so a recording that could have gone out in this very
//     pass is not deleted a moment before its chance. A sweep that ran first
//     would turn a flickering line into lost audio.
//
// Every pass is wrapped by its caller's recover, because a sweeper that dies
// on one bad pass leaves audio on a disk forever.
func sweepOnce(box queues.Spool) {
	defer func() {
		if panicked := recover(); panicked != nil {
			log.Printf("an outbox pass failed and the next one will still "+
				"run: %v", panicked)
		}
	}()
	// The same timestamp spelling every row in both engines is dated with.
	now := store.Now()

	// No senders. This engine serves no scribe route and has no connector, so
	// there is nothing here that can send one; see this file's own header.
	senders := map[string]queues.Sender{}

	if _, err := queues.Recover(box, senders, now, queues.InFlightSeconds,
		queues.MaxAttempts); err != nil {
		log.Printf("an outbox recovery pass failed: %v",
			queues.Scrubbed(err.Error()))
	}

	gone, err := queues.SweepAudio(box, now, os.Remove,
		queues.AudioMaxHoldSeconds)
	if err != nil {
		log.Printf("an outbox retention pass failed and held audio may still "+
			"be on this disk: %v", queues.Scrubbed(err.Error()))
		return
	}
	if len(gone) > 0 {
		log.Printf("%d held recording(s) reached the retention ceiling and "+
			"were deleted untranscribed", len(gone))
	}
}
