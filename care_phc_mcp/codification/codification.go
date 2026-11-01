// Package codification is kernel/codification.py: the codification seam. A
// heard phrase in, candidate codes out, and the empty answer as the ordinary
// one.
//
// What this package is for
// ------------------------
// A clinician says "sugar". Something has to turn that into a code a second
// facility will read the same way. Multilingual concept ranking over twelve
// Indian languages is the one piece of this product we cannot build and should
// not try, which is why that row of the coded data plan's authority table goes
// to Eka's codification service. This package is the seam that row sits
// behind.
//
// THE RULE THE WHOLE FILE EXISTS TO HOLD
// --------------------------------------
// CODIFICATION PROPOSES. IT NEVER DECIDES. So:
//
//   - nothing here returns a value. It returns Candidates, and a candidate is
//     not an answer to anything until a person picks one;
//   - there is NO SCORE THRESHOLD in this file and there must not be one. A
//     threshold is the mechanism by which a suggestion becomes a decision, and
//     nobody has validated one. The candidates come back in the order the
//     service ranked them and a person reads the list;
//   - Linked is carried through and acted on by nothing. It is the service's
//     own confidence that it found the single right match, which is worth
//     showing beside a candidate and is not a licence to fill a field.
//
// The Python's own file records where it disagrees with the plan it implements
// (invariant I4, which would have a linked candidate write a confirmed
// verification status) and why it follows the authority table instead. That
// reasoning is NOT restated here and is not re-opened here: it is the
// Python's, this is a port, and a second copy of a contested decision is a
// second place for it to drift.
//
// What makes a candidate a candidate
// ----------------------------------
// Four refusals, each with its own reason, applied in this order by Resolve. A
// refused candidate is counted and named, never silently dropped, because "the
// service found nothing" and "the service found four things this build cannot
// code" are different sentences to put in front of a doctor.
//
//  1. NO SPAN. The phrase a candidate was asked about must appear in the
//     transcript: a code with no words behind it is unarguable afterwards.
//  2. NOT RESOLVABLE. The code must come back from the terminology's Bound,
//     which is the only constructor of a Coding in this product. An external
//     service returning a code this build cannot resolve is refused, not
//     stored. Today that refuses nearly everything, and that is the real
//     operating condition rather than a temporary state to design around.
//  3. WRONG BRANCH. A SNOMED candidate carries its semantic tag, and the value
//     set declares which tags its concepts carry. A procedure offered for a
//     diagnosis is refused on the tag before anything looks at the code. A
//     separate rule from 2 on purpose: with the local cache the two coincide
//     for most codes, and with the NRCeS index behind the same seam, where a
//     value set is a whole branch, they will not.
//  4. ALREADY SEEN. The service returns the same concept under several term
//     names. The first, highest ranked one is kept.
//
// THE ONE DECISION THIS PORT HAD TO MAKE, AND WHICH WAY IT WENT
// -------------------------------------------------------------
// Whether an UNCACHED value set is an error or simply a set with no
// categories. The Python raises UnboundCoding, because `accepted_tags` reads
// the tags through the cache's own loader and catches only AttributeError. The
// Go terminology cache's Tags returns nil for a slug it does not hold, which
// cannot be told apart from a value set that declares no tags at all.
//
// THE PYTHON IS RIGHT AND THIS PACKAGE MATCHES IT. An empty tag set means
// "the tag rule does not apply", so reading an uncached value set as having no
// categories would turn refusal 3 OFF SILENTLY and let a procedure through for
// a diagnosis. And an uncached value set is not an operating condition the way
// an empty answer is: a question's binding is linted against the cache at
// build time, so a slug that is not there means the declarations are broken or
// a connector invented one. This build fails closed and loudly on a
// declaration error everywhere else, and this is that.
//
// So AcceptedTags returns an error, in the terminology's own words, and
// Resolve passes it out rather than answering with an empty suggestion. The
// Python was NOT changed to make the port look right; it was already the one
// that had this correct.
//
// Layering. This package may not open a socket: the seam, the refusals and the
// stub are here, and an implementation that speaks to a network would live
// beside the other connectors, the way the patient directory's does. Pure:
// reads the local terminology cache and nothing else.
package codification

import (
	"fmt"
	"regexp"
	"sort"
	"strings"

	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/terminology"
)

// SemanticTags and SemanticTag are where a value set says which semantic tags
// its concepts carry. Named rather than spelled at the use site for the reason
// every other clinical fact is: this package may know that codes have
// categories and may not know what any category is called.
const (
	SemanticTags = "semantic_tags"
	SemanticTag  = "semantic_tag"
)

var spaces = regexp.MustCompile(`\s+`)

// norm is the same normalisation api/extract.py compares spans with, and
// kernel/codification._norm copies by hand for the same reason: the rule is
// one sentence and a wrapper would hide more than it saves.
func norm(text string) string {
	return strings.ToLower(strings.TrimSpace(spaces.ReplaceAllString(text, " ")))
}

// Result is one raw service result, in the shape every connector translates
// its own wire format into. The translation belongs to that service's
// connector; what is here is every rule that must hold whichever service is
// behind the seam.
type Result struct {
	Code   string `json:"code"`
	Term   string `json:"term"`
	Score  any    `json:"score"`
	Linked bool   `json:"linked"`
	Tag    string `json:"tag"`
}

// Candidate is one suggested code, with everything a person needs to refuse
// it.
//
// It carries a terminology.Coding rather than a code and a system, and that is
// the whole of why it needs no gate of its own: a Coding's fields are
// unexported and Bound is its only constructor, so a Candidate cannot be made
// to carry a code nothing vouched for. One gate is enough and it is in the
// terminology package.
//
//	Coding  the resolved code. Its display is the terminology's, never the
//	        service's term, so a service that disagrees with the value set
//	        cannot rename a concept on a doctor's screen.
//	Score   what the service reported, or nil. Nil is the ordinary case for a
//	        medication candidate, where the contract documents score as null.
//	        Carried and compared against nothing.
//	Linked  the service's own flag that it believes this is the single right
//	        match. Shown beside a candidate, never acted on.
//	Span    the words in the transcript this was asked about.
//	Term    what the service called it, kept only so a person can see what was
//	        matched. Never stored and never displayed as the code's name.
//
// UNEXPORTED FIELDS AND READERS, which is the shape G5 settled for Coding and
// for the same reason: Go cannot make a struct literal illegal from another
// package, so a Candidate built anywhere else is the zero value and carries no
// Coding at all.
type Candidate struct {
	coding terminology.Coding
	score  any
	linked bool
	span   string
	term   string
}

// NewCandidate is the one constructor. It takes a Coding, which is the only
// thing in this product that has been through a value set.
func NewCandidate(coding terminology.Coding, score any, linked bool,
	span, term string) (Candidate, error) {
	if coding.Code() == "" {
		return Candidate{}, fmt.Errorf("a Candidate carries a Coding, which " +
			"is the only thing in this product that has been through a value set")
	}
	return Candidate{coding: coding, score: score, linked: linked,
		span: span, term: term}, nil
}

// The readers. Value receivers and no pointer method anywhere, so a Candidate
// cannot be mutated through one.
func (c Candidate) Coding() terminology.Coding { return c.coding }
func (c Candidate) Score() any                 { return c.score }
func (c Candidate) Linked() bool               { return c.linked }
func (c Candidate) Span() string               { return c.span }
func (c Candidate) Term() string               { return c.term }

// Public is the candidate as a renderer reads it: the code, the terminology's
// own display, and the two things that let a person judge it.
//
// THERE IS NO `value` KEY AND THERE MUST NOT BE ONE. A shape a form control
// could bind to directly is how a candidate becomes a value without anybody
// picking it.
func (c Candidate) Public() map[string]any {
	return map[string]any{
		"code": c.coding.Code(), "system": c.coding.System(),
		"display": c.coding.Display(), "valueset": c.coding.ValueSet(),
		"score": c.score, "linked": c.linked,
		"span": c.span, "term": c.term,
	}
}

// Suggestions is the ranked candidates, and why the rest are not here.
//
// The Python is a tuple subclass, so every caller that treats the answer as a
// sequence is right and the empty answer needs no special handling at all. Go
// has no such trick, so Candidates is a plain slice and the empty answer is a
// slice of length nought, which `len(s.Candidates) == 0` answers. `Refused` is
// beside it rather than inside it: a caller drawing a picker iterates the
// candidates, and a caller explaining an empty picker reads the sentences.
type Suggestions struct {
	Candidates []Candidate
	Refused    []string
	Asked      string
	// Reachable is false ONLY when the service could not be ASKED. One that
	// answered and offered nothing is reachable, and the two are different
	// sentences for the same reason a directory lookup's are: "nobody matched"
	// and "I could not look" lead a clinician to different next actions.
	Reachable bool
}

// Len makes the empty case readable without unwrapping anything.
func (s Suggestions) Len() int { return len(s.Candidates) }

// Codification is the seam. One method.
//
// `text` is what was heard. `valueset` is the slug the question binds its
// answer to, which is what decides both which ontology is asked and which
// codes may come back. `context` carries the hints the service's accuracy
// depends on, which for a laboratory value is the unit and the specimen and
// for a medicine is the form; an implementation that wants none ignores it.
// `transcript` is what the span is checked against.
type Codification interface {
	Suggest(text, valueset string, context map[string]any,
		transcript, span string) (Suggestions, error)
}

// None is the implementation everything must work against: nothing, every
// time.
//
// NOT A TEST DOUBLE. This is what a primary health centre with no line runs,
// and it is the default wherever a codifier is optional, so the offline path
// is the path that gets exercised rather than a fallback nobody reaches.
// Reachable is true, because a facility that has no codification configured is
// not a facility whose codification is down.
type None struct{}

// Suggest answers nothing, reachably.
func (None) Suggest(text, valueset string, context map[string]any,
	transcript, span string) (Suggestions, error) {
	return Suggestions{Candidates: []Candidate{}, Refused: []string{},
		Asked: text, Reachable: true}, nil
}

// Tagger is all this package needs of a terminology: which tags a value set
// declares, whether it is cached at all, and the one constructor of a Coding.
// Narrowed to an interface so a crafted value set can be put behind it by a
// test without this package reaching for the real cache.
type Tagger interface {
	Known(slug string) bool
	Tags(slug string) []string
	Bound(slug string, code any) (terminology.Coding, error)
	Unbound(slug string) error
}

// AcceptedTags is the semantic tags this value set's own concepts carry.
//
// Empty when the value set DECLARES none, and an empty set means the tag rule
// does not apply rather than that everything is refused: the FHIR status value
// sets and the UCUM units have no semantic tags and never will, because they
// are not SNOMED and the concept of a semantic tag is SNOMED's.
//
// AN UNCACHED VALUE SET IS AN ERROR AND NOT AN EMPTY SET. See the package
// comment: the two are indistinguishable through the cache's own Tags, and
// reading the one as the other turns the wrong-branch refusal off silently.
func AcceptedTags(terms Tagger, valueset string) (map[string]bool, error) {
	if terms == nil {
		return nil, fmt.Errorf("no terminology was given, so no value set's " +
			"semantic tags could be read")
	}
	if !terms.Known(valueset) {
		return nil, terms.Unbound(valueset)
	}
	out := map[string]bool{}
	for _, tag := range terms.Tags(valueset) {
		if trimmed := strings.ToLower(strings.TrimSpace(tag)); trimmed != "" {
			out[trimmed] = true
		}
	}
	return out, nil
}

// Resolve turns raw service results into Suggestions, applying the four
// refusals in order.
//
// THE ORDER OF THE RESULTS IS PRESERVED EXACTLY. Nothing is re-sorted by
// score, because sorting by score is one line away from picking by score.
func Resolve(results []Result, valueset string, terms Tagger,
	transcript, span, text string) (Suggestions, error) {

	tags, err := AcceptedTags(terms, valueset)
	if err != nil {
		// Out rather than down: an uncached value set is a declaration that
		// does not hold, and answering it with an empty suggestion would read
		// as a service that found nothing.
		return Suggestions{}, err
	}
	asked := text
	if asked == "" {
		asked = span
	}
	heard := norm(transcript)

	if span != "" && heard != "" && !strings.Contains(heard, norm(span)) {
		// ONE REFUSAL FOR THE WHOLE BATCH: the words were not said, so no
		// candidate for them can be traced to anything.
		return Suggestions{
			Candidates: []Candidate{},
			Refused: []string{fmt.Sprintf("%s is not in the transcript, so "+
				"nothing suggested for it can be traced to what was said",
				pyval.Repr(span))},
			Asked: asked, Reachable: true}, nil
	}

	kept := []Candidate{}
	refused := []string{}
	seen := map[string]bool{}
	for _, raw := range results {
		code := strings.TrimSpace(raw.Code)
		term := raw.Term
		if code == "" {
			refused = append(refused, "a candidate came back with no code")
			continue
		}
		named := term
		if named == "" {
			named = "no name"
		}
		tag := strings.ToLower(strings.TrimSpace(raw.Tag))
		if len(tags) > 0 && !tags[tag] {
			kind := tag
			if kind == "" {
				kind = "concept of no stated kind"
			}
			refused = append(refused, fmt.Sprintf(
				"%s (%s) is a %s, and %s holds %s, so it is not a candidate "+
					"for this question",
				code, named, kind, valueset, strings.Join(sortedTags(tags), " or ")))
			continue
		}
		coding, err := terms.Bound(valueset, code)
		if err != nil {
			refused = append(refused, fmt.Sprintf(
				"%s (%s) is not in %s, so this build cannot resolve it and it "+
					"may not be offered", code, named, valueset))
			continue
		}
		if seen[coding.Code()] {
			continue // the same concept under another of its names
		}
		seen[coding.Code()] = true
		candidate, err := NewCandidate(coding, raw.Score, raw.Linked, span, term)
		if err != nil {
			return Suggestions{}, err
		}
		kept = append(kept, candidate)
	}
	return Suggestions{Candidates: kept, Refused: refused, Asked: asked,
		Reachable: true}, nil
}

// sortedTags is the accepted tags in the order the Python's
// `" or ".join(sorted(tags))` puts them, so the refusal sentence is the same
// on both sides.
func sortedTags(tags map[string]bool) []string {
	out := make([]string, 0, len(tags))
	for tag := range tags {
		out = append(out, tag)
	}
	sort.Strings(out)
	return out
}
