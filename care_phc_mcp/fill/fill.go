// Package fill is api/fill.py in Go: one questionnaire, any questionnaire,
// its fields as a flat list, and a heard value made into a value that field
// can hold, or refused.
//
// REPEATING GROUPS, AND WHY THE TICK GETS HARDER HERE
// ---------------------------------------------------
// A repeating group's answer is a list of rows, so a recording that fills one
// is filling several values per row and several rows per question. Two rules
// hold that together and both are REFUSALS:
//
//	an answer is addressed to one row, by number, as `medications[1].dose`. A
//	row field answered with no row number is DROPPED. It is never folded into
//	the first row, because a dose that belongs to a medicine nobody identified
//	is a dose on the wrong medicine.
//
//	every filled non text value of every row is owed its own tick, under its
//	own row addressed id. One tick per question would mean confirming the
//	first medicine and committing four more unread.
//
// The tick is a patient-safety rule and it is held in three places:
// kernel/tests/test_contracts.py owns the structural half,
// web/src/scribe/scribe.check.ts the renderer half, and
// scripts/check_go_parity.py now holds the two engines' answers against each
// other. None of the three was weakened to land this.
//
// ORDER IS PART OF THE ANSWER
// ---------------------------
// `tick` is a LIST and the Python's order is the order the ids were built in:
// the surviving top level answers in the order they were heard, then the row
// answers group by group, row by row, field by field. Go maps have no order,
// so every structure this file carries an answer in is ordered explicitly.
// A set would have compared equal on the demo's own case and differed on the
// first real recording.
//
// PURE. No model, no network, no clock except the `today` a caller hands in.
// The one thing it reads is the local terminology cache, which is an offline
// file, so that a choice bound to a value set has options to match a heard
// word against.
package fill

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// TickTypes is api/fill.py's TICK_TYPES: every non text answer type. A
// string, a text block and a url are not on it, which is the whole rule: a
// number, a date, a choice and a boolean are read back and ticked, and prose
// is read as prose.
var TickTypes = []string{"integer", "decimal", "quantity", "date", "dateTime",
	"time", "choice", "boolean"}

func owesTick(kind string) bool {
	for _, t := range TickTypes {
		if t == kind {
			return true
		}
	}
	return false
}

// Cap is api/fill.py's CAP: under web/src/form/Form.tsx SURE, so every heard
// value reads as unconfirmed.
const Cap = 0.89

// rowID is how an answer names the row it belongs to. One shape, used by the
// extractor that produces an answer, the draft that carries it, the tick that
// is owed for it and the renderer that resolves it against the payload.
var rowID = regexp.MustCompile(`^([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]\.([A-Za-z_][A-Za-z0-9_]*)$`)

// RowID is api/fill.row_id.
func RowID(group string, index int, linkID string) string {
	return fmt.Sprintf("%s[%d].%s", group, index, linkID)
}

// SplitID is api/fill.split_id: (group, index, link_id) for a row addressed
// id, and ("", -1, id) for anything else. The Python answers None for the
// first two; a caller here tests the group.
func SplitID(ident string) (string, int, string) {
	found := rowID.FindStringSubmatch(ident)
	if found == nil {
		return "", -1, ident
	}
	index, _ := strconv.Atoi(found[2])
	return found[1], index, found[3]
}

// Field is one answerable question as flatten() hands it over. The JSON names
// are api/fill.flatten's own keys, because the two engines' answers are
// compared as JSON.
type Field struct {
	LinkID         string            `json:"link_id"`
	Path           string            `json:"path"`
	Text           string            `json:"text"`
	Description    string            `json:"description"`
	Type           string            `json:"type"`
	StructuredType any               `json:"structured_type"`
	Required       bool              `json:"required"`
	Repeats        bool              `json:"repeats"`
	Unit           any               `json:"unit"`
	Options        []string          `json:"options"`
	Labels         map[string]string `json:"labels"`
	RowOf          any               `json:"row_of"`
	ValueSet       string            `json:"valueset"`
	EnableWhen     []any             `json:"enable_when"`

	// rowOf as a string, because RowOf is `any` only so that an absent one
	// marshals as null the way the Python's None does.
	group      string
	enableWhen []map[string]any
}

// Flatten is api/fill.flatten: every answerable question, with the repeating
// group each one is inside.
//
// A repeating group is not itself answerable, so it is not in the list; its
// sub questions are, each carrying `row_of`, the group they belong to. That is
// what keeps this list flat while the payload is not: one entry per question
// to ask about, and the row addressing lives on the answers.
func Flatten(schema *questionnaire.Schema, terms *terminology.Cache) []Field {
	out := []Field{}
	var walk func(questions []any, prefix []string, rowOf string)
	walk = func(questions []any, prefix []string, rowOf string) {
		for _, item := range questions {
			node, ok := item.(map[string]any)
			if !ok {
				continue
			}
			linkID := str(node["link_id"])
			path := append(append([]string(nil), prefix...), linkID)
			kind := str(node["type"])
			if kind == "group" {
				inner := rowOf
				if isRowGroup(node) {
					inner = linkID
				}
				walk(list(node["questions"]), path, inner)
				continue
			}
			if kind == "display" {
				continue
			}
			out = append(out, field(node, path, rowOf, terms))
			walk(list(node["questions"]), path, rowOf)
		}
	}
	walk(list(schema.Raw["questions"]), nil, "")
	return out
}

func isRowGroup(node map[string]any) bool {
	repeats, _ := node["repeats"].(bool)
	return str(node["type"]) == "group" && repeats
}

func field(node map[string]any, path []string, rowOf string, terms *terminology.Cache) Field {
	phc := map[string]any{}
	if styling, ok := node["styling_metadata"].(map[string]any); ok {
		if inner, ok := styling["phc"].(map[string]any); ok {
			phc = inner
		}
	}
	required, _ := node["required"].(bool)
	repeats, _ := node["repeats"].(bool)
	f := Field{
		LinkID:         str(node["link_id"]),
		Path:           strings.Join(path, "."),
		Text:           str(node["text"]),
		Description:    str(node["description"]),
		Type:           str(node["type"]),
		StructuredType: node["structured_type"],
		Required:       required,
		Repeats:        repeats,
		// `q.get("unit") or phc.get("unit")`: the question's own key wins and
		// an empty one falls through to the phc block, which is where a unit
		// actually lives in this tree. Absent is null and not "", because
		// the two engines' answers are compared as JSON.
		Unit:  firstTruthy(node["unit"], phc["unit"]),
		RowOf: nullIf(rowOf),
		group: rowOf,
	}
	slug := strings.TrimSpace(str(node["answer_value_set"]))
	f.ValueSet = slug
	f.Options, f.Labels = options(node, slug, terms)
	f.EnableWhen = list(node["enable_when"])
	if f.EnableWhen == nil {
		f.EnableWhen = []any{}
	}
	for _, rule := range f.EnableWhen {
		if node, ok := rule.(map[string]any); ok {
			f.enableWhen = append(f.enableWhen, node)
		}
	}
	return f
}

// options is api/fill._options and _labels, which read the same declaration
// and must not be able to disagree.
//
// Two sources, and a BOUND one wins, because it is the authority: a question
// with an `answer_value_set` takes the codes that value set holds, and one
// with `answer_option` takes the values the form declares.
//
// A bound choice used to come back with NO options, and that was not
// cosmetic: coerce matches a heard word against this list, so an empty list
// refused every heard value and a recording could not fill a bound choice at
// all.
func options(node map[string]any, slug string, terms *terminology.Cache) ([]string, map[string]string) {
	labels := map[string]string{}
	if slug != "" {
		concepts := terms.Concepts(slug)
		codes := make([]string, 0, len(concepts))
		for code, concept := range concepts {
			codes = append(codes, code)
			display, _ := concept["display"].(string)
			labels[code] = display
		}
		sort.Strings(codes)
		return codes, labels
	}
	out := []string{}
	for _, item := range list(node["answer_option"]) {
		option, ok := item.(map[string]any)
		if !ok {
			continue
		}
		value, carried := option["value"]
		if !carried || value == nil {
			continue
		}
		// str(), so a numeric option is offered as the string a heard word is
		// matched against. The Python does the same and the stored value is
		// the string too.
		out = append(out, pyval.Str(value))
	}
	return out, labels
}

// --------------------------------------------------------------------------
// coercion
// --------------------------------------------------------------------------

var squash = regexp.MustCompile(`\s+`)

var months = map[string]int{"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
	"jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

var dayMonth = regexp.MustCompile(`^(?:(\d{1,2})\s+([a-z]+)|([a-z]+)\s+(\d{1,2}))$`)

// parseDate is api/fill._date. The spoken forms are "15 August" and
// "August 15" only; api/fill.py carries a ponytail note for weekday phrases
// and this copies the note rather than the feature.
func parseDate(value any, today time.Time) (time.Time, bool) {
	text := strings.ToLower(strings.TrimSpace(pyval.Str(value)))
	switch text {
	case "today":
		return today, true
	case "yesterday":
		return today.AddDate(0, 0, -1), true
	}
	if found, err := time.Parse("2006-01-02", text); err == nil {
		return found, true
	}
	match := dayMonth.FindStringSubmatch(text)
	if match == nil {
		return time.Time{}, false
	}
	day, month := match[1], match[2]
	if day == "" {
		day, month = match[4], match[3]
	}
	if len(month) > 3 {
		month = month[:3]
	}
	number, known := months[month]
	if !known {
		return time.Time{}, false
	}
	count, err := strconv.Atoi(day)
	if err != nil {
		return time.Time{}, false
	}
	// datetime.date refuses a day its month does not have; Go's Date rolls
	// over into the next month instead, so the roll is caught and refused.
	found := time.Date(today.Year(), time.Month(number), count, 0, 0, 0, 0, time.UTC)
	if int(found.Month()) != number || found.Day() != count {
		return time.Time{}, false
	}
	if found.After(today) {
		found = found.AddDate(-1, 0, 0)
	}
	return found, true
}

var truthy = []string{"true", "yes", "y", "1", "haan", "ha"}
var falsy = []string{"false", "no", "n", "0", "nahi"}

// Coerce is api/fill.coerce: a heard value made into a value this field can
// hold, or refused. The second return is the Python's `ok`.
func Coerce(f Field, value any, today time.Time) (any, bool) {
	if pyval.IsBlank(value) {
		// `value is None or value == "" or value == []`. Not {}, which
		// IsBlank also covers and which no extractor produces; a mapping
		// arriving here falls through to the type switch and is refused by
		// every branch of it anyway.
		if value == nil || value == "" {
			return nil, false
		}
		if listed, ok := value.([]any); ok && len(listed) == 0 {
			return nil, false
		}
	}
	switch f.Type {
	case "integer":
		number, ok := pyval.AsFloat(value)
		if !ok {
			return nil, false
		}
		if number != float64(int64(number)) {
			return nil, false
		}
		return int64(number), true
	case "decimal", "quantity":
		number, ok := pyval.AsFloat(value)
		if !ok {
			return nil, false
		}
		return number, true
	case "boolean":
		text := strings.ToLower(strings.TrimSpace(pyval.Str(value)))
		for _, yes := range truthy {
			if text == yes {
				return true, true
			}
		}
		for _, no := range falsy {
			if text == no {
				return false, true
			}
		}
		return nil, false
	case "date", "dateTime":
		found, ok := parseDate(value, today)
		if !ok {
			return nil, false
		}
		return found.Format("2006-01-02"), true
	case "choice":
		want := strings.ToLower(squash.ReplaceAllString(pyval.Str(value), ""))
		for _, option := range f.Options {
			if pyval.Equal(value, option) ||
				strings.ToLower(squash.ReplaceAllString(option, "")) == want {
				return option, true
			}
		}
		// A bound choice's answer is a code and nobody speaks a code. The
		// value stored is still the code: the display is how it was found,
		// never what is kept, so a value set that renames a concept cannot
		// rewrite what was recorded.
		//
		// Sorted, because the Python walks a dict built from the cache and Go
		// would walk it in map order. The displays in one value set are
		// distinct, so the order only decides which of two identical displays
		// wins, and there are none; sorting makes it decided rather than
		// decided per run.
		codes := make([]string, 0, len(f.Labels))
		for code := range f.Labels {
			codes = append(codes, code)
		}
		sort.Strings(codes)
		for _, code := range codes {
			display := f.Labels[code]
			if display == "" {
				continue
			}
			if strings.ToLower(squash.ReplaceAllString(display, "")) == want {
				return code, true
			}
		}
		return nil, false
	case "structured":
		listed, ok := value.([]any)
		if !ok {
			return nil, false
		}
		for _, item := range listed {
			if _, ok := item.(map[string]any); !ok {
				return nil, false
			}
		}
		return listed, true
	case "string", "text", "url", "time":
		return strings.TrimSpace(pyval.Str(value)), true
	}
	return nil, false
}

// --------------------------------------------------------------------------
// enable_when
// --------------------------------------------------------------------------

// Enabled is api/fill.enabled: the answers whose own enable_when rules all
// hold, in the order they were given.
//
// The Python deletes from the dict it is reading, so a rule referring to an
// answer an earlier rule already removed sees it gone. Copied exactly,
// including that, because the order answers arrive in is the order a
// transcript named them in.
func Enabled(fields []Field, values *Ordered) *Ordered {
	by := map[string]Field{}
	for _, f := range fields {
		by[f.LinkID] = f
	}
	out := values.Clone()
	for _, linkID := range values.Keys() {
		rules := by[linkID].enableWhen
		if len(rules) == 0 {
			continue
		}
		held := true
		for _, rule := range rules {
			have, _ := out.Get(str(rule["question"]))
			if !holds(str(rule["operator"]), have, rule["answer"]) {
				held = false
				break
			}
		}
		if !held {
			out.Delete(linkID)
		}
	}
	return out
}

// holds is api/fill._OPS. The four ordering operators compare Python values,
// and api/fill.py does NOT catch the TypeError Python raises for a string
// against a number; no declaration in this bundle has one, and a Go engine
// quietly answering false there would be this engine inventing a behaviour.
// So an incomparable pair answers false and is recorded here as the one place
// the two engines could differ without either being checked.
func holds(operator string, have, want any) bool {
	switch operator {
	case "exists":
		yes, _ := want.(bool)
		return (have != nil) == yes
	case "equals":
		return pyval.Equal(have, want)
	case "not_equals":
		return !pyval.Equal(have, want)
	case "greater", "less", "greater_or_equals", "less_or_equals":
		if have == nil {
			return false
		}
		a, aok := pyval.AsFloat(have)
		b, bok := pyval.AsFloat(want)
		if !aok || !bok {
			return false
		}
		switch operator {
		case "greater":
			return a > b
		case "less":
			return a < b
		case "greater_or_equals":
			return a >= b
		}
		return a <= b
	}
	return false
}

// --------------------------------------------------------------------------
// the draft
// --------------------------------------------------------------------------

// Answer is one heard answer: what was said, how sure the recogniser was, and
// the words it came from.
type Answer struct {
	ID         string  `json:"id"`
	Value      any     `json:"value"`
	Confidence float64 `json:"confidence"`
	Evidence   string  `json:"evidence"`
}

// Draft is api/fill.build_draft's return value, with the Python's own keys.
//
// Candidates is absent rather than empty when there is nothing to offer,
// because a key that is always there and always empty is how a renderer
// learns to stop looking at it.
type Draft struct {
	Instrument string             `json:"instrument"`
	Operation  string             `json:"operation"`
	Values     map[string]any     `json:"values"`
	Confidence map[string]float64 `json:"confidence"`
	Evidence   map[string]string  `json:"evidence"`
	Tick       []string           `json:"tick"`
	Unfilled   []string           `json:"unfilled"`
	Transcript string             `json:"transcript"`
	Candidates map[string]any     `json:"candidates,omitempty"`
}

// BuildDraft is api/fill.build_draft: one draft from a set of heard answers,
// or nil when nothing coerced.
//
// `answers` is a LIST and not a map, because the Python walks a dict in
// insertion order and that order reaches the answer: it decides which row is
// row zero, and therefore every row addressed id in `values`, `tick`,
// `confidence` and `evidence`.
func BuildDraft(operation string, schema *questionnaire.Schema, answers []Answer,
	transcript, instrument string, today time.Time, terms *terminology.Cache) *Draft {

	fields := Flatten(schema, terms)
	by := map[string]Field{}
	for _, f := range fields {
		by[f.LinkID] = f
	}

	flat := NewOrdered()
	var unfilled []string
	heard := map[string]Answer{}
	// group -> ordered row indices -> ordered field values
	rows := map[string]*rowSet{}
	var groupOrder []string

	for _, a := range answers {
		group, index, linkID := SplitID(a.ID)
		f, known := by[linkID]
		var value any
		ok := false
		if known {
			value, ok = Coerce(f, a.Value, today)
		}
		if ok && f.group != group {
			// Either a row field answered with no row, or a field answered
			// into a group it is not in. Both are dropped. The first is the
			// one that matters: folding it into row zero would put a dose on
			// whichever medicine happened to be first.
			ok = false
		}
		if !ok {
			unfilled = append(unfilled, a.ID)
			continue
		}
		heard[a.ID] = a
		if group == "" {
			flat.Set(linkID, value)
			continue
		}
		set, started := rows[group]
		if !started {
			set = newRowSet()
			rows[group] = set
			groupOrder = append(groupOrder, group)
		}
		set.set(index, linkID, value)
	}

	kept := Enabled(fields, flat)
	for _, linkID := range flat.Keys() {
		if _, held := kept.Get(linkID); !held {
			unfilled = append(unfilled, linkID)
		}
	}

	values := map[string]any{}
	for _, linkID := range kept.Keys() {
		value, _ := kept.Get(linkID)
		values[linkID] = value
	}

	// Renumbered in the extractor's own row order, which is the order the
	// transcript named them in. `was` maps the id an answer ends up under
	// back to the id it arrived under, so its confidence and its words follow
	// it through the renumbering.
	was := map[string]string{}
	var newIDs []string
	sort.Strings(groupOrder)
	for _, group := range groupOrder {
		set := rows[group]
		made := []any{}
		for _, index := range set.indices() {
			row := set.row(index)
			for _, linkID := range row.Keys() {
				fresh := RowID(group, len(made), linkID)
				was[fresh] = RowID(group, index, linkID)
				newIDs = append(newIDs, fresh)
			}
			built := map[string]any{}
			for _, linkID := range row.Keys() {
				value, _ := row.Get(linkID)
				built[linkID] = value
			}
			made = append(made, built)
		}
		values[group] = made
	}

	ids := append(append([]string(nil), kept.Keys()...), newIDs...)
	if len(ids) == 0 {
		return nil
	}

	confidence := map[string]float64{}
	evidence := map[string]string{}
	tick := []string{}
	for _, id := range ids {
		under := id
		if old, renumbered := was[id]; renumbered {
			under = old
		}
		a := heard[under]
		if a.Confidence < Cap {
			confidence[id] = a.Confidence
		} else {
			confidence[id] = Cap
		}
		evidence[id] = a.Evidence
		// Every filled non text value, each under its own id, so a row's
		// third field is owed a tick of its own rather than riding on the
		// question's.
		_, _, linkID := SplitID(id)
		if owesTick(by[linkID].Type) {
			tick = append(tick, id)
		}
	}
	sort.Strings(unfilled)
	if unfilled == nil {
		unfilled = []string{}
	}

	return &Draft{
		Instrument: instrument, Operation: operation, Values: values,
		Confidence: confidence, Evidence: evidence, Tick: tick,
		Unfilled: unfilled, Transcript: transcript,
		// Candidate codes for the bound fields a recording could not fill are
		// the codifier's, and the codifier this health centre runs is
		// kernel/codification.NoCodification: nothing, every time. It is the
		// default in api/fill.py too, so the offline path is the path that
		// gets exercised rather than a fallback nobody reaches. A candidate is
		// NOT a value: it never enters `values`, it is never owed a tick, and
		// the field stays in `unfilled`. The connector behind the seam is not
		// this slice's and the key stays absent until it is.
		Candidates: nil,
	}
}

// --------------------------------------------------------------------------
// ordered maps, because order is part of the answer
// --------------------------------------------------------------------------

// Ordered is a string-keyed map that remembers insertion order, which is what
// a Python dict is and what api/fill.py depends on.
type Ordered struct {
	keys  []string
	value map[string]any
}

func NewOrdered() *Ordered {
	return &Ordered{value: map[string]any{}}
}

func (o *Ordered) Set(key string, value any) {
	if _, already := o.value[key]; !already {
		o.keys = append(o.keys, key)
	}
	o.value[key] = value
}

func (o *Ordered) Get(key string) (any, bool) {
	value, found := o.value[key]
	return value, found
}

func (o *Ordered) Delete(key string) {
	if _, found := o.value[key]; !found {
		return
	}
	delete(o.value, key)
	for i, k := range o.keys {
		if k == key {
			o.keys = append(o.keys[:i], o.keys[i+1:]...)
			break
		}
	}
}

func (o *Ordered) Keys() []string { return append([]string(nil), o.keys...) }

func (o *Ordered) Clone() *Ordered {
	out := &Ordered{keys: append([]string(nil), o.keys...),
		value: make(map[string]any, len(o.value))}
	for k, v := range o.value {
		out.value[k] = v
	}
	return out
}

// rowSet is one repeating group's answered rows: the extractor's own row
// numbers, each holding that row's answers in the order they arrived.
type rowSet struct {
	order []int
	byRow map[int]*Ordered
}

func newRowSet() *rowSet { return &rowSet{byRow: map[int]*Ordered{}} }

func (r *rowSet) set(index int, linkID string, value any) {
	row, started := r.byRow[index]
	if !started {
		row = NewOrdered()
		r.byRow[index] = row
		r.order = append(r.order, index)
	}
	row.Set(linkID, value)
}

// indices is sorted, which is the Python's `for index in sorted(rows[group])`.
func (r *rowSet) indices() []int {
	out := append([]int(nil), r.order...)
	sort.Ints(out)
	return out
}

func (r *rowSet) row(index int) *Ordered { return r.byRow[index] }

// --------------------------------------------------------------------------

func str(v any) string {
	if text, ok := v.(string); ok {
		return text
	}
	return ""
}

func list(v any) []any {
	listed, _ := v.([]any)
	return listed
}

func firstTruthy(values ...any) any {
	for _, v := range values {
		if v == nil {
			continue
		}
		if text, ok := v.(string); ok && text == "" {
			continue
		}
		return v
	}
	return nil
}

func nullIf(text string) any {
	if text == "" {
		return nil
	}
	return text
}
