// Package plugins is kernel/plugins.py in Go: a facility's shape, resolved to
// one subtraction, and the lint that keeps a shape from looking configured
// while being broken.
//
// A plugin is a NAMED GROUP OF ONE BUNDLE'S OWN WORDS, declared in
// bundles/<id>/bundle.yaml beside `roles:` and carried through catalogue.json
// unresolved. A facility is one line: which of those groups this centre does
// not run. Two primary health centres then run the same binary, the same
// bundle and the same compiled catalogue, and differ by one declared list.
//
// THE MECHANISM, WHICH IS THE PYTHON'S AND NOT A NEW ONE
// ------------------------------------------------------
// A plugin that is off is a capability the caller does not hold. Subtracted
// once, by Effective, in the one place a caller is resolved. Everything
// downstream -- the guard's denial, the quick action row, GET /whoami and
// therefore the MCP server's tool list, and every view's own capability gate
// -- reads the one narrowed set, so there is no render-time hide to implement
// and nothing to forget.
//
// WHY THIS IS A PACKAGE AND NOT FIVE FUNCTIONS IN cmd/api
// -------------------------------------------------------
// It began as five unexported functions beside the routes, which is where a
// transcription naturally lands. The lint is why they moved: Lint is the half
// of kernel/plugins.py that REFUSES, and a refusal nothing outside package
// main can call is a refusal no test and no differential check can reach.
//
// WHAT CANNOT TRAVEL, SAID HERE RATHER THAN DISCOVERED
// ---------------------------------------------------
// Three of the Python lint's refusals are about the SHAPE of a declaration
// rather than its content: an unknown key on a plugin or a facility, a
// declaration that is not a mapping at all, and the spelling YAML 1.1 reads
// as a boolean (`off:` parses as a key named False, so the facility withholds
// nothing). All three are caught where bundle.yaml is PARSED, and no Go
// process ever sees bundle.yaml: kernel/declarations.compile_json writes the
// known keys of `plugins:` and `facilities:` into catalogue.json and drops
// the rest, so an unknown key has already been discarded by the time this
// package can look. Nothing here can refuse what it cannot see, and nothing
// here pretends to. The key is spelled `without` and not `off` for exactly
// that reason; do not rename it.
//
// Pure: reads the parsed catalogue, touches no database and no network.
package plugins

import (
	"fmt"
	"os"
	"sort"
	"strings"

	carephc "github.com/eka-care/care_phc_mcp"
)

// ENV is the environment variable that picks a shape, read exactly where
// PHC_BUNDLE is read and for the same reason: one kernel serves one facility.
const ENV = "PHC_FACILITY"

// Chosen is kernel/plugins.chosen: which shape this kernel is running, or ""
// if the bundle declares none.
//
// The argument wins over the environment, which wins over the bundle's own
// default. A bundle with no facilities has one shape and no choice to make,
// which is what keeps bundles/lab valid with nothing added to it.
func Chosen(cat *carephc.Catalogue, want string) string {
	if len(cat.Facilities.Declared) == 0 {
		return ""
	}
	if want != "" {
		return want
	}
	if asked := os.Getenv(ENV); asked != "" {
		return asked
	}
	return cat.Facilities.Default
}

// Off is kernel/plugins.off: the plugin ids this facility does not run, in
// declaration order, and only those the bundle actually declares.
//
// The filter is the Python's. It is NOT the guard against a switch wired to
// nothing: Lint is, and it refuses the bundle. Keeping the filter here and
// the refusal there is what the Python does, and dropping either one is how a
// facility that names a plugin nobody declares runs everything instead.
func Off(cat *carephc.Catalogue, facility string) []string {
	var out []string
	for _, pid := range cat.Facilities.Declared[facility].Without {
		if _, declared := cat.Plugins[pid]; declared {
			out = append(out, pid)
		}
	}
	return out
}

// Withheld is kernel/plugins.withheld: {capability: the plugin id that
// withholds it} for this facility.
//
// The whole of the runtime effect, as one map. The guard reads it to name a
// denial and Effective reads it to subtract. There is no second form.
func Withheld(cat *carephc.Catalogue, facility string) map[string]string {
	out := map[string]string{}
	for _, pid := range Off(cat, facility) {
		for _, cap := range cat.Plugins[pid].Capabilities {
			out[cap] = pid
		}
	}
	return out
}

// Absent is kernel/plugins.absent: {plugin id: its declared title} for the
// plugins this facility does not run.
//
// The same fact as Withheld read from the other end, and the only reason it
// exists separately is that a screen has to be able to SAY it: Withheld
// answers "which capability is gone", this answers "what is the thing this
// centre does not run", in the words the bundle chose for it, so a renderer
// can explain a switch it has disabled without typing a plugin's id at a
// clinician.
func Absent(cat *carephc.Catalogue, facility string) map[string]string {
	out := map[string]string{}
	for _, pid := range Off(cat, facility) {
		title := cat.Plugins[pid].Title
		if title == "" {
			title = pid
		}
		out[pid] = title
	}
	return out
}

// Effective is kernel/plugins.effective: caps minus what this facility
// withholds, order preserved. One function, called once. A second subtraction
// somewhere else would be a second place to forget.
func Effective(caps []string, heldBack map[string]string) []string {
	out := make([]string, 0, len(caps))
	for _, cap := range caps {
		if _, gone := heldBack[cap]; !gone {
			out = append(out, cap)
		}
	}
	return out
}

// Seeded is kernel/plugins.seeded: this facility's demo day, which is the
// seeded threads it could really have had.
//
// A seed is fixture data rather than a declaration, but a thread whose history
// names an operation nobody at this centre may perform is a lie about what
// happened here, and it draws a pending card no person can confirm. So a
// thread is dropped WHOLE rather than edited: half a visit with its laboratory
// step quietly deleted reads as a visit that finished.
func Seeded(threads []map[string]any, ops map[string]carephc.Operation,
	heldBack map[string]string) []map[string]any {
	if len(heldBack) == 0 {
		return threads
	}
	kept := []map[string]any{}
	for _, thread := range threads {
		drop := false
		for _, key := range []string{"proposals", "audit"} {
			listed, _ := thread[key].([]any)
			for _, item := range listed {
				entry, isMap := item.(map[string]any)
				if !isMap {
					continue
				}
				opID, _ := entry["operation"].(string)
				op, declared := ops[opID]
				if !declared {
					continue
				}
				if _, withheld := heldBack[op.Capability]; withheld {
					drop = true
				}
			}
		}
		if !drop {
			kept = append(kept, thread)
		}
	}
	return kept
}

// --------------------------------------------------------------------------
// lint
// --------------------------------------------------------------------------

// Shape is everything Lint reads, passed in rather than taken off a
// *Catalogue, for one reason: a lint that could only be asked about the
// embedded catalogue could only ever be asked whether the real bundle is
// sound, which it is. Bending a declaration is how a refusal is proved to
// refuse, and that is what both the parity check and a Go test do with this.
//
// Operations is the CATALOGUE-WIDE set, not the loaded bundle's, because that
// is what kernel/declarations.load hands plugins.lint: `ops =
// catalogue["operations"]`. Narrowing it here would be this engine deciding
// something the Python did not.
//
// Asked is PHC_FACILITY as the process read it, passed rather than read, so
// the check that a misspelt one is refused does not depend on mutating the
// environment of a running kernel.
type Shape struct {
	Plugins      map[string]carephc.Plugin
	Facilities   carephc.Facilities
	Capabilities []string
	Operations   map[string]carephc.Operation
	Workflows    []*carephc.Workflow
	Asked        string
}

// ShapeOf reads a loaded catalogue and the environment into a Shape: what a
// real kernel is about to run.
func ShapeOf(cat *carephc.Catalogue) Shape {
	var flows []*carephc.Workflow
	if cat.Workflow != nil {
		flows = append(flows, cat.Workflow)
	}
	return Shape{
		Plugins:      cat.Plugins,
		Facilities:   cat.Facilities,
		Capabilities: cat.Vocabulary.Capabilities,
		Operations:   cat.Operations,
		Workflows:    flows,
		Asked:        os.Getenv(ENV),
	}
}

// closers is kernel/plugins._closers: {done_when: whether any operation still
// available raises it}.
//
// An operation raises a flag by declaring it in `emits`, which is the only
// place that claim is made. Station is deliberately NOT part of this: an
// operation can stand at one station and close another's step, which is a
// fact about a line and not a mistake.
func closers(wf *carephc.Workflow, ops map[string]carephc.Operation,
	heldBack map[string]string) map[string]bool {
	out := map[string]bool{}
	for _, step := range wf.Steps {
		flag := step.DoneWhen
		if _, seen := out[flag]; !seen {
			out[flag] = false
		}
		for _, op := range ops {
			for _, emitted := range op.Emits {
				if emitted != flag {
					continue
				}
				if _, withheld := heldBack[op.Capability]; !withheld {
					out[flag] = true
				}
			}
		}
	}
	return out
}

// Lint returns a list of failure strings. Empty means every shape is sound.
//
// The sentences are the Python's, word for word, because they are compared to
// the Python's by scripts/check_go_parity.py. A message reworded to read
// better in Go would be this engine disagreeing about what a build operator
// is told.
//
// What this refuses, each one a centre that would look configured and be
// broken:
//
//   - a plugin naming a capability this bundle does not declare, or two
//     plugins claiming the same one. A capability no plugin claims is always
//     on, which is the default-on rule: a plugin added later cannot silently
//     take an ability away from a facility that never heard of it.
//   - a facility naming a plugin that does not exist, which is a switch wired
//     to nothing, and one that names a plugin twice.
//   - a facility switching off a plugin declared always on.
//   - a bundle declaring facilities and no default, or a default that is not
//     one of them, OR AN UNKNOWN SHAPE ASKED FOR BY THE ENVIRONMENT. That
//     last one is the whole reason this function exists in Go: Chosen returns
//     whatever PHC_FACILITY says, an unrecognised shape resolves to no
//     declaration, and no declaration withholds nothing, so without this rule
//     a typo in the variable runs the FULL facility and a centre meant to have
//     no laboratory quietly has one.
//   - and the one that matters: a facility whose choice stops the line. If no
//     operation this centre may still perform raises a step's done_when, and
//     that step has no applies_when to skip it, every patient waits at that
//     station forever. A step that CAN be skipped is the mechanism, not the
//     bug: that is how a centre with no laboratory has no laboratory queue.
//
// EVERY DECLARED SHAPE IS LINTED, NOT THE CHOSEN ONE
// --------------------------------------------------
// The loop below is over all of Facilities.Declared, which is the Python's
// loop. Linting only the shape this process runs would pass on the centre
// that runs every plugin and ship a narrowed one that stops the line, which
// is the exact asymmetry this module is built to make impossible.
//
// What this does NOT refuse: a view or a metric left unreachable. A facility
// that withholds a reporting capability means to stop reading its own numbers
// on that screen, and GET /views/{id} already answers 403 with the capability
// named. Refusing it would make the switch unusable for the one thing it is
// for.
func Lint(s Shape) []string {
	var bad []string
	if len(s.Plugins) == 0 && len(s.Facilities.Declared) == 0 {
		return bad
	}

	caps := map[string]bool{}
	for _, cap := range s.Capabilities {
		caps[cap] = true
	}
	owner := map[string]string{}
	for _, pid := range sortedPlugins(s.Plugins) {
		decl := s.Plugins[pid]
		where := "bundle.yaml plugins." + pid
		if decl.Title == "" {
			bad = append(bad, fmt.Sprintf("%s: missing title", where))
		}
		if len(decl.Capabilities) == 0 {
			bad = append(bad, fmt.Sprintf("%s: missing capabilities", where))
		}
		for _, cap := range decl.Capabilities {
			if !caps[cap] {
				bad = append(bad, fmt.Sprintf("%s: names '%s', which this bundle "+
					"does not declare, so the switch is wired to nothing", where, cap))
			} else if already, claimed := owner[cap]; claimed {
				bad = append(bad, fmt.Sprintf("%s: claims '%s', which plugin '%s' "+
					"already claims. Two switches on one ability means neither one "+
					"turns it off", where, cap, already))
			} else {
				owner[cap] = pid
			}
		}
	}

	shapes := s.Facilities.Declared
	if len(shapes) > 0 && s.Facilities.Default == "" {
		bad = append(bad, "bundle.yaml: declares facilities and no `facility:` "+
			"saying which one this build runs")
	}
	if s.Facilities.Default != "" {
		if _, declared := shapes[s.Facilities.Default]; !declared {
			bad = append(bad, fmt.Sprintf("bundle.yaml facility: '%s' is not one "+
				"of the declared facilities %s", s.Facilities.Default,
				pyList(sortedFacilities(shapes))))
		}
	}
	if s.Asked != "" {
		if _, declared := shapes[s.Asked]; !declared {
			bad = append(bad, fmt.Sprintf("%s=%s is not one of the facilities "+
				"bundle.yaml declares: %s", ENV, s.Asked,
				pyList(sortedFacilities(shapes))))
		}
	}

	for _, fid := range sortedFacilities(shapes) {
		decl := shapes[fid]
		where := "bundle.yaml facilities." + fid
		if decl.Title == "" {
			bad = append(bad, fmt.Sprintf("%s: missing title", where))
		}
		seen := map[string]bool{}
		twice := false
		for _, pid := range decl.Without {
			plugin, declared := s.Plugins[pid]
			if !declared {
				bad = append(bad, fmt.Sprintf("%s: switches off '%s', which is not "+
					"a plugin this bundle declares", where, pid))
			} else if plugin.Always {
				bad = append(bad, fmt.Sprintf("%s: switches off '%s', which is "+
					"declared always on", where, pid))
			}
			if seen[pid] {
				twice = true
			}
			seen[pid] = true
		}
		if twice {
			bad = append(bad, fmt.Sprintf("%s: names a plugin twice", where))
		}

		heldBack := map[string]string{}
		for _, pid := range decl.Without {
			if plugin, declared := s.Plugins[pid]; declared {
				for _, cap := range plugin.Capabilities {
					heldBack[cap] = pid
				}
			}
		}
		for _, wf := range s.Workflows {
			raisable := closers(wf, s.Operations, heldBack)
			for _, step := range wf.Steps {
				if step.AppliesWhen != "" {
					continue
				}
				if !raisable[step.DoneWhen] {
					bad = append(bad, fmt.Sprintf("%s: nothing this centre may do "+
						"raises '%s', and the '%s' step of %s has no applies_when to "+
						"skip it, so every visit waits there forever",
						where, step.DoneWhen, step.Station, wf.ID))
				}
			}
		}
	}

	return bad
}

func sortedPlugins(in map[string]carephc.Plugin) []string {
	out := make([]string, 0, len(in))
	for id := range in {
		out = append(out, id)
	}
	sort.Strings(out)
	return out
}

func sortedFacilities(in map[string]carephc.Facility) []string {
	out := make([]string, 0, len(in))
	for id := range in {
		out = append(out, id)
	}
	sort.Strings(out)
	return out
}

// pyList renders a sorted list of ids the way Python's %s of a list does,
// because that is what the message a build operator reads already says.
func pyList(in []string) string {
	quoted := make([]string, 0, len(in))
	for _, one := range in {
		quoted = append(quoted, "'"+one+"'")
	}
	return "[" + strings.Join(quoted, ", ") + "]"
}
