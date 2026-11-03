// Package spine is kernel/spine.py in Go: one subject, every visit it has had.
//
// A thread is one encounter. That is the right unit for a guard — a
// precondition is about this visit, not about a life — but it is the wrong
// unit for a person, who arrives more than once and whose second visit is
// only meaningful beside the first.
//
// WHAT JOINS TWO ENCOUNTERS IS NOT SOMETHING THIS PACKAGE MAY KNOW
// ----------------------------------------------------------------
// `patient` is the health centre's word; a laboratory's continuing subject is
// its own. So the workflow declares it:
//
//	subject: encounter   # what a thread is about
//	spine:   patient     # the field on that resource naming what continues
//
// A workflow that declares no spine has no continuing subject, and the route
// that reads this answers 404 rather than guessing one. That is the honest
// answer for a bundle whose threads genuinely do not join up, and it is why
// nothing here names a patient.
//
// NO STORE METHOD WAS ADDED FOR THIS, IN EITHER ENGINE
// ----------------------------------------------------
// Select already takes a nil thread and the subject resource already carries
// the spine field, so both reads below are ordinary selects. SelectNullable
// rather than Select because the subject row goes on the wire whole: the
// Python's select() answers None for an unfilled column and a flattened read
// answers "", and a screen drawing "no ABHA number yet" sees the difference.
package spine

import (
	"sort"
	"strings"
	"time"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/kstate"
	"github.com/eka-care/care_phc_mcp/store"
)

// Reader is the part of the store this package needs. Read only, as the
// Python's is: a timeline may not write.
type Reader interface {
	kstate.Reader
	SelectNullable(resource string, thread *string, where store.Query, fields []string, limit int) ([]map[string]any, error)
}

// Visit is one encounter on a subject's timeline, in the Python's own key
// order.
type Visit struct {
	Thread   string   `json:"thread"`
	OpenedAt string   `json:"opened_at"`
	Status   string   `json:"status"`
	Token    string   `json:"token"`
	Flags    []string `json:"flags"`
	Station  any      `json:"station"`
	// §26: a timeline entry needs to say what the visit WAS, not only when it
	// was. The operations that actually committed are the bundle's own words
	// for that, and they are already on the audit.
	Did []Did `json:"did"`
}

// Did is one operation this visit committed, titled by its own declaration.
type Did struct {
	Operation string `json:"operation"`
	Title     any    `json:"title"`
}

// Found is what GET /subjects/{id} answers.
type Found struct {
	Subject    map[string]any `json:"subject"`
	Spine      string         `json:"spine"`
	Encounters []Visit        `json:"encounters"`
	Episodes   []Episode      `json:"episodes"`
}

// Episode is the level between a person and a visit: one course of care that
// starts, runs and ends, holding the visits that happened during it.
// kernel/spine.episodes is the Python half and carries the reasoning.
type Episode struct {
	ID          string   `json:"id"`
	Type        string   `json:"type"`
	Status      string   `json:"status"`
	OpenedAt    string   `json:"opened_at"`
	EndedAt     string   `json:"ended_at"`
	Outcome     string   `json:"outcome"`
	AnchorDate  string   `json:"anchor_date"`
	AnchorBasis string   `json:"anchor_basis"`
	Encounters  []string `json:"encounters"`
}

// Declared is the spine resource for this workflow, or "" if it declares none.
func Declared(wf *carephc.Workflow) string { return wf.Spine }

// Of is the subject row, and every thread that shares it, newest first.
//
// Returns nil when the workflow declares no spine or the subject does not
// exist. The caller turns that into a 404; inventing an empty subject here
// would let a typo render as a person with no visits.
func Of(s Reader, wf *carephc.Workflow, operations map[string]carephc.Operation,
	subjectID string, limit int) (*Found, error) {
	link := Declared(wf)
	if link == "" {
		return nil, nil
	}
	rows, err := s.SelectNullable(link, nil, store.Query{"id": {Equals: subjectID}}, nil, 1)
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	subject := rows[0]

	// ponytail: one select for the encounters, then one flags derivation per
	// encounter. That is N+1 reads for N visits, which is right for a person
	// with a handful and wrong for a cohort screen. The fix when it matters is
	// a store method that returns flags for many threads at once, not a cache.
	encounters, err := s.SelectNullable(wf.Subject, nil,
		store.Query{link: {Equals: subjectID}}, nil, limit)
	if err != nil {
		return nil, err
	}
	visits := make([]Visit, 0, len(encounters))
	for _, row := range encounters {
		thread, _ := row["id"].(string)
		known, err := kstate.Flags(s, thread, wf, time.Time{})
		if err != nil {
			return nil, err
		}
		did, err := didOn(s, thread, operations)
		if err != nil {
			return nil, err
		}
		visits = append(visits, Visit{
			Thread: thread, OpenedAt: text(row["created_date"]),
			Status: text(row["status"]), Token: text(row["token"]),
			Flags: sortedKeys(known), Station: nullIfEmpty(kstate.Station(wf, known)),
			Did: did,
		})
	}
	// Stable, as the Python's list.sort is, so two visits opened in the same
	// second keep the order the store answered in.
	sort.SliceStable(visits, func(i, j int) bool {
		return visits[i].OpenedAt > visits[j].OpenedAt
	})
	arcs, err := Episodes(s, wf, subjectID, visits)
	if err != nil {
		return nil, err
	}
	return &Found{Subject: subject, Spine: link, Encounters: visits, Episodes: arcs}, nil
}

// Episodes is kernel/spine.episodes: this subject's episodes, newest first,
// each holding its own visits.
//
// AN EPISODE ENDS BY GAINING A ROW rather than by having its first one
// rewritten, so the rows come back in pairs and an implementation that
// simply listed them would report a closed pregnancy as two episodes, one
// of them still open. An episode that reads as open is an episode something
// goes on chasing.
//
// WHICH VISITS BELONG TO ONE IS DERIVED FROM THE DATES. A column on the
// encounter would have to be written before anybody knew the answer, and a
// column nothing writes is a column that lies.
func Episodes(s Reader, wf *carephc.Workflow, subjectID string,
	visits []Visit) ([]Episode, error) {
	if wf.Episode == "" {
		return []Episode{}, nil
	}
	rows, err := s.SelectNullable(wf.Episode, nil,
		store.Query{"patient": {Equals: subjectID}}, nil, 200)
	if err != nil {
		return nil, err
	}
	sort.SliceStable(rows, func(i, j int) bool {
		return text(rows[i]["created_date"]) < text(rows[j]["created_date"])
	})

	out := []Episode{}
	openOfType := map[string]int{}
	for _, row := range rows {
		of := text(row["type"])
		if text(row["status"]) == "ended" {
			if at, open := openOfType[of]; open {
				out[at].EndedAt = text(row["created_date"])
				out[at].Outcome = text(row["outcome"])
				out[at].Status = "ended"
				delete(openOfType, of)
			}
			continue
		}
		out = append(out, Episode{
			ID: text(row["id"]), Type: of, Status: "active",
			OpenedAt:    text(row["created_date"]),
			AnchorDate:  text(row["anchor_date"]),
			AnchorBasis: text(row["anchor_basis"]),
		})
		openOfType[of] = len(out) - 1
	}

	for i := range out {
		out[i].Encounters = []string{}
		for _, v := range visits {
			if v.OpenedAt >= out[i].OpenedAt &&
				(out[i].EndedAt == "" || v.OpenedAt <= out[i].EndedAt) {
				out[i].Encounters = append(out[i].Encounters, v.Thread)
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool {
		return out[i].OpenedAt > out[j].OpenedAt
	})
	return out, nil
}

// committed are the audit outcome prefixes that mean this visit did the thing.
// A proposal is a request and a denial is the opposite of one, so neither is
// here; "committed" is carried because the Python carries it, although no
// outcome in this build begins with it.
var committed = []string{"committed", "confirmed", "allowed"}

// didOn is kernel/spine._did: the distinct operations this visit committed, in
// the order they landed, titled by their own declarations.
func didOn(s Reader, thread string, operations map[string]carephc.Operation) ([]Did, error) {
	trail, err := s.Audit(thread)
	if err != nil {
		return nil, err
	}
	out := []Did{}
	seen := map[string]bool{}
	for _, record := range trail {
		did := false
		for _, prefix := range committed {
			if strings.HasPrefix(record.Outcome, prefix) {
				did = true
				break
			}
		}
		if !did || seen[record.Operation] {
			continue
		}
		seen[record.Operation] = true
		var title any = record.Operation
		if op, declared := operations[record.Operation]; declared {
			// The declaration's own word. An operation the bundle does not
			// hold keeps its id, which is what the Python's getattr fallback
			// answers for the same case.
			title = op.Title
		}
		out = append(out, Did{Operation: record.Operation, Title: title})
	}
	return out, nil
}

func text(v any) string {
	s, _ := v.(string)
	return s
}

func sortedKeys(set map[string]bool) []string {
	out := make([]string, 0, len(set))
	for key := range set {
		out = append(out, key)
	}
	sort.Strings(out)
	return out
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
