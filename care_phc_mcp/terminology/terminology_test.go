// The terminology properties no socket can reach.
//
// WHY THESE ARE HERE AND NOT IN scripts/check_go_parity.py
// --------------------------------------------------------
// The port's rule is that the socket checks are the acceptance test, and most
// of this package already answers to them: GET /valuesets/{slug} is diffed
// against the Python expansion for expansion, and an answer outside its value
// set is refused through the guard in both engines. What is left over is the
// part of kernel/terminology.py that never reaches a wire — the shape of the
// Coding type itself, the two BUILD time binding forms that the Python
// resolved before catalogue.json was written, the semantic tags, and the FHIR
// element — and a property that cannot fail is not a property, so each one is
// held here with the mutation that breaks it named in the comment above it.
//
// EXTERNAL TEST PACKAGE, DELIBERATELY
// -----------------------------------
// `package terminology_test` and not `package terminology`. The invariant
// this file exists to hold is that a Coding cannot be constructed carrying
// anything from OUTSIDE this package, so the check has to stand outside it.
// An internal test would be able to write Coding{system: "..."} and would
// therefore be proving the opposite of what it claims.
package terminology_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"github.com/eka-care/care_phc_mcp/questionnaire"
	"github.com/eka-care/care_phc_mcp/terminology"
)

func cache(t *testing.T) *terminology.Cache {
	t.Helper()
	terms, err := terminology.Load(filepath.Join("..", "..", "terminology"))
	if err != nil {
		t.Fatal(err)
	}
	return terms
}

// files is the cached value sets as they are written on disk, so that nothing
// below compares this package against itself. A display, a system or a
// semantic tag asserted here was read out of the declaration, not typed.
func files(t *testing.T) map[string]map[string]any {
	t.Helper()
	paths, err := filepath.Glob(filepath.Join("..", "..", "terminology", "*.json"))
	if err != nil || len(paths) == 0 {
		t.Fatalf("no value sets on disk: %v", err)
	}
	out := map[string]map[string]any{}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var blob map[string]any
		if err := json.Unmarshal(raw, &blob); err != nil {
			t.Fatalf("%s: %v", path, err)
		}
		out[strings.TrimSuffix(filepath.Base(path), ".json")] = blob
	}
	return out
}

func conceptsOf(t *testing.T, blob map[string]any) map[string]map[string]any {
	t.Helper()
	raw, ok := blob["concepts"].(map[string]any)
	if !ok {
		t.Fatal("a cached value set with no concepts")
	}
	out := map[string]map[string]any{}
	for code, concept := range raw {
		node, _ := concept.(map[string]any)
		out[code] = node
	}
	return out
}

// TestACodingCannotBeConstructedUnvalidated is invariant I1 carried into Go,
// and it is carried as a SHAPE because Go has no way to make a struct literal
// illegal from another package. The Python holds it with a module private
// sentinel: Coding's constructor refuses anything that did not come through
// Terminology.bound(). Here the fields are unexported and reachable only
// through methods, so a Coding built anywhere else is the zero value and
// carries no code, no system and no display.
//
// MUTATE: add any exported field to Coding, or give it a pointer receiver
// method. Either is the ordinary way this guarantee is lost — somebody adds
// `Raw string` for convenience, or a `SetDisplay` for a renderer — and
// neither changes one byte on any wire, so nothing else in this tree would
// notice.
func TestACodingCannotBeConstructedUnvalidated(t *testing.T) {
	value := reflect.TypeOf(terminology.Coding{})
	if value.NumField() == 0 {
		t.Fatal("Coding carries nothing, so this check proves nothing")
	}
	for i := 0; i < value.NumField(); i++ {
		field := value.Field(i)
		if field.IsExported() {
			t.Fatalf("Coding.%s is exported, so another package can build a "+
				"coding no value set vouched for", field.Name)
		}
	}
	// And no exported mutator, which is the Python's __setattr__ refusal:
	// every method a caller can reach takes the coding by value, so nothing
	// may rewrite one in place. A pointer receiver method shows up on the
	// pointer type and not on the value type, so the two counts agreeing is
	// the proof that none exists.
	pointer := reflect.TypeOf(&terminology.Coding{})
	if value.NumMethod() != pointer.NumMethod() {
		t.Fatalf("Coding has %d methods by value and %d by pointer, so at "+
			"least one can rewrite a coding in place",
			value.NumMethod(), pointer.NumMethod())
	}
	if value.NumMethod() == 0 {
		t.Fatal("Coding answers nothing, so this check proves nothing")
	}
	// What a Coding built outside this package actually carries: nothing.
	var outside terminology.Coding
	for _, fact := range []string{"code", "system", "display"} {
		if got := outside.Fact(fact); got != "" {
			t.Fatalf("a Coding built outside the package carries %s = %q",
				fact, got)
		}
	}
	if outside.ValueSet() != "" || outside.Code() != "" ||
		outside.System() != "" || outside.Display() != "" {
		t.Fatal("a Coding built outside the package carries something")
	}
}

// TestBoundIsTheOnlyConstructorAndItValidates walks every code of every
// cached value set through Bound, and every code of every OTHER value set
// against it. Nothing is written down: the codes come off the files, so a
// value set that is re-coded moves this check with it.
//
// MUTATE: delete the `held` branch in Bound, or make Validate answer true for
// an unknown slug.
func TestBoundIsTheOnlyConstructorAndItValidates(t *testing.T) {
	terms, disk := cache(t), files(t)
	bound, refused := 0, 0
	for slug, blob := range disk {
		concepts := conceptsOf(t, blob)
		system, _ := blob["system"].(string)
		for code, concept := range concepts {
			coding, err := terms.Bound(slug, code)
			if err != nil {
				t.Fatalf("%s/%s: %v", slug, code, err)
			}
			if coding.Code() != code || coding.ValueSet() != slug ||
				coding.System() != system {
				t.Fatalf("%s/%s: bound %#v", slug, code, coding)
			}
			// The display is the CACHE'S and never a caller's, which is
			// CARE's free text Coding.display problem removed rather than
			// handled. There is no caller-supplied display to compare
			// against, so the comparison is against the file.
			declared, _ := concept["display"].(string)
			if coding.Display() != declared {
				t.Fatalf("%s/%s: display %q, declared %q", slug, code,
					coding.Display(), declared)
			}
			bound++
		}
		// A real code, from another list this facility caches, whose only
		// fault is which list it is on. Never a literal.
		for other, elsewhere := range disk {
			if other == slug {
				continue
			}
			for code := range conceptsOf(t, elsewhere) {
				if _, alsoHere := concepts[code]; alsoHere {
					continue
				}
				if _, err := terms.Bound(slug, code); err == nil {
					t.Fatalf("%s bound %q, which only %s holds", slug, code, other)
				}
				if terms.Validate(slug, code) {
					t.Fatalf("%s validated %q, which only %s holds", slug, code, other)
				}
				refused++
			}
		}
	}
	if bound == 0 || refused == 0 {
		t.Fatalf("%d bound and %d refused, so this proves nothing", bound, refused)
	}
	// And a value set nothing caches: refused, in the Python's own words,
	// because GET /valuesets/{slug} hands that sentence to a caller as a 404.
	uncached := strings.Join(terms.Cached(), "-")
	if terms.Known(uncached) {
		t.Fatalf("%q is cached, so this proves nothing", uncached)
	}
	_, err := terms.Bound(uncached, "whatever")
	if err == nil || !strings.Contains(err.Error(), "is cached in") {
		t.Fatalf("an uncached value set answered: %v", err)
	}
	if _, err := terms.Expand(uncached, "", 10); err == nil {
		t.Fatal("an uncached value set expanded")
	}
	if terms.Concepts(uncached) != nil || terms.Tags(uncached) != nil ||
		terms.Codes(uncached) != nil {
		t.Fatal("an uncached value set answered with concepts, tags or codes")
	}
	t.Logf("%d codes bound, %d codes refused by the list they are not on",
		bound, refused)
}

// TestTheThreeBindingFormsComeOffTheDeclarations reads the forms out of the
// questionnaires rather than out of this file: a question's own `code`, its
// `styling_metadata.phc.unit`, and its `answer_value_set`. Every one of the
// three has to resolve against a cached value set, and the walk refuses to
// pass if the bundle on disk exercises fewer than three of them.
//
// This is the property the Python holds at BUILD time, where
// kernel/mapping._compile_question calls question_codings and a declared code
// outside its value set is a lint failure. The compiled facts are what the Go
// engine reads, so without this the Go side would trust them unexamined.
//
// MUTATE: make QuestionCodings skip a declared code, or drop one of the two
// forms from its loop.
func TestTheThreeBindingFormsComeOffTheDeclarations(t *testing.T) {
	terms := cache(t)
	set, err := questionnaire.Load(filepath.Join("..", "..", "questionnaires"))
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]int{}
	for _, slug := range set.Slugs() {
		schema, err := set.Get(slug)
		if err != nil {
			t.Fatal(err)
		}
		for _, q := range schema.Walk() {
			codings, err := terminology.QuestionCodings(q, terms)
			if err != nil {
				t.Fatalf("%s/%s: %v", slug, q.LinkID, err)
			}
			if q.Code != "" {
				coding, declared := codings["code"]
				if !declared || coding.Code() != q.Code ||
					coding.ValueSet() != terminology.CodeBinding {
					t.Fatalf("%s/%s declares code %q, resolved %#v",
						slug, q.LinkID, q.Code, coding)
				}
				seen["code"]++
			} else if _, declared := codings["code"]; declared {
				t.Fatalf("%s/%s binds a code it never declared", slug, q.LinkID)
			}
			if q.Unit != "" {
				coding, declared := codings["unit"]
				if !declared || coding.Code() != q.Unit ||
					coding.ValueSet() != terminology.UnitBinding {
					t.Fatalf("%s/%s declares unit %q, resolved %#v",
						slug, q.LinkID, q.Unit, coding)
				}
				seen["unit"]++
			} else if _, declared := codings["unit"]; declared {
				t.Fatalf("%s/%s binds a unit it never declared", slug, q.LinkID)
			}
			if bound := terminology.AnswerBinding(q); bound != "" {
				if !terms.Known(bound) {
					t.Fatalf("%s/%s binds its answer to %q, which this "+
						"facility cannot check offline", slug, q.LinkID, bound)
				}
				if len(terms.Codes(bound)) == 0 {
					t.Fatalf("%s/%s binds its answer to %q, which is an empty "+
						"dropdown", slug, q.LinkID, bound)
				}
				seen["answer"]++
			}
		}
	}
	// And the NAMES. Both constants are field names in somebody else's
	// schema — FHIR's for one and CARE's for the other — and this engine
	// spells each of them into a refusal a clinician reads. Nothing else in
	// the gate can see either spelling: renaming AnswerValueSet to anything
	// at all passed the whole gate as a mutation, because its one use is a
	// sentence no reachable payload produces (a mapping that asks for an
	// answer coding on a question binding nothing is refused at build time).
	// So the names are held against the declarations that use them, which is
	// the only place they are true.
	for name, key := range map[string]string{
		"AnswerValueSet": terminology.AnswerValueSet,
		"UnitOf":         terminology.UnitOf,
	} {
		if !declaresKey(t, key) {
			t.Fatalf("terminology.%s is %q, which no questionnaire in this "+
				"tree declares, so this engine reads the third binding form "+
				"or the unit rule off a field name nothing writes", name, key)
		}
	}
	for _, form := range []string{"code", "unit", "answer"} {
		if seen[form] == 0 {
			t.Fatalf("no question in this bundle declares the %s binding, so "+
				"this check proves nothing about it", form)
		}
	}
	t.Logf("the three binding forms: %d codes, %d units, %d bound answers",
		seen["code"], seen["unit"], seen["answer"])
}

// declaresKey answers whether any questionnaire on disk uses this field name,
// anywhere in its tree. The raw files, not the parsed Question, because the
// parser is the thing being held to the declaration.
func declaresKey(t *testing.T, key string) bool {
	t.Helper()
	paths, err := filepath.Glob(filepath.Join("..", "..", "questionnaires", "*.json"))
	if err != nil || len(paths) == 0 {
		t.Fatalf("no questionnaires on disk: %v", err)
	}
	for _, path := range paths {
		raw, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		var blob any
		if err := json.Unmarshal(raw, &blob); err != nil {
			t.Fatalf("%s: %v", path, err)
		}
		if holdsKey(blob, key) {
			return true
		}
	}
	return false
}

func holdsKey(node any, key string) bool {
	switch shape := node.(type) {
	case map[string]any:
		if _, found := shape[key]; found {
			return true
		}
		for _, inner := range shape {
			if holdsKey(inner, key) {
				return true
			}
		}
	case []any:
		for _, inner := range shape {
			if holdsKey(inner, key) {
				return true
			}
		}
	}
	return false
}

// refusing is a Terminology that vouches for nothing, which is what the seam
// exists for: the Python takes the terminology as an argument so that a check
// hands over a stand-in rather than replacing a package global, which is
// exactly what CARE does for its whole suite (care/utils/tests/base.py:19)
// and why its own guarantee is never exercised in CI.
//
// MUTATE: make QuestionCodings reach for a package level cache instead of its
// argument. Nothing else in this tree would notice, because the real cache
// holds every code the declarations name.
type refusing struct{ terminology.Terminology }

func (refusing) Bound(string, any) (terminology.Coding, error) {
	return terminology.Coding{}, os.ErrNotExist
}

func TestTheSeamTakesAStandIn(t *testing.T) {
	terms := cache(t)
	set, err := questionnaire.Load(filepath.Join("..", "..", "questionnaires"))
	if err != nil {
		t.Fatal(err)
	}
	var declared questionnaire.Question
	for _, slug := range set.Slugs() {
		schema, _ := set.Get(slug)
		for _, q := range schema.Walk() {
			if q.Code != "" || q.Unit != "" {
				declared = q
			}
		}
	}
	if declared.Code == "" && declared.Unit == "" {
		t.Fatal("no question declares a build time binding, so this proves nothing")
	}
	if _, err := terminology.QuestionCodings(declared, terms); err != nil {
		t.Fatalf("the real cache refused %s: %v", declared.LinkID, err)
	}
	if _, err := terminology.QuestionCodings(declared, refusing{terms}); err == nil {
		t.Fatalf("%s resolved against a terminology that vouches for nothing, "+
			"so the argument is not what was consulted", declared.LinkID)
	}
}

// TestTagsAreTheDeclaredSemanticTags holds Tags to the files, and refuses to
// pass unless the tree contains both a value set that declares some and one
// that declares none: a check that only ever saw one of the two would pass
// whichever way the absent case was broken.
//
// MUTATE: return a fixed list, or drop the `semantic_tags` read in Load.
func TestTagsAreTheDeclaredSemanticTags(t *testing.T) {
	terms, disk := cache(t), files(t)
	withTags, without := 0, 0
	for slug, blob := range disk {
		var want []string
		if raw, ok := blob["semantic_tags"].([]any); ok {
			for _, tag := range raw {
				text, _ := tag.(string)
				want = append(want, text)
			}
		}
		got := terms.Tags(slug)
		if len(got) != len(want) {
			t.Fatalf("%s: tags %v, declared %v", slug, got, want)
		}
		for i := range want {
			if got[i] != want[i] {
				t.Fatalf("%s: tags %v, declared %v", slug, got, want)
			}
		}
		if len(want) > 0 {
			withTags++
		} else {
			without++
		}
	}
	if withTags == 0 || without == 0 {
		t.Fatalf("%d value sets declare semantic tags and %d declare none, so "+
			"this check proves nothing", withTags, without)
	}
	t.Logf("%d value sets carry semantic tags, %d carry none", withTags, without)
}

// TestTheCacheCannotBeEditedThroughWhatItHandsBack. The cache is read only
// and generated: nothing in the product writes a value set, which is the
// answer to "who may edit one" — nobody, here. Both readers promise it in as
// many words ("a copy, so a caller cannot edit the cache through it") and in
// Go a promise about a map or a slice is only true if the copy was actually
// made, because both are references.
//
// This is the property the first pass missed. It is also the worst one to
// miss: a caller holding the concepts of a value set in order to render a
// picker could rewrite a display, or blank a concept's `unit`, and from then
// on every validation in this process would be against a list the clinician
// edited. Nothing on any wire would change at the moment it happened, so no
// socket check and no diff could see it; the next write would simply be
// vouched for by the wrong list.
//
// MUTATE: return set.concepts directly from Concepts, or set.tags directly
// from Tags, or copy the concept map's top level without copying each node.
func TestTheCacheCannotBeEditedThroughWhatItHandsBack(t *testing.T) {
	terms, disk := cache(t), files(t)
	edited := 0
	for slug, blob := range disk {
		// Every concept of every value set, edited through what Concepts
		// handed back, and then asked for again.
		handed := terms.Concepts(slug)
		if len(handed) == 0 {
			t.Fatalf("%s handed back nothing", slug)
		}
		for code := range handed {
			handed[code]["display"] = "edited by a caller"
			handed[code]["unit"] = "edited by a caller"
			delete(handed, code)
			edited++
		}
		again := terms.Concepts(slug)
		if len(again) != len(conceptsOf(t, blob)) {
			t.Fatalf("%s: a caller deleted %d concepts from the cache",
				slug, len(conceptsOf(t, blob))-len(again))
		}
		for code, concept := range conceptsOf(t, blob) {
			declared, _ := concept["display"].(string)
			if got, _ := again[code]["display"].(string); got != declared {
				t.Fatalf("%s/%s: a caller rewrote the cached display to %q",
					slug, code, got)
			}
		}
		// And a Bound coding after the edit, because that is the one that
		// becomes a row: the display a clinical fact travels under.
		for code, concept := range conceptsOf(t, blob) {
			coding, err := terms.Bound(slug, code)
			if err != nil {
				t.Fatal(err)
			}
			declared, _ := concept["display"].(string)
			if coding.Display() != declared {
				t.Fatalf("%s/%s binds with %q after a caller edited the cache",
					slug, code, coding.Display())
			}
		}
		// The same for the tags, where the slice is the reference.
		if tags := terms.Tags(slug); len(tags) > 0 {
			tags[0] = "edited by a caller"
			if again := terms.Tags(slug); again[0] == "edited by a caller" {
				t.Fatalf("%s: a caller rewrote a semantic tag in the cache", slug)
			}
			edited++
		}
		// And the codes, which a picker holds.
		if codes := terms.Codes(slug); len(codes) > 0 {
			codes[0] = "edited by a caller"
			if again := terms.Codes(slug); again[0] == "edited by a caller" {
				t.Fatalf("%s: a caller rewrote a code in the cache", slug)
			}
			edited++
		}
	}
	if edited == 0 {
		t.Fatal("nothing was edited, so this check proves nothing")
	}
	// WHAT THIS DOES NOT PROVE. The ORDER of Tags is the file's order and not
	// sorted, which no check here can see: the only two value sets in this
	// tree that declare semantic tags declare them already in sorted order,
	// and the one caller reads them as a SET anyway
	// (kernel/codification.accepted_tags). So sorting them would pass. Said
	// rather than implied.
	t.Logf("%d copies edited through and the cache held", edited)
}

// TestToFHIR is the FHIR R4 Coding element, over every cached code.
//
// `system` is always present, unlike CARE's, which makes it optional while
// requiring `code`: a code without a system is meaningless in FHIR R4 and
// unexportable to ABDM. `display` is present only where the cache recorded
// one, because a key present and empty is not the same document.
//
// MUTATE: write the display unconditionally, or drop the system.
func TestToFHIR(t *testing.T) {
	terms, disk := cache(t), files(t)
	withDisplay, bare := 0, 0
	for slug, blob := range disk {
		system, _ := blob["system"].(string)
		for code, concept := range conceptsOf(t, blob) {
			coding, err := terms.Bound(slug, code)
			if err != nil {
				t.Fatal(err)
			}
			element := coding.ToFHIR()
			if element["system"] != system || element["code"] != code {
				t.Fatalf("%s/%s: %v", slug, code, element)
			}
			display, _ := concept["display"].(string)
			shown, carried := element["display"]
			switch {
			case display == "" && carried:
				t.Fatalf("%s/%s carries an empty display", slug, code)
			case display != "" && (!carried || shown != display):
				t.Fatalf("%s/%s: display %v, declared %q", slug, code,
					shown, display)
			}
			if display == "" {
				bare++
			} else {
				withDisplay++
			}
		}
	}
	if withDisplay == 0 {
		t.Fatal("no cached concept has a display, so this proves nothing")
	}
	// WHAT THIS DOES NOT PROVE, SAID RATHER THAN IMPLIED. Every one of the 87
	// cached concepts in this tree declares a display, so `bare` is zero and
	// the OMISSION branch is never taken: writing the display
	// unconditionally passes this check and the whole gate. It cannot be made
	// to fail without a concept that has no display, and nothing here may
	// edit a value set to manufacture one — terminology/condition-code.json
	// says it is not a primary health centre diagnosis list and awaits a
	// named clinician. So the claim is the narrow one: a declared display is
	// carried verbatim. The day a real NRCeS release sits behind this seam
	// with a display-less concept in it, this is the branch nothing watched.
	// The assertion for it is written above and will run the moment such a
	// concept exists; what is missing is a concept to run it on.
	// The zero Coding, which is the one a Go caller outside this package can
	// hold, projects to a code with no system. kernel/fhir._coding refuses
	// exactly that shape ("no system means no coding"), so an empty coding
	// stays out of a document by the ordinary route rather than by a second
	// rule here. Said out loud because it is the one place where Go has a
	// state the Python cannot reach.
	var outside terminology.Coding
	if outside.ToFHIR()["system"] != "" {
		t.Fatal("the zero Coding carries a system")
	}
	t.Logf("%d codings carry a display, %d do not", withDisplay, bare)
}

// TestExpandIsSortedByCodeAndCapped. The order is the Python's
// `sorted(blob["concepts"].items())`, which is by CODE and not by display,
// and it is what makes the cap deterministic rather than map order. The
// filter is a substring of either the display or the code.
//
// MUTATE: sort by display, drop the cap, or match the display only.
func TestExpandIsSortedByCodeAndCapped(t *testing.T) {
	terms, disk := cache(t), files(t)
	for slug, blob := range disk {
		concepts := conceptsOf(t, blob)
		want := make([]string, 0, len(concepts))
		for code := range concepts {
			want = append(want, code)
		}
		sort.Strings(want)

		found, err := terms.Expand(slug, "", len(want))
		if err != nil {
			t.Fatal(err)
		}
		if len(found) != len(want) {
			t.Fatalf("%s: %d expanded of %d", slug, len(found), len(want))
		}
		for i, coding := range found {
			if coding.Code() != want[i] {
				t.Fatalf("%s: expansion %d is %q, by code it is %q", slug, i,
					coding.Code(), want[i])
			}
		}
		// The cap, at one, which is the only count smaller than every value
		// set here and therefore the only one that can be seen to bite.
		capped, err := terms.Expand(slug, "", 1)
		if err != nil {
			t.Fatal(err)
		}
		if len(capped) != 1 || capped[0].Code() != want[0] {
			t.Fatalf("%s: a cap of one answered %d", slug, len(capped))
		}
		// The filter, over a word from this value set's own first display and
		// over a fragment of its own first code. Both halves, because a
		// filter that reads the display only would pass the first.
		first := found[0]
		if words := strings.Fields(first.Display()); len(words) > 0 {
			byDisplay, err := terms.Expand(slug, words[0], len(want))
			if err != nil {
				t.Fatal(err)
			}
			if !holds(byDisplay, first.Code()) {
				t.Fatalf("%s: %q does not find %q by display", slug, words[0],
					first.Code())
			}
		}
		byCode, err := terms.Expand(slug, first.Code(), len(want))
		if err != nil {
			t.Fatal(err)
		}
		if !holds(byCode, first.Code()) {
			t.Fatalf("%s: %q does not find itself by code", slug, first.Code())
		}
		none, err := terms.Expand(slug, "nothing anybody declared", len(want))
		if err != nil {
			t.Fatal(err)
		}
		if len(none) != 0 {
			t.Fatalf("%s: a phrase nobody declared found %d", slug, len(none))
		}
	}
}

func holds(codings []terminology.Coding, code string) bool {
	for _, coding := range codings {
		if coding.Code() == code {
			return true
		}
	}
	return false
}
