// Package schedule is kernel/schedule.py in Go: what is owed on one episode,
// and whether it has been done.
//
// NOTHING HERE IS STORED, AND THAT IS THE SAFETY PROPERTY. A contact is
// computed every time somebody asks, from the schedule declaration, the
// episode's own anchor date and what the audit says was committed. No row is
// generated when a pregnancy opens and none is cancelled when it ends.
//
// Generating rows up front is what most trackers do and it has one failure
// mode this product cannot survive: a generated schedule has to be CANCELLED
// when the pregnancy ends, so somebody has to remember to cancel it in every
// path that could end one, including the ones added later. Miss one and a
// woman who has just lost a baby gets the call asking why she missed her
// twenty eight week visit. Deriving makes that impossible rather than
// unlikely.
//
// The Python half carries the full reasoning and the two must agree, which
// scripts/check_go_parity.py enforces over the spine route.
package schedule

import (
	"sort"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/store"
)

// The four states a contact can be in.
const (
	Upcoming = "upcoming"
	Due      = "due"
	Done     = "done"
	Missed   = "missed"
)

// Reader is the part of the store this package needs. Read only: deciding
// what is owed may not write.
type Reader interface {
	Audit(thread string) ([]store.AuditRecord, error)
}

// Episode is the shape spine.Episode has, taken as an interface-free struct
// so this package does not import spine and spine can import this.
type Episode struct {
	ID          string
	Type        string
	Status      string
	OpenedAt    string
	AnchorDate  string
	AnchorBasis string
	Encounters  []string
}

// Contact is one computed contact, in the Python's own JSON field order.
type Contact struct {
	Contact   string `json:"contact"`
	Title     string `json:"title"`
	Schedule  string `json:"schedule"`
	Episode   string `json:"episode"`
	Opens     string `json:"opens"`
	Due       string `json:"due"`
	Closes    string `json:"closes"`
	State     string `json:"state"`
	Owner     string `json:"owner"`
	Operation string `json:"operation"`
	Authority string `json:"authority"`
	ReportsAs string `json:"reports_as"`
	DoneAt    string `json:"done_at"`
	Basis     string `json:"basis"`
}

// committed are the audit outcome prefixes that mean the thing was done.
// catalogue/vocab.WROTE is the Python's list and this is it.
var committed = []string{"committed", "confirmed", "allowed", "amended"}

func wrote(outcome string) bool {
	for _, prefix := range committed {
		if len(outcome) >= len(prefix) && outcome[:len(prefix)] == prefix {
			return true
		}
	}
	return false
}

// day parses a stored date. Both `YYYY-MM-DD` and a full timestamp are
// accepted, because the first is what a date question answers and the second
// is what created_date holds.
func day(text string) (time.Time, bool) {
	if len(text) < 10 {
		return time.Time{}, false
	}
	parsed, err := time.Parse("2006-01-02", text[:10])
	if err != nil {
		return time.Time{}, false
	}
	return parsed, true
}

// ForEpisode is kernel/schedule.for_episode: the schedule that applies to
// this episode's type, or nil.
func ForEpisode(cat *carephc.Catalogue, ep Episode) *carephc.Schedule {
	if ep.Type == "" {
		return nil
	}
	ids := make([]string, 0, len(cat.Schedules))
	for id := range cat.Schedules {
		ids = append(ids, id)
	}
	// Sorted, so two schedules for one episode type resolve the same way in
	// both engines rather than by map iteration order.
	sort.Strings(ids)
	for _, id := range ids {
		if s := cat.Schedules[id]; s.Episode == ep.Type {
			found := s
			return &found
		}
	}
	return nil
}

// StartOf is kernel/schedule.start_of: day zero of the arc.
//
// The episode records WHAT WAS OBSERVED and the schedule declares what each
// basis means in days. A basis the schedule does not know is refused rather
// than assumed to be zero, because assuming would date a pregnancy from a
// scan's delivery date as though it were a last period.
func StartOf(s *carephc.Schedule, ep Episode) (time.Time, bool) {
	offset, known := s.Anchor[ep.AnchorBasis]
	if !known {
		return time.Time{}, false
	}
	// WHERE THE DATE COMES FROM IS THE SCHEDULE'S TO SAY. A pregnancy is
	// measured from a date somebody recorded, because the event happened
	// before the record of it. A referral is measured from the moment it
	// was raised, which IS the record.
	source := ep.AnchorDate
	if s.AnchorFrom == "opened" {
		source = ep.OpenedAt
	}
	anchored, parsed := day(source)
	if !parsed {
		return time.Time{}, false
	}
	return anchored.AddDate(0, 0, offset), true
}

// Contacts is kernel/schedule.contacts: every contact this episode owes.
//
// An empty slice for an episode that has ended, one with no schedule, and
// one nobody has dated. Why takes those three apart for a screen.
func Contacts(cat *carephc.Catalogue, s Reader, ep Episode, at time.Time) ([]Contact, error) {
	out := []Contact{}
	sched := ForEpisode(cat, ep)
	if sched == nil || ep.Status == "ended" {
		return out, nil
	}
	start, dated := StartOf(sched, ep)
	if !dated {
		return out, nil
	}
	if at.IsZero() {
		at = time.Now().UTC()
	}
	today, _ := day(at.UTC().Format("2006-01-02"))

	closed, err := closures(s, ep, sched, start)
	if err != nil {
		return nil, err
	}

	for _, contact := range sched.Contacts {
		opens := start.AddDate(0, 0, contact.Opens)
		due := start.AddDate(0, 0, contact.Due)
		shuts := start.AddDate(0, 0, contact.Closes)
		doneAt, isDone := closed[contact.ID]

		state := Due
		owner := contact.Owner
		switch {
		case isDone:
			state = Done
		case today.Before(opens):
			state = Upcoming
		case today.After(shuts):
			state = Missed
			// A missed contact changes hands rather than turning red at the
			// same person. That is the whole of what escalation means here.
			if contact.EscalatesTo != "" {
				owner = contact.EscalatesTo
			}
		}

		out = append(out, Contact{
			Contact: contact.ID, Title: contact.Title, Schedule: sched.ID,
			Episode: ep.ID,
			Opens:   opens.Format("2006-01-02"),
			Due:     due.Format("2006-01-02"),
			Closes:  shuts.Format("2006-01-02"),
			State:   state, Owner: owner, Operation: contact.Operation,
			Authority: contact.Authority, ReportsAs: contact.ReportsAs,
			DoneAt: doneAt, Basis: ep.AnchorBasis,
		})
	}
	return out, nil
}

// Why is kernel/schedule.why: why an episode owes nothing, in words, or ""
// when it owes something. An empty list is three different situations and a
// screen that cannot tell them apart says "nothing due" to a woman nobody
// has dated.
func Why(cat *carephc.Catalogue, ep Episode) string {
	if ep.ID == "" && ep.Type == "" {
		return "there is no episode"
	}
	if ep.Status == "ended" {
		return "this is over"
	}
	sched := ForEpisode(cat, ep)
	if sched == nil {
		return "nothing is scheduled for this kind of episode"
	}
	source := ep.AnchorDate
	if sched.AnchorFrom == "opened" {
		source = ep.OpenedAt
	}
	if _, dated := day(source); !dated {
		return "nobody has dated this yet"
	}
	if _, known := StartOf(sched, ep); !known {
		return "it is dated in a way this schedule does not know"
	}
	return ""
}

type event struct {
	when      time.Time
	operation string
}

// closures is kernel/schedule._closures.
//
// ONE VISIT CLOSES ONE CONTACT: the earliest still open contact whose window
// contains the day it was committed. The windows in a schedule touch, so
// without that rule a single visit could discharge two and a woman who came
// once would read as having come twice.
//
// A contact can be closed LATE, which is the common case rather than an
// edge: the Mother and Child Protection card is paper and is often more
// complete than anything the centre holds. A late commit closes the latest
// contact whose window has already opened, so a visit recorded at thirty
// weeks does not quietly discharge the twelve week contact nobody attended.
func closures(s Reader, ep Episode, sched *carephc.Schedule,
	start time.Time) (map[string]string, error) {
	byOperation := map[string][]carephc.Contact{}
	for _, contact := range sched.Contacts {
		byOperation[contact.Operation] = append(byOperation[contact.Operation], contact)
	}

	events := []event{}
	for _, thread := range ep.Encounters {
		records, err := s.Audit(thread)
		if err != nil {
			return nil, err
		}
		for _, record := range records {
			if !wrote(record.Outcome) {
				continue
			}
			if _, scheduled := byOperation[record.Operation]; !scheduled {
				continue
			}
			if when, parsed := day(record.At); parsed {
				events = append(events, event{when, record.Operation})
			}
		}
	}
	sort.SliceStable(events, func(i, j int) bool {
		if events[i].when.Equal(events[j].when) {
			return events[i].operation < events[j].operation
		}
		return events[i].when.Before(events[j].when)
	})

	closed := map[string]string{}
	for _, e := range events {
		var inside, opened *carephc.Contact
		for i := range byOperation[e.operation] {
			contact := byOperation[e.operation][i]
			if _, already := closed[contact.ID]; already {
				continue
			}
			opens := start.AddDate(0, 0, contact.Opens)
			shuts := start.AddDate(0, 0, contact.Closes)
			if !e.when.Before(opens) && !e.when.After(shuts) {
				if inside == nil || contact.Due < inside.Due {
					held := contact
					inside = &held
				}
			}
			if !e.when.Before(opens) {
				if opened == nil || contact.Due > opened.Due {
					held := contact
					opened = &held
				}
			}
		}
		if inside != nil {
			closed[inside.ID] = e.when.Format("2006-01-02")
			continue
		}
		if opened != nil {
			closed[opened.ID] = e.when.Format("2006-01-02")
		}
	}
	return closed, nil
}
