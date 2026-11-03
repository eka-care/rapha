package main

// The declared views, the queue, the patient spine and the local half of the
// patient directory. api/main.py's view, queue, subject and patient routes.
//
// Every route here is a shell, as that file's own docstring insists: it parses
// a request, checks the caller's capability to OPEN a view, and hands the
// answer back. The decision about what a view CONTAINS is the declaration's,
// evaluated in package views; what joins two visits is the workflow's,
// evaluated in package spine. Nothing in this file names a station, a flag, a
// metric or a bundle.

import (
	"net/http"
	"sort"
	"strconv"
	"time"

	"github.com/eka-care/care_phc_mcp/directory"
	"github.com/eka-care/care_phc_mcp/pyval"
	"github.com/eka-care/care_phc_mcp/spine"
	"github.com/eka-care/care_phc_mcp/views"
)

// bundle is the declarations a view resolves against, assembled from the
// loaded catalogue. Built per request rather than cached, because it is four
// map references and a cached copy would be one more thing to invalidate.
func (k *kernel) viewBundle() views.Bundle {
	return views.Bundle{Views: k.cat.Views, Metrics: k.cat.Metrics,
		Workflow: k.cat.Workflow, Operations: k.operations, Atoms: k.cat.ActionJSON}
}

// intParam is FastAPI's `limit: int = default`, clamped the way the route that
// reads it clamps it. The 422 for a value that is not an integer is FastAPI's;
// its body is a list of validation errors rather than a `detail` string and
// that shape is NOT reproduced, for the reason cmd/api/forms.go gives at the
// same place.
func intParam(w http.ResponseWriter, r *http.Request, name string, def, low, high int) (int, bool) {
	value := def
	if given := r.URL.Query().Get(name); given != "" {
		parsed, err := strconv.Atoi(given)
		if err != nil {
			detail(w, http.StatusUnprocessableEntity, "%s must be an integer", name)
			return 0, false
		}
		value = parsed
	}
	if value > high {
		value = high
	}
	if value < low {
		value = low
	}
	return value, true
}

// queue is api/main.py's /queue: the declared queue, with `view` defaulting to
// the bundle's first queue view.
//
// "First" is sorted by id, which is what the Python's sorted() over the view
// ids gives. A bundle that declares no queue view answers 404 rather than an
// empty screen.
func (k *kernel) queue(w http.ResponseWriter, r *http.Request) {
	want := r.URL.Query().Get("view")
	if want == "" {
		var queues []string
		for id, v := range k.cat.Views {
			if v.Kind == "queue" {
				queues = append(queues, id)
			}
		}
		if len(queues) == 0 {
			detail(w, http.StatusNotFound, "this bundle declares no queue view")
			return
		}
		sort.Strings(queues)
		want = queues[0]
	}
	k.resolveView(w, r, want)
}

// view is api/main.py's /views/{view_id}.
func (k *kernel) view(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("view_id")
	if id == "" {
		detail(w, http.StatusNotFound, "Not Found")
		return
	}
	k.resolveView(w, r, id)
}

func (k *kernel) resolveView(w http.ResponseWriter, r *http.Request, viewID string) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	declaration, declared := k.cat.Views[viewID]
	if !declared {
		detail(w, http.StatusNotFound, "unknown view %s", pyval.Repr(viewID))
		return
	}
	caps, _ := capsOf(person)
	// The view's own capability, and the ONE place it is checked. The
	// caller's set was already narrowed by what this facility withholds, in
	// caller(), so a view gated by a plugin this centre does not run is
	// refused here with no render-time hide to implement.
	if !caps[declaration.Capability] {
		detail(w, http.StatusForbidden, "missing capability %s", declaration.Capability)
		return
	}
	var thread *string
	if given := r.URL.Query().Get("thread"); given != "" {
		thread = &given
	}
	result, err := views.Resolve(k.viewBundle(), viewID, k.store, thread, caps,
		time.Now().UTC())
	if err != nil {
		// api/main.py catches ValueError around resolve() and turns it into a
		// 400; anything else is a 500. views.Declared is that ValueError.
		if named, isDeclared := err.(views.Declared); isDeclared {
			detail(w, http.StatusBadRequest, "%s", named.Reason)
			return
		}
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

// subject is api/main.py's /subjects/{subject_id}: the spine, one subject and
// every visit it has had.
//
// A thread is one encounter, which is the right unit for the guard and the
// wrong one for a person. What joins encounters is declared by the workflow
// (`spine:`), never assumed here, so a bundle that declares none gets a 404
// rather than a screen built on a guess.
//
// Read only, and scoped by the same capability that opens a thread: this
// returns clinical state across visits, so it is not more public than one.
func (k *kernel) subject(w http.ResponseWriter, r *http.Request) {
	person, ok := k.who(w, r)
	if !ok {
		return
	}
	id := r.PathValue("subject_id")
	if id == "" {
		detail(w, http.StatusNotFound, "Not Found")
		return
	}
	if spine.Declared(k.cat.Workflow) == "" {
		detail(w, http.StatusNotFound, "this bundle declares no spine")
		return
	}
	caps, _ := capsOf(person)
	if !caps["patient.find"] {
		detail(w, http.StatusForbidden, "missing capability patient.find")
		return
	}
	// 200 is kernel/spine.of's own default limit, which is a person's whole
	// timeline and not a page of it.
	found, err := spine.Of(k.store, k.cat, k.cat.Workflow, k.operations, id, 200)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	if found == nil {
		detail(w, http.StatusNotFound, "unknown subject %s", pyval.Repr(id))
		return
	}
	writeJSON(w, http.StatusOK, found)
}

// patientSearch is api/main.py's /patients/search: who might this be, from
// the local register and then the directory.
//
// ALWAYS 200. A directory that could not be asked is reported in the body
// (`reachable: false` and a reason) beside whatever the local register found,
// and never as an error status: a clerk looking for a patient who is in
// today's line must not be shown a failure about a directory they were not
// relying on.
//
// This engine has no vendor behind the directory seam, so the answer is
// always the kernel's own AbsentDirectory one. See package directory for why
// that is a named gap rather than a stub.
func (k *kernel) patientSearch(w http.ResponseWriter, r *http.Request) {
	// A capability-free read, but 400 on a bad role: the Python calls
	// caller() here for exactly that and throws the result away.
	if _, ok := k.who(w, r); !ok {
		return
	}
	limit, ok := intParam(w, r, "limit", 10, 1, 50)
	if !ok {
		return
	}
	found, err := directory.Resolve(k.store, r.URL.Query().Get("q"), limit)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"query":       found.Query,
		"local":       found.Local,
		"suggestions": found.Suggestions,
		"reachable":   found.Reachable,
		"reason":      found.Reason,
		// What a suggestion is FOR. Said on the wire so the renderer cannot
		// invent a different answer: these are values for the register form,
		// and committing them is an ordinary guarded write.
		"commits_through": "phc.op.patient-register",
	})
}

// patientPending is api/main.py's /patients/pending: patients this facility
// registered that the directory has not seen.
//
// A query over rows we already keep rather than a queue, so it cannot
// disagree with the records it is about.
func (k *kernel) patientPending(w http.ResponseWriter, r *http.Request) {
	if _, ok := k.who(w, r); !ok {
		return
	}
	limit, ok := intParam(w, r, "limit", 200, 1, 500)
	if !ok {
		return
	}
	rows, err := directory.Pending(k.store, limit)
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"pending": rows, "count": len(rows)})
}
