package queues

import (
	"fmt"
	"os"

	carephc "github.com/eka-care/care_phc_mcp"
	"github.com/eka-care/care_phc_mcp/fhir"
	"github.com/eka-care/care_phc_mcp/kstate"
)

// DocumentBody is a waiting visit, projected now rather than when it was
// queued.
//
// THE FIRST PRODUCTION CALL OF fhir.Document IN THIS MODULE. Everything that
// projected a document before this was a check.
//
// THE PLACEMENT COMES FROM THE CATALOGUE AND NOT FROM THE CALLER, which is the
// third seam closed. `documents` is a bundle key as of 2026-11-01, so the
// declaration travels in catalogue.json and this function reads it; before
// that it had to be handed in, and a caller that can hand in a placement is a
// caller that can retype one. That is exactly the defect the declaration was
// moved onto the bundle to end: the same diagnosis was filed under Chief
// complaints in one check and under Medical History in another.
//
// Projected at send time and not at queue time for two reasons. A correction
// made while the item waited belongs in the document that actually leaves. And
// a bundle written to the outbox would be a second copy of a patient's record
// on disk, which is the thing the document path is designed not to need.
func DocumentBody(rows fhir.Rows, cat *carephc.Catalogue, item Item, now,
	document string) (any, error) {

	if document == "" {
		document = "consultation"
	}
	if cat.Documents == nil {
		// Not the same as a bundle that declares none. LoadDeclarations sets
		// this to an empty map, so nil means the declarations were never
		// loaded, and a queue that published on a placement it never read
		// would be guessing.
		return nil, Unsendablef("the compiled documents have not been loaded, " +
			"so there is nothing to publish through")
	}
	declared, publishes := cat.Documents[document]
	if !publishes {
		return nil, Unsendablef("this bundle declares no '%s' document, so "+
			"there is nothing to publish", document)
	}
	wanted, err := Wanted(declared)
	if err != nil {
		// A condition the query grammar does not hold. Not a line failure
		// either: it is a declaration this build cannot run, and the lint that
		// should have caught it is kernel/declarations._lint_documents.
		return nil, Unsendablef("this bundle's '%s' document cannot be "+
			"queried: %s", document, err)
	}
	made, err := fhir.Document(rows, item.Thread, declared.Profile,
		wanted, now, "")
	if err != nil {
		// A visit with no subject, or a section the profile does not declare.
		// NOT A LINE FAILURE: no number of retries fixes it, so it comes back
		// as an Unsendable and the attempt counter stops it.
		return nil, Unsendablef("this visit cannot be published: %s", err)
	}
	return made, nil
}

// Wanted is the compiled placement as the projection's own argument.
//
// THE ONE PLACE THE DECLARATION BECOMES A PROJECTION ARGUMENT, and it is a
// straight carry: the order of the sections is the order the artifact holds,
// which is the order the bundle declared. The artifact carries a list for
// exactly this reason, and the order is observable three times in what gets
// published. See kernel/contracts.BUNDLE_KEYS.
// The condition is turned into the store's own grammar by kstate.Query, which
// is the ONE converter the state rules and the views already go through, so a
// section's `where` cannot be read one way here and another way there.
func Wanted(declared carephc.DocumentDecl) ([]fhir.Want, error) {
	out := make([]fhir.Want, 0, len(declared.Sections))
	for _, section := range declared.Sections {
		want := fhir.Want{Slice: section.Slice}
		for _, q := range section.Queries {
			where, err := kstate.Query(q.Where)
			if err != nil {
				return nil, fmt.Errorf("%s.%s: %w", section.Slice, q.Resource, err)
			}
			want.Queries = append(want.Queries, fhir.Query{
				Resource: q.Resource, Where: where})
		}
		out = append(out, want)
	}
	return out, nil
}

// AudioBody is the recording's bytes, read from the one copy we kept.
func AudioBody(item Item) (any, error) {
	if item.Blob == "" {
		return nil, Unsendablef("the recording is no longer on disk, so there " +
			"is nothing to send")
	}
	raw, err := os.ReadFile(item.Blob)
	if err != nil {
		return nil, Unsendablef("the recording is no longer on disk, so there " +
			"is nothing to send")
	}
	return raw, nil
}
