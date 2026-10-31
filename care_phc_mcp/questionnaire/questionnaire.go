// Package questionnaire is catalogue/validate.py in Go: payload validation
// against the CARE questionnaire an operation names, and the flags a payload
// raises.
//
// WHERE THE SCHEMAS COME FROM, AND WHY NOT THE EMBEDDED CATALOGUE
// ---------------------------------------------------------------
// questionnaires/*.json on disk, read at startup. The port plan says so in as
// many words: "catalogue/, bundles/, questionnaires/, terminology/ — the
// declarations. The Go engine reads them; it does not restate them."
// catalogue.json's per-operation `fields` is a FLATTENED list for an agent's
// tool schema; it carries no range, no critical band, no repeating group and
// no answer_value_set, so validating against it would be validating against
// less than the Python does. Fail closed: a missing or unreadable
// questionnaire is a startup failure, not a permissive validator.
//
// THIS IS DELIBERATELY THIN, AND SO IS THE PYTHON
// -----------------------------------------------
// Required answers, types, choices, and the range rule. Everything subtler is
// CARE's job. The one part that is not thin is the repeating group: a `group`
// with `repeats: true` holds a list of rows and every rule above applies per
// row, with the row number in every sentence, because "medications is
// invalid" does not tell a prescriber which line to fix.
package questionnaire

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
)

// Question is one questionnaire question. Raw keeps the fields this package
// does not read, because kernel/terminology.py reads two of them
// (`answer_value_set` and `styling_metadata.phc.unit_of`) off the same
// question and the two packages must not hold two copies of the declaration.
type Question struct {
	LinkID    string
	Type      string
	Text      string
	Required  bool
	Repeats   bool
	Questions []Question

	// AnswerOption values, in declaration order. The choice rule compares
	// against the set; the sentence sorts it.
	Options []any

	// AnswerValueSet is the value set this question's ANSWER is drawn from.
	AnswerValueSet string
	// Code is the question's own concept, when the question IS the concept.
	Code string
	// Unit, Range, Critical, UnitOf and Flags are styling_metadata.phc, which
	// is where they already live, next to each other.
	Unit     string
	Range    *Band
	Critical *Band
	UnitOf   string
	Flags    string
	// rowLabel is styling_metadata.phc.row: what one row of a repeating group
	// is called. Unexported because RowLabel is the only honest reader of it;
	// an empty one is "row" and a caller must not see the difference.
	rowLabel string
}

// Band is a {low, high} pair, with the two bounds kept as their JSON literals
// so a denial spells them the way Python's str() does.
type Band struct {
	Low  json.Number
	High json.Number
}

// Schema is one questionnaire.
type Schema struct {
	Slug      string
	Questions []Question
}

// Set is every questionnaire this kernel can validate against, by slug.
type Set struct {
	schemas map[string]*Schema
}

// numeric is CARE's two numeric question types and the Python cast each one
// does. The cast is not a formality: int("140.5") fails where
// float("140.5") does not, and the cast value is what the range is checked
// against and what the denial prints.
var numeric = map[string]bool{"integer": true, "decimal": true}

// Load reads every questionnaire under dir. Loud on a directory that is not
// there: a kernel that cannot validate must not start, because guard step 1
// with no validator is the one hole this whole architecture exists to close.
func Load(dir string) (*Set, error) {
	paths, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return nil, err
	}
	if len(paths) == 0 {
		return nil, fmt.Errorf("no questionnaires in %s: an operation's "+
			"validator is loaded from the questionnaire it names, and a "+
			"kernel that cannot load one must not serve a write", dir)
	}
	set := &Set{schemas: map[string]*Schema{}}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		var blob map[string]any
		if err := pyval.Decode(raw, &blob); err != nil {
			return nil, fmt.Errorf("%s: %w", filepath.Base(path), err)
		}
		// Keyed by the FILENAME, which is what an operation's `input` names:
		// catalogue/validate.load does `SCHEMAS / f"{schema_id}.json"` and
		// never reads the `slug` field. The two disagree on every file in the
		// tree — phc.schema.vitals-v1.json carries slug "vitals-v1" — so
		// keying by `slug` makes every validator nil, which fails closed and
		// refuses every write. It did, which is how this was found. The slug
		// is carried for whoever wants it and is not the key.
		name := strings.TrimSuffix(filepath.Base(path), ".json")
		slug, _ := blob["slug"].(string)
		set.schemas[name] = &Schema{Slug: slug, Questions: parseQuestions(blob["questions"])}
	}
	return set, nil
}

// Get is catalogue/validate.load: the questionnaire by slug, or the same
// failure the Python raises.
func (s *Set) Get(slug string) (*Schema, error) {
	schema, found := s.schemas[slug]
	if !found {
		return nil, fmt.Errorf("no questionnaire for '%s'", slug)
	}
	return schema, nil
}

// Slugs is every questionnaire loaded, for a check rather than the product.
func (s *Set) Slugs() []string {
	out := make([]string, 0, len(s.schemas))
	for slug := range s.schemas {
		out = append(out, slug)
	}
	sort.Strings(out)
	return out
}

func parseQuestions(v any) []Question {
	listed, ok := v.([]any)
	if !ok {
		return nil
	}
	out := make([]Question, 0, len(listed))
	for _, item := range listed {
		node, ok := item.(map[string]any)
		if !ok {
			continue
		}
		out = append(out, parseQuestion(node))
	}
	return out
}

func parseQuestion(node map[string]any) Question {
	q := Question{Questions: parseQuestions(node["questions"])}
	q.LinkID, _ = node["link_id"].(string)
	q.Type, _ = node["type"].(string)
	q.Text, _ = node["text"].(string)
	q.Required, _ = node["required"].(bool)
	q.Repeats, _ = node["repeats"].(bool)
	q.AnswerValueSet = text(node["answer_value_set"])
	q.Code = text(node["code"])
	if options, ok := node["answer_option"].([]any); ok {
		for _, o := range options {
			if option, ok := o.(map[string]any); ok {
				if value, has := option["value"]; has {
					q.Options = append(q.Options, value)
				}
			}
		}
	}
	phc := map[string]any{}
	if styling, ok := node["styling_metadata"].(map[string]any); ok {
		if inner, ok := styling["phc"].(map[string]any); ok {
			phc = inner
		}
	}
	q.Unit = text(phc["unit"])
	q.UnitOf = text(phc["unit_of"])
	q.Flags = text(phc["flags"])
	q.rowLabel = text(phc["row"])
	q.Range = band(phc["range"])
	q.Critical = band(phc["critical"])
	return q
}

func text(v any) string {
	switch t := v.(type) {
	case string:
		return t
	case json.Number:
		return string(t)
	}
	return ""
}

func band(v any) *Band {
	node, ok := v.(map[string]any)
	if !ok {
		return nil
	}
	low, lowOK := node["low"].(json.Number)
	high, highOK := node["high"].(json.Number)
	if !lowOK || !highOK {
		return nil
	}
	return &Band{Low: low, High: high}
}

// Walk yields every question on this form, nested ones included.
func (s *Schema) Walk() []Question {
	return walk(s.Questions)
}

func walk(questions []Question) []Question {
	var out []Question
	for _, q := range questions {
		out = append(out, q)
		out = append(out, walk(q.Questions)...)
	}
	return out
}

// IsRowGroup answers whether this question holds a list of rows.
//
// A `group` that repeats. Both halves matter: a group that does not repeat is
// a heading over questions answered once, and a repeating question that is
// not a group is one answer given several times, which nothing here declares.
func IsRowGroup(q Question) bool {
	return q.Type == "group" && q.Repeats
}

// RowGroups is every repeating group on this form, in declaration order.
func (s *Schema) RowGroups() []Question {
	var out []Question
	for _, q := range s.Walk() {
		if IsRowGroup(q) {
			out = append(out, q)
		}
	}
	return out
}

// RowQuestions is one repeating group's sub questions, in declaration order.
func RowQuestions(group Question) []Question {
	return walk(group.Questions)
}

// RowLabel is what one row of this group is called, for a sentence a
// clinician reads. Declared in styling_metadata.phc.row, and "row" when a
// group does not say. Not derived from the link_id: `medications` would give
// "medications", and "medications 2 is required" is not a sentence.
func RowLabel(group Question) string {
	if group.rowLabel != "" {
		return group.rowLabel
	}
	return "row"
}

// Validate is make_validator's returned callable: the problems in this
// payload, as sentences, in the Python's order.
func (s *Schema) Validate(payload map[string]any) []string {
	groups := s.RowGroups()
	inside := map[string]bool{}
	isGroup := map[string]bool{}
	for _, group := range groups {
		isGroup[group.LinkID] = true
		for _, sub := range RowQuestions(group) {
			inside[sub.LinkID] = true
		}
	}
	// A repeating group's sub questions are answered inside its rows and
	// never at the top level, so they are not top level questions. That also
	// makes a sub question's link_id arriving at the top level an unknown key,
	// which is what it is: a renderer sending `condition` beside `diagnosis`
	// has lost the row it belonged to.
	var questions []Question
	known := map[string]bool{}
	for _, q := range s.Walk() {
		if inside[q.LinkID] || isGroup[q.LinkID] {
			continue
		}
		questions = append(questions, q)
		known[q.LinkID] = true
	}

	problems := []string{}
	override := strings.TrimSpace(pyval.Str(nonNil(payload["override_reason"])))

	for _, q := range questions {
		value, present := payload[q.LinkID]
		answered := present && !pyval.IsUnanswered(value)
		if q.Required && !answered {
			problems = append(problems, q.LinkID+" is required")
			continue
		}
		if !answered {
			continue
		}
		problems = append(problems, answerProblems(q, value, "", override)...)
	}

	for _, group := range groups {
		problems = append(problems, rowProblems(group, payload, override)...)
	}

	var unknown []string
	for key := range payload {
		if key == "override_reason" || known[key] || isGroup[key] {
			continue
		}
		unknown = append(unknown, key)
	}
	sort.Strings(unknown)
	for _, key := range unknown {
		problems = append(problems, key+" is not a question on this form")
	}
	return problems
}

func nonNil(v any) any {
	if v == nil {
		return ""
	}
	return v
}

// answerProblems is the type, choice and range failures for one answered
// value. `where` is the prefix that says which row it was in, and is empty at
// the top level.
func answerProblems(q Question, value any, where, override string) []string {
	linkID := where + q.LinkID
	if numeric[q.Type] {
		if q.Type == "integer" {
			cast, ok := pyval.AsInt(value)
			if !ok {
				return []string{fmt.Sprintf("%s must be %s", linkID, q.Type)}
			}
			return rangeProblems(q, linkID, float64(cast), pyval.Str(int64(cast)), override)
		}
		cast, ok := pyval.AsFloat(value)
		if !ok {
			return []string{fmt.Sprintf("%s must be %s", linkID, q.Type)}
		}
		return rangeProblems(q, linkID, cast, pyval.FloatStr(cast), override)
	}
	switch q.Type {
	case "boolean":
		if _, ok := value.(bool); !ok {
			return []string{linkID + " must be boolean"}
		}
	case "choice":
		if len(q.Options) > 0 {
			for _, option := range q.Options {
				if pyval.Equal(value, option) {
					return nil
				}
			}
			allowed := make([]string, 0, len(q.Options))
			for _, option := range q.Options {
				allowed = append(allowed, pyval.Str(option))
			}
			return []string{fmt.Sprintf("%s must be one of %s", linkID,
				pyval.ReprStrings(allowed))}
		}
	}
	// The range rule only applies to a numeric question: the Python's `caster`
	// is falsy for every other type, so a range declared on a string is inert
	// there and is inert here.
	return nil
}

// rangeProblems is the addendum SSA rule: a value outside physiological range
// blocks the commit and requires an explicit override carrying a reason. The
// override is recorded, not waived.
func rangeProblems(q Question, linkID string, value float64, shown, override string) []string {
	if q.Range == nil {
		return nil
	}
	low, lowOK := pyval.AsFloat(q.Range.Low)
	high, highOK := pyval.AsFloat(q.Range.High)
	if !lowOK || !highOK {
		return nil
	}
	if low <= value && value <= high {
		return nil
	}
	if override != "" {
		return nil
	}
	return []string{fmt.Sprintf("%s is %s, outside %s to %s. Enter a reason to "+
		"override, or correct the value.", linkID, shown,
		pyval.Str(q.Range.Low), pyval.Str(q.Range.High))}
}

// rowProblems is every failure in one repeating group's answer.
//
// The whole point of the repeating group: each row is validated, so there is
// no answer on this form that nothing checks.
func rowProblems(group Question, payload map[string]any, override string) []string {
	subs := RowQuestions(group)
	declared := map[string]bool{}
	for _, sub := range subs {
		declared[sub.LinkID] = true
	}
	label := RowLabel(group)
	value := payload[group.LinkID]
	if pyval.IsBlank(value) {
		if group.Required {
			return []string{group.LinkID + " is required"}
		}
		return nil
	}
	listed, ok := value.([]any)
	if !ok {
		return []string{fmt.Sprintf("%s is a list of rows, one per %s",
			group.LinkID, label)}
	}
	var problems []string
	for index, item := range listed {
		where := fmt.Sprintf("%s[%d].", group.LinkID, index)
		row, ok := item.(map[string]any)
		if !ok {
			problems = append(problems, fmt.Sprintf("%s[%d] is not a %s: a %s is "+
				"a set of answers, not a single value", group.LinkID, index, label, label))
			continue
		}
		for _, sub := range subs {
			given, present := row[sub.LinkID]
			answered := present && !pyval.IsUnanswered(given)
			if sub.Required && !answered {
				problems = append(problems, where+sub.LinkID+" is required")
				continue
			}
			if !answered {
				continue
			}
			problems = append(problems, answerProblems(sub, given, where, override)...)
		}
		var extra []string
		for key := range row {
			if !declared[key] {
				extra = append(extra, key)
			}
		}
		sort.Strings(extra)
		for _, key := range extra {
			problems = append(problems, fmt.Sprintf("%s%s is not a question on this %s",
				where, key, label))
		}
	}
	return problems
}

// Flags is the state flags this payload raises. Critical values promote an
// action, and a question that declares `flags` with no `critical` band raises
// its flag when the answer is yes.
//
// The second form is what a consent is. A consent has no physiological range
// to be outside of, so requiring `critical` here is what left
// capture.consented declared, gated on, and raised by nothing. Deliberately
// strict: only a real boolean true raises, so a missing answer and a string
// fail closed to no flag.
func (s *Schema) Flags(payload map[string]any) map[string]bool {
	raised := map[string]bool{}
	type seen struct {
		q     Question
		value any
	}
	var answers []seen
	// A repeating group's sub questions are answered in rows, so looking for
	// them in the payload finds nothing. Flattened here with their row's value
	// rather than passed over: a sub question that declares a flag and raises
	// it nowhere is the hole `capture.consented` already had once.
	for _, q := range s.Walk() {
		if IsRowGroup(q) {
			rows, _ := payload[q.LinkID].([]any)
			for _, item := range rows {
				row, ok := item.(map[string]any)
				if !ok {
					continue
				}
				for _, sub := range RowQuestions(q) {
					answers = append(answers, seen{sub, row[sub.LinkID]})
				}
			}
			continue
		}
		answers = append(answers, seen{q, payload[q.LinkID]})
	}
	for _, a := range answers {
		if a.q.Flags == "" || pyval.IsUnanswered(a.value) {
			continue
		}
		if a.q.Critical == nil {
			if yes, ok := a.value.(bool); ok && yes {
				raised[a.q.Flags] = true
			}
			continue
		}
		value, ok := pyval.AsFloat(a.value)
		if !ok {
			continue
		}
		low, lowOK := pyval.AsFloat(a.q.Critical.Low)
		high, highOK := pyval.AsFloat(a.q.Critical.High)
		if !lowOK || !highOK {
			continue
		}
		if !(low <= value && value <= high) {
			raised[a.q.Flags] = true
		}
	}
	return raised
}
