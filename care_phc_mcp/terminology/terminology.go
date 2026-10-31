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

// AnswerValueSet is where a question says which value set its ANSWER is drawn
// from: the third binding form. The FHIR questionnaire field name, verbatim,
// because CARE has it too and this is the one place the two models should not
// diverge. Named here rather than spelled into a sentence, because the
// Python interpolates the same constant into the refusal a caller reads
// (kernel/terminology.answer_coding) and two spellings of one field name is
// how the two engines start disagreeing about what the declaration is called.
const AnswerValueSet = "answer_value_set"

// Terminology is the seam, the Go side of kernel/terminology.Terminology:
// small enough that a local file and a real terminology server both satisfy
// it, and narrow enough that a check can pass a stand-in.
//
// That last part is the point, and it is the Python's stated reason for the
// seam existing at all: CARE replaces `validate_valueset` with the identity
// function for its whole suite (care/utils/tests/base.py:19), so its
// guarantee is never exercised in CI. Here the terminology is an argument, so
// a check hands over a fake rather than rewriting a package global.
//
// Validate is on the write path and must work with no network. Expand is for
// a picker and may be poorer offline than online.
type Terminology interface {
	Validate(valueset string, code any) bool
	Concepts(valueset string) map[string]map[string]any
	Tags(valueset string) []string
	Expand(valueset, query string, count int) ([]Coding, error)
	Bound(valueset string, code any) (Coding, error)
}

// The local cache is one implementation behind that seam, and today the only
// one. Asserted at compile time rather than in prose: an argument that drops
// off the interface should stop the build here and not at a caller.
var _ Terminology = (*Cache)(nil)

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

// ToFHIR is this coding as a FHIR R4 Coding element.
//
// `system` is always present, unlike CARE's (care/emr/resources/common/
// coding.py makes it optional while `code` is required). A code without a
// system is meaningless in FHIR R4 and unexportable to ABDM, so it cannot be
// absent here: the value set carries it and every Coding came from one.
//
// The display is omitted when the cache recorded none, which is the Python's
// `if self.display`. A key present and empty is not the same document: ABDM's
// validator reads an empty display as a display.
func (c Coding) ToFHIR() map[string]any {
	out := map[string]any{"system": c.system, "code": c.code}
	if c.display != "" {
		out["display"] = c.display
	}
	return out
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
	tags     []string
}

// Load reads every cached value set under dir.
//
// The directory is resolved to an absolute path, because it is INTERPOLATED
// INTO A DENIAL: kernel/terminology.CACHE is `ROOT / "terminology"`, a
// pathlib.Path, so the Python's "no value set 'x' is cached in /..." carries
// the absolute path and a relative one here would be a sentence the two
// engines disagree about. GET /valuesets/{slug} hands that sentence to a
// caller as a 404 body.
func Load(dir string) (*Cache, error) {
	if absolute, err := filepath.Abs(dir); err == nil {
		dir = absolute
	}
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
		// `semantic_tags` is optional and its absence is not a failure: the
		// Python's `.get("semantic_tags") or []` says so, and twelve of the
		// fourteen cached value sets here declare none. Order is the FILE'S
		// order and not sorted, because the declaration's order is the
		// declaration's business and sorting it would be this engine having
		// an opinion about a list it only reads.
		if declared, ok := blob["semantic_tags"].([]any); ok {
			for _, tag := range declared {
				if text, ok := tag.(string); ok {
					set.tags = append(set.tags, text)
				}
			}
		}
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

// Unbound is the UnboundCoding a missing value set raises, in the Python's
// own words, because GET /valuesets/{slug} answers 404 with str(broke).
func (c *Cache) Unbound(slug string) error {
	return fmt.Errorf("no value set '%s' is cached in %s. A question may not "+
		"bind to a value set this facility cannot check offline.", slug, c.dir)
}

// Expand is kernel/terminology.CachedTerminology.expand: the concepts of one
// value set, filtered by a substring of the display or the code, capped at
// `count`.
//
// Sorted by CODE and not by display, which is the Python's
// `sorted(blob["concepts"].items())` and is what makes the cap deterministic
// rather than map-order. The cap is a silent truncation and the route clamps
// it at 200 (see api/main.py's valueset); every value set here holds at most
// nine concepts, so it has never bitten, and it is what goes short the day a
// real NRCeS release sits behind the same seam.
func (c *Cache) Expand(slug, query string, count int) ([]Coding, error) {
	set, found := c.sets[slug]
	if !found {
		return nil, c.Unbound(slug)
	}
	want := strings.ToLower(strings.TrimSpace(query))
	out := []Coding{}
	for _, code := range set.order {
		display, _ := set.concepts[code]["display"].(string)
		if want != "" && !strings.Contains(strings.ToLower(display), want) &&
			!strings.Contains(strings.ToLower(code), want) {
			continue
		}
		out = append(out, Coding{system: set.system, code: code,
			display: display, valueset: slug})
		if len(out) >= count {
			break
		}
	}
	return out, nil
}

// Concepts is the cached concepts behind a value set, by code. A copy, so a
// caller cannot edit the cache through it, and nil for a value set that is
// not cached: kernel/terminology.concepts raises there, and the one caller
// (the expansion route) has already failed on Expand by then.
func (c *Cache) Concepts(slug string) map[string]map[string]any {
	set, found := c.sets[slug]
	if !found {
		return nil
	}
	out := make(map[string]map[string]any, len(set.concepts))
	for code, concept := range set.concepts {
		copied := make(map[string]any, len(concept))
		for k, v := range concept {
			copied[k] = v
		}
		out[code] = copied
	}
	return out
}

// Tags is the ontology semantic tags this value set's concepts carry.
//
// Declared in the file, under `semantic_tags`, beside the sentence that says
// what was confirmed and what was not. Empty for a value set that is not a
// branch of an ontology with semantic tags, which is every one here that is
// not SNOMED: a UCUM symbol and a FHIR status code have no semantic tag and
// never will.
//
// Nil for a value set nothing caches, the same way Concepts is, and that is a
// DIVERGENCE said out loud rather than hidden: kernel/terminology.tags goes
// through the same _load as everything else and therefore RAISES for an
// uncached slug, while the one caller of it (kernel/codification's accepted
// tags) reads an empty list as "this code system has no categories". So a
// caller here owes Known() first, exactly as the expansion route does, and
// nothing in this package may read Tags without it. Reported to the owner
// with the slice rather than papered over with an error return that no
// present caller would read.
//
// Read here rather than in a codification module for the ordinary reason:
// what the categories of a code system are called is the terminology's
// business, and no engine module may type one.
func (c *Cache) Tags(slug string) []string {
	set, found := c.sets[slug]
	if !found {
		return nil
	}
	return append([]string(nil), set.tags...)
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

// QuestionCodings is the bound codings one questionnaire question declares,
// by fact name: the FIRST TWO of the three binding forms, both resolved from
// the question's own declaration.
//
//	code   the question's own concept, bound to CodeBinding. Declared as a
//	       bare code and not a triple: the system comes from the value set
//	       and the display comes from the cache, so neither can be retyped
//	       wrongly. CARE declares all three per field and its displays are
//	       free text as a result.
//	unit   the quantity's unit, bound to UnitBinding. Read from
//	       styling_metadata.phc.unit, which is where it already lives, next
//	       to the range that validates it. Not moved and not duplicated.
//
// Both optional, and an absent one is absent rather than empty: a question
// that binds nothing gets nothing back, and a mapping source that reads a
// fact nothing declared fails rather than writing a null.
//
// WHEN THIS RUNS, AND WHY THE GO ENGINE IS NOT THE ONE THAT USUALLY RUNS IT.
// In the Python this is BUILD time: kernel/mapping._compile_question calls it
// once per question per build and keeps only the resolved facts, which land
// in catalogue.json's compiled `mapping` and are what this engine reads. So
// the Go serving path does not resolve these two forms, it re-checks a
// resolved one (mapping.boundFact) before a column is written, which is the
// write-path half of invariant I1. This function is the other half, read out
// of the declarations rather than out of the compiled artifact, so that a
// questionnaire whose declared code or unit its value set does not hold is a
// failure a check can see on this side of the port too. Nothing on the hot
// path calls it, deliberately: the cache is the authority and it does not
// change between builds, so a per-write lookup would buy nothing and cost a
// map walk on every row.
func QuestionCodings(q questionnaire.Question, t Terminology) (map[string]Coding, error) {
	out := map[string]Coding{}
	for _, form := range []struct{ fact, slug, declared string }{
		{"code", CodeBinding, q.Code},
		{"unit", UnitBinding, q.Unit},
	} {
		if form.declared == "" {
			continue
		}
		coding, err := t.Bound(form.slug, form.declared)
		if err != nil {
			return nil, err
		}
		out[form.fact] = coding
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
		return Coding{}, fmt.Errorf("question %s declares no %s, so its answer "+
			"carries no concept", pyval.Repr(q.LinkID), AnswerValueSet)
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
