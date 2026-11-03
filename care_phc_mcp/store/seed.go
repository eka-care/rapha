package store

// The seed and the demo day. adapters/local/store.py's seed(),
// declared_seed() and roll_seed_forward(), transcribed.
//
// WHY THIS LANDED WITH THE SLICE THAT SERVES A QUEUE
// --------------------------------------------------
// The package comment above said it: a seeded demo day is only observable
// through a view, so writing the seed before anything could resolve one would
// have been a second unproven implementation of a function whose whole
// behaviour is about what a screen shows. The views slice is this one, and
// this is that function arriving with the thing that can see it.
//
// THE ROWS ARE THE BUNDLE'S AND THIS FILE ONLY KNOWS HOW TO PUT THEM ON DISK
// -------------------------------------------------------------------------
// Until 2026.09.13 the rows themselves lived in Python, so every bundle got a
// primary health centre's demo day: a laboratory opened on six outpatients
// with tokens like A01 and a pending Amoxicillin on a specimen. A seed speaks
// a facility's words, so it lives in bundles/<id>/seed.yaml and is read from
// the tree here, the way cmd/api already reads questionnaires/ and
// terminology/. It is NOT in catalogue.json, and that is deliberate on the
// Python's side too (kernel/declarations.Bundle's own docstring: "It is
// fixture data and not a declaration... and it stays out of catalogue.json").
// Carrying it there would also break the one property that makes a facility a
// choice and not a fork, because kernel/plugins.seeded() narrows the seed PER
// SHAPE while the compiled artifact is byte identical across every shape.
//
// A bundle with no seed.yaml starts empty, which is a supported outcome and
// not a crash.

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// LoadSeed is kernel/declarations.load_seed: the threads bundles/<id>/seed.yaml
// declares, or none.
//
// Returned unfiltered. Which of them a FACILITY could really have had is
// kernel/plugins.seeded()'s question, it depends on which plugins this centre
// runs, and it is answered by the caller.
func LoadSeed(dir string) ([]map[string]any, error) {
	path := filepath.Join(dir, "seed.yaml")
	raw, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var file struct {
		Threads []map[string]any `yaml:"threads"`
	}
	if err := yaml.Unmarshal(raw, &file); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	return file.Threads, nil
}

// RollSeedForward moves a stale demo day to today, and returns how many days
// it moved.
//
// Every queue view is `scope: today`, which is what a queue means, so a file
// seeded yesterday drew an empty workspace this morning and the documented fix
// was "delete the SQLite file and restart". That throws away whatever was done
// on it. Instead the seeded threads walk forward: the whole demo day shifts by
// whole days, keeping the time of day and the order of every row inside it.
//
// Only threads the seed opened move, found by encounter.created_by = 'seed',
// and only rows dated on the seed's own day, so real work done on a seeded
// thread after that day keeps the date it happened on. A thread a person
// opened is never touched: "today" still means today for real work.
//
// AND NOTHING IS PUSHED INTO THE FUTURE. Rolling forward by whole DAYS while
// keeping the time of day puts every row whose seeded time-of-day is later
// than the current wall clock into the future for the hours of "today" before
// that time arrives. A future opened_at makes the renderer's elapsedMinutes()
// negative, which painted a wait bar backwards out of its own row and printed
// "0m" on every row all day. ISO-8601 timestamps of the same +00:00 shape sort
// lexicographically in the same order they sort chronologically, so a plain
// string MIN against `now` is the whole clamp.
//
// Called from Open, so every process that opens the file gets it, including
// the ones this adapter does not own.
func (s *SQLite) RollSeedForward() (int, error) {
	var newest *string
	row := s.db.QueryRow("SELECT MAX(created_date) AS d FROM encounter WHERE created_by = ?",
		SeedActor)
	if err := row.Scan(&newest); err != nil {
		return 0, err
	}
	if newest == nil || *newest == "" {
		return 0, nil
	}
	if len(*newest) < 10 {
		return 0, nil
	}
	seededOn, err := time.Parse("2006-01-02", (*newest)[:10])
	if err != nil {
		// A hand edited date is not worth a dead constructor.
		return 0, nil
	}
	now := time.Now().UTC()
	today := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, time.UTC)
	days := int(today.Sub(seededOn).Hours() / 24)
	if days <= 0 {
		return 0, nil
	}
	cutoff := seededOn.AddDate(0, 0, 1).Format("2006-01-02")
	stamp := now.Format("2006-01-02T15:04:05+00:00")

	threadRows, err := s.db.Query("SELECT id FROM encounter WHERE created_by = ?", SeedActor)
	if err != nil {
		return 0, err
	}
	var threads []any
	for threadRows.Next() {
		var id string
		if err := threadRows.Scan(&id); err != nil {
			threadRows.Close()
			return 0, err
		}
		threads = append(threads, id)
	}
	threadRows.Close()
	if err := threadRows.Err(); err != nil {
		return 0, err
	}
	if len(threads) == 0 {
		return 0, nil
	}

	// Every table, in the declaration order Tables is written in, because the
	// Python walks TABLES. Go maps have no order, so the names are sorted:
	// each statement touches one table and none reads another's new values,
	// so the order cannot change the outcome. Sorted rather than left to the
	// map, because a non-deterministic statement order is not something to
	// leave in a migration.
	names := make([]string, 0, len(Tables))
	for name := range Tables {
		names = append(names, name)
	}
	sort.Strings(names)
	marks := strings.TrimSuffix(strings.Repeat("?, ", len(threads)), ", ")

	for _, name := range names {
		join, column := DefaultThreadColumn, "created_date"
		if pair, kernelOwn := KernelRecord[name]; kernelOwn {
			join, column = pair[0], pair[1]
		} else if named, declared := ThreadColumn[name]; declared {
			join = named
		}
		var where string
		switch name {
		case "encounter":
			where = fmt.Sprintf("id IN (%s)", marks)
		case "patient":
			where = fmt.Sprintf("id IN (SELECT patient FROM encounter WHERE id IN (%s))", marks)
		default:
			if join == "" {
				// Reached through the thread's patient; see ThreadColumn.
				where = fmt.Sprintf(
					"patient IN (SELECT patient FROM encounter WHERE id IN (%s))", marks)
				break
			}
			where = fmt.Sprintf("%s IN (%s)", join, marks)
		}
		// SQLite's datetime() understands the +00:00 suffix and drops it,
		// returning "YYYY-MM-DD HH:MM:SS". Everything that compares these
		// columns compares strings, so the isoformat spelling is put back
		// before the two candidates are compared and the smaller (that is,
		// not-later-than-now) one kept.
		stmt := fmt.Sprintf(
			"UPDATE %s SET %s = MIN(replace(datetime(%s, ?), ' ', 'T') || '+00:00', ?)"+
				" WHERE %s AND %s < ?", name, column, column, where, column)
		params := append([]any{fmt.Sprintf("+%d days", days), stamp}, threads...)
		params = append(params, cutoff)
		if _, err := s.db.Exec(stmt, params...); err != nil {
			return 0, fmt.Errorf("rolling %s forward: %w", name, err)
		}
	}
	return days, nil
}

// Seed populates an empty store from a bundle's declared seed, and returns
// the thread ids in declaration order. An empty seed returns nothing and
// writes nothing.
//
// Row ids are `seed-NNNN` in declaration order because select() orders by
// created_date then id and every seeded row shares one stamp: without it a
// report would list four analytes in whatever order a random id chose.
func Seed(s *SQLite, threads []map[string]any) ([]string, error) {
	stamp := Now()
	serial := 0
	rowID := func() string {
		serial++
		return fmt.Sprintf("seed-%04d", serial)
	}
	stamped := func(record map[string]any) map[string]any {
		out := map[string]any{"id": rowID(), "created_by": SeedActor,
			"created_date": stamp}
		for k, v := range record {
			out[k] = v
		}
		return out
	}
	// thread id -> the patient row it created, so a later thread can declare
	// itself the same person returning. Without this every seeded thread makes
	// its own patient row and the spine can only ever show one visit per
	// person, which is the one shape that cannot demonstrate it.
	patientOf := map[string]string{}

	opened := []string{}
	for _, t := range threads {
		thread, _ := t["id"].(string)
		if thread == "" {
			return nil, fmt.Errorf("a seeded thread has no id")
		}
		opened = append(opened, thread)

		// A thread's own `minutes_ago` backdates only its encounter row (the
		// one column opened_at is read from), so the wait rule has a seeded
		// row that is actually past a declared target_minutes: without one,
		// the spec's own acceptance criterion ("one row seeded past target:
		// exactly one [data-over]") is unsatisfiable against the shipped
		// fixture, since every other row shares the same "now" stamp.
		// RollSeedForward's later day-walk only ever adds whole days, so this
		// relative offset survives it.
		when := stamp
		if minutes, given := asInt(t["minutes_ago"]); given && minutes != 0 {
			when = time.Now().UTC().Add(-time.Duration(minutes) * time.Minute).
				Format("2006-01-02T15:04:05+00:00")
		}
		if _, err := s.put("encounter", map[string]any{
			"id": thread, "token": t["token"], "status": orDefault(textOf(t["status"]), "in_progress"),
			"arrival": t["arrival"],
			"created_by": SeedActor, "created_date": when}, thread); err != nil {
			return nil, err
		}

		if returning, _ := t["same_patient_as"].(string); returning != "" {
			// The same person, back again. Point this encounter at the row the
			// earlier thread created rather than writing a second person with
			// the same name, which is what a duplicate registration looks
			// like and is not what a returning patient is.
			known, made := patientOf[returning]
			if !made {
				return nil, fmt.Errorf("seed thread %q: same_patient_as %q, which has "+
					"no patient (is it declared later in the file?)", thread, returning)
			}
			if _, err := s.put("encounter", map[string]any{"id": thread, "patient": known},
				thread); err != nil {
				return nil, err
			}
			patientOf[thread] = known
		} else if person, given := t["patient"].(map[string]any); given {
			// Write and not put: attaching the person to the thread is the
			// adapter's own join and it is already written down once.
			written, err := s.Write("patient", stamped(person), thread)
			if err != nil {
				return nil, err
			}
			patientOf[thread] = written
		}

		for _, item := range asList(t["rows"]) {
			record, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("seed thread %q: a row is not a mapping", thread)
			}
			resource, _ := record["resource"].(string)
			rest := map[string]any{}
			for k, v := range record {
				if k != "resource" {
					rest[k] = v
				}
			}
			if _, err := s.put(resource, stamped(rest), thread); err != nil {
				return nil, err
			}
		}
		for _, item := range asList(t["flags"]) {
			flag, _ := item.(string)
			if err := s.RaiseFlag(thread, flag, SeedActor); err != nil {
				return nil, err
			}
		}
		for _, item := range asList(t["audit"]) {
			entry, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("seed thread %q: an audit entry is not a mapping", thread)
			}
			// A seeded thread that claims work was done has to say who did
			// it: "not actor of lab.op.result-enter" is evaluated against this
			// trail, so without these rows the demo day cannot show the rule.
			//
			// And WHAT was recorded, not only that something was. The thread
			// draws a posted operation's values from this payload, so an entry
			// without one is a receipt for something invisible: a card headed
			// "Record vitals and triage" with no vitals under it.
			operation, _ := entry["operation"].(string)
			actor, _ := entry["actor"].(string)
			if err := s.AppendAudit(AuditRecord{
				ID: rowID(), Thread: thread, Operation: operation, Actor: actor,
				Surface: orDefault(textOf(entry["surface"]), "rendered"),
				Payload: asMap(entry["payload"]),
				Outcome: orDefault(textOf(entry["outcome"]), "confirmed"), At: stamp,
			}); err != nil {
				return nil, err
			}
		}
		for _, item := range asList(t["proposals"]) {
			p, ok := item.(map[string]any)
			if !ok {
				return nil, fmt.Errorf("seed thread %q: a proposal is not a mapping", thread)
			}
			pid, _ := p["id"].(string)
			if pid == "" {
				pid = rowID()
			}
			payload := asMap(p["payload"])
			operation, _ := p["operation"].(string)
			proposedBy, _ := p["proposed_by"].(string)
			surface := orDefault(textOf(p["surface"]), "mcp")
			if err := s.PutProposal(Proposal{
				ID: pid, Thread: thread, Operation: operation, Payload: payload,
				ProposedBy: proposedBy, Surface: surface,
				Status: orDefault(textOf(p["status"]), "pending"), CreatedAt: stamp,
			}); err != nil {
				return nil, err
			}
			if err := s.AppendAudit(AuditRecord{
				ID: rowID(), Thread: thread, Operation: operation, Actor: proposedBy,
				Surface: surface, Payload: payload, Outcome: "proposed", At: stamp,
				Proposal: pid,
			}); err != nil {
				return nil, err
			}
		}
	}
	return opened, nil
}

// ---------------------------------------------------------------------------
// reading a YAML value the way the Python reads a parsed one
// ---------------------------------------------------------------------------

func asList(v any) []any {
	out, _ := v.([]any)
	return out
}

func asMap(v any) map[string]any {
	out, ok := v.(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return out
}

// textOf reads a declared value as the string it is, so an absent key and a
// null both fall through to the caller's default, as Python's `or` does.
func textOf(v any) string {
	s, _ := v.(string)
	return s
}

func asInt(v any) (int, bool) {
	switch t := v.(type) {
	case int:
		return t, true
	case int64:
		return int(t), true
	case float64:
		return int(t), true
	}
	return 0, false
}

// IsEmpty answers api/main.py's make_store() question: has this store any
// thread at all? The Python asks `SELECT 1 FROM encounter` and seeds when
// nothing comes back, so this is that one condition and nothing wider.
func (s *SQLite) IsEmpty() (bool, error) {
	var one int
	err := s.db.QueryRow("SELECT 1 FROM encounter LIMIT 1").Scan(&one)
	if err == sql.ErrNoRows {
		return true, nil
	}
	return false, err
}
