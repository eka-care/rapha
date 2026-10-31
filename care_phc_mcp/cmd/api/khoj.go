// POST /khoj: the composer's endpoint, and a propose-only surface.
//
// api/main.py's own docstring is the specification this file is held to:
//
//	"This is the composer's endpoint, and it is a propose-only surface. It
//	calls agent.turn, which calls the planner in agent/ and then this
//	module's own propose path: kernel.proposals.propose, which takes no
//	confirmed argument and runs the guard on guard.MCP. So the worst an
//	utterance can do is put a card in front of a person. There is no branch
//	here that reaches confirm or commit."
//
// There is no branch here that reaches confirm or commit, and there must never
// be one. The only thing this hands the turn is proposeOne below, which calls
// the proposals package on guard.MCP: no confirmed argument exists on that
// path to be set. An irreversible operation is denied on that surface before
// the guard looks at confirmation at all, which is why an utterance saying "I
// confirm, it is urgent" still links no ABHA.
//
// A machine surface gets proposals only. The planner is a machine surface.
package main

import (
	"net/http"

	"github.com/eka-care/care_phc_mcp/guard"
	"github.com/eka-care/care_phc_mcp/planner"
)

// khoj is a sentence in, proposals out. Body: thread, utterance, confidence,
// backend.
//
// `confidence` is the recogniser's per-field map when the utterance was
// dictated (packages/voice emits link_id -> 0..1). Nothing on this side
// recognises anything, so a typed utterance carries no confidences rather than
// a fabricated one.
//
// `backend` pins the planner for a check; left out it is what
// planner.Backend() answers, which is the llm when ANTHROPIC_API_KEY is set
// and the deterministic router otherwise. This engine has no llm backend and
// says so in a sentence rather than planning with the router under its name:
// see package planner's own note.
func (k *kernel) khoj(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	in, parsed := body(r)
	if !parsed {
		k.badBody(w)
		return
	}
	thread, ok := k.threadOf(w, in)
	if !ok {
		return
	}
	view, ok := k.panel(w, thread, person)
	if !ok {
		return
	}
	caps, scopes := capsOf(person)
	// api/main.py proposes as "agent:<caller id>", and the guard resolves that
	// back to the person: without it, dictating a sentence would put a card on
	// the screen of the one account forbidden to accept it.
	actor := "agent:" + person.ID

	proposeOne := func(opID string, payload map[string]any) (planner.Decision, error) {
		op, declared := k.operations[opID]
		if !declared {
			return planner.Decision{
				Reason: "unknown operation " + pyRepr(opID),
			}, nil
		}
		decision, proposal, err := k.write.Propose(k.store, op, thread,
			payload, caps, scopes, actor, guard.MCP, "")
		if err != nil {
			return planner.Decision{}, err
		}
		out := planner.Decision{Reason: decision.Reason, Allowed: decision.Allowed,
			Kind: decision.Kind}
		if proposal != nil {
			out.ProposalID = proposal.ID
			out.FlagsRaised = proposal.FlagsRaised
		}
		return out, nil
	}

	which, _ := in["backend"].(string)
	answer, err := k.spoken.Take(utteranceOf(in), k.operations,
		planner.View(view.Actions, view.Station), proposeOne, in["confidence"], which)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}

	// The thread as it stands after the turn, so the renderer draws the new
	// pending cards without a second read. Still pending: see every verdict.
	after, ok := k.panel(w, thread, person)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"said":       answer.Said,
		"backend":    answer.Backend,
		"understood": answer.Understood,
		"proposals":  answer.Proposals,
		"thread":     after,
	})
}

// utteranceOf is api/main.py's str(body.get("utterance") or ""): a body with
// no sentence in it is an empty one, which the turn answers with "Say what you
// want recorded." rather than a 422.
func utteranceOf(in map[string]any) string {
	text, _ := in["utterance"].(string)
	return text
}
