// The write path's routes: the shells api/main.py's own docstring says they
// are.
//
// "Every route here is a shell. The decision is kernel/proposals.py, which is
// catalogue.guard.evaluate; the thread is kernel/state.py; the rows are
// adapters/local. This module parses a request, checks the caller's
// capability to open a view, and turns a Decision into a status code. There is
// no clinical logic in it and there must never be any."
//
// That rule is why this file is short and must stay short. Two routes reach
// the store and both go through package proposals, which hard codes the
// rendered surface:
//
//	POST /operations/{op}/commit    a person tapped commit
//	POST /operations/{op}/amend     a person corrected what was kept
//	POST /proposals/{id}/confirm    a person accepted a machine's proposal
//
// Propose writes a proposal and an audit line and no clinical row. Confirm
// refuses an id propose never issued (404) and a proposal that is not pending
// (409), so a double tap, a retry or a replayed request cannot write twice.
//
// Voice never appears here, which is the point: an instrument produces a
// draft in the renderer, a person reads it back on screen and taps, and the
// tap arrives as an ordinary commit through the same validator as the keypad.
package main

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/guard"
	"github.com/eka-care/care_phc_mcp/kstate"
	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/store"
	"github.com/eka-care/care_phc_mcp/tokens"
)

// body reads the request's JSON object, which FastAPI's `Body(default={})`
// makes optional. Numbers are kept as json.Number: the difference between the
// integer 140 and the float 140.0 is visible in a denial sentence.
func body(r *http.Request) (map[string]any, bool) {
	raw, err := io.ReadAll(io.LimitReader(r.Body, 8<<20))
	if err != nil {
		return nil, false
	}
	if len(strings.TrimSpace(string(raw))) == 0 {
		return map[string]any{}, true
	}
	out := map[string]any{}
	if err := pyval.Decode(raw, &out); err != nil {
		return nil, false
	}
	return out, true
}

// payloadOf is `body.get("payload") or {}`.
func payloadOf(in map[string]any) map[string]any {
	out, ok := in["payload"].(map[string]any)
	if !ok || len(out) == 0 {
		return map[string]any{}
	}
	return out
}

func truthy(v any) bool {
	switch t := v.(type) {
	case bool:
		return t
	case string:
		return t != ""
	case json.Number:
		f, ok := pyval.AsFloat(t)
		return ok && f != 0
	case []any:
		return len(t) > 0
	case map[string]any:
		return len(t) > 0
	}
	return false
}

// who answers the caller, or writes api/main.py's own 400 for a role the
// bundle does not declare.
func (k *kernel) who(w http.ResponseWriter, r *http.Request) (user, bool) {
	person, refused := k.caller(r)
	if refused != "" {
		detail(w, http.StatusBadRequest, "no such role %s", pyRepr(refused))
		return user{}, false
	}
	return person, true
}

func capsOf(person user) (map[string]bool, map[string]bool) {
	caps := map[string]bool{}
	for _, c := range person.Capabilities {
		caps[c] = true
	}
	scopes := map[string]bool{}
	for _, c := range person.Scopes {
		scopes[c] = true
	}
	return caps, scopes
}

// operationOr404 is api/main.py's operation_or_404.
func (k *kernel) operationOr404(w http.ResponseWriter, opID string) (carephc.Operation, bool) {
	op, declared := k.operations[opID]
	if !declared {
		detail(w, http.StatusNotFound, "unknown operation %s", pyval.Repr(opID))
		return carephc.Operation{}, false
	}
	return op, true
}

// refOr404 is api/main.py's ref_or_404: the thread, with the subject fields a
// view or a panel may show.
func (k *kernel) refOr404(w http.ResponseWriter, thread string) (store.ThreadRef, map[string]any, bool) {
	rows, err := k.store.SelectNullable("encounter", &thread, nil, nil, 1)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return store.ThreadRef{}, nil, false
	}
	if len(rows) == 0 {
		detail(w, http.StatusNotFound, "no such thread %s", pyval.Repr(thread))
		return store.ThreadRef{}, nil, false
	}
	subject := map[string]any{
		"encounter": thread,
		"token":     rows[0]["token"],
		"status":    rows[0]["status"],
		// How the person reached the queue. Carried here as well as on
		// Threads, because a panel and a queue row describe the same visit and
		// a field on one and not the other is the two engines disagreeing
		// about what a subject is.
		"arrival": rows[0]["arrival"],
	}
	patient, err := k.store.SelectNullable("patient", &thread, nil, nil, 1)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return store.ThreadRef{}, nil, false
	}
	if len(patient) > 0 {
		for key, value := range patient[0] {
			// WITHOUT `operation`, for the reason store.Threads gives at
			// the other place a subject is built: it is which form opened
			// the row, so a correction can find it, and it is not a fact
			// about the person. It reached the context rail as a line
			// reading "Operation: phc.op.patient-register" beside
			// somebody's village, which is our schema shown to a clinician.
			if key == "operation" {
				continue
			}
			subject[key] = value
		}
	}
	openedAt, _ := rows[0]["created_date"].(string)
	return store.ThreadRef{ID: thread, Workflow: k.workflow, OpenedAt: openedAt},
		subject, true
}

// panel is api/main.py's panel(): the thread view, plus the one line of
// wayfinding the renderer may ignore.
//
// The caller's id and not just their capabilities: an action whose
// precondition names an actor ("not actor of lab.op.result-enter") is then
// ABSENT for the person it excludes rather than drawn and refused on the tap.
func (k *kernel) panel(w http.ResponseWriter, thread string, person user) (*kstate.ThreadView, bool) {
	ref, subject, ok := k.refOr404(w, thread)
	if !ok {
		return nil, false
	}
	caps, _ := capsOf(person)
	view, err := kstate.View(k.store, ref, k.cat.Workflow, k.operations,
		k.cat.ActionJSON, caps, k.caps, true, person.ID, "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return nil, false
	}
	view.Subject = subject
	view.Nudge = kstate.Nudge(view)
	return view, true
}

// threadOf is api/main.py's thread_of: the MCP server sends `patient`, the
// renderer sends `thread`, and both mean the id of the thread.
func (k *kernel) threadOf(w http.ResponseWriter, in map[string]any) (string, bool) {
	var thread string
	for _, key := range []string{"thread", "encounter", "patient"} {
		if text, ok := in[key].(string); ok && text != "" {
			thread = text
			break
		}
	}
	if thread == "" {
		detail(w, http.StatusBadRequest, "body needs a thread id")
		return "", false
	}
	if _, _, ok := k.refOr404(w, thread); !ok {
		return "", false
	}
	return thread, true
}

// allowedOr422 turns a Decision into a status code. The guard's reason is the
// useful thing to hand back, to a person and to an agent alike.
func allowedOr422(w http.ResponseWriter, decision guard.Decision) bool {
	if !decision.Allowed {
		detail(w, http.StatusUnprocessableEntity, "%s", decision.Reason)
		return false
	}
	return true
}

func (k *kernel) badBody(w http.ResponseWriter) {
	// FastAPI answers 422 for a body it cannot parse, and names the field.
	// One sentence rather than its list, because nothing in this repository
	// reads the list and inventing its shape would be inventing a contract.
	detail(w, http.StatusUnprocessableEntity, "the body is not a JSON object")
}

// ---------------------------------------------------------------- threads

// openThread opens an empty visit, so reception has something to register
// against.
//
// This writes an encounter row and no clinical fact whatsoever: an empty
// thread asserts nothing about a person. Every fact still goes through the
// guard, which is why opening one is not an operation in the catalogue.
//
// THE NUMBER IS ISSUED HERE AND IS NOT THE CALLER'S TO CHOOSE. A token in the
// body is ignored, exactly as api/main.py's own route ignores one, and that is
// the point: a number a client picks is a number nothing else knew it had
// given out, and two clients each picking their own is how one waiting room
// ends up with two people called seven.
//
// Until 2026-11-01 this route read body["token"] and handed it straight to the
// store, which then made one up out of the row id if it was empty. So this
// engine's numbers came from whichever client asked. The sequence rule is
// package tokens and the reservation is Store.IssueToken; the body is not
// consulted about it.
func (k *kernel) openThread(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	if _, parsed := body(r); !parsed {
		k.badBody(w)
		return
	}
	number, err := k.issueToken()
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	thread, err := k.store.OpenThread(number, person.ID)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if view, ok := k.panel(w, thread, person); ok {
		writeJSON(w, http.StatusOK, view)
	}
}

// issueToken is kernel/tokens.issue: the next number for this facility's day,
// as the string a row stores.
//
// A string because that is what the token column holds and what a screen
// draws; the sequence is arithmetic, the token is a label.
//
// Two steps, and only the second one decides. tokens.After reads the rows and
// says the lowest number that would be honest; Store.IssueToken reserves one
// not below it and is the only thing that can say which. A caller racing this
// one may well compute the same floor, and that is not a defect: the store's
// UNIQUE key means exactly one of them inserts it and the rest are incremented
// past it.
func (k *kernel) issueToken() (string, error) {
	refs, err := k.store.Threads(k.workflow, "today")
	if err != nil {
		return "", err
	}
	seen := make([]string, 0, len(refs))
	for _, ref := range refs {
		// The token lives in the subject map, which is where Threads puts it,
		// and a thread with no number contributes an empty string. After()
		// skips it rather than counting it, so a visit with no token spent no
		// number: kernel/tokens.py's own rule.
		text, _ := ref.Subject["token"].(string)
		seen = append(seen, text)
	}
	number, err := k.store.IssueToken(k.workflow, "today", tokens.After(seen))
	if err != nil {
		return "", err
	}
	return strconv.Itoa(number), nil
}

func (k *kernel) getThread(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	if view, ok := k.panel(w, r.PathValue("thread_id"), person); ok {
		writeJSON(w, http.StatusOK, view)
	}
}

// ----------------------------------------------------------------- writes

// propose is guard steps 1 to 4 on the machine surface, then a proposal. No
// write.
//
// An irreversible operation is denied here by design: guard step 4 refuses it
// on any surface but rendered, before it looks at a confirmed flag at all. An
// agent cannot propose an ABHA link, and it should not be able to.
func (k *kernel) propose(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	op, declared := k.operationOr404(w, r.PathValue("op_id"))
	if !declared {
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
	caps, scopes := capsOf(person)
	decision, proposal, err := k.write.Propose(k.store, op, thread,
		payloadOf(in), caps, scopes, person.ID, guard.MCP, "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if !allowedOr422(w, decision) {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"proposal_id":  proposal.ID,
		"status":       decision.Reason,
		"operation":    op.ID,
		"awaiting":     "clinician review on the rendered surface",
		"flags_raised": proposal.FlagsRaised,
		"proposal":     proposal,
	})
}

// commit is a person tapping commit on the rendered surface.
//
// This is also where a voice or scribe draft lands, once it has been read
// back on screen and tapped. By the time it arrives it is indistinguishable
// from typing, and that is exactly the safety property: there is no route by
// which a recognised value reaches the store without a person seeing it.
func (k *kernel) commit(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	op, declared := k.operationOr404(w, r.PathValue("op_id"))
	if !declared {
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
	caps, scopes := capsOf(person)
	decision, err := k.write.Commit(k.store, op, thread, payloadOf(in), caps,
		scopes, person.ID, truthy(in["confirmed"]), "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if !allowedOr422(w, decision) {
		return
	}
	view, ok := k.panel(w, thread, person)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"committed": op.ID, "thread": view})
}

// amend is api/main.py's amend: a person corrected something already
// recorded. Not a second commit -- it REPLACES the rows the same operation
// wrote on this visit instead of adding a contradictory set, and it refuses
// once the visit is over.
func (k *kernel) amend(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	op, declared := k.operationOr404(w, r.PathValue("op_id"))
	if !declared {
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
	caps, scopes := capsOf(person)
	decision, err := k.write.Amend(k.store, op, thread, payloadOf(in), caps,
		scopes, person.ID, truthy(in["confirmed"]), "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if !allowedOr422(w, decision) {
		return
	}
	view, ok := k.panel(w, thread, person)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"amended": op.ID, "thread": view})
}

// proposalOr404 is api/main.py's proposal_or_404.
func (k *kernel) proposalOr404(w http.ResponseWriter, id string) (store.Proposal, bool) {
	found, exists, err := k.store.Proposal(id)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return store.Proposal{}, false
	}
	if !exists {
		detail(w, http.StatusNotFound, "no such proposal %s: confirm only "+
			"accepts an id that propose issued", pyval.Repr(id))
		return store.Proposal{}, false
	}
	return *found, true
}

// getProposal takes no caller, exactly as api/main.py's get_proposal does not.
func (k *kernel) getProposal(w http.ResponseWriter, r *http.Request) {
	if found, ok := k.proposalOr404(w, r.PathValue("proposal_id")); ok {
		writeJSON(w, http.StatusOK, found)
	}
}

// confirm accepts a proposal. Rendered surface only, and once only.
//
// Three refusals, in order: an id propose never issued (404); a proposal that
// is not pending (409, so a replayed request cannot write twice); and
// whatever the guard says now (422), evaluated again against the state as it
// is at this moment and the payload as the person edited it.
func (k *kernel) confirm(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	id := r.PathValue("proposal_id")
	proposal, found := k.proposalOr404(w, id)
	if !found {
		return
	}
	if proposal.Status != "pending" {
		detail(w, http.StatusConflict, "proposal %s is already %s; a proposal "+
			"is confirmed once", id, proposal.Status)
		return
	}
	in, parsed := body(r)
	if !parsed {
		k.badBody(w)
		return
	}
	edited, given := in["payload"].(map[string]any)
	caps, scopes := capsOf(person)
	decision, decided, err := k.write.Confirm(k.store, proposal, caps, scopes,
		person.ID, edited, given, truthy(in["confirmed"]), "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if !allowedOr422(w, decision) {
		return
	}
	view, ok := k.panel(w, proposal.Thread, person)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"proposal": decided, "thread": view})
}

func (k *kernel) reject(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	id := r.PathValue("proposal_id")
	proposal, found := k.proposalOr404(w, id)
	if !found {
		return
	}
	if proposal.Status != "pending" {
		detail(w, http.StatusConflict, "proposal %s is already %s", id, proposal.Status)
		return
	}
	in, parsed := body(r)
	if !parsed {
		k.badBody(w)
		return
	}
	reason, _ := in["reason"].(string)
	decided, err := k.write.Reject(k.store, proposal, person.ID, reason, "")
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	view, ok := k.panel(w, proposal.Thread, person)
	if !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"proposal": decided, "thread": view})
}

// only answers FastAPI's 405 for the wrong verb on a route that exists.
//
// Registered WITHOUT a method in the pattern, deliberately. Go's mux turns a
// method mismatch into a 405 only when no other pattern matches the path, and
// this engine mounts a 404 catch-all under each prefix, so a bare `POST
// /…/threads` pattern made GET /…/threads a 404 where the Python answers 405.
// The verb is checked here instead, which is the same answer by the same
// rule.
func only(method string, next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != method {
			detail(w, http.StatusMethodNotAllowed, "Method Not Allowed")
			return
		}
		next(w, r)
	}
}

// mountGuard registers the write path under both prefixes. Wildcard patterns,
// so the templated routes win over the subtree a sibling 501 mounts and over
// the prefix's own 404 catch-all.
func (k *kernel) mountGuard(mux *http.ServeMux, prefix string) {
	mux.HandleFunc(prefix+"/threads", only(http.MethodPost, k.openThread))
	mux.HandleFunc(prefix+"/threads/{thread_id}", only(http.MethodGet, k.getThread))
	mux.HandleFunc(prefix+"/operations/{op_id}/propose", only(http.MethodPost, k.propose))
	mux.HandleFunc(prefix+"/operations/{op_id}/commit", only(http.MethodPost, k.commit))
	mux.HandleFunc(prefix+"/operations/{op_id}/amend", only(http.MethodPost, k.amend))
	mux.HandleFunc(prefix+"/proposals/{proposal_id}", only(http.MethodGet, k.getProposal))
	mux.HandleFunc(prefix+"/proposals/{proposal_id}/confirm", only(http.MethodPost, k.confirm))
	mux.HandleFunc(prefix+"/proposals/{proposal_id}/reject", only(http.MethodPost, k.reject))
}
