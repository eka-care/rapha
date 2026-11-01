package queues_test

// The third seam, closed: the placement a document is published through comes
// from the COMPILED CATALOGUE and not from the caller.
//
// Until 2026-11-01 `documents` was not a bundle key, so the word did not
// appear in catalogue.json and no Go process could read it. fhir.Document had
// to be handed the placement, and a caller that can hand one in is a caller
// that can retype one, which is the defect the declaration was moved onto the
// bundle to end: the same diagnosis was filed under Chief complaints in one
// check and under Medical History in another.
//
// So what is held here is that the production body builder reads the
// declaration, in the order the bundle declared it, with NO placement written
// down in this file. The only way this test knows which sections to expect is
// by asking the catalogue, which is the point.

import (
	"strings"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/fhir"
	"github.com/eka-care/care_phc_mcp/queues"
	"github.com/eka-care/care_phc_mcp/store"
)

// rowsFor is the one read fhir.Document makes, over a visit held in memory.
type rowsFor struct {
	thread string
	tables map[string][]map[string]string
}

func (r rowsFor) Select(resource string, thread *string, where store.Query,
	fields []string, limit int) ([]map[string]string, error) {
	if thread != nil && *thread != r.thread {
		return nil, nil
	}
	out := []map[string]string{}
	for _, row := range r.tables[resource] {
		keep := true
		for field, cond := range where {
			if cond.Present {
				if row[field] == "" {
					keep = false
				}
				continue
			}
			if row[field] != cond.Equals {
				keep = false
			}
		}
		if keep {
			out = append(out, row)
		}
		if limit > 0 && len(out) >= limit {
			break
		}
	}
	return out, nil
}

func loadedCatalogue(t *testing.T) *carephc.Catalogue {
	t.Helper()
	cat, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := cat.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	return cat
}

func TestThePlacementComesFromTheCompiledCatalogue(t *testing.T) {
	cat := loadedCatalogue(t)
	if len(cat.Documents) == 0 {
		t.Fatal("the compiled catalogue carries no `documents`, so no Go " +
			"process can know where a row is filed and nothing can be " +
			"published. That is the third seam, and it is supposed to be shut.")
	}
	declared, publishes := cat.Documents["consultation"]
	if !publishes {
		t.Fatalf("this bundle declares %v and not a consultation",
			keysOf(cat.Documents))
	}
	if declared.Profile == "" {
		t.Error("the declared document names no profile")
	}
	if len(declared.Sections) == 0 {
		t.Error("the declared document names no section")
	}
	// The sections arrive as an ORDERED list, which is the shape decision: a
	// mapping could not carry the order through a dumper that sorts its keys.
	// What is asserted is that the order is not the alphabetical one, because
	// that is the order a mapping would have arrived in.
	names := make([]string, 0, len(declared.Sections))
	for _, section := range declared.Sections {
		if section.Slice == "" {
			t.Error("a declared section names no slice")
		}
		if len(section.Queries) == 0 {
			t.Errorf("the %s section asks for no rows, so it could never have "+
				"anything in it", section.Slice)
		}
		names = append(names, section.Slice)
	}
	if isSorted(names) {
		t.Errorf("this bundle's declared sections %v are in alphabetical "+
			"order, so nothing here would notice a compiler that sorted "+
			"them", names)
	}
}

// And the placement reaches the PROJECTION, in that order. This is the whole
// of what the third seam was blocking: a document built by a Go process, filed
// where the bundle says.
func TestADocumentIsBuiltThroughTheDeclaredPlacementInOrder(t *testing.T) {
	cat := loadedCatalogue(t)
	declared := cat.Documents["consultation"]

	// A visit with one row under each section the bundle declares, so every
	// declared section has something in it and the order is observable. The
	// RESOURCE names come from the declaration, not from this file.
	rows := rowsFor{thread: "enc-1", tables: map[string][]map[string]string{
		"encounter": {{"id": "enc-1", "patient": "pat-1", "status": "finished",
			"created_by": "user:mo", "created_date": "2026-11-01"}},
		"patient": {{"id": "pat-1", "name": "A Patient", "age": "40",
			"sex": "female", "created_by": "user:mo"}},
	}}
	for n, section := range declared.Sections {
		for _, query := range section.Queries {
			row := map[string]string{
				"id":           "row-" + itoa(n),
				"encounter":    "enc-1",
				"created_by":   "user:mo",
				"created_date": "2026-11-01",
				// Enough for every projection this bundle files: a coded row
				// needs a code, a narrative row needs text.
				"code":                "73211009",
				"code_system":         "http://snomed.info/sct",
				"code_display":        "a finding",
				"clinical_status":     "active",
				"verification_status": "confirmed",
				"medication":          "387517004",
				"medication_system":   "http://snomed.info/sct",
				"medication_display":  "a medicine",
				"intent":              "order",
				"status":              "active",
				"text":                "the doctor's own words",
			}
			// A section's own condition is honoured, so a declaration that
			// narrows its rows is not quietly widened here.
			for field, cond := range mustQuery(t, query.Where) {
				if cond.Equals != "" {
					row[field] = cond.Equals
				}
			}
			rows.tables[query.Resource] = append(rows.tables[query.Resource], row)
		}
	}

	body, err := queues.DocumentBody(rows, cat,
		queues.Item{Kind: "document", Key: "enc-1", Thread: "enc-1"},
		"2026-11-01T10:05:00+00:00", "consultation")
	if err != nil {
		t.Fatalf("a visit with a row under every declared section would not "+
			"publish: %v", err)
	}
	bundle, isBundle := body.(map[string]any)
	if !isBundle {
		t.Fatalf("the body is %T and not a document bundle", body)
	}
	entries, _ := bundle["entry"].([]any)
	if len(entries) == 0 {
		t.Fatal("the document has no entries")
	}
	first, _ := entries[0].(map[string]any)
	composition, _ := first["resource"].(map[string]any)
	sections, _ := composition["section"].([]any)
	if len(sections) != len(declared.Sections) {
		t.Fatalf("the document carries %d sections and the bundle declares %d",
			len(sections), len(declared.Sections))
	}
	// THE ORDER. Each published section's title is the profile's own for the
	// slice the bundle declared at that position, so this compares the
	// published order against the DECLARED order without naming a heading.
	for n, section := range declared.Sections {
		wantTitle := titleOf(t, declared.Profile, section.Slice)
		published, _ := sections[n].(map[string]any)
		gotTitle, _ := published["title"].(string)
		if gotTitle != wantTitle {
			t.Errorf("section %d of the document is %q and the bundle "+
				"declares %q at that position. A section order that changes "+
				"between the declaration and the document publishes this "+
				"facility's consultations the wrong way round.",
				n, gotTitle, wantTitle)
		}
	}
}

// A document this bundle does not declare is refused, and the refusal says so
// rather than publishing an empty one.
func TestADocumentThisBundleDoesNotDeclareIsRefused(t *testing.T) {
	cat := loadedCatalogue(t)
	_, err := queues.DocumentBody(rowsFor{thread: "enc-1"}, cat,
		queues.Item{Kind: "document", Key: "enc-1", Thread: "enc-1"},
		"2026-11-01T10:05:00+00:00", "a-document-nobody-declared")
	if err == nil {
		t.Fatal("a document this bundle does not declare was published")
	}
	if !strings.Contains(err.Error(), "declares no") {
		t.Errorf("the refusal does not say why: %v", err)
	}
}

// And a catalogue whose declarations were never loaded is refused rather than
// treated as a bundle that publishes nothing. Those are different facts: one
// is a facility that files no documents, the other is a kernel that never read
// where to file them.
func TestAnUnloadedCatalogueIsRefusedRatherThanReadAsPublishingNothing(t *testing.T) {
	bare, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if bare.Documents != nil {
		t.Fatal("Load filled Documents, so this distinction cannot be made")
	}
	_, err = queues.DocumentBody(rowsFor{thread: "enc-1"}, bare,
		queues.Item{Kind: "document", Key: "enc-1", Thread: "enc-1"},
		"2026-11-01T10:05:00+00:00", "consultation")
	if err == nil {
		t.Fatal("a kernel that never loaded the placement published anyway")
	}
	if !strings.Contains(err.Error(), "not been loaded") {
		t.Errorf("the refusal does not say which of the two happened: %v", err)
	}
}

func keysOf(m map[string]carephc.DocumentDecl) []string {
	out := []string{}
	for key := range m {
		out = append(out, key)
	}
	return out
}

func isSorted(names []string) bool {
	for i := 1; i < len(names); i++ {
		if names[i-1] > names[i] {
			return false
		}
	}
	return true
}

func mustQuery(t *testing.T, where map[string]any) store.Query {
	t.Helper()
	out := store.Query{}
	for field, value := range where {
		if text, is := value.(string); is {
			out[field] = store.Cond{Equals: text}
		}
	}
	return out
}

// titleOf is the profile's own title for a slice, read from the projection
// package rather than written down, so no heading is typed in this file.
func titleOf(t *testing.T, profile, slice string) string {
	t.Helper()
	section, found := fhir.Sections(profile)[slice]
	if !found {
		t.Fatalf("%s declares no section %q, which the lint should have "+
			"refused at build time", profile, slice)
	}
	return section.Title
}
