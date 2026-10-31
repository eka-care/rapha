// The one mapping property the socket cannot reach, and a check that the
// compiled declaration is actually being read.
//
// Found by mutation: deleting the refusal to write a row whose coded answer
// is absent changed nothing either engine answered, because the validator
// refuses that payload at guard step 1 — every such answer is declared
// required. So the refusal here is a SECOND line, and a second line is
// exactly the kind of code that rots unproved. It exists because a
// laboratory result whose analyte was left blank became an observation
// carrying a value and a unit and no code, which is a clinical number with
// nothing saying what it measured.
package mapping

import (
	"path/filepath"
	"testing"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/terminology"
)

func loaded(t *testing.T) (*carephc.Catalogue, *terminology.Cache) {
	t.Helper()
	cat, err := carephc.Load()
	if err != nil {
		t.Fatal(err)
	}
	if err := cat.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	terms, err := terminology.Load(filepath.Join("..", "..", "terminology"))
	if err != nil {
		t.Fatal(err)
	}
	return cat, terms
}

func recordsOf(t *testing.T, cat *carephc.Catalogue, id string) []Record {
	t.Helper()
	var out []Record
	found, err := cat.Mapping(id, &out)
	if err != nil {
		t.Fatal(err)
	}
	if !found || len(out) == 0 {
		t.Fatalf("%s carries no compiled mapping; recompile with "+
			"python3 -m catalogue.build && python3 -m kernel.declarations", id)
	}
	return out
}

// A prescription row, with every sub answer the compiled mapping's own
// `questions` map says carries a concept. Built from the declaration so it
// grows with the form.
func prescription(t *testing.T, record Record, terms *terminology.Cache) map[string]any {
	t.Helper()
	row := map[string]any{"dose": 1, "duration": 1}
	for linkID := range record.Questions {
		node, _ := record.Questions[linkID].(map[string]any)
		slug, _ := node["answer_value_set"].(string)
		if slug == "" {
			t.Fatalf("%s declares no answer_value_set in the compiled mapping", linkID)
		}
		row[linkID] = anyCode(t, terms, slug)
	}
	return row
}

// anyCode is a code the value set holds, taken through the only constructor
// rather than off the file: a code this test picked that the value set did not
// hold would make the test about the test.
func anyCode(t *testing.T, terms *terminology.Cache, slug string) string {
	t.Helper()
	for _, candidate := range terms.Codes(slug) {
		if c, err := terms.Bound(slug, candidate); err == nil {
			return c.Code()
		}
	}
	t.Fatalf("no code in %s", slug)
	return ""
}

// NO ROW IS WRITTEN WHOSE CODED ANSWER IS ABSENT.
//
// For every per_row record the catalogue declares with an answer-coded
// column: the full row writes one row, and the same row with that one answer
// removed writes none. Not an uncoded row, and not a row borrowing the
// concept from the line above it.
func TestARowWhoseCodedAnswerIsAbsentIsNotWritten(t *testing.T) {
	cat, terms := loaded(t)
	checked := 0
	for _, id := range carephc.SortedOperationIDs(cat.BundleOperations()) {
		var records []Record
		if found, err := cat.Mapping(id, &records); err != nil {
			t.Fatal(err)
		} else if !found {
			continue
		}
		for _, record := range records {
			if record.PerRow == "" || len(record.Questions) == 0 {
				continue
			}
			coded := codedAnswers(record)
			if len(coded) == 0 {
				continue
			}
			full := prescription(t, record, terms)
			payload := map[string]any{record.PerRow: []any{clone(full)}}
			rows, err := Records(records, payload, "user:test", terms)
			if err != nil {
				t.Fatalf("%s: the full row failed: %v", id, err)
			}
			if len(rows) == 0 {
				t.Fatalf("%s: a fully answered row wrote nothing, so this "+
					"test proves nothing", id)
			}
			before := len(rows)
			for _, linkID := range coded {
				short := clone(full)
				delete(short, linkID)
				payload := map[string]any{record.PerRow: []any{short}}
				rows, err := Records(records, payload, "user:test", terms)
				if err != nil {
					// A refusal is an acceptable answer: what must not happen
					// is a row.
					continue
				}
				for _, row := range rows {
					if row.Resource == record.Resource {
						t.Fatalf("%s: %s was not answered and a %s row was "+
							"written anyway: %v", id, linkID, row.Resource, row.Columns)
					}
				}
				checked++
			}
			if before == 0 {
				t.Fatal("unreachable")
			}
		}
	}
	if checked == 0 {
		t.Fatal("no per_row record with a coded answer in the catalogue, so " +
			"this proves nothing")
	}
}

// AN ANSWER THE VALUE SET DOES NOT HOLD NEVER REACHES A COLUMN, which is the
// write-time half of invariant I1: the compiled mapping travels as plain
// JSON, so the facts arrive as strings and a string carries no proof.
func TestAnAnswerOutsideItsValueSetCannotFillAColumn(t *testing.T) {
	cat, terms := loaded(t)
	records := recordsOf(t, cat, "phc.op.rx-prescribe")
	var per Record
	for _, record := range records {
		if record.PerRow != "" && len(record.Questions) > 0 {
			per = record
		}
	}
	row := prescription(t, per, terms)
	row["drug"] = "999999999"
	payload := map[string]any{per.PerRow: []any{row}}
	if rows, err := Records(records, payload, "user:test", terms); err == nil {
		t.Fatalf("a drug code no value set holds became %d rows: %v",
			len(rows), rows)
	}
}

func codedAnswers(record Record) []string {
	seen := map[string]bool{}
	var out []string
	for _, column := range record.columns() {
		source := record.Fields[column]
		if _, coded := answerCodingFacts[source.Kind]; !coded {
			continue
		}
		if key, ok := source.Arg.(string); ok && !seen[key] {
			seen[key] = true
			out = append(out, key)
		}
	}
	return out
}

func clone(in map[string]any) map[string]any {
	out := map[string]any{}
	for k, v := range in {
		out[k] = v
	}
	return out
}
