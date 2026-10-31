// Package mapping is the evaluation half of kernel/mapping.py: which answer
// becomes which column, read from the compiled declaration rather than
// guessed.
//
// WHY ONLY THE EVALUATION HALF
// ----------------------------
// kernel/mapping.py is two things: a lint-and-compile pass over the operation
// atoms, and an evaluator that turns one payload into rows. The compile half
// stays in Python, because it runs at build time against catalogue/ops/*.md
// and resolves each `{question: code}` through the terminology once per build.
// What it emits is plain JSON, and from 2026-10-31 it is in catalogue.json
// under `mapping` (see kernel/contracts.BUNDLE_KEYS). So this package reads a
// finished declaration and never parses an atom.
//
// THE WRITE-TIME HALF OF INVARIANT I1 IS HERE AND IS NOT A FORMALITY
// ------------------------------------------------------------------
// The compiled mapping travels as plain JSON, which means a Coding object
// cannot travel and the facts arrive as strings. A string carries no proof, so
// the proof is re-established where the row is made: every `{question: code}`
// and every `{answer_code: ...}` is checked against the same value set again
// before it will fill a column. The check is a map lookup in a file read at
// startup. No socket, no database, nothing that can be down.
//
// A RECORD THAT HAS NOTHING TO SAY WRITES NOTHING
// -----------------------------------------------
// A record that codes a column from an answer writes NOTHING when that answer
// is absent. Not a style choice: without it a laboratory result whose analyte
// was left blank became an observation carrying a value and a unit and no
// code, which is a clinical number with nothing saying what it measured. Found
// by mutation on the Python side.
package mapping

import (
	"fmt"
	"sort"
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// Record is one compiled mapping record: one resource, one fan-out rule, and
// the columns.
type Record struct {
	Resource    string            `json:"resource"`
	PerRow      string            `json:"per_row"`
	PerItem     string            `json:"per_item"`
	PerQuestion []map[string]any  `json:"per_question"`
	Questions   map[string]any    `json:"questions"`
	Fields      map[string]Source `json:"fields"`
}

// Source is one of the mapping grammar's single-key dicts. Kind is the key
// and Arg the argument, which is a literal for `const`, a link_id for most of
// the rest, and a list for `joined` and `note`.
type Source struct {
	Kind string
	Arg  any
}

// UnmarshalJSON reads the single-key dict the grammar is, refusing anything
// else. Lint has already refused it on the Python side, so this is the second
// line rather than the first.
func (s *Source) UnmarshalJSON(raw []byte) error {
	var node map[string]any
	if err := pyval.Decode(raw, &node); err != nil {
		return err
	}
	if len(node) != 1 {
		return fmt.Errorf("a mapping source is one key, got %d", len(node))
	}
	for kind, arg := range node {
		s.Kind, s.Arg = kind, arg
	}
	return nil
}

// payloadFree are the sources that do not read the payload. A record made
// only of these is written every time; a record with any other source is
// written only when the payload gave one of them a value.
var payloadFree = map[string]bool{"const": true, "actor": true}

// answerCodingFacts is the answer-bound family and which part of the resolved
// coding each reads. Unlike the `question:` facts these cannot be resolved at
// build time: the concept is whichever one the technician picked.
var answerCodingFacts = map[string]string{
	"answer_code": "code", "answer_code_system": "system",
	"answer_code_display": "display",
}

// codingFacts is what `{question: X}` may ask about a question's BINDING, and
// which binding each one belongs to.
var codingFacts = map[string]string{
	"code": "code", "code_system": "code", "code_display": "code",
	"unit": "unit", "unit_system": "unit",
}

// codingBinding is the value set each binding is closed over.
var codingBinding = map[string]string{
	"code": terminology.CodeBinding, "unit": terminology.UnitBinding,
}

// Row is one record's output: the resource it belongs to and the columns.
type Row struct {
	Resource string
	Columns  map[string]any
}

// Records is the rows this payload becomes, in declared order.
//
// An operation with no mapping writes nothing, which lint already refuses for
// a write operation.
func Records(records []Record, payload map[string]any, actor string,
	terms *terminology.Cache) ([]Row, error) {
	var out []Row
	for _, record := range records {
		// The bound questions this record's answer coding sources need, so
		// value() never opens a questionnaire. Compiled in, and JSON-able,
		// because the compiled mapping travels to the renderer.
		bound := record.Questions
		if record.PerRow != "" {
			// One record row per group row, and the row IS the payload. Every
			// source below it therefore behaves identically to the top level,
			// including the refusal to write a row whose coded answer is
			// absent: a medicine with no drug code is no medication_request,
			// not an uncoded one, and it does not borrow the drug from the
			// line above it.
			for _, given := range rows(payload, record.PerRow) {
				context := map[string]any{}
				if len(bound) > 0 {
					context["questions"] = bound
				}
				made, err := row(record, given, context, actor, terms)
				if err != nil {
					return nil, err
				}
				if made != nil {
					out = append(out, Row{record.Resource, made})
				}
			}
			continue
		}
		var contexts []map[string]any
		switch {
		case record.PerItem != "":
			contexts = items(payload, record.PerItem)
		case record.PerQuestion != nil:
			for _, q := range record.PerQuestion {
				linkID, _ := q["link_id"].(string)
				answer := payload[linkID]
				if pyval.IsBlank(answer) {
					continue
				}
				context := map[string]any{}
				for k, v := range q {
					context[k] = v
				}
				context["answer"] = answer
				contexts = append(contexts, context)
			}
		default:
			contexts = []map[string]any{{}}
		}
		for _, context := range contexts {
			if len(bound) > 0 {
				merged := map[string]any{}
				for k, v := range context {
					merged[k] = v
				}
				merged["questions"] = bound
				context = merged
			}
			made, err := row(record, payload, context, actor, terms)
			if err != nil {
				return nil, err
			}
			if made != nil {
				out = append(out, Row{record.Resource, made})
			}
		}
	}
	return out, nil
}

// items is a repeating structured answer as a list of dicts. A bare string
// counts as {"code": <it>}, because that is what a renderer sends for a free
// text line and dropping it would lose the order.
func items(payload map[string]any, linkID string) []map[string]any {
	value := payload[linkID]
	if pyval.IsBlank(value) {
		return nil
	}
	listed, ok := value.([]any)
	if !ok {
		listed = []any{value}
	}
	out := make([]map[string]any, 0, len(listed))
	for _, item := range listed {
		if node, ok := item.(map[string]any); ok {
			out = append(out, node)
			continue
		}
		out = append(out, map[string]any{"code": pyval.Str(item)})
	}
	return out
}

// rows is a repeating group's answer as a list of row payloads.
//
// Unlike items above, a row that is not a mapping is DROPPED rather than read
// as {code: <it>}. The difference is the point: a structured answer had no
// declared shape, so a bare string was the only thing a renderer could send
// and salvaging it was right. A group declares its sub questions, so a bare
// string is a renderer that lost the row, and the validator has already
// refused it.
func rows(payload map[string]any, linkID string) []map[string]any {
	value := payload[linkID]
	if pyval.IsBlank(value) {
		return nil
	}
	listed, ok := value.([]any)
	if !ok {
		listed = []any{value}
	}
	var out []map[string]any
	for _, item := range listed {
		if node, ok := item.(map[string]any); ok {
			copied := map[string]any{}
			for k, v := range node {
				copied[k] = v
			}
			out = append(out, copied)
		}
	}
	return out
}

func first(context map[string]any, arg any) any {
	for _, key := range stringList(arg) {
		if value, has := context[key]; has && !pyval.IsBlank(value) {
			return value
		}
	}
	return nil
}

func stringList(arg any) []string {
	switch t := arg.(type) {
	case string:
		return []string{t}
	case []any:
		out := make([]string, 0, len(t))
		for _, item := range t {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	}
	return nil
}

// boundFact is one fact a question's binding produced, re-checked before it is
// stored. The clause that makes this a check and not a comment is the
// Validate call: a code the value set does not hold stops the write rather
// than becoming a row. A missing fact stops it too, because a coding column
// that lands null is the silent failure this file exists to prevent.
func boundFact(fact string, context map[string]any, terms *terminology.Cache) (any, error) {
	which := codingFacts[fact]
	var code any
	if which == "code" {
		code = context["code"]
	} else {
		code = context[which]
	}
	value := context[fact]
	where := context["link_id"]
	if pyval.IsBlank(code) || pyval.IsBlank(value) {
		return nil, fmt.Errorf("question %s has no %s binding, so {question: %s} "+
			"has nothing a value set vouched for", pyval.Repr(where), which, fact)
	}
	if !terms.Validate(codingBinding[which], code) {
		return nil, fmt.Errorf("question %s would store %s, which value set %s "+
			"does not hold", pyval.Repr(where), pyval.Repr(code),
			pyval.Repr(codingBinding[which]))
	}
	return value, nil
}

func value(source Source, payload, context map[string]any, actor string,
	terms *terminology.Cache) (any, error) {
	switch source.Kind {
	case "const":
		return source.Arg, nil
	case "actor":
		return actor, nil
	case "answer":
		key, _ := source.Arg.(string)
		return payload[key], nil
	case "answer_code", "answer_code_system", "answer_code_display":
		key, _ := source.Arg.(string)
		declared, _ := context["questions"].(map[string]any)
		node, onForm := declared[key].(map[string]any)
		if !onForm {
			return nil, fmt.Errorf("{%s: %s} has no question to read a binding "+
				"from; lint should have refused it", source.Kind, key)
		}
		answer := payload[key]
		if pyval.IsBlank(answer) {
			// Unreachable from row(), which refuses the whole record first.
			// Kept as the same fail-closed shape boundFact has rather than
			// returning nothing: a code column that lands null is the silent
			// failure this package exists to prevent, and the two coding
			// families must not disagree about that.
			return nil, fmt.Errorf("question %s was not answered, so {%s: %s} "+
				"has no concept to store", pyval.Repr(key), source.Kind, key)
		}
		coding, err := terms.AnswerCoding(questionOf(node), answer)
		if err != nil {
			return nil, err
		}
		return coding.Fact(answerCodingFacts[source.Kind]), nil
	case "item":
		return first(context, source.Arg), nil
	case "minus":
		found := first(context, source.Arg)
		if pyval.IsBlank(found) {
			return nil, nil
		}
		return "-" + pyval.Str(found), nil
	case "question":
		fact, _ := source.Arg.(string)
		if _, coded := codingFacts[fact]; coded {
			return boundFact(fact, context, terms)
		}
		return context[fact], nil
	case "joined":
		var parts []string
		for _, key := range stringList(source.Arg) {
			if !pyval.IsBlank(payload[key]) {
				parts = append(parts, pyval.Str(payload[key]))
			}
		}
		if len(parts) == 0 {
			return nil, nil
		}
		return strings.Join(parts, " "), nil
	case "note":
		var parts []string
		for _, key := range stringList(source.Arg) {
			if !pyval.IsBlank(payload[key]) {
				parts = append(parts, title(key)+": "+pyval.Str(payload[key]))
			}
		}
		if len(parts) == 0 {
			return nil, nil
		}
		return strings.Join(parts, "\n\n"), nil
	case "json":
		return pyval.Dumps(payload), nil
	}
	return nil, fmt.Errorf("unknown mapping source %s; lint should have refused it",
		pyval.Repr(source.Kind))
}

// title is Python's str.title() over a link_id, which is what the `note`
// source labels a paragraph with. Python's title() uppercases the first
// cased character of every run of letters and lowercases the rest, so
// `past_history` becomes "Past_History".
func title(s string) string {
	out := []rune(strings.ToLower(s))
	start := true
	for i, r := range out {
		if r >= 'a' && r <= 'z' {
			if start {
				out[i] = r - 32
			}
			start = false
			continue
		}
		if r >= '0' && r <= '9' {
			start = false
			continue
		}
		start = true
	}
	return string(out)
}

// questionOf rebuilds the one questionnaire question an answer coding source
// needs. The compiled mapping carries exactly the two fields that decide a
// binding, so this is the declaration rather than a copy of it.
func questionOf(node map[string]any) questionnaire.Question {
	q := questionnaire.Question{}
	q.LinkID, _ = node["link_id"].(string)
	q.AnswerValueSet, _ = node["answer_value_set"].(string)
	return q
}

// row is one row, or nil when this record has nothing to say about this
// payload.
func row(record Record, payload, context map[string]any, actor string,
	terms *terminology.Cache) (map[string]any, error) {
	for _, column := range record.columns() {
		source := record.Fields[column]
		if _, coded := answerCodingFacts[source.Kind]; !coded {
			continue
		}
		key, _ := source.Arg.(string)
		if pyval.IsBlank(payload[key]) {
			return nil, nil
		}
	}
	out := map[string]any{}
	derived, anyDerivedSource := false, false
	for _, column := range record.columns() {
		source := record.Fields[column]
		fromPayload := !payloadFree[source.Kind]
		anyDerivedSource = anyDerivedSource || fromPayload
		filled, err := value(source, payload, context, actor, terms)
		if err != nil {
			return nil, err
		}
		if pyval.IsBlank(filled) {
			continue
		}
		out[column] = filled
		derived = derived || fromPayload
	}
	if anyDerivedSource && !derived {
		return nil, nil
	}
	return out, nil
}

// columns is the record's columns, alphabetically.
//
// NOT the declared order, and it cannot be: kernel/declarations.write_catalogue
// dumps catalogue.json with sort_keys=True, so by the time this engine reads
// `fields` the order is already alphabetical. It does not change what is
// written, because a row is a mapping of column to value. The one place it
// shows is WHICH failure is reported when two sources of one record would
// both fail: Python reports the first in declaration order and this reports
// the first alphabetically. Both refuse the write. Recorded here rather than
// discovered, because a denial sentence is compared between the engines.
func (r Record) columns() []string {
	out := make([]string, 0, len(r.Fields))
	for column := range r.Fields {
		out = append(out, column)
	}
	sort.Strings(out)
	return out
}
