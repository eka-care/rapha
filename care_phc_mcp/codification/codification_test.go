package codification_test

// An EXTERNAL test package, for the reason G5's terminology test gives for its
// own: a test inside the package could build a Candidate past its one
// constructor and prove the opposite of what it claims.

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/eka-care/care_phc_mcp/codification"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// The slug the real cache holds, so what is exercised is this bundle's own
// declarations rather than a value set written here.
const slug = "condition-code"

func realTerms(t *testing.T) *terminology.Cache {
	t.Helper()
	terms, err := terminology.Load(filepath.Join("..", "..", "terminology"))
	if err != nil {
		t.Fatal(err)
	}
	return terms
}

// crafted is a value set written for one test, which the Python's own demo
// needs too: the wrong-branch rule can only be reached by a terminology that
// WOULD resolve the code, or the unresolvable rule catches the case first and
// the tag rule could be deleted with nothing failing.
func crafted(t *testing.T, body string) *terminology.Cache {
	t.Helper()
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, slug+".json"),
		[]byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	terms, err := terminology.Load(dir)
	if err != nil {
		t.Fatal(err)
	}
	return terms
}

// 1. Nothing found is the ordinary answer, and the empty case needs no
// unwrapping.
func TestNothingFoundIsTheOrdinaryAnswer(t *testing.T) {
	got, err := codification.None{}.Suggest("dengue", slug, nil, "dengue hai", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 0 || len(got.Candidates) != 0 {
		t.Errorf("the stub offered %d candidates", got.Len())
	}
	if !got.Reachable {
		t.Error("a facility with no codification configured is not a facility " +
			"whose codification is down")
	}
	if len(got.Refused) != 0 {
		t.Errorf("the stub refused something: %v", got.Refused)
	}
	if got.Asked != "dengue" {
		t.Errorf("asked = %q", got.Asked)
	}
}

// 2. A code this build can resolve comes back as a candidate, carrying the
// TERMINOLOGY'S display and not the service's name for it.
func TestAResolvableCodeBecomesACandidateCarryingTheTerminologysDisplay(t *testing.T) {
	terms := realTerms(t)
	// The code is read off the value set rather than typed, so this test names
	// no clinical code and grows with the bundle.
	codes := terms.Codes(slug)
	if len(codes) == 0 {
		t.Fatalf("%s holds no codes, so this proves nothing", slug)
	}
	code := codes[0]
	concept, err := terms.Concept(slug, code)
	if err != nil {
		t.Fatal(err)
	}
	display, _ := concept["display"].(string)
	tag, _ := concept[codification.SemanticTag].(string)

	got, err := codification.Resolve([]codification.Result{{
		Code: code, Term: "what the service called it", Score: 0.98,
		Linked: true, Tag: tag}}, slug, terms, "the patient said something", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 1 {
		t.Fatalf("one resolvable code gave %d candidates, refused %v",
			got.Len(), got.Refused)
	}
	one := got.Candidates[0]
	if one.Coding().Code() != code {
		t.Errorf("the candidate carries %q", one.Coding().Code())
	}
	if one.Coding().Display() != display {
		t.Errorf("the candidate's display is %q and the terminology says %q: a "+
			"service that disagrees with the value set must not be able to "+
			"rename a concept on a doctor's screen",
			one.Coding().Display(), display)
	}
	if one.Term() != "what the service called it" {
		t.Errorf("the service's own name was not kept: %q", one.Term())
	}
	if !one.Linked() || one.Score() != 0.98 {
		t.Errorf("the service's own two judgements were not carried: %+v", one)
	}
	public := one.Public()
	if public["display"] != display {
		t.Errorf("the public shape's display is %v", public["display"])
	}
	if _, bindable := public["value"]; bindable {
		t.Error("a candidate has a `value` key, which is a shape a form " +
			"control can bind to: that is how a suggestion becomes a value " +
			"without anybody picking it")
	}
}

// 3. A code this build cannot resolve is refused, and NAMED in a sentence.
// This is the ordinary outcome for almost anything a clinician says.
func TestACodeThisBuildCannotResolveIsRefusedAndNamed(t *testing.T) {
	terms := realTerms(t)
	got, err := codification.Resolve([]codification.Result{{
		Code: "38362002", Term: "a thing this build does not code",
		Score: 0.99, Linked: true, Tag: "disorder"}}, slug, terms,
		"the patient said something", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 0 {
		t.Fatalf("an unresolvable code was offered: %+v", got.Candidates)
	}
	if len(got.Refused) != 1 {
		t.Fatalf("the refusals are %v", got.Refused)
	}
	if !strings.Contains(got.Refused[0], "38362002") {
		t.Errorf("the refusal does not name the code: %q", got.Refused[0])
	}
	if !strings.Contains(got.Refused[0], "cannot resolve") {
		t.Errorf("the refusal does not say why: %q", got.Refused[0])
	}
}

// 4. WRONG BRANCH of the ontology, over a crafted value set that WOULD resolve
// the code. Without that, the unresolvable rule above catches the case and the
// tag rule could be deleted with nothing failing.
func TestACandidateFromTheWrongBranchIsRefusedOnItsTag(t *testing.T) {
	terms := crafted(t, `{"slug": "`+slug+`",
		"system": "http://snomed.info/sct",
		"semantic_tags": ["disorder", "finding"],
		"concepts": {"71388002": {"display": "A Concept",
		                          "semantic_tag": "procedure"}}}`)
	if !terms.Validate(slug, "71388002") {
		t.Fatal("the crafted value set does not hold the code, so the tag rule " +
			"is not what is being reached")
	}
	wrong, err := codification.Resolve([]codification.Result{{
		Code: "71388002", Term: "A Concept", Score: 0.9, Linked: true,
		Tag: "procedure"}}, slug, terms, "something was said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if wrong.Len() != 0 {
		t.Fatalf("a candidate from the wrong branch was offered: %+v",
			wrong.Candidates)
	}
	if !strings.Contains(wrong.Refused[0], "is a procedure") {
		t.Errorf("the refusal does not name the branch: %q", wrong.Refused[0])
	}

	// THE SAME CODE, THE SAME TERMINOLOGY, AN ACCEPTED TAG: kept. This is what
	// proves the refusal above was the tag rule and nothing else.
	right, err := codification.Resolve([]codification.Result{{
		Code: "71388002", Term: "A Concept", Tag: "disorder"}}, slug, terms,
		"something was said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if right.Len() != 1 {
		t.Fatalf("the same code with an accepted tag was refused: %v",
			right.Refused)
	}
}

// A value set that declares NO tags does not refuse everything: an empty tag
// set means the rule does not apply. The FHIR status value sets and the UCUM
// units have no semantic tags and never will.
func TestAValueSetThatDeclaresNoTagsDoesNotRefuseEverything(t *testing.T) {
	terms := crafted(t, `{"slug": "`+slug+`",
		"system": "http://snomed.info/sct",
		"concepts": {"71388002": {"display": "A Concept"}}}`)
	tags, err := codification.AcceptedTags(terms, slug)
	if err != nil {
		t.Fatal(err)
	}
	if len(tags) != 0 {
		t.Fatalf("a value set that declares no tags reported %v", tags)
	}
	got, err := codification.Resolve([]codification.Result{{
		Code: "71388002", Term: "A Concept", Tag: "anything at all"}}, slug,
		terms, "something was said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 1 {
		t.Fatalf("a value set with no declared tags refused a candidate: %v",
			got.Refused)
	}
}

// THE ONE DECISION THIS PORT HAD TO MAKE. An uncached value set is an ERROR
// and not a set with no categories, which is what the Python does and is the
// one of the two that is right: an empty tag set turns the wrong-branch rule
// off, so reading a missing value set as "no categories" would let a procedure
// through for a diagnosis, silently. See the package comment.
func TestAnUncachedValueSetIsAnErrorAndNotASetWithNoCategories(t *testing.T) {
	terms := realTerms(t)
	const nobodys = "a-value-set-nobody-cached"
	if terms.Known(nobodys) {
		t.Fatalf("%s is cached, so this proves nothing", nobodys)
	}

	if _, err := codification.AcceptedTags(terms, nobodys); err == nil {
		t.Fatal("an uncached value set reported its tags, so the wrong-branch " +
			"refusal is off for it and a procedure can be offered for a " +
			"diagnosis")
	} else if !strings.Contains(err.Error(), "cannot check offline") {
		t.Errorf("the error is not the terminology's own sentence: %v", err)
	}

	// And Resolve passes it OUT rather than answering with an empty
	// suggestion: an empty answer reads as a service that found nothing, and
	// this is a declaration that does not hold.
	got, err := codification.Resolve([]codification.Result{{
		Code: "71388002", Tag: "procedure"}}, nobodys, terms,
		"something was said", "", "")
	if err == nil {
		t.Fatalf("resolving against an uncached value set answered %+v rather "+
			"than failing", got)
	}
	if got.Len() != 0 || len(got.Refused) != 0 {
		t.Error("a failed resolve also returned suggestions, so a caller that " +
			"reads the answer before the error sees candidates")
	}
}

// The same concept under several of its names is kept once, at its highest
// rank. The service returns localised and transliterated variants of one
// concept.
func TestTheSameConceptUnderSeveralNamesIsKeptOnce(t *testing.T) {
	terms := realTerms(t)
	code := terms.Codes(slug)[0]
	concept, err := terms.Concept(slug, code)
	if err != nil {
		t.Fatal(err)
	}
	tag, _ := concept[codification.SemanticTag].(string)
	got, err := codification.Resolve([]codification.Result{
		{Code: code, Term: "the first name", Score: 0.9, Tag: tag},
		{Code: code, Term: "the second name", Score: 0.8, Tag: tag},
		{Code: code, Term: "the third name", Score: 0.7, Tag: tag},
	}, slug, terms, "something was said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 1 {
		t.Fatalf("one concept under three names gave %d candidates", got.Len())
	}
	if got.Candidates[0].Term() != "the first name" {
		t.Errorf("the kept candidate is %q, and the first one the service "+
			"ranked was the first name", got.Candidates[0].Term())
	}
}

// A span that was never said refuses the WHOLE BATCH, with one sentence: the
// words were not said, so no candidate for them can be traced to anything.
func TestASpanThatWasNeverSaidRefusesTheWholeBatch(t *testing.T) {
	terms := realTerms(t)
	code := terms.Codes(slug)[0]
	got, err := codification.Resolve([]codification.Result{
		{Code: code, Term: "a name", Tag: "disorder"},
		{Code: code, Term: "another", Tag: "disorder"},
	}, slug, terms, "the patient said one thing", "a phrase nobody uttered", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 0 {
		t.Fatalf("a span that was never said still produced %d candidates",
			got.Len())
	}
	if len(got.Refused) != 1 {
		t.Fatalf("the batch produced %d refusals, want one for the whole batch: %v",
			len(got.Refused), got.Refused)
	}
	if !strings.Contains(got.Refused[0], "not in the transcript") {
		t.Errorf("the refusal does not say why: %q", got.Refused[0])
	}
}

// A result with no code is refused and COUNTED, never silently dropped: "the
// service found nothing" and "the service found four things this build cannot
// code" are different sentences to put in front of a doctor.
func TestACandidateWithNoCodeIsRefusedAndCounted(t *testing.T) {
	terms := realTerms(t)
	got, err := codification.Resolve([]codification.Result{
		{Code: "", Term: "nameless"},
		{Code: "   ", Term: "blank"},
	}, slug, terms, "something was said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 0 {
		t.Fatalf("a codeless result became a candidate")
	}
	if len(got.Refused) != 2 {
		t.Errorf("two codeless results produced %d refusals: %v",
			len(got.Refused), got.Refused)
	}
}

// THE ORDER THE SERVICE RANKED THEM IS PRESERVED EXACTLY, because sorting by
// score is one line away from picking by score.
func TestTheServicesOwnOrderIsPreserved(t *testing.T) {
	terms := realTerms(t)
	codes := terms.Codes(slug)
	if len(codes) < 3 {
		t.Skipf("%s holds %d codes and this needs three", slug, len(codes))
	}
	results := []codification.Result{}
	// Deliberately ASCENDING scores, so anything that sorted by score would
	// reverse the list.
	for n, code := range codes[:3] {
		concept, err := terms.Concept(slug, code)
		if err != nil {
			t.Fatal(err)
		}
		tag, _ := concept[codification.SemanticTag].(string)
		results = append(results, codification.Result{
			Code: code, Term: "name", Score: 0.1 * float64(n+1), Tag: tag})
	}
	got, err := codification.Resolve(results, slug, terms, "said", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if got.Len() != 3 {
		t.Fatalf("three codes gave %d candidates: %v", got.Len(), got.Refused)
	}
	for n, candidate := range got.Candidates {
		if candidate.Coding().Code() != codes[n] {
			t.Errorf("candidate %d is %s and the service ranked %s there; "+
				"nothing here may re-sort by score", n,
				candidate.Coding().Code(), codes[n])
		}
	}
}

// A Candidate built anywhere but its constructor is the zero value and carries
// no Coding, which is the shape G5 settled for Coding and the reason it was
// settled that way: Go cannot make a struct literal illegal from another
// package.
func TestACandidateCannotBeBuiltCarryingACodeNothingVouchedFor(t *testing.T) {
	var made codification.Candidate
	if made.Coding().Code() != "" {
		t.Error("a zero Candidate carries a code")
	}
	if _, err := codification.NewCandidate(terminology.Coding{}, nil, false,
		"", ""); err == nil {
		t.Error("a Candidate was built from a Coding that had been through no " +
			"value set")
	}
}
