// One conversational turn, with no I/O in it. The Go half of agent/turn.py.
//
// An utterance comes in, a list of proposal cards goes out, and in between
// this file does exactly three things: ask a planner what was heard, sort the
// answer into the order the KERNEL already put this thread's actions in, and
// hand each operation to a Propose func. It never decides anything. It cannot
// write: the only func it is given is Propose, and the caller that supplies it
// (cmd/api) supplies the proposals package's Propose on guard.MCP, which hard
// codes the machine surface where a write can only ever come back "proposed".
//
// Why a file of its own and not the route: the route is a shell around a
// store, and this is the part worth checking without a socket.
//
// Honest about the confidence map. Nothing here recognises speech. A caller
// that dictated the utterance passes the recogniser's per-field confidence
// along (packages/voice emits exactly that shape, link_id -> 0..1) and this
// carries it to the card so the renderer can mark those fields unsure. A
// typed utterance has no confidences and the map is empty, which is the truth
// rather than a 1.0 nobody measured.
package planner

import (
	"encoding/json"
	"fmt"
	"strings"

	carephc "github.com/eka-care/care_phc_mcp"
)

// Unsure is what the planner says instead of guessing.
const Unsure = "I do not know which operation that is, and I will not guess: a " +
	"wrong proposal in front of a busy clinician is worse than none."

// preconditionNext is what to do next, for a precondition denial. Keyed by the
// guard's own machine-stable classification (PreconditionKind), never by the
// clerk sentence it writes: those sentences are exactly what a copy pass
// rewords, and a string match on them would degrade silently to nextOtherwise
// the moment the wording changed.
var preconditionNext = map[string]string{
	// A separation of duties rule is about WHO, not about the visit, so it
	// gets its own half sentence.
	"actor_negated": "Somebody else has to do this one. Whoever did the step it names cannot " +
		"also do this, whatever capabilities they hold.",
	"actor_required": "Only the person who did the step it names may do this one.",
	"unevaluable": "Nobody said who is acting here, and the kernel will not guess on a " +
		"rule about who did what.",
	// Both polarities of a plain flag precondition ("Already registered." and
	// "Requires rx confirmed.") get the same half sentence: it must be true of
	// either, so it claims no order of its own.
	"flag_negated": "The state of this visit does not satisfy that. " +
		"The kernel decides what is open here, not me.",
	"flag_required": "The state of this visit does not satisfy that. " +
		"The kernel decides what is open here, not me.",
}

// next is everything else the guard can deny on: no precondition kind travels
// with these (only a precondition denial gets one), so they are still keyed by
// the shape of the guard's own reason string. None of these are the
// clerk-facing precondition sentences a copy pass is about to touch.
var nextAdvice = []struct{ prefix, advice string }{
	{"payload invalid", "Open the form on screen and fill in the rest. I only " +
		"fill what the words actually said."},
	{"missing capability", "This account does not hold that capability. " +
		"Someone who does has to do it."},
	{"outside scope", "That is outside this account's scope of practice."},
	{"irreversible", "Irreversible work is done on screen with an explicit tap. " +
		"I cannot propose it, and that is deliberate."},
	{"not a step of", "This line has no station that draws it, so it cannot " +
		"happen on this visit at all."},
}

const nextOtherwise = "Open it on screen if it should still happen."

// NextStep dispatches on the guard's machine-stable kind before it ever looks
// at the reason string, so a copy pass over the guard's sentences cannot
// silently change the advice.
func NextStep(reason, kind string) string {
	if advice, found := preconditionNext[kind]; found {
		return advice
	}
	for _, n := range nextAdvice {
		if strings.Contains(reason, n.prefix) {
			return n.advice
		}
	}
	return nextOtherwise
}

// HeardWith is the recogniser's confidence for answers that actually made the
// payload.
//
// A trust boundary: a caller that sends anything other than a map of link_id
// to number gets no confidences rather than a 500, and a confidence for a
// field nobody filled is dropped rather than drawn against nothing.
func HeardWith(confidence any, payload map[string]any) map[string]any {
	out := map[string]any{}
	asMap, ok := confidence.(map[string]any)
	if !ok {
		return out
	}
	for k, v := range asMap {
		if _, filled := payload[k]; !filled {
			continue
		}
		// A number and nothing else is a confidence. The route decodes a body
		// with pyval, which keeps a number as json.Number rather than
		// narrowing it to a float64, so the digits the caller sent are the
		// digits that reach the card: 0.8 does not become 0.8000000000000001
		// on the way through. A bool is not a number here, which is
		// agent/turn.py's own exclusion and is what Go's type switch already
		// gives.
		switch number := v.(type) {
		case json.Number:
			out[k] = number
		case float64:
			out[k] = number
		case int:
			out[k] = number
		}
	}
	return out
}

// Verdict is one card's verdict: the guard's words, unedited, and what to do
// next. Paraphrasing a refusal is how an agent starts inventing policy.
type Verdict struct {
	Allowed bool   `json:"allowed"`
	Reason  string `json:"reason"`
	Next    string `json:"next"`
}

// Decision is what a Propose func answers: the proposal's id when the guard
// allowed it, the guard's reason, the flags the proposal raised, and the
// guard's machine-stable precondition kind ("" for a denial that is not a
// precondition, and for an allow).
type Decision struct {
	ProposalID  string
	Reason      string
	FlagsRaised []string
	Kind        string
	Allowed     bool
}

// Propose is the only thing here that touches a store, injected so a turn runs
// without one. There is no second func and there must not be: a confirm
// argument would be a hole a sentence could reach.
type Propose func(operation string, payload map[string]any) (Decision, error)

// Answer is the whole turn, as the route hands it back.
type Answer struct {
	Said       string           `json:"said"`
	Backend    string           `json:"backend"`
	Understood bool             `json:"understood"`
	Proposals  []map[string]any `json:"proposals"`
}

// card is everything the thread needs to draw one proposal, and nothing it has
// to compute. `order` is the kernel's ordering explained, never an opinion.
func card(op carephc.Operation, p Proposed, decision Decision,
	actions []map[string]any, station any, confidence any) map[string]any {

	allowed := decision.ProposalID != ""
	offered := false
	var seat any
	for _, a := range actions {
		if id, _ := a["id"].(string); id == op.ID {
			offered = true
			if text, ok := a["station"].(string); ok {
				seat = text
			}
			break
		}
	}
	var proposalID any
	if allowed {
		proposalID = decision.ProposalID
	}
	var instrument any
	if op.Instrument != "" {
		instrument = op.Instrument
	}
	next := ""
	if !allowed {
		next = NextStep(decision.Reason, decision.Kind)
	}
	flags := decision.FlagsRaised
	if flags == nil {
		flags = []string{}
	}
	ask := p.Ask
	if ask == nil {
		ask = []string{}
	}
	return map[string]any{
		"proposal_id":     proposalID,
		"operation":       op.ID,
		"title":           op.Title,
		"instrument":      instrument,
		"irreversibility": op.Irreversibility,
		// Keyed by link_id, so the renderer can label each answer with the
		// questionnaire's own question text.
		"payload":    p.Payload,
		"confidence": HeardWith(confidence, p.Payload),
		"heard":      p.Why,
		// What the planner heard and would not resolve. Empty is the usual
		// case; a question here is the alternative to a guess, not to a
		// refusal.
		"ask": ask,
		"verdict": Verdict{
			Allowed: allowed,
			Reason:  decision.Reason,
			Next:    next,
		},
		"flags_raised": flags,
		"station":      seat,
		// The kernel does not offer it here: a card the renderer should draw
		// as superseded rather than as work.
		"offered_here": offered,
		"order":        ExplainOrder(p, actions, station),
	}
}

func waitingFor(actions []map[string]any) string {
	if len(actions) == 0 {
		return "Nothing on this visit is open to you right now."
	}
	titles := []string{}
	for _, a := range actions {
		if len(titles) == 5 {
			break
		}
		title, _ := a["title"].(string)
		titles = append(titles, title)
	}
	return "Open to you here: " + strings.Join(titles, ", ") + "."
}

// say is the reply, composed from what the guard said. No clinical prose.
func say(cards []map[string]any, actions []map[string]any) string {
	if len(cards) == 0 {
		return Unsure + " " + waitingFor(actions)
	}
	lines := []string{}
	for _, c := range cards {
		verdict := c["verdict"].(Verdict)
		title, _ := c["title"].(string)
		if verdict.Allowed {
			lines = append(lines, fmt.Sprintf("Proposed %s for you to confirm.", title))
		} else {
			// The guard's reason sometimes ends in a full stop of its own.
			lines = append(lines, fmt.Sprintf("%s was refused: %s. %s",
				title, strings.TrimRight(verdict.Reason, ". "), verdict.Next))
		}
	}
	// A question the planner would not answer for itself, asked out loud.
	for _, c := range cards {
		if asks, ok := c["ask"].([]string); ok {
			lines = append(lines, asks...)
		}
	}
	// No "nothing is recorded until you confirm" line: the card under this
	// sentence carries the confirm control, and it said so the last five times.
	return strings.Join(lines, " ")
}

// Take plans, orders by the kernel, proposes each, and reports every verdict.
//
// Every operation the planner named is sent, including one the kernel does not
// currently offer, because the refusal is the guard's to state and an agent
// that pre-filters is an agent quietly making clinical decisions.
func (s SpokenFields) Take(utterance string, ops map[string]carephc.Operation,
	view *kernelView, propose Propose, confidence any, which string) (Answer, error) {

	if which == "" {
		which = Backend()
	}
	actions := view.Actions
	if actions == nil {
		actions = []map[string]any{}
	}
	if strings.TrimSpace(utterance) == "" {
		return Answer{Said: "Say what you want recorded.", Backend: which,
			Understood: false, Proposals: []map[string]any{}}, nil
	}
	plan, err := s.Plan(utterance, ops, which)
	if err != nil {
		// Say which planner failed and stop. Falling back to the other backend
		// silently would hide which one produced what.
		return Answer{
			Said: fmt.Sprintf("The %s planner failed: %s", which, err),
			Backend: which, Understood: false,
			Proposals: []map[string]any{}}, nil
	}

	cards := []map[string]any{}
	for _, p := range ByKernelOrder(plan, actions) {
		op, declared := ops[p.Operation]
		if !declared {
			continue
		}
		// The trust boundary, again, at the last moment before the guard: a
		// planner answers the questionnaire's own questions and nothing else,
		// and never override_reason. A model must not grant itself an
		// override.
		p.Payload = Typed(op, p.Payload)
		decision, err := propose(p.Operation, p.Payload)
		if err != nil {
			return Answer{}, err
		}
		cards = append(cards, card(op, p, decision, actions, view.Station, confidence))
	}
	return Answer{Said: say(cards, actions), Backend: which,
		Understood: len(cards) > 0, Proposals: cards}, nil
}

// kernelView is the part of a thread view a turn reads: the kernel's own
// ordering of what is open here, and where the thread is standing. Declared as
// its own type so this file depends on no store and no socket.
type kernelView struct {
	Actions []map[string]any
	Station any
}

// View is the thread view a turn reads, built by the caller from the kernel's
// own ThreadView.
func View(actions []map[string]any, station any) *kernelView {
	return &kernelView{Actions: actions, Station: station}
}
