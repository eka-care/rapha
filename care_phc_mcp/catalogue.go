// Package main serves the PHC operation catalogue over MCP.
//
// The tool list is generated from catalogue.json, which is compiled from the
// operation atoms. That is the whole point: an operation cannot reach an agent
// without passing the same lint that puts it on the rendered surface, and it
// cannot be added here by hand.
package main

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
	ID    string `json:"id"`
	Title string `json:"title"`
	Khoj  Khoj   `json:"khoj"`
}

type Catalogue struct {
	Capabilities []string             `json:"capabilities"`
	Bundles      map[string][]string  `json:"bundles"`
	States       []string             `json:"states"`
	Operations   map[string]Operation `json:"operations"`
	Manifest     Manifest             `json:"manifest"`
}

func Load() (*Catalogue, error) {
	var c Catalogue
	if err := json.Unmarshal(catalogueJSON, &c); err != nil {
		return nil, fmt.Errorf("embedded catalogue is not valid: %w", err)
	}
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
