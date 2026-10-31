// Package terminology is the Go side of kernel/terminology.py: the offline
// value set cache, the one validating constructor of a Coding, and guard step
// 1's terminology half.
//
// THE INVARIANT, AND HOW IT IS HELD IN GO
// ---------------------------------------
//
//	I1. A stored coding is in the value set its question binds to.
//
// In Python that is held by a module-private sentinel: Coding's constructor
// refuses anything that did not come through Terminology.bound(). Go has no
// way to make a struct literal illegal from another package, so the same
// guarantee is made the way Go makes it: Coding's fields are unexported and
// reachable only through methods, so a Coding built outside this package is
// the zero value and carries no code, no system and no display. A row filled
// from it would be empty rather than wrong, and kernel/mapping's own refusal
// to write a row whose coded answer is absent then stops it.
//
// WHAT IS READ, AND FROM WHERE
// ----------------------------
// terminology/<slug>.json on disk, exactly as the Python reads it, and for
// the reason the port plan gives: the declarations do not move, and the Go
// engine reads them rather than restating them. Read only. Nothing in the
// product writes a value set, which is the answer to "who may edit one":
// nobody, here.
//
// NO SOCKET ON THIS PATH, DELIBERATELY
// ------------------------------------
// A primary health centre on a bad line needs validate to work with no
// network, so the offline path is the only path rather than a fallback nobody
// tests.
package terminology

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/questionnaire"
)

// The two bindings a question's own declaration may carry. LOINC and UCUM are
// nobody's choice, so they sit beside the kernel's grammar rather than in a
// bundle's own words.
const (
	CodeBinding = "observation-code"
	UnitBinding = "ucum-units"
)

// UnitOf is where a question says which other answer's concept decides its
// unit. The field name is CARE's, verbatim.
const UnitOf = "unit_of"

// Coding is one code from one code system, vouched for by one value set.
// Immutable from outside this package: the fields are the identity of a
// clinical fact and nothing may rewrite one in place.
type Coding struct {
	system   string
	code     string
	display  string
	valueset string
}

func (c Coding) System() string   { return c.system }
func (c Coding) Code() string     { return c.code }
func (c Coding) Display() string  { return c.display }
func (c Coding) ValueSet() string { return c.valueset }

// Fact reads one part of this coding by the name a mapping source uses.
func (c Coding) Fact(which string) string {
	switch which {
	case "code":
		return c.code
	case "system":
		return c.system
	case "display":
		return c.display
	}
	return ""
}

// Cache is the local value sets, by slug.
type Cache struct {
	dir   string
	sets  map[string]*valueSet
	known []string
}

type valueSet struct {
	slug     string
	system   string
	concepts map[string]map[string]any
	order    []string
}

// Load reads every cached value set under dir.
func Load(dir string) (*Cache, error) {
	paths, err := filepath.Glob(filepath.Join(dir, "*.json"))
	if err != nil {
		return nil, err
	}
	if len(paths) == 0 {
		return nil, fmt.Errorf("no value sets cached in %s: a question may not "+
			"bind to a value set this facility cannot check offline", dir)
	}
	cache := &Cache{dir: dir, sets: map[string]*valueSet{}}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		var blob map[string]any
		if err := pyval.Decode(raw, &blob); err != nil {
			return nil, fmt.Errorf("%s: %w", filepath.Base(path), err)
		}
		name := strings.TrimSuffix(filepath.Base(path), ".json")
		set := &valueSet{concepts: map[string]map[string]any{}}
		set.slug, _ = blob["slug"].(string)
		set.system, _ = blob["system"].(string)
		concepts, hasConcepts := blob["concepts"].(map[string]any)
		// The Python raises for a cached file missing any of the three, and
		// for one whose slug disagrees with its filename. Same here, at
		// startup rather than at the first write.
		if set.slug == "" || set.system == "" || !hasConcepts {
			return nil, fmt.Errorf("%s: a cached value set needs 'slug', "+
				"'system' and 'concepts'", filepath.Base(path))
		}
		if set.slug != name {
			return nil, fmt.Errorf("%s: declares slug '%s'", filepath.Base(path), set.slug)
		}
		for code, concept := range concepts {
			if node, ok := concept.(map[string]any); ok {
				set.concepts[code] = node
				set.order = append(set.order, code)
			}
		}
		sort.Strings(set.order)
		cache.sets[set.slug] = set
		cache.known = append(cache.known, set.slug)
	}
	sort.Strings(cache.known)
	return cache, nil
}

// Cached is every value set slug on disk. For a check, not for the product.
func (c *Cache) Cached() []string { return c.known }

// Validate answers whether this code is in that value set. An unknown value
// set is not a pass: the Python raises UnboundCoding, and a Go caller on the
// write path treats a false here the same way.
func (c *Cache) Validate(slug string, code any) bool {
	set, found := c.sets[slug]
	if !found {
		return false
	}
	_, held := set.concepts[pyval.Str(code)]
	return held
}

// Known answers whether this value set is cached at all, which is the
// difference between "that is not a code" and "no value set by that name".
func (c *Cache) Known(slug string) bool {
	_, found := c.sets[slug]
	return found
}

// Bound is the only constructor of a Coding. Validates, then builds.
//
// The display comes from the cache and never from the caller, so a display
// that disagrees with the terminology is not expressible.
func (c *Cache) Bound(slug string, code any) (Coding, error) {
	set, found := c.sets[slug]
	if !found {
		return Coding{}, fmt.Errorf("no value set '%s' is cached in %s. A "+
			"question may not bind to a value set this facility cannot check "+
			"offline.", slug, c.dir)
	}
	text := pyval.Str(code)
	concept, held := set.concepts[text]
	if !held {
		return Coding{}, fmt.Errorf("'%s' is not in value set '%s', so it may "+
			"not be stored against a question bound to it", text, slug)
	}
	display, _ := concept["display"].(string)
	return Coding{system: set.system, code: text, display: display, valueset: slug}, nil
}

// Codes is every code this value set holds, sorted. For a check and for a
// picker, not for the write path: a caller that wants one code wants Bound.
func (c *Cache) Codes(slug string) []string {
	set, found := c.sets[slug]
	if !found {
		return nil
	}
	return append([]string(nil), set.order...)
}

// Concept is the raw cached concept behind a code, for the facts a Coding has
// no field for. Today that is one fact: the unit LOINC reports an analyte in.
//
// Deliberately not on Coding. A Coding is the four things FHIR's Coding
// element has, and an expected unit is a fact ABOUT the concept rather than
// part of it.
func (c *Cache) Concept(slug string, code any) (map[string]any, error) {
	if !c.Validate(slug, code) {
		return nil, fmt.Errorf("%s is not in value set %s", pyval.Repr(code),
			pyval.Repr(slug))
	}
	out := map[string]any{}
	for k, v := range c.sets[slug].concepts[pyval.Str(code)] {
		out[k] = v
	}
	return out, nil
}

// AnswerBinding is the value set this question's ANSWER is drawn from, or "".
func AnswerBinding(q questionnaire.Question) string {
	return strings.TrimSpace(q.AnswerValueSet)
}

// AnswerCoding is the coding an answer names, through the question's own
// value set: the third binding form, resolved at WRITE time rather than build
// time, because the answer is not known until somebody answers. Everything
// else about it is identical to the other two — one constructor, which
// validates before it returns — so an answer the value set does not hold
// cannot become a coding and therefore cannot become a row.
func (c *Cache) AnswerCoding(q questionnaire.Question, answer any) (Coding, error) {
	slug := AnswerBinding(q)
	if slug == "" {
		return Coding{}, fmt.Errorf("question %s declares no answer_value_set, "+
			"so its answer carries no concept", pyval.Repr(q.LinkID))
	}
	if pyval.IsUnanswered(answer) {
		return Coding{}, fmt.Errorf("question %s was not answered, so there is "+
			"no concept to store", pyval.Repr(q.LinkID))
	}
	return c.Bound(slug, answer)
}

// AnswerProblems is guard step 1's terminology half: the terminology failures
// in a payload, as sentences, or none.
//
// Two rules:
//
//	every answer bound to a value set is a code that value set holds;
//	an answer declared `unit_of` another is the unit that other answer's
//	concept is reported in.
//
// The second is why a laboratory value and its unit are one checked thing
// rather than two strings. A haemoglobin of 12 is a normal haemoglobin in
// g/dL and a nonsense one in mg/dL, and nothing in the payload said which
// until this rule.
func (c *Cache) AnswerProblems(schema *questionnaire.Schema, payload map[string]any) []string {
	var problems []string
	// A repeating group's answer is a list of rows, and each row is a payload
	// over that group's own sub questions. So the rules below run once per row
	// with the row as the payload, and the row number is in the sentence.
	//
	// This is where a repeating group multiplies the risk rather than adding
	// to it: one unbound code used to be one bad row, and now one unbound
	// code is one bad row out of five on a prescription a pharmacist reads.
	for _, group := range schema.RowGroups() {
		rows, ok := payload[group.LinkID].([]any)
		if !ok {
			continue
		}
		subs := questionnaire.RowQuestions(group)
		for index, item := range rows {
			row, ok := item.(map[string]any)
			if !ok {
				continue
			}
			for _, line := range c.problems(subs, row) {
				problems = append(problems, fmt.Sprintf("%s[%d].%s",
					group.LinkID, index, line))
			}
		}
	}
	inside := map[string]bool{}
	for _, group := range schema.RowGroups() {
		for _, sub := range questionnaire.RowQuestions(group) {
			inside[sub.LinkID] = true
		}
	}
	var questions []questionnaire.Question
	for _, q := range schema.Walk() {
		if !inside[q.LinkID] {
			questions = append(questions, q)
		}
	}
	return append(problems, c.problems(questions, payload)...)
}

// problems is the two terminology rules over one flat set of answers, which
// is either the payload or one row of a repeating group: the rules are
// identical and a row is a payload over fewer questions, so there is one
// implementation and a row cannot be checked less than the form.
func (c *Cache) problems(questions []questionnaire.Question, payload map[string]any) []string {
	by := map[string]questionnaire.Question{}
	for _, q := range questions {
		by[q.LinkID] = q
	}
	var problems []string
	for _, question := range questions {
		answer := payload[question.LinkID]
		slug := AnswerBinding(question)
		if slug != "" && !pyval.IsUnanswered(answer) {
			if !c.Validate(slug, answer) {
				problems = append(problems, fmt.Sprintf(
					"%s is %s, which is not a code in %s", question.LinkID,
					pyval.Repr(answer), slug))
				continue
			}
		}
		other := strings.TrimSpace(question.UnitOf)
		if other == "" {
			continue
		}
		peer, onForm := by[other]
		if !onForm {
			problems = append(problems, fmt.Sprintf("%s declares %s '%s', which "+
				"is not a question on this form", question.LinkID, UnitOf, other))
			continue
		}
		peerSlug := AnswerBinding(peer)
		peerAnswer := payload[other]
		if peerSlug == "" || pyval.IsUnanswered(peerAnswer) || pyval.IsUnanswered(answer) {
			continue
		}
		if !c.Validate(peerSlug, peerAnswer) {
			continue // the peer's own failure is already reported above
		}
		concept, err := c.Concept(peerSlug, peerAnswer)
		wanted := ""
		if err == nil {
			wanted, _ = concept["unit"].(string)
		}
		if wanted == "" {
			// A concept with no unit recorded cannot decide one. Reported
			// rather than passed over: a rule that silently stops applying is
			// worse than one that is absent.
			problems = append(problems, fmt.Sprintf("%s is reported with no unit "+
				"in %s, so %s cannot be checked against it", pyval.Str(peerAnswer),
				peerSlug, question.LinkID))
			continue
		}
		if pyval.Str(answer) != wanted {
			problems = append(problems, fmt.Sprintf("%s is %s, and %s is reported "+
				"in %s. Correct the unit, or pick the analyte that is measured "+
				"in %s.", question.LinkID, pyval.Repr(answer), pyval.Str(peerAnswer),
				pyval.Repr(wanted), pyval.Repr(answer)))
		}
	}
	return problems
}
