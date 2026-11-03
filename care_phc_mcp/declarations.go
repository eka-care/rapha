package carephc

import (
	"encoding/json"
	"fmt"
	"sort"

	"github.com/eka-care/care_phc_mcp/pyval"
)

// StateQuery is one `{resource, where}` pair inside a state rule. It is the
// store's query grammar as a declaration writes it, before kstate turns it
// into the store's own conditions.
type StateQuery struct {
	Resource string         `json:"resource"`
	Where    map[string]any `json:"where"`
}

// AllOfItem is one entry of an `all_of` rule: either a flag name, possibly
// negated with the "not " prefix, or a nested rule.
type AllOfItem struct {
	Flag    string
	Negated bool
	Rule    *StateRule
}

// StateRule is one flag's rule, in one of the four forms
// kernel/declarations.RULE_FORMS allows. Form names which, so an unknown form
// is a named failure rather than a rule that quietly reads as false.
type StateRule struct {
	Form   string
	Exists StateQuery
	Gte    [2]StateQuery
	AllOf  []AllOfItem
}

// UnmarshalJSON reads the single-key dict a rule is. A rule with no key, or
// with more than one, is refused: the Python destructures `(form, arg), =
// rule.items()` and would raise, and a Go engine reading it as empty would
// make the flag silently false.
func (r *StateRule) UnmarshalJSON(raw []byte) error {
	var node map[string]json.RawMessage
	if err := json.Unmarshal(raw, &node); err != nil {
		return err
	}
	if len(node) != 1 {
		return fmt.Errorf("a state rule is one of stored, exists, gte, all_of; "+
			"this one has %d keys", len(node))
	}
	for form, arg := range node {
		r.Form = form
		switch form {
		case "stored":
			var on bool
			if err := json.Unmarshal(arg, &on); err != nil {
				return err
			}
		case "exists":
			if err := pyval.Decode(arg, &r.Exists); err != nil {
				return err
			}
		case "gte":
			var pair []StateQuery
			if err := pyval.Decode(arg, &pair); err != nil {
				return err
			}
			if len(pair) != 2 {
				return fmt.Errorf("a gte rule is two queries, got %d", len(pair))
			}
			r.Gte = [2]StateQuery{pair[0], pair[1]}
		case "all_of":
			var listed []json.RawMessage
			if err := json.Unmarshal(arg, &listed); err != nil {
				return err
			}
			for _, item := range listed {
				var flag string
				if err := json.Unmarshal(item, &flag); err == nil {
					entry := AllOfItem{Flag: flag}
					if len(flag) > 4 && flag[:4] == "not " {
						entry.Flag, entry.Negated = flag[4:], true
					}
					r.AllOf = append(r.AllOf, entry)
					continue
				}
				nested := &StateRule{}
				if err := nested.UnmarshalJSON(item); err != nil {
					return err
				}
				r.AllOf = append(r.AllOf, AllOfItem{Rule: nested})
			}
		default:
			return fmt.Errorf("unknown state rule form '%s'", form)
		}
	}
	return nil
}

// Step is one step of a workflow's line.
type Step struct {
	Station     string   `json:"station"`
	DoneWhen    string   `json:"done_when"`
	AppliesWhen string   `json:"applies_when"`
	Operations  []string `json:"operations"`
}

// Workflow is kernel/contracts.Workflow as the compiled catalogue carries it.
//
// StateOrder is the order the rules were DECLARED in, which the States map
// cannot carry: catalogue.json is written with sorted keys. See
// kernel/declarations.compile_json for what goes wrong when an engine
// evaluates them alphabetically instead.
type Workflow struct {
	ID         string               `json:"id"`
	Title      string               `json:"title"`
	Summary    string               `json:"summary"`
	Subject    string               `json:"subject"`
	Spine      string               `json:"spine"`
	// The level between the spine and the subject: one course of care that
	// starts, runs and ends. Empty for a bundle that declares none.
	Episode    string               `json:"episode"`
	Steps      []Step               `json:"steps"`
	States     map[string]StateRule `json:"states"`
	StateOrder []string             `json:"state_order"`
	Stored     []string             `json:"stored"`
}

// LoadDeclarations fills the parts of the embedded catalogue that Load leaves
// as `any`: the typed workflow, the compiled mapping, and each operation's
// own JSON.
//
// Separate from Load because Load is what cmd/mcp has always called and it
// does not write rows. A reader that only builds a tool list has no business
// failing on a mapping it will never evaluate.
func (c *Catalogue) LoadDeclarations() error {
	var raw struct {
		Workflows  map[string]json.RawMessage `json:"workflows"`
		Mapping    map[string]json.RawMessage `json:"mapping"`
		Operations map[string]json.RawMessage `json:"operations"`
		Views      json.RawMessage            `json:"views"`
		Metrics    json.RawMessage            `json:"metrics"`
		Schedules  json.RawMessage            `json:"schedules"`
		Documents  json.RawMessage            `json:"documents"`
	}
	// c.raw and not the embedded copy: Load may have read the tree, and two
	// readers reaching for different bundles would serve one bundle's manifest
	// over the other's workflow with nothing saying so.
	if len(c.raw) == 0 {
		return fmt.Errorf("this catalogue was not built by Load, so there are " +
			"no bytes to read the declarations out of")
	}
	if err := json.Unmarshal(c.raw, &raw); err != nil {
		return fmt.Errorf("the catalogue at %s is not an object: %w", c.Source, err)
	}
	c.Workflow = nil
	c.MappingRaw = raw.Mapping
	c.OperationsRaw = raw.Operations

	// The views and the metrics again, through pyval, because Load reads them
	// with encoding/json's default and that turns every number in a `where`
	// into a float64. A declaration's conditions are compared as TEXT by the
	// store (every column is TEXT), so 30 spelled "30" and 30 spelled "30.0"
	// are two different queries. Nothing in this tree declares a numeric
	// condition today; re-decoding here is what keeps that from becoming a
	// silent difference the first time one does.
	if len(raw.Views) > 0 {
		views := map[string]View{}
		if err := pyval.Decode(raw.Views, &views); err != nil {
			return fmt.Errorf("the compiled views are not readable: %w", err)
		}
		c.Views = views
	}
	if len(raw.Metrics) > 0 {
		metrics := map[string]Metric{}
		if err := pyval.Decode(raw.Metrics, &metrics); err != nil {
			return fmt.Errorf("the compiled metrics are not readable: %w", err)
		}
		c.Metrics = metrics
	}

	// The schedules, through pyval for the same reason: a contact's days are
	// whole numbers in the declaration and encoding/json would make them
	// float64, which is a different thing to add to a date.
	c.Schedules = map[string]Schedule{}
	if len(raw.Schedules) > 0 {
		if err := pyval.Decode(raw.Schedules, &c.Schedules); err != nil {
			return fmt.Errorf("the compiled schedules are not readable: %w", err)
		}
	}

	// Where each kind of row is filed when this bundle publishes. Through
	// pyval for the same reason the two above are, and an EMPTY MAP rather
	// than nil when the bundle declares none, so "this bundle publishes
	// nothing" and "the placement was never loaded" are different facts to
	// the one caller that sends documents.
	c.Documents = map[string]DocumentDecl{}
	if len(raw.Documents) > 0 {
		if err := pyval.Decode(raw.Documents, &c.Documents); err != nil {
			return fmt.Errorf("the compiled documents are not readable: %w", err)
		}
	}

	// The atom a thread panel draws, which is the compiled operation WITH its
	// mapping merged back in. api/main.py hands the renderer
	// BUNDLE.operations, whose entries carry `mapping` because
	// kernel/declarations attaches it, and web/src/structured.ts reads it. So
	// the compiled mapping goes on the wire and this is where the two halves
	// of catalogue.json are put back together.
	//
	// An operation with no mapping gets an empty list rather than no key: the
	// Python attaches `mapping` to every operation and only
	// kernel/declarations.compile_json drops the empty ones, so an absent key
	// here would be this engine inventing a difference.
	c.ActionJSON = map[string]map[string]any{}
	for id, blob := range raw.Operations {
		node := map[string]any{}
		if err := pyval.Decode(blob, &node); err != nil {
			return fmt.Errorf("%s: the compiled atom is not readable: %w", id, err)
		}
		records := []any{}
		if mapped, declared := raw.Mapping[id]; declared {
			if err := pyval.Decode(mapped, &records); err != nil {
				return fmt.Errorf("%s: the compiled mapping is not readable: %w", id, err)
			}
		}
		node["mapping"] = records
		c.ActionJSON[id] = node
	}
	if len(raw.Workflows) != 1 {
		return fmt.Errorf("%s declares %d workflows; api/main.py's WORKFLOW is "+
			"the one a bundle has", c.Manifest.ID, len(raw.Workflows))
	}
	for _, blob := range raw.Workflows {
		wf := &Workflow{}
		if err := pyval.Decode(blob, wf); err != nil {
			return fmt.Errorf("the compiled workflow is not readable: %w", err)
		}
		if len(wf.StateOrder) != len(wf.States) {
			return fmt.Errorf("%s carries %d state rules and %d in state_order. "+
				"The order is what makes an all_of rule evaluable; recompile "+
				"with python3 -m catalogue.build && python3 -m kernel.declarations.",
				wf.ID, len(wf.States), len(wf.StateOrder))
		}
		c.Workflow = wf
	}
	return nil
}

// Mapping is the compiled mapping records for one operation, or none. Decoded
// on demand rather than at load, so a kernel that never writes a row never
// parses one.
func (c *Catalogue) Mapping(opID string, into any) (bool, error) {
	blob, declared := c.MappingRaw[opID]
	if !declared {
		return false, nil
	}
	if err := pyval.Decode(blob, into); err != nil {
		return false, fmt.Errorf("%s: the compiled mapping is not readable: %w", opID, err)
	}
	return true, nil
}

// Stations is every station the one workflow's steps name, in line order.
func (c *Catalogue) Stations() []string {
	var out []string
	seen := map[string]bool{}
	for _, step := range c.Workflow.Steps {
		if !seen[step.Station] {
			seen[step.Station] = true
			out = append(out, step.Station)
		}
	}
	return out
}

// BundleOperations is the operations the loaded bundle's manifest lists, which
// is narrower than the catalogue-wide `operations` key: catalogue.json embeds
// every bundle's atoms and is narrowed at runtime.
func (c *Catalogue) BundleOperations() map[string]Operation {
	listed := map[string]bool{}
	for _, id := range c.Manifest.Operations {
		listed[id] = true
	}
	out := map[string]Operation{}
	for id, op := range c.Operations {
		if listed[id] {
			out[id] = op
		}
	}
	return out
}

// SortedOperationIDs is every operation id the loaded bundle holds, sorted.
func SortedOperationIDs(ops map[string]Operation) []string {
	out := make([]string, 0, len(ops))
	for id := range ops {
		out = append(out, id)
	}
	sort.Strings(out)
	return out
}

// CompiledJSON is GET /catalogue's whole body, which api/main.py builds as
//
//	dict(declarations.compile_json(BUNDLE),
//	     capabilities=sorted(vocab.CAPABILITIES), bundles=vocab.BUNDLES,
//	     states=sorted(vocab.STATES), operations=BUNDLE.operations)
//
// Every one of compile_json's ten keys is already written into catalogue.json
// for the LOADED bundle by kernel/declarations.write_catalogue, so this reads
// the embedded file whole and substitutes exactly the four keys the route
// overrides. Read whole rather than field by field for the reason ManifestRaw
// is kept raw: what goes on the wire is the declaration the Python compiled,
// so a key added to kernel/contracts.BUNDLE_KEYS arrives here without being
// retyped in Go.
//
// THE TRAP IN THAT FILE, WHICH IS WHY THE FOUR KEYS ARE SUBSTITUTED
// -----------------------------------------------------------------
// catalogue.json's top level `capabilities`, `bundles` and `states` are the
// UNION OVER EVERY BUNDLE — 22 capabilities and 13 roles — because the file is
// embedded whole and narrowed at runtime (see write_catalogue's own comment).
// What this route serves is the loaded bundle's own, 16 and 9, and those live
// under `vocabulary`. Serving the union would hand the only account the
// browser can be six laboratory capabilities a health centre does not
// declare, and the renderer's capability list and role editor are built off
// exactly this answer. `operations` is the same trap in the same file: it too
// is catalogue wide, and it is narrowed here by the manifest's own list.
//
// Needs LoadDeclarations, because the operations it serves are the ones a
// thread panel draws: the compiled atom with its mapping merged back in.
func (c *Catalogue) CompiledJSON() (map[string]any, error) {
	if c.ActionJSON == nil {
		return nil, fmt.Errorf("the compiled catalogue has not been loaded: " +
			"call LoadDeclarations before serving GET /catalogue")
	}
	body := map[string]any{}
	if err := pyval.Decode(c.raw, &body); err != nil {
		return nil, fmt.Errorf("the catalogue at %s is not an object: %w",
			c.Source, err)
	}
	caps := append([]string(nil), c.Vocabulary.Capabilities...)
	sort.Strings(caps)
	states := append([]string(nil), c.Vocabulary.States...)
	sort.Strings(states)
	operations := map[string]any{}
	for id := range c.BundleOperations() {
		operations[id] = c.ActionJSON[id]
	}
	body["capabilities"] = caps
	body["bundles"] = c.Vocabulary.Roles
	body["states"] = states
	body["operations"] = operations
	return body, nil
}
