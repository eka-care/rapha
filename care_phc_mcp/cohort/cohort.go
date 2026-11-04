// Package cohort is kernel/cohort.py in Go: what a centre owes between two
// dates, across every open episode.
//
// THIS IS spine.Episodes' PAIRING WIDENED FROM ONE SUBJECT TO ALL OF THEM.
// schedule.Contacts answers for one episode; a facility wants one day's work.
// The episode rows are read directly rather than found through recent visits,
// because the subject this screen exists to surface is the one nobody has seen
// for months, and that subject has no recent visit to be found by.
//
// NOTHING HERE IS STORED. No table, no cache, no queue. Every call re-derives
// the answer from the episode rows and the audit, through schedule.Contacts,
// which returns nothing for an episode that has ended. So there is nothing to
// cancel when an episode ends badly, and a subject whose episode has ended
// cannot appear here on any day, past or future. This package reimplements
// none of the date or state logic; it only asks.
//
// WHAT THIS COSTS. Here: one read per episode type, and two per subject with
// an open episode. In schedule.Contacts: one audit read per visit of each open
// episode. That is right for a centre and wrong for a district. The fix when
// it bites is a store method that answers for many threads at once, never a
// stored contact, because a stored contact is what has to be cancelled.
//
// No clinical word appears here; the episode types arrive as data.
package cohort

import (
	"fmt"
	"sort"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/schedule"
	"github.com/eka-care/care_phc_mcp/store"
)

// all is the most rows one read may return. Reaching it is an error rather
// than a truncation: a screen whose purpose is that nobody is missed must not
// drop rows without saying so.
const all = 100000

// Reader is the part of the store this package needs. Read only.
type Reader interface {
	schedule.Reader
	SelectNullable(resource string, thread *string, where store.Query, fields []string, limit int) ([]map[string]any, error)
}

// Entry is one schedule contact plus who it is owed to and the days in the
// window it covers, in the Python's own key order.
type Entry struct {
	schedule.Contact
	Subject    string         `json:"subject"`
	SubjectRow map[string]any `json:"subject_row"`
	On         []string       `json:"on"`
}

func text(v any) string {
	s, _ := v.(string)
	return s
}

// Owed is kernel/cohort.owed: every contact due to any open episode of these
// types. A contact is listed when its [opens, closes] intersects
// [since, until], or when it is missed, which stays owed after its window
// shuts; its On is then empty if the window lies wholly outside. Sorted by
// due, then subject.
func Owed(cat *carephc.Catalogue, s Reader, wf *carephc.Workflow, types []string,
	since, until, at time.Time) ([]Entry, error) {
	link, kind := wf.Spine, wf.Episode
	if link == "" || kind == "" {
		return []Entry{}, nil
	}

	// Patients in the order they first appear, as the Python's dict keeps them,
	// so equal sort keys come out in the same order from both engines.
	var order []string
	byPatient := map[string][]map[string]any{}
	for _, of := range types {
		got, err := s.SelectNullable(kind, nil, store.Query{"type": {Equals: of}}, nil, all)
		if err != nil {
			return nil, err
		}
		if len(got) >= all {
			return nil, fmt.Errorf("more than %d %q episodes: the sweep needs a bulk read", all, of)
		}
		for _, row := range got {
			// An episode with no subject cannot be drawn: there is nobody to
			// name on the screen. It is dropped rather than shown as a blank.
			patient := text(row["patient"])
			if patient == "" {
				continue
			}
			if _, seen := byPatient[patient]; !seen {
				order = append(order, patient)
			}
			byPatient[patient] = append(byPatient[patient], row)
		}
	}

	out := []Entry{}
	for _, patient := range order {
		theirs := byPatient[patient]
		// The sort spine.Episodes uses, for the reason given there: an opening
		// beats an ending at an equal timestamp.
		ended := func(row map[string]any) int {
			if text(row["status"]) == "ended" {
				return 1
			}
			return 0
		}
		sort.SliceStable(theirs, func(i, j int) bool {
			a, b := text(theirs[i]["created_date"]), text(theirs[j]["created_date"])
			if a != b {
				return a < b
			}
			return ended(theirs[i]) < ended(theirs[j])
		})
		// Open episodes by type, in the order a Python dict would hold them:
		// a type seen again keeps its place, a type that ended and reopened
		// goes to the back.
		var kinds []string
		open := map[string]map[string]any{}
		for _, row := range theirs {
			of := text(row["type"])
			if text(row["status"]) == "ended" {
				if _, is := open[of]; is {
					delete(open, of)
					for n, t := range kinds {
						if t == of {
							kinds = append(kinds[:n], kinds[n+1:]...)
							break
						}
					}
				}
				continue
			}
			if _, is := open[of]; !is {
				kinds = append(kinds, of)
			}
			open[of] = row
		}
		if len(open) == 0 {
			continue
		}

		subject, err := s.SelectNullable(link, nil, store.Query{"id": {Equals: patient}}, nil, 1)
		if err != nil {
			return nil, err
		}
		subjectRow := map[string]any{}
		if len(subject) > 0 {
			subjectRow = subject[0]
		}
		visits, err := s.SelectNullable(wf.Subject, nil, store.Query{link: {Equals: patient}}, nil, all)
		if err != nil {
			return nil, err
		}
		if len(visits) >= all {
			return nil, fmt.Errorf("more than %d visits for %q: the sweep needs a bulk read", all, patient)
		}
		for _, of := range kinds {
			row := open[of]
			opened := text(row["created_date"])
			encounters := []string{}
			for _, v := range visits {
				if text(v["created_date"]) >= opened {
					encounters = append(encounters, text(v["id"]))
				}
			}
			episode := schedule.Episode{
				ID: text(row["id"]), Type: text(row["type"]), Status: "active",
				OpenedAt: opened, AnchorDate: text(row["anchor_date"]),
				AnchorBasis: text(row["anchor_basis"]), Encounters: encounters,
			}
			contacts, err := schedule.Contacts(cat, s, episode, at)
			if err != nil {
				return nil, err
			}
			for _, contact := range contacts {
				on, err := days(contact, since, until)
				if err != nil {
					return nil, err
				}
				if len(on) == 0 && contact.State != schedule.Missed {
					continue
				}
				out = append(out, Entry{Contact: contact, Subject: patient,
					SubjectRow: subjectRow, On: on})
			}
		}
	}

	sort.SliceStable(out, func(i, j int) bool {
		if out[i].Due != out[j].Due {
			return out[i].Due < out[j].Due
		}
		return out[i].Subject < out[j].Subject
	})
	return out, nil
}

// days is the ISO dates in [since, until] that this contact's window covers.
func days(c schedule.Contact, since, until time.Time) ([]string, error) {
	opens, err := time.Parse("2006-01-02", c.Opens)
	if err != nil {
		return nil, err
	}
	closes, err := time.Parse("2006-01-02", c.Closes)
	if err != nil {
		return nil, err
	}
	first, last := opens, closes
	if since.After(first) {
		first = since
	}
	if until.Before(last) {
		last = until
	}
	on := []string{}
	for d := first; !d.After(last); d = d.AddDate(0, 0, 1) {
		on = append(on, d.Format("2006-01-02"))
	}
	return on, nil
}
