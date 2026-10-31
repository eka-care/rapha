package fhir

import (
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/store"
)

// Rows is the one thing Document needs from a store, which is the read it
// already serves. Narrowed to an interface rather than taking the whole
// Store, so that nothing in this package can write.
type Rows interface {
	Select(resource string, thread *string, where store.Query, fields []string,
		limit int) ([]map[string]string, error)
}

// Query is one of a section's row queries: a resource table and the condition
// its rows must meet.
type Query struct {
	Resource string
	Where    store.Query
}

// Want is one section slice and the rows that go in it, in the order the
// bundle declared them.
//
// A SLICE AND NOT A MAP, which is not a Go idiom preference. The Python
// iterates `sections_wanted` in insertion order, and that order is observable
// three times over: which order the sections come out in, which order the
// Bundle's entries come out in, and which order the authors are discovered
// in. A Go map would publish a different document on every run.
type Want struct {
	Slice   string
	Queries []Query
}

// Document is a thread as an ABDM DocumentBundle for one profile.
//
// `wanted` maps a section slice name to the resource rows that go in it. The
// CALLER says which section a kind of row belongs in, because that is a
// declaration and not this file's business: the same division the views have,
// where a view declares a query and the kernel runs it.
//
// Refuses a profile or a section slice the standard does not declare, rather
// than emitting a section ABDM will reject.
func Document(rows Rows, thread string, profile string, wanted []Want, now string,
	identifierSystem string) (map[string]any, error) {
	spec, known := Profiles[profile]
	if !known {
		// Python indexes PROFILES directly, so an unknown profile is a
		// KeyError whose message is the key itself. Said the same way here.
		return nil, refuse("%s", pyval.Repr(profile))
	}
	if identifierSystem == "" {
		identifierSystem = "http://phc.local"
	}
	declaredSlices := make([]string, 0, len(spec.Sections))
	for name := range spec.Sections {
		declaredSlices = append(declaredSlices, name)
	}
	for _, want := range wanted {
		if _, has := spec.Sections[want.Slice]; !has {
			return nil, refuse("%s declares no section '%s'; it has %s",
				profile, want.Slice, pyval.ReprStrings(declaredSlices))
		}
	}

	encRows, err := rows.Select("encounter", &thread, store.Query{}, nil, 1)
	if err != nil {
		return nil, err
	}
	if len(encRows) == 0 {
		return nil, refuse("no such thread %s", pyval.Repr(thread))
	}
	enc := encRows[0]
	patRows, err := rows.Select("patient", &thread, store.Query{}, nil, 1)
	if err != nil {
		return nil, err
	}
	if len(patRows) == 0 {
		// A visit with no person on it cannot be published: every profile
		// makes Composition.subject required, and a document about nobody is
		// not a degraded document, it is a different kind of mistake. Refused
		// here rather than emitted and rejected by the gateway an hour later.
		return nil, refuse("thread %s has no subject, so it has no "+
			"Composition.subject", pyval.Repr(thread))
	}
	pat := patRows[0]

	subjectRef := URN(pat["id"])
	encounterRef := URN(enc["id"])
	type entry struct {
		resource map[string]any
		ref      string
	}
	entries := []entry{{Patient(pat), subjectRef}, {Encounter(enc, subjectRef), encounterRef}}

	var authors []entry
	var sectionOut []any
	for _, want := range wanted {
		var refs []any
		for _, query := range want.Queries {
			where := query.Where
			if where == nil {
				where = store.Query{}
			}
			found, err := rows.Select(query.Resource, &thread, where, nil, 200)
			if err != nil {
				return nil, err
			}
			for _, row := range found {
				ref := URN(row["id"])
				performer := ""
				if actor := row["created_by"]; actor != "" {
					prac := Practitioner(actor)
					performer = URN(prac["id"].(string))
					seen := false
					for _, author := range authors {
						if author.ref == performer {
							seen = true
							break
						}
					}
					if !seen {
						authors = append(authors, entry{prac, performer})
					}
				}
				project, has := Projections[query.Resource]
				if !has {
					return nil, refuse("no FHIR projection for a %s row, so a "+
						"section asking for one would publish something else. Add "+
						"it to PROJECTIONS rather than letting the nearest one "+
						"serve.", pyval.Repr(query.Resource))
				}
				var documentType *DocumentType
				if TypedByProfile[query.Resource] {
					kind := spec.Type
					documentType = &kind
				}
				made, err := project(row, subjectRef, encounterRef, performer, documentType)
				if err != nil {
					return nil, err
				}
				if made == nil {
					// A projection that refuses this particular row: an empty
					// narrative is the only one today. Skipped rather than
					// published as an entry pointing at nothing.
					continue
				}
				entries = append(entries, entry{made, ref})
				display := ResourceType[query.Resource]
				if display == "" {
					display = query.Resource
				}
				refs = append(refs, map[string]any{"reference": ref, "display": display})
			}
		}
		if len(refs) == 0 {
			// An empty section is not a section. Every slice is min 0, so
			// omitting it is correct, and emitting an entryless one would
			// publish a heading claiming nothing was found rather than that
			// nothing was looked for.
			continue
		}
		declared := spec.Sections[want.Slice]
		section := map[string]any{"title": declared.Title, "entry": refs}
		if declared.Code != "" {
			// The display the standard publishes for that code, which is not
			// the section's title: the "Chief complaints" section carries the
			// display "Chief complaint section". Using the title would put a
			// display beside a code that the code system does not give it.
			section["code"] = map[string]any{"coding": []any{map[string]any{
				"system": SNOMED, "code": declared.Code, "display": declared.Display}}}
		}
		sectionOut = append(sectionOut, section)
	}

	if len(sectionOut) == 0 {
		return nil, refuse("thread %s has nothing to put in %s, and every profile "+
			"requires at least one section", pyval.Repr(thread), profile)
	}
	entries = append(authors, entries...)

	authorRefs := make([]any, 0, len(authors))
	for _, author := range authors {
		authorRefs = append(authorRefs, map[string]any{"reference": author.ref})
	}
	compositionType := map[string]any{"text": spec.Type.Text}
	composition := map[string]any{
		"resourceType": "Composition",
		"id":           "comp-" + enc["id"],
		"meta":         map[string]any{"profile": []any{spec.Profile}, "lastUpdated": now},
		"language":     "en-IN",
		"identifier":   map[string]any{"system": identifierSystem, "value": enc["id"]},
		"status":       "final",
		"subject":      map[string]any{"reference": subjectRef},
		"encounter":    map[string]any{"reference": encounterRef},
		"date":         now,
		"author":       authorRefs,
		"title":        spec.Title,
		"type":         compositionType,
		"section":      sectionOut,
	}
	if spec.Type.Code != "" {
		compositionType["coding"] = []any{map[string]any{"system": SNOMED,
			"code": spec.Type.Code, "display": spec.Type.Text}}
	}
	entries = append([]entry{{composition, URN("composition:" + enc["id"])}}, entries...)

	out := make([]any, 0, len(entries))
	for _, one := range entries {
		out = append(out, map[string]any{"fullUrl": one.ref, "resource": one.resource})
	}
	return map[string]any{
		"resourceType": "Bundle",
		"id":           "phc-" + strings.ToLower(profile) + "-" + enc["id"],
		// versionId is required by the DocumentBundle profile, not optional
		// metadata: a bundle without it fails NRCeS validation. "1" because a
		// correction is published as a new bundle that relatesTo this one,
		// which is how ABDM versions a record, rather than as a second
		// version of the same identifier.
		"meta": map[string]any{"versionId": "1", "profile": []any{DocumentBundle},
			"lastUpdated": now},
		"identifier": map[string]any{"system": identifierSystem, "value": enc["id"]},
		"type":       "document",
		"timestamp":  now,
		"entry":      out,
	}, nil
}
