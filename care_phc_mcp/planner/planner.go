// Package planner turns an utterance into PROPOSED operations. It is the Go
// half of agent/planner.py, and it decides nothing.
//
// A planner picks operations and fills in what it is sure of. Then the guard
// decides, on the machine surface, where a write can only ever come back
// "proposed". A person confirms it on the rendered surface, or it does not
// happen. Nothing in this package runs the guard, and there is no argument
// anywhere on this path that could set confirmed.
//
// ONE BACKEND, NOT TWO, AND SAID SO
// ---------------------------------
// agent/planner.py has two: route(), deterministic, and llm(), the anthropic
// SDK on claude-opus-5 when ANTHROPIC_API_KEY is set. This package ports
// route() and refuses the other by name. That is deliberate rather than
// unfinished: the port may make no network call and may take no new
// third-party dependency, and a Go llm backend would need both. Backend()
// below answers "llm" exactly where the Python's does, and Plan() returns an
// error naming the gap instead of quietly planning with the router and
// reporting a backend it did not use. The Python's own llm() has never been
// run against api.anthropic.com either; what is NOT true is that the two
// engines agree about it, and the honest place for that is an error.
//
// The vocabulary is the compiled catalogue's, so a new atom is routable the
// moment it lints. The one hand written list is spoken below: words a nurse
// says out loud that no frontmatter field would ever hold.
package planner

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/pyval"
)

// Proposed is what a planner wants. Not a decision, and not a write.
type Proposed struct {
	Operation string
	Payload   map[string]any
	Why       string
	Backend   string
	Score     int
	// Ask is what the planner heard but would not resolve, in its own words. A
	// question is the honest alternative to a guess; it is not a decision and
	// nothing reads it back as one.
	Ask []string
}

// stop are words that carry no signal. Short on purpose: a stopword list that
// grows is a list nobody maintains, and a stray match costs one point out of
// several. agent/planner.py's STOP, word for word.
var stop = wordSet(`
a an and are as at be by for from has have how in into is it its of on or that
the this to was what when where which who will with you your patient patients
their her his please record records new
`)

func wordSet(blob string) map[string]bool {
	out := map[string]bool{}
	for _, w := range strings.Fields(blob) {
		out[w] = true
	}
	return out
}

// spoken are the words the catalogue does not contain. agent/planner.py's
// SPOKEN, operation for operation.
var spoken = map[string][]string{
	"phc.op.patient-register":  {"register", "enrol", "enroll", "registration", "intake"},
	"phc.op.abha-link":         {"abha", "aadhaar", "aadhar", "ayushman", "link"},
	"phc.op.vitals-record":     {"bp", "pressure", "sats", "obs", "triage", "vitals"},
	"phc.op.consult-document":  {"consult", "consultation", "note", "opd", "seen", "history"},
	"phc.op.rx-prescribe":      {"prescribe", "prescription", "medicine", "medicines", "drug", "tablet", "tablets", "rx"},
	"phc.op.lab-order":         {"test", "tests", "investigation", "investigations", "cbc", "sugar"},
	"phc.op.lab-result-enter":  {"result", "results", "report", "bench", "analyte"},
	"phc.op.pharmacy-dispense": {"dispense", "issue", "pharmacy", "stock", "handout"},
	"phc.op.household-visit":   {"household", "home", "visit", "doorstep", "field"},
}

// A keyword from the operation's own identity is worth more than one from its
// prose, because prose is shared between operations and identity is not.
const strong, weak = 2, 1

// SpokenFields are the spoken names for a questionnaire field, keyed by
// link_id. ONE list, and it lives in packages/voice because that is where it
// already existed and where it is data rather than code: grammar.ts imports
// this same JSON, and agent/planner.py reads this same file. Two lists would
// drift, and the way you find out is a clinician saying "temp 37.2" into a box
// that only knows "temperature".
//
// Read from the tree rather than restated here, which is the port plan's rule
// for every declaration the Python reads from a file. That makes this package
// depend on a path under packages/, which is named in the report as a seam
// rather than hidden: the better home is the questionnaire itself, beside the
// unit and the range styling_metadata.phc already carries.
type SpokenFields map[string][]string

// LoadSpoken reads packages/voice/src/spoken.json, relative to root.
//
// Loud on failure, for guard step 1's reason reaching back to startup: a
// planner that silently lost its field vocabulary still answers, and what it
// answers is a thinner payload that reads as the utterance not having said
// the value. An empty map is not a safe default here, it is a quiet one.
func LoadSpoken(root string) (SpokenFields, error) {
	path := filepath.Join(root, "packages", "voice", "src", "spoken.json")
	blob, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("the spoken field names did not load: %w", err)
	}
	var out SpokenFields
	if err := json.Unmarshal(blob, &out); err != nil {
		return nil, fmt.Errorf("%s is not a JSON object of link_id to names: %w", path, err)
	}
	return out, nil
}

var notWord = regexp.MustCompile(`[^a-z0-9]+`)

// textWords is agent/planner.py's _words: lowercase, split on anything that is
// not a letter or a digit, and drop the stopwords and the empties.
func textWords(text string) []string {
	out := []string{}
	for _, w := range notWord.Split(strings.ToLower(text), -1) {
		if w != "" && !stop[w] {
			out = append(out, w)
		}
	}
	return out
}

// Keywords is the vocabulary of one operation, weighted. Derived from the
// compiled catalogue so a new atom is routable the moment it lints.
func Keywords(op carephc.Operation) map[string]int {
	weights := map[string]int{}
	add := func(text string, weight int) {
		for _, w := range textWords(text) {
			if weights[w] < weight {
				weights[w] = weight
			}
		}
	}
	// The last dotted segment of the id, which is agent/planner.py's
	// op["id"].rsplit(".", 1)[-1].
	id := op.ID
	if i := strings.LastIndex(id, "."); i >= 0 {
		id = id[i+1:]
	}
	add(id, strong)
	add(strings.ReplaceAll(op.Capability, ".", " "), strong)
	add(op.Short, strong)
	for _, w := range spoken[op.ID] {
		weights[w] = strong
	}
	add(op.Title, weak)
	add(op.Summary, weak)
	for _, f := range op.Fields {
		add(f.LinkID, weak)
	}
	return weights
}

// A number next to a field name. Deliberately narrow: digits only. Spoken
// numbers ("one forty") are parsed at the point of capture by packages/voice,
// where the value can be read back on screen before anyone commits it.
const numPattern = `(\d+(?:\.\d+)?)`

var pairRe = regexp.MustCompile(`\b(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b`)

// Between a field's name and its answer: "assessment is X", "history: X",
// "assessment of X", and the bare "assessment X". Matches empty, which is the
// last of those. Anchored with ^ and applied to the remainder of the string,
// because agent/planner.py applies it at one position with re.match(text, pos).
var leadinRe = regexp.MustCompile(`^[\s:=,-]*(?:(?:is|was|are|were|of|reads|shows|says)\b)?[\s:=,-]*`)

// A later field name only ends the clause when it is being used as a label:
// either it is followed by a lead-in ("plan is amlodipine") or it opens a
// fresh clause ("..., examination chest clear"). "history of hypertension" is
// neither, so it stays inside the answer it was said in.
var labelledRe = regexp.MustCompile(`^\s*(?:[:=-]|(?:is|was|are|were)\b)`)

// aliases are the spoken names for one field: its link_id, the distinctive
// words of its label, and the spoken names packages/voice already knew.
// Ambiguous words are dropped by the caller, not resolved.
func (s SpokenFields) aliases(f carephc.Field) map[string]bool {
	out := map[string]bool{strings.ToLower(f.LinkID): true}
	for _, a := range s[f.LinkID] {
		out[strings.ToLower(a)] = true
	}
	for _, w := range textWords(f.Text) {
		if utf8.RuneCountInString(w) > 2 {
			out[w] = true
		}
	}
	return out
}

// span is one occurrence of a word the form owns, in byte offsets into the
// lowercased utterance.
type span struct {
	start, end int
	linkID     string
}

// marks finds every whole-word occurrence of each word, sorted by position.
func marks(text string, from map[string]bool) []span {
	found := []span{}
	for word := range from {
		re, err := regexp.Compile(`\b` + regexp.QuoteMeta(word) + `\b`)
		if err != nil {
			continue
		}
		for _, m := range re.FindAllStringIndex(text, -1) {
			found = append(found, span{start: m[0], end: m[1]})
		}
	}
	sort.Slice(found, func(i, j int) bool {
		if found[i].start != found[j].start {
			return found[i].start < found[j].start
		}
		return found[i].end < found[j].end
	})
	return found
}

// isLabel is agent/planner.py's _is_label.
func isLabel(text string, start, end int) bool {
	before := strings.TrimRight(text[:start], " \t\n\r\v\f")
	if labelledRe.MatchString(text[end:]) {
		return true
	}
	if before == "" {
		return true
	}
	last := before[len(before)-1]
	return last == ',' || last == '.' || last == ';'
}

// runeIndex maps a byte offset in text to the rune offset agent/planner.py
// would have used, so a slice taken at a regex's offsets lands on the same
// characters whichever string it is taken from. Python indexes a string by
// code point; Go's regexp answers in bytes, and outside ASCII the two are not
// the same number.
func runeIndex(text string) map[int]int {
	out := map[int]int{}
	n := 0
	for at := range text {
		out[at] = n
		n++
	}
	out[len(text)] = n
	return out
}

// clauses are the text answers, sliced out of the utterance by the words
// themselves. agent/planner.py's _clauses.
//
// A field's own name marks where its answer starts; the answer runs to the end
// of what was said, or to the next word the form owns that is being used as a
// label, whichever comes first. Nothing is invented: every character returned
// was spoken.
//
// Two vocabularies, deliberately different sizes. Only an unambiguous field
// name may START a clause, because starting one is a claim about which field
// the words belong to. Anything the operation declares may END one: an
// ambiguous field name, a numeric field's name, a declared answer option.
// Ending a clause early only ever gives a person less to correct.
//
// One clause per field, first mention wins, and a declared word that opens a
// clause of its own always ends the one before it, so "history: pain, plan to
// come back" ends the history at "pain".
func (s SpokenFields) clauses(fields []carephc.Field, unique map[string]string,
	text, utterance string) map[string]string {

	owned := map[string]bool{}
	for _, f := range fields {
		for a := range s.aliases(f) {
			owned[a] = true
		}
		for _, option := range f.Options {
			for _, w := range notWord.Split(strings.ToLower(option), -1) {
				if w != "" {
					owned[w] = true
				}
			}
		}
	}
	ends := marks(text, owned)

	starts := []span{}
	for alias, linkID := range unique {
		for _, m := range marks(text, map[string]bool{alias: true}) {
			starts = append(starts, span{start: m.start, end: m.end, linkID: linkID})
		}
	}
	sort.Slice(starts, func(i, j int) bool {
		if starts[i].start != starts[j].start {
			return starts[i].start < starts[j].start
		}
		if starts[i].end != starts[j].end {
			return starts[i].end < starts[j].end
		}
		return starts[i].linkID < starts[j].linkID
	})

	// Which string the value is cut from, and the index map that makes the cut
	// land on the same characters. agent/planner.py keeps the ORIGINAL case
	// when the fold did not change the width, and only then.
	at := runeIndex(text)
	srcRunes := []rune(utterance)
	if utf8.RuneCountInString(text) != utf8.RuneCountInString(utterance) {
		srcRunes = []rune(text)
	}
	cut := func(begin, stop int) string {
		b, okB := at[begin]
		e, okE := at[stop]
		if !okB || !okE || b > e || e > len(srcRunes) {
			return ""
		}
		return string(srcRunes[b:e])
	}

	out := map[string]string{}
	claimed := [][2]int{}
	for _, s0 := range starts {
		// A name said inside somebody else's answer is part of that answer,
		// not a label of its own: "assessment of history of asthma" is one
		// clause, and the history in it is not a second.
		if _, already := out[s0.linkID]; already {
			continue
		}
		inside := false
		for _, c := range claimed {
			if c[0] <= s0.start && s0.start < c[1] {
				inside = true
				break
			}
		}
		if inside {
			continue
		}
		begin := s0.end + len(leadinRe.FindString(text[s0.end:]))
		stop := len(text)
		for _, other := range ends {
			if other.start >= begin && isLabel(text, other.start, other.end) {
				stop = other.start
				break
			}
		}
		value := strings.Trim(cut(begin, stop), " \t\n.,;:-")
		if utf8.RuneCountInString(value) > 1 {
			out[s0.linkID] = value
			claimed = append(claimed, [2]int{begin, stop})
		}
	}
	return out
}

// choice is one declared answer_option, or a question. Never a guess.
//
// Matched against the values the questionnaire declares, so "venous blood"
// finds "venous-blood" and nothing has to be spelled with a hyphen out loud.
// When two options fit the words equally well the pair is named and asked
// about, because picking one of them is exactly the kind of quiet decision
// this whole system exists to refuse.
func choice(f carephc.Field, text string) (string, string) {
	type opt struct {
		name  string
		words []string
	}
	opts := make([]opt, 0, len(f.Options))
	for _, o := range f.Options {
		ws := []string{}
		for _, w := range notWord.Split(strings.ToLower(o), -1) {
			if w != "" {
				ws = append(ws, w)
			}
		}
		opts = append(opts, opt{name: o, words: ws})
	}
	fits := []string{}
	for _, o := range opts {
		if len(o.words) == 0 {
			continue
		}
		parts := make([]string, 0, len(o.words))
		for _, w := range o.words {
			parts = append(parts, regexp.QuoteMeta(w))
		}
		re, err := regexp.Compile(`\b` + strings.Join(parts, `\W+`) + `\b`)
		if err == nil && re.MatchString(text) {
			fits = append(fits, o.name)
		}
	}
	if len(fits) == 0 {
		// No whole option was said. A single word of one, and only one, option
		// is still the option; a word two of them share is a question.
		for _, o := range opts {
			for _, w := range o.words {
				if stop[w] {
					continue
				}
				re, err := regexp.Compile(`\b` + regexp.QuoteMeta(w) + `\b`)
				if err == nil && re.MatchString(text) {
					fits = append(fits, o.name)
					break
				}
			}
		}
	}
	if len(fits) == 1 {
		return fits[0], ""
	}
	if len(fits) > 1 {
		return "", fmt.Sprintf("Which did you mean for %s: %s?",
			f.Text, strings.Join(fits[:len(fits)-1], ", ")+" or "+fits[len(fits)-1])
	}
	return "", ""
}

// Extract fills in only what is unambiguous, and returns the payload with the
// questions it would not answer for itself.
//
// A thin payload is the normal outcome and the correct one: the rest is typed
// at the rendered surface, and the guard denies a proposal that is missing a
// required answer rather than the planner inventing one. Nothing here writes a
// value the utterance did not contain, in any of the four shapes it reads: the
// blood pressure pair, a number beside a field name, a declared choice, and a
// text clause introduced by the field's own name.
func (s SpokenFields) Extract(op carephc.Operation, utterance string) (map[string]any, []string) {
	low := strings.ToLower(utterance)
	if utf8.RuneCountInString(low) != utf8.RuneCountInString(utterance) {
		// A case fold that changed the width would misalign every text slice.
		utterance = low
	}
	text := low
	payload := map[string]any{}
	asks := []string{}

	// Typed() strips override_reason before the guard ever sees it, so this
	// planner can never answer it. A field it cannot answer should not be
	// taking alias words off the fields it can: "Reason for accepting a value
	// outside the plausible band" was quietly making "value" ambiguous.
	fields := []carephc.Field{}
	ids := map[string]bool{}
	for _, f := range op.Fields {
		if f.LinkID == "override_reason" {
			continue
		}
		fields = append(fields, f)
		ids[f.LinkID] = true
	}

	// "140/90" and "140 over 90", the way blood pressure is actually said.
	if m := pairRe.FindStringSubmatchIndex(text); m != nil && ids["systolic"] && ids["diastolic"] {
		systolic, _ := strconv.Atoi(text[m[2]:m[3]])
		diastolic, _ := strconv.Atoi(text[m[4]:m[5]])
		payload["systolic"] = systolic
		payload["diastolic"] = diastolic
		// Blanked in place rather than cut out, so the offsets a text clause
		// is sliced with still line up with the utterance.
		text = text[:m[0]] + strings.Repeat(" ", m[1]-m[0]) + text[m[1]:]
	}

	// A word that names more than one field names none of them.
	seen := map[string][]string{}
	for _, f := range fields {
		for alias := range s.aliases(f) {
			seen[alias] = append(seen[alias], f.LinkID)
		}
	}
	unique := map[string]string{}
	for alias, names := range seen {
		if len(names) == 1 {
			unique[alias] = names[0]
		}
	}
	clauses := s.clauses(fields, unique, text, utterance)

	for _, f := range fields {
		if _, done := payload[f.LinkID]; done {
			continue
		}
		names := []string{}
		for a := range s.aliases(f) {
			if unique[a] == f.LinkID {
				names = append(names, a)
			}
		}
		sort.Strings(names)
		switch {
		case (f.Type == "integer" || f.Type == "decimal") && len(names) > 0:
			alt := make([]string, 0, len(names))
			for _, n := range names {
				alt = append(alt, regexp.QuoteMeta(n))
			}
			re, err := regexp.Compile(`\b(?:` + strings.Join(alt, "|") + `)\b\D{0,12}` + numPattern)
			if err != nil {
				continue
			}
			if m := re.FindStringSubmatch(text); m != nil {
				value, _ := strconv.ParseFloat(m[1], 64)
				if f.Type == "integer" {
					payload[f.LinkID] = int(value)
				} else {
					// A decimal field keeps a float in agent/planner.py, and
					// json.dumps writes float(37) as "37.0" where Go writes
					// float64(37) as "37". pyval already spells a Python
					// float; the value is carried as those digits so the two
					// engines put the same bytes on the wire.
					payload[f.LinkID] = json.Number(pyval.FloatStr(value))
				}
			}
		case f.Type == "choice" && len(f.Options) > 0:
			value, ask := choice(f, text)
			if value != "" {
				payload[f.LinkID] = value
			} else if ask != "" {
				asks = append(asks, ask)
			}
		case f.Type == "text" || f.Type == "string":
			if value, found := clauses[f.LinkID]; found {
				payload[f.LinkID] = value
			}
		}
	}
	return payload, asks
}

// Typed keeps only the answers the operation actually declares.
//
// The validator ignores a key it does not know, which means an invented key
// rides along into the proposal a person then taps. Two of those are dangerous
// rather than untidy: override_reason waives the physiological range check,
// and any stray key is a value nobody typed. So a planner may answer the
// questions the questionnaire asks and nothing else. A person can still
// override at the rendered surface, by writing the reason themselves.
func Typed(op carephc.Operation, payload map[string]any) map[string]any {
	allowed := map[string]bool{}
	for _, f := range op.Fields {
		if f.LinkID != "override_reason" {
			allowed[f.LinkID] = true
		}
	}
	out := map[string]any{}
	for k, v := range payload {
		if allowed[k] {
			out[k] = v
		}
	}
	return out
}

// Route matches an utterance to operations, using only the compiled
// catalogue.
//
// Needs at least two points before it will name an operation, so a single
// incidental word does not conjure a proposal out of small talk.
func (s SpokenFields) Route(utterance string, ops map[string]carephc.Operation, limit int) []Proposed {
	said := map[string]bool{}
	for _, w := range textWords(utterance) {
		said[w] = true
	}
	scored := []Proposed{}
	for _, id := range carephc.SortedOperationIDs(ops) {
		op := ops[id]
		kws := Keywords(op)
		hits := []string{}
		score := 0
		for w := range said {
			if weight, found := kws[w]; found {
				hits = append(hits, w)
				score += weight
			}
		}
		if score < strong {
			continue
		}
		sort.Strings(hits)
		payload, ask := s.Extract(op, utterance)
		scored = append(scored, Proposed{
			Operation: op.ID,
			Payload:   payload,
			Why:       "matched " + strings.Join(hits, ", "),
			Backend:   "router",
			Score:     score,
			Ask:       ask,
		})
	}
	sort.SliceStable(scored, func(i, j int) bool {
		if scored[i].Score != scored[j].Score {
			return scored[i].Score > scored[j].Score
		}
		return scored[i].Operation < scored[j].Operation
	})
	if limit > 0 && len(scored) > limit {
		scored = scored[:limit]
	}
	return scored
}

// Backend answers which planner is live, exactly where agent/planner.py's
// backend() does. The key is the switch; there is nothing to config.
func Backend() string {
	if os.Getenv("ANTHROPIC_API_KEY") != "" {
		return "llm"
	}
	return "router"
}

// NoLLM is what Plan answers for the backend this engine does not have. Said
// as a sentence rather than a silent fall back to the router, because falling
// back would report a backend that did not plan.
const NoLLM = "the Go backend has no llm planner: agent/planner.py's llm() is " +
	"the anthropic SDK on claude-opus-5, and this engine makes no network call " +
	"and takes no SDK. Ask for the router backend, or run this with " +
	"PHC_BACKEND=python, which is the default."

// Plan is the one interface. It returns Proposed, never a decision and never a
// write.
func (s SpokenFields) Plan(utterance string, ops map[string]carephc.Operation, which string) ([]Proposed, error) {
	if which == "" {
		which = Backend()
	}
	if which == "llm" {
		return nil, fmt.Errorf("%s", NoLLM)
	}
	return s.Route(utterance, ops, 3), nil
}

// ByKernelOrder sorts a plan into the order the kernel already put its actions
// in.
//
// ThreadView.Actions is kstate's Actions(): visible operations sorted by this
// thread's current station and then by the declared line. That is the
// ordering, and it is not this package's to have an opinion about. Route()
// scores how well an utterance names an operation, which is a different
// question; that score decides what was heard, never what to do next.
//
// An operation the kernel does not list here sorts last and is still sent, so
// the guard gets to state the refusal rather than the agent guessing it.
func ByKernelOrder(proposals []Proposed, actions []map[string]any) []Proposed {
	rank := map[string]int{}
	for i, a := range actions {
		if id, ok := a["id"].(string); ok {
			rank[id] = i
		}
	}
	place := func(p Proposed) int {
		if i, found := rank[p.Operation]; found {
			return i
		}
		return len(rank)
	}
	out := append([]Proposed(nil), proposals...)
	sort.SliceStable(out, func(i, j int) bool {
		if place(out[i]) != place(out[j]) {
			return place(out[i]) < place(out[j])
		}
		return out[i].Operation < out[j].Operation
	})
	return out
}

// ExplainOrder is one sentence about where the kernel puts this, sourced from
// the kernel.
func ExplainOrder(p Proposed, actions []map[string]any, station any) string {
	ids := make([]string, 0, len(actions))
	for _, a := range actions {
		id, _ := a["id"].(string)
		ids = append(ids, id)
	}
	at := -1
	for i, id := range ids {
		if id == p.Operation {
			at = i
			break
		}
	}
	if at < 0 {
		where := ""
		if text, ok := station.(string); ok && text != "" {
			where = fmt.Sprintf(" (it is standing at %s)", text)
		}
		return "the kernel does not offer this on this thread now" + where
	}
	seat, _ := actions[at]["station"].(string)
	return fmt.Sprintf("the kernel lists it %d of %d at %s", at+1, len(ids), seat)
}
