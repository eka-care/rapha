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
//
// THE FILE IS READ FROM THE TREE, AND THE EMBEDDED COPY IS THE FALLBACK
// ---------------------------------------------------------------------
// The fifth seam, closed 2026-11-01. One bundle used to be compiled INTO the
// binary and nothing else could be served: cmd/api refuses by name to serve a
// bundle it was not compiled for, which is right and stays, but it was
// unsatisfiable, because the only way to change which bundle the binary held
// was to rebuild the binary. A facility running two bundles could not be
// served by one Go binary, and the laboratory's own separation rule was
// unprovable on Go for that reason and no other.
//
// So the catalogue is read the way the questionnaires, the value sets, the
// seed and the spoken field names already are: from the tree at startup. The
// embedded copy remains, and it is the honest design rather than a leftover,
// because the deployment argument for Go here is ONE FILE COPIED TO A CLINIC
// PC. A binary that could not start without a source tree beside it would
// give that up. So: the tree if there is one, the embedded copy if there is
// not, and the Catalogue says which it read so a check and a log line can
// tell them apart rather than guessing.
//
// A path named EXPLICITLY is not a fallback. PHC_CATALOGUE is a deliberate
// choice of file, so a missing or unreadable one is fatal and does not
// silently become the embedded bundle: that silence is how a check would
// report a second bundle passing while the first one answered.
package carephc

import (
	_ "embed"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

//go:embed catalogue.json
var embeddedCatalogue []byte

// CatalogueEnv names one compiled catalogue file outright. Set per process,
// which is what lets a second bundle be started without rebuilding anything.
const CatalogueEnv = "PHC_CATALOGUE"

// RootEnv is the repository root the tree is read relative to, the same
// variable the questionnaires, the value sets and the seed are read against.
const RootEnv = "PHC_ROOT"

// CataloguePath is where the compile step writes the artifact, relative to the
// root. Written in kernel/declarations.write_catalogue and catalogue/build.py;
// spelled once here.
var CataloguePath = filepath.Join("catalogue", "catalogue.json")

// Embedded is what the binary was compiled with, for a caller that wants to
// say which bundle that was.
const Embedded = "the catalogue compiled into this binary"

// catalogueBytes is the compiled catalogue and where it came from.
func catalogueBytes() ([]byte, string, error) {
	if named := os.Getenv(CatalogueEnv); named != "" {
		raw, err := os.ReadFile(named)
		if err != nil {
			// Named outright, so this is fatal. Falling back here would serve
			// one bundle while a check believed it had started another.
			return nil, named, fmt.Errorf("%s=%q could not be read, and a "+
				"catalogue named outright is not one this kernel may silently "+
				"replace with the embedded copy: %w", CatalogueEnv, named, err)
		}
		return raw, named, nil
	}
	root := os.Getenv(RootEnv)
	if root == "" {
		root = "."
	}
	at := filepath.Join(root, CataloguePath)
	if raw, err := os.ReadFile(at); err == nil {
		return raw, at, nil
	}
	// No tree. One file copied to a clinic PC, which is the whole deployment
	// argument for Go here.
	return embeddedCatalogue, Embedded, nil
}

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
	// Who covers which habitation at this centre: the sub-centres, the ANM on
	// each, and the ASHA on each village under it. Staffing and geography,
	// not a clinical declaration, and a pointer so a centre that declares
	// none answers null exactly as the Python does.
	Catchment *Catchment `json:"catchment"`
}

// Catchment is a facility's own answer to "who is responsible for this
// person between visits". `Column` is which of the subject's columns names
// the habitation; nothing here or in either engine knows what a sub-centre
// is, which is the point of it being declared.
type Catchment struct {
	Column string `json:"column"`
	Areas  []struct {
		Area     string            `json:"area"`
		ANM      string            `json:"anm"`
		Villages map[string]string `json:"villages"`
	} `json:"areas"`
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
//
// THIS STRUCT IS NOT THE WHOLE OF THAT KEY, AND THAT IS SAID HERE SO IT IS
// NOT DISCOVERED. `vocabulary` also carries `capability_titles` and
// `role_titles`: what a person reads for a capability and for a role, which
// bundles/<id>/bundle.yaml declares beside the id. They are NOT typed here,
// because nothing in Go reads a word a person reads. They still reach the
// browser from this engine: CompiledJSON serves the catalogue body whole and
// substitutes exactly four keys, so `vocabulary` travels as the Python
// compiled it. scripts/check_go_parity.py compares GET /catalogue between the
// two engines byte for byte, which is what holds that true.
//
// The three fields below keep their shapes for the same reason the titles
// sit beside them rather than inside them: GET /roles serves `Roles` as the
// shipped presets and a save is validated against `Capabilities`, so a name
// is a new fact about a word and never a new shape for the word.
type Vocabulary struct {
	Capabilities []string            `json:"capabilities"`
	Roles        map[string][]string `json:"roles"`
	States       []string            `json:"states"`
}

// DocumentQuery is one row query inside a declared section: a resource table
// and the condition its rows must meet. kernel/declarations._documents writes
// it as a `(resource, where)` pair; the artifact names both halves so neither
// can be read as the other.
type DocumentQuery struct {
	Resource string         `json:"resource"`
	Where    map[string]any `json:"where"`
}

// DocumentSection is one section slice of a profile and the rows filed under
// it.
type DocumentSection struct {
	Slice   string          `json:"slice"`
	Queries []DocumentQuery `json:"queries"`
}

// DocumentDecl is one entry of bundle.yaml's `documents:`: which profile this
// facility publishes and which section of it each kind of row is filed under.
// kernel.declarations._lint_documents has already refused a profile this build
// does not emit, a slice the profile does not declare, a resource with no
// projection and a resource no operation here writes, so what arrives is a
// placement that projects.
//
// SECTIONS ARE ORDERED AND THAT IS LOAD BEARING. The projection walks them in
// order and the order shows up three times in the document: the order of the
// sections, the order of the Bundle's entries, and the order the authors are
// discovered in. See kernel/contracts.BUNDLE_KEYS for why the artifact carries
// a list rather than a mapping.
type DocumentDecl struct {
	Profile  string            `json:"profile"`
	Sections []DocumentSection `json:"sections"`
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
	// calendar: the episode type names whose schedules it draws.
	Episodes []string `json:"episodes"`
}

// Metric is kernel/contracts.Metric. Denominator is a pointer because None
// and an empty query are different facts: a plain count declares none, and a
// rate with an empty denominator is zero rather than an error.
// Contact is kernel/contracts.Contact: one thing a schedule says is owed,
// measured in days from the anchor. `Due` is the day it is aimed at and
// Opens/Closes are the window either side, because a visit due at 28 weeks
// is not late at 28 weeks and one day.
type Contact struct {
	ID          string `json:"id"`
	Title       string `json:"title"`
	Due         int    `json:"due"`
	Opens       int    `json:"opens"`
	Closes      int    `json:"closes"`
	Owner       string `json:"owner"`
	Operation   string `json:"operation"`
	Authority   string `json:"authority"`
	EscalatesTo string `json:"escalates_to"`
	ReportsAs   string `json:"reports_as"`
	// ProgrammeTitle is the programme's own phrasing, shown on hover; optional.
	ProgrammeTitle string `json:"programme_title"`
}

// Schedule is kernel/contracts.Schedule: what a centre owes somebody over
// the life of one episode. A PlanDefinition in FHIR; what it produces for
// one person is a CarePlan, and nothing of it is stored.
type Schedule struct {
	ID       string         `json:"id"`
	Title    string         `json:"title"`
	Summary  string         `json:"summary"`
	Episode  string         `json:"episode"`
	Anchor   map[string]int `json:"anchor"`
	Contacts []Contact      `json:"contacts"`
	// Where the date the offsets apply to comes from: "recorded" (the
	// default) is a date somebody wrote down, "opened" is the moment the
	// episode itself was opened. A referral is the second kind.
	AnchorFrom string `json:"anchor_from"`
}

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
	Schedules  map[string]Schedule `json:"schedules"`
	Workflows  map[string]any    `json:"workflows"`

	// Where this catalogue was read from: a path, or Embedded. Carried so a
	// startup line and a check can say which, rather than a reader having to
	// work it out from the environment.
	Source string `json:"-"`
	// The bytes Load read, so nothing below it goes back to the embedded copy
	// and reads a different bundle. See Load.
	raw []byte

	// Filled by LoadDeclarations, not by a tag. The one workflow a bundle
	// has, typed, because the guard reads its steps and its state rules.
	Workflow *Workflow `json:"-"`
	// Where each kind of row is filed when this bundle publishes, by document
	// id. Filled by LoadDeclarations and NOT by a tag, for the reason the
	// views and the metrics are: a `where` read with encoding/json's default
	// turns every number into a float64, and the store compares conditions as
	// text, so 30 would be asked for as "30" by one engine and "30.0" by the
	// other.
	Documents map[string]DocumentDecl `json:"-"`
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
	blob, from, err := catalogueBytes()
	if err != nil {
		return nil, err
	}
	var c Catalogue
	if err := json.Unmarshal(blob, &c); err != nil {
		return nil, fmt.Errorf("the catalogue at %s is not valid: %w", from, err)
	}
	var raw struct {
		Manifest json.RawMessage `json:"manifest"`
	}
	if err := json.Unmarshal(blob, &raw); err != nil {
		return nil, fmt.Errorf("the catalogue at %s has no manifest: %w", from, err)
	}
	c.ManifestRaw = raw.Manifest
	// THE BYTES ARE KEPT, and every later read goes through them rather than
	// back to the embedded copy. LoadDeclarations and CompiledJSON both used to
	// re-read the package level variable, which was harmless only while there
	// was one catalogue: once the file can come from the tree, a Load that read
	// the laboratory's and a LoadDeclarations that read the health centre's
	// would have served one bundle's manifest over the other's workflow, and
	// nothing would have said so.
	c.raw = blob
	c.Source = from
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
