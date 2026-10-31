// The declarations a form is made of, served rather than compiled into the
// browser bundle. api/main.py's catalogue(), questionnaires() and valueset().
//
// WHAT THESE THREE ROUTES ARE FOR
// -------------------------------
// Until they existed the renderer read questionnaires/*.json and
// terminology/*.json through a Vite build time glob, which made the forms the
// one part of a screen the kernel did not serve: a facility could not change
// what a form asked without rebuilding the browser bundle.
// scripts/check_live.py is the check that the renderer really reads them from
// here, and it is the acceptance test for this slice.
package main

import (
	"net/http"
	"strconv"

	carephc "github.com/eka-care/care_phc_mcp"
)

// catalogue is the compiled catalogue: the operations, and the four
// declaration types that join them.
//
// NO CALLER CHECK, DELIBERATELY. api/main.py's catalogue() takes no Request
// and never calls caller(), so an unknown X-PHC-Role that makes /whoami
// answer 400 makes this answer 200. Copied rather than tidied: the body is
// the bundle's own declarations and holds nothing about anybody, and the
// difference is on the wire where a check can see it.
func (k *kernel) catalogue(w http.ResponseWriter, r *http.Request) {
	body, err := k.cat.CompiledJSON()
	if err != nil {
		detail(w, http.StatusInternalServerError, "%v", err)
		return
	}
	writeJSON(w, http.StatusOK, body)
}

// questionnaires is every form this bundle's operations ask, by the slug an
// operation names.
//
// NOT NARROWED BY THE CALLER'S CAPABILITIES, which is api/main.py's own
// decision and its own docstring. A form is a bundle's declaration and not a
// facility's choice, and the renderer labels an OLD audit row with the
// questionnaire of whatever operation wrote it, so a narrowed list would
// quietly lose the label on a card a colleague left behind. What a facility
// narrows is which operations it offers, and that is subtracted once in
// caller() and reaches the screen as thread.actions. The guard is the
// enforcement; this is only the words on a label.
//
// Keyed by the FILENAME an operation's `input` names, never by the `slug`
// inside the file: the two disagree on every questionnaire in the tree
// (phc.schema.vitals-v1.json carries slug "vitals-v1") and only the filename
// is ever read. See questionnaire.Load.
func (k *kernel) questionnaires(w http.ResponseWriter, r *http.Request) {
	if _, ok := k.who(w, r); !ok {
		return
	}
	out := map[string]any{}
	// Sorted rather than in Go's map order. The ANSWER does not depend on
	// the order -- a slug reached twice is the same file -- but a
	// deterministic walk is what makes the 500 below reproducible.
	for _, id := range carephc.SortedOperationIDs(k.operations) {
		slug := k.operations[id].Input
		if slug == "" {
			continue
		}
		if _, already := out[slug]; already {
			continue
		}
		schema, err := k.write.Schemas.Get(slug)
		if err != nil {
			// catalogue/validate.load raises FileNotFoundError, which FastAPI
			// turns into a 500. A form an operation names and nobody shipped
			// is a broken bundle and not a thin answer.
			detail(w, http.StatusInternalServerError, "%v", err)
			return
		}
		out[slug] = schema.Raw
	}
	writeJSON(w, http.StatusOK, map[string]any{"questionnaires": out})
}

// valueset expands a value set, for a picker.
//
// A question that binds its answer to a value set has no `answer_option`
// list, by design: the codes live in the value set and duplicating them into
// the questionnaire would be the same list twice. So something has to offer
// them, and this is it. Without this route the third binding form would be a
// column nothing could fill from a screen.
//
// TWO THINGS WORTH SAYING OUT LOUD, BOTH THE PYTHON'S
// ---------------------------------------------------
// The count is clamped at 200 and the renderer asks for 200, so the clamp
// never bites today — every value set here holds at most nine concepts — and
// it goes SILENTLY SHORT the day a real NRCeS release sits behind the same
// seam. And `q` exists and nothing calls it: the renderer filters the
// expansion it already has. Both are copied, neither is fixed.
func (k *kernel) valueset(w http.ResponseWriter, r *http.Request) {
	if _, ok := k.who(w, r); !ok {
		return
	}
	slug := r.PathValue("slug")
	if slug == "" {
		detail(w, http.StatusNotFound, "Not Found")
		return
	}
	query := r.URL.Query()
	limit := 50
	if given := query.Get("limit"); given != "" {
		parsed, err := strconv.Atoi(given)
		if err != nil {
			// FastAPI's own 422 for a query parameter that is not an int. Its
			// body is a list of validation errors rather than a `detail`
			// string, and that one shape is NOT reproduced here: it is
			// Starlette's, no caller in this repository reads it, and
			// inventing a copy of it would be this engine asserting a shape
			// instead of serving one. Said rather than hidden.
			detail(w, http.StatusUnprocessableEntity,
				"limit must be an integer")
			return
		}
		limit = parsed
	}
	if limit > 200 {
		limit = 200
	}
	if limit < 1 {
		limit = 1
	}
	q := query.Get("q")
	found, err := k.write.Terms.Expand(slug, q, limit)
	if err != nil {
		detail(w, http.StatusNotFound, "%v", err)
		return
	}
	concepts := k.write.Terms.Concepts(slug)
	out := make([]map[string]any, 0, len(found))
	for _, coding := range found {
		// `value` and `display` are the names a choice control already reads,
		// so a picker needs no new shape. The extras are what a coded answer
		// needs beside the code: the system it is from, and for an analyte the
		// unit it is reported in, which is what makes the unit field
		// answerable without a second lookup.
		row := map[string]any{"value": coding.Code(), "display": coding.Display(),
			"system": coding.System()}
		for _, extra := range []string{"unit", "unit_system"} {
			if value, carried := concepts[coding.Code()][extra]; carried {
				row[extra] = value
			}
		}
		out = append(out, row)
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"valueset": slug, "query": q, "concepts": out})
}
