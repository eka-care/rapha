// Package carephc reads the compiled PHC catalogue. It is the one reader, and
// both commands in this module use it rather than keeping a parser each.
//
// The declarations do not move for the Go port: catalogue.json is compiled
// from the operation atoms by python3 -m catalogue.build and
// python3 -m kernel.declarations, and this package reads it. That is the whole
// point: an operation cannot reach an agent or a screen without passing the
// same lint, and it cannot be added in Go by hand.
//
// The package sits at the module root because the embedded catalogue.json
// does: //go:embed cannot reach up a directory, and the file's path is
// written into kernel/declarations.py and catalogue/build.py. So cmd/api and
// cmd/mcp are directories beside the reader's files rather than siblings of
// its directory. That is the one place this module's shape was decided by
// where the Python already writes a file.
package carephc

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"sort"
)

//go:embed catalogue.json
var catalogueJSON []byte

type Field struct {
	LinkID   string   `json:"link_id"`
	Type     string   `json:"type"`
	Text     string   `json:"text"`
	Required bool     `json:"required"`
	Options  []string `json:"options"`
}

type Operation struct {
	ID              string   `json:"id"`
	Kind            string   `json:"kind"`
	Short           string   `json:"short"`
	Title           string   `json:"title"`
	Summary         string   `json:"summary"`
	Capability      string   `json:"capability"`
	ScopeQualifier  *string  `json:"scope_qualifier"`
	Station         string   `json:"station"`
	Instrument      string   `json:"instrument"`
	Preconditions   []string `json:"preconditions"`
	Irreversibility string   `json:"irreversibility"`
	Input           string   `json:"input"`
	Writes          []string `json:"writes"`
	Emits           []string `json:"emits"`
	Surfaces        []string `json:"surfaces"`
	Verified        string   `json:"verified"`
	Tool            string   `json:"tool"`
	Description     string   `json:"description"`
	Fields          []Field  `json:"fields"`
}

// Khoj is the ask-and-search surface's own name, reachable from the compiled
// catalogue's manifest so this server learns the word without being told it
// separately. Tool is the MCP tool name ("khoj"), Endpoint the kernel route
// it calls, and Description exactly what the tool tells an agent: it
// searches, answers, and proposes, and it never commits.
type Khoj struct {
	Tool        string `json:"tool"`
	Endpoint    string `json:"endpoint"`
	Description string `json:"description"`
}

type Manifest struct {
	ID      string `json:"id"`
	Version string `json:"version"`
	Title   string `json:"title"`
	Khoj    Khoj   `json:"khoj"`
	// Which operation atoms THIS bundle lists. The catalogue-wide
	// `operations` key below holds every bundle's, because the file is
	// embedded whole and narrowed at runtime, so this is the narrowing.
	Operations []string `json:"operations"`
}

// Plugin is one entry of bundle.yaml's `plugins:`, carried through
// catalogue.json unresolved. A plugin is a NAMED GROUP OF ONE BUNDLE'S OWN
// WORDS and nothing more: ids, a title a screen can say, and whether it is the
// floor. kernel/plugins.py owns what that means.
type Plugin struct {
	Title        string   `json:"title"`
	Capabilities []string `json:"capabilities"`
	Always       bool     `json:"always"`
}

// Facility is one entry of bundle.yaml's `facilities:`: a centre's whole
// choice, which is a list of what it does NOT run. There is no positive list,
// because one would mean a plugin added later ships off for everybody and
// nobody notices until a clinician cannot do their job.
type Facility struct {
	Title   string   `json:"title"`
	Without []string `json:"without"`
}

// Facilities carries the shapes a bundle declares and the one its own
// `facility:` picks when nothing overrides it. The default sits beside the
// shapes rather than on the manifest because it is only meaningful against
// them.
type Facilities struct {
	Default  string              `json:"default"`
	Declared map[string]Facility `json:"declared"`
}

// Vocabulary is the LOADED bundle's own words. The catalogue wide
// `capabilities`, `bundles` and `states` below are the union over every
// bundle, because this file is embedded whole and narrowed at runtime; these
// are the one bundle's, which is what api/main.py has always served.
type Vocabulary struct {
	Capabilities []string            `json:"capabilities"`
	Roles        map[string][]string `json:"roles"`
	States       []string            `json:"states"`
}

// Section is one block of a summary view: kernel/contracts.Section. Exactly
// one of Show or Resource is set, which the Python lint already holds.
type Section struct {
	Title    string         `json:"title"`
	Show     string         `json:"show"`
	Resource *string        `json:"resource"`
	Where    map[string]any `json:"where"`
	Fields   []string       `json:"fields"`
}

// Task is one row of a tasklist view: kernel/contracts.Task. `Where` is
// {"flag": str | [str], "not": str | [str]} and either member may be a bare
// string or a list, which is why both are read through AsList below rather
// than typed as a slice.
type Task struct {
	Title     string         `json:"title"`
	Where     map[string]any `json:"where"`
	Operation *string        `json:"operation"`
}

// View is kernel/contracts.View as the compiled catalogue carries it: one
// declaration for four kinds, with the fields the other three do not use left
// empty. Four Go types would need four resolvers and four response shapes,
// which is the reason the Python has one dataclass.
type View struct {
	ID         string `json:"id"`
	Kind       string `json:"kind"`
	Title      string `json:"title"`
	Summary    string `json:"summary"`
	Capability string `json:"capability"`
	Workflow   string `json:"workflow"`
	// queue
	Scope   string            `json:"scope"`
	GroupBy string            `json:"group_by"`
	Columns []string          `json:"columns"`
	Badges  map[string]string `json:"badges"`
	// summary
	Sections []Section `json:"sections"`
	// dashboard
	Metrics []string `json:"metrics"`
	Window  string   `json:"window"`
	// tasklist
	Tasks []Task `json:"tasks"`
}

// Metric is kernel/contracts.Metric. Denominator is a pointer because None
// and an empty query are different facts: a plain count declares none, and a
// rate with an empty denominator is zero rather than an error.
type Metric struct {
	ID          string      `json:"id"`
	Title       string      `json:"title"`
	Summary     string      `json:"summary"`
	Unit        string      `json:"unit"`
	Numerator   StateQuery  `json:"numerator"`
	Window      string      `json:"window"`
	Denominator *StateQuery `json:"denominator"`
	CertifiedBy *string     `json:"certified_by"`
}

// AsList is kernel/views._as_list: a declaration may write one flag or a
// list of them and both mean the same thing.
func AsList(v any) []string {
	switch t := v.(type) {
	case nil:
		return nil
	case string:
		return []string{t}
	case []any:
		out := make([]string, 0, len(t))
		for _, item := range t {
			if text, ok := item.(string); ok {
				out = append(out, text)
			}
		}
		return out
	}
	return nil
}

type Catalogue struct {
	Capabilities []string             `json:"capabilities"`
	Bundles      map[string][]string  `json:"bundles"`
	States       []string             `json:"states"`
	Operations   map[string]Operation `json:"operations"`
	Manifest     Manifest             `json:"manifest"`

	// The manifest again, unparsed, filled by Load rather than by a tag:
	// encoding/json silently drops BOTH of two fields that claim one name, so
	// tagging this `manifest` too would have left Manifest above empty and
	// every tool description blank.
	//
	// It is here because GET /facility serves asdict(manifest) WHOLE. Serving
	// it from the raw bytes means a field added to kernel/contracts.Manifest
	// reaches the response without being retyped in Go, which is that
	// dataclass's own rule (add, never rename) honoured on this side.
	ManifestRaw json.RawMessage `json:"-"`

	Plugins    map[string]Plugin `json:"plugins"`
	Facilities Facilities        `json:"facilities"`
	Vocabulary Vocabulary        `json:"vocabulary"`
	Views      map[string]View   `json:"views"`
	Metrics    map[string]Metric `json:"metrics"`
	Workflows  map[string]any    `json:"workflows"`

	// Filled by LoadDeclarations, not by a tag. The one workflow a bundle
	// has, typed, because the guard reads its steps and its state rules.
	Workflow *Workflow `json:"-"`
	// The compiled mapping and the operation atoms, unparsed. Kept raw for
	// the reason ManifestRaw is: what is served or evaluated is the
	// declaration the Python compiled, so a field added there arrives without
	// being retyped in Go.
	MappingRaw    map[string]json.RawMessage `json:"-"`
	OperationsRaw map[string]json.RawMessage `json:"-"`
	// Each atom as a thread panel draws it: the compiled operation with its
	// mapping merged back in. See LoadDeclarations.
	ActionJSON map[string]map[string]any `json:"-"`
}

func Load() (*Catalogue, error) {
	var c Catalogue
	if err := json.Unmarshal(catalogueJSON, &c); err != nil {
		return nil, fmt.Errorf("embedded catalogue is not valid: %w", err)
	}
	var raw struct {
		Manifest json.RawMessage `json:"manifest"`
	}
	if err := json.Unmarshal(catalogueJSON, &raw); err != nil {
		return nil, fmt.Errorf("embedded catalogue has no manifest: %w", err)
	}
	c.ManifestRaw = raw.Manifest
	return &c, nil
}

// For returns the operations this service account may invoke, sorted so the
// tool list is stable between runs. v0.1 §6 wants a role's surface well under
// fifty operations; the bundles already partition it, so there is no splitting
// logic here beyond two filters: the capability, and which operations the
// kernel's loaded bundle holds. A nil or empty `bundle` does not narrow, which
// is what the offline PHC_CAPABILITIES hatch wants.
func (c *Catalogue) For(caps map[string]bool, bundle map[string]bool) []Operation {
	var ops []Operation
	for _, op := range c.Operations {
		if !caps[op.Capability] {
			continue
		}
		if len(bundle) > 0 && !bundle[op.ID] {
			continue
		}
		ops = append(ops, op)
	}
	sort.Slice(ops, func(i, j int) bool { return ops[i].ID < ops[j].ID })
	return ops
}

var jsonType = map[string]string{
	"integer": "integer", "decimal": "number", "boolean": "boolean",
	"string": "string", "text": "string", "date": "string",
	"dateTime": "string", "time": "string", "choice": "string",
	"url": "string", "quantity": "number", "structured": "object",
	"group": "object", "display": "string",
}

// InputSchema builds the JSON Schema an agent sees, from the CARE questionnaire
// the operation names.
func (op Operation) InputSchema() map[string]any {
	props := map[string]any{}
	var required []string
	for _, f := range op.Fields {
		p := map[string]any{"type": jsonType[f.Type], "description": f.Text}
		if len(f.Options) > 0 {
			p["enum"] = f.Options
		}
		props[f.LinkID] = p
		if f.Required {
			required = append(required, f.LinkID)
		}
	}
	if op.Kind == "write" {
		props["override_reason"] = map[string]any{
			"type": "string",
			"description": "Required only to accept a value outside its " +
				"physiological range. Recorded with the result.",
		}
	}
	return map[string]any{"type": "object", "properties": props, "required": required}
}

// ToolDescription is what an agent reads to decide whether to call this. It
// leads with the atom's plain-words section and then states, plainly, that a
// write is a proposal a person still has to confirm.
func (op Operation) ToolDescription() string {
	d := op.Title + ".\n\n" + op.Description
	if op.Kind == "write" {
		d += "\n\nThis PROPOSES the operation. It does not commit it. The " +
			"proposal is placed on the patient thread for a clinician to " +
			"review, edit and confirm on screen. There is no tool that commits."
		if op.Irreversibility == "irreversible" {
			d += " This operation is irreversible and can only be confirmed " +
				"by a person, never from here."
		}
	}
	if len(op.Preconditions) > 0 {
		d += "\n\nPreconditions: " + fmt.Sprint(op.Preconditions)
	}
	if op.Verified != "verified" {
		d += "\n\nStatus: " + op.Verified + ". This operation has not been run " +
			"against a live CARE instance."
	}
	return d
}
