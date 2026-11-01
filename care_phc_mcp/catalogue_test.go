package carephc

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------------------------------------------------------------------------
// The fifth seam: where the catalogue comes from.
//
// One bundle used to be compiled INTO the binary and nothing else could be
// served. cmd/api's refusal to serve a bundle it was not compiled for is right
// and stays; what was wrong is that the only way to satisfy it was to rebuild.
// These hold the order the file is looked for in, and the one hazard the
// change introduced: two readers reaching for different copies.
// ---------------------------------------------------------------------------

// A test's working directory is this module, so there is no catalogue/ beside
// it and the fallback is what answers. That is the deployment the embedded
// copy exists for: one file copied to a clinic PC, with no source tree.
func TestWithNoTreeBesideItTheEmbeddedCatalogueAnswers(t *testing.T) {
	t.Setenv(CatalogueEnv, "")
	t.Setenv(RootEnv, "")
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if c.Source != Embedded {
		t.Errorf("with no tree beside it the kernel read %q", c.Source)
	}
	if len(c.Operations) == 0 {
		t.Error("the embedded catalogue is empty")
	}
}

// And with a tree, the tree. This is the whole of the seam: the file is a
// file, so a second bundle is compiled and read without rebuilding anything.
func TestWithATreeTheCatalogueIsReadFromIt(t *testing.T) {
	t.Setenv(CatalogueEnv, "")
	t.Setenv(RootEnv, "..")
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if c.Source == Embedded {
		t.Fatal("a kernel with the repository root given still read its own " +
			"embedded copy, so a second bundle could not be served")
	}
	if !strings.HasSuffix(c.Source, CataloguePath) {
		t.Errorf("it read %q", c.Source)
	}
	if len(c.Operations) == 0 {
		t.Error("the catalogue in the tree is empty")
	}
}

// A path named OUTRIGHT is a choice and not a fallback, so an unreadable one
// is fatal. Falling back here is how a check would report a second bundle
// passing while the first one answered.
func TestACatalogueNamedOutrightIsNotSilentlyReplaced(t *testing.T) {
	t.Setenv(RootEnv, "")
	t.Setenv(CatalogueEnv, filepath.Join(t.TempDir(), "nothing-is-here.json"))
	c, err := Load()
	if err == nil {
		t.Fatalf("a missing catalogue named outright was replaced by %q", c.Source)
	}
	if !strings.Contains(err.Error(), CatalogueEnv) {
		t.Errorf("the failure does not name the variable: %v", err)
	}
}

// THE HAZARD THE CHANGE INTRODUCED, and the reason the bytes are kept on the
// Catalogue. Load, LoadDeclarations and CompiledJSON all used to re-read the
// package level embedded variable, which was harmless only while there was one
// catalogue. Once the file can come from the tree, a Load that read one bundle
// and a LoadDeclarations that read another would serve one bundle's manifest
// over the other's workflow, and nothing would have said so.
func TestEveryReaderUsesTheBytesLoadActuallyRead(t *testing.T) {
	// A catalogue that differs from the embedded one in a way every reader
	// passes through: the manifest, which Load types, LoadDeclarations leaves
	// raw, and CompiledJSON serves whole.
	var body map[string]any
	if err := json.Unmarshal(embeddedCatalogue, &body); err != nil {
		t.Fatal(err)
	}
	manifest, _ := body["manifest"].(map[string]any)
	if manifest == nil {
		t.Fatal("the embedded catalogue has no manifest")
	}
	const marker = "a title no compiled catalogue carries"
	manifest["title"] = marker
	blob, err := json.MarshalIndent(body, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	at := filepath.Join(t.TempDir(), "catalogue.json")
	if err := os.WriteFile(at, blob, 0o600); err != nil {
		t.Fatal(err)
	}

	t.Setenv(RootEnv, "")
	t.Setenv(CatalogueEnv, at)
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if c.Manifest.Title != marker {
		t.Errorf("Load read %q, not the file it was pointed at", c.Manifest.Title)
	}
	if err := c.LoadDeclarations(); err != nil {
		t.Fatal(err)
	}
	served, err := c.CompiledJSON()
	if err != nil {
		t.Fatal(err)
	}
	out, _ := served["manifest"].(map[string]any)
	if out == nil || out["title"] != marker {
		t.Errorf("GET /catalogue would serve the manifest %v, which is not the "+
			"one Load read: two readers are reaching for different copies",
			out["title"])
	}
}

// And a Catalogue that Load did not build has no bytes to read, which is said
// rather than answered from the embedded copy.
func TestACatalogueLoadDidNotBuildHasNothingToReadDeclarationsFrom(t *testing.T) {
	bare := &Catalogue{}
	if err := bare.LoadDeclarations(); err == nil {
		t.Fatal("a Catalogue nobody loaded read its declarations from somewhere")
	}
}

func load(t *testing.T) *Catalogue {
	t.Helper()
	c, err := Load()
	if err != nil {
		t.Fatal(err)
	}
	if len(c.Operations) == 0 {
		t.Fatal("embedded catalogue is empty")
	}
	return c
}

// The property the whole design rests on: an agent has complete coverage and
// cannot be the last hand on a clinical write.
func TestNoToolCommitsAWrite(t *testing.T) {
	for id, op := range load(t).Operations {
		if op.Kind == "write" && !strings.HasPrefix(op.Tool, "propose_") {
			t.Errorf("%s exposes %q, which is not a proposal", id, op.Tool)
		}
		for _, banned := range []string{"confirm", "commit", "approve", "sign"} {
			if strings.Contains(op.Tool, banned) {
				t.Errorf("%s exposes %q, which reads as a commit verb", id, op.Tool)
			}
		}
	}
}

func TestEveryOperationIsOnBothSurfaces(t *testing.T) {
	for id, op := range load(t).Operations {
		got := strings.Join(op.Surfaces, ",")
		if !strings.Contains(got, "rendered") || !strings.Contains(got, "mcp") {
			t.Errorf("%s has surfaces %v", id, op.Surfaces)
		}
	}
}

func TestAnAccountOnlySeesToolsItCanUse(t *testing.T) {
	c := load(t)
	pharmacist := map[string]bool{"patient.find": true, "pharmacy.dispense": true}
	ops := c.For(pharmacist, nil)
	if len(ops) != 1 || ops[0].ID != "phc.op.pharmacy-dispense" {
		t.Fatalf("pharmacist saw %d operations, want just dispense", len(ops))
	}
	if len(c.For(map[string]bool{}, nil)) != 0 {
		t.Error("an account with no capabilities saw tools")
	}
	all := map[string]bool{}
	for _, cap := range c.Capabilities {
		all[cap] = true
	}
	if len(c.For(all, nil)) != len(c.Operations) {
		t.Error("an account with every capability could not see every operation")
	}
}

// catalogue.json is embedded at build time and holds every bundle's atoms, so
// a server pointed at a kernel that loaded one bundle must not offer another
// bundle's tools: the kernel answers those with a 404.
func TestOnlyTheLoadedBundlesOperationsAreOffered(t *testing.T) {
	c := load(t)
	all := map[string]bool{}
	for _, cap := range c.Capabilities {
		all[cap] = true
	}
	var one string
	for id := range c.Operations {
		one = id
		break
	}
	ops := c.For(all, map[string]bool{one: true})
	if len(ops) != 1 || ops[0].ID != one {
		t.Fatalf("bundle of one offered %d tools, want just %s", len(ops), one)
	}
	if len(c.For(all, nil)) != len(c.Operations) {
		t.Error("no bundle given must not narrow: that is the offline hatch")
	}
}

func TestWriteToolsSayTheyDoNotCommit(t *testing.T) {
	for id, op := range load(t).Operations {
		if op.Kind != "write" {
			continue
		}
		d := op.ToolDescription()
		if !strings.Contains(d, "does not commit it") {
			t.Errorf("%s does not tell an agent it is only a proposal", id)
		}
		if op.Irreversibility == "irreversible" && !strings.Contains(d, "never from here") {
			t.Errorf("%s is irreversible but does not say so", id)
		}
	}
}

func TestUnverifiedOperationsAdmitIt(t *testing.T) {
	for id, op := range load(t).Operations {
		if op.Verified != "verified" && !strings.Contains(op.ToolDescription(), "not been run") {
			t.Errorf("%s is %s but its description does not say so", id, op.Verified)
		}
	}
}

// Khoj is not a catalogue.Operation: it is a manifest-level constant, so an
// agent reading the embedded catalogue learns the ask-and-search tool's name
// without a declaration type invented just to carry one word. This is the
// property main.go's tool registration depends on: it reads
// cat.Manifest.Khoj.Tool and .Description verbatim.
func TestKhojIsReachableFromTheCompiledCatalogue(t *testing.T) {
	khoj := load(t).Manifest.Khoj
	if khoj.Tool != "khoj" {
		t.Fatalf("manifest.khoj.tool = %q, want %q", khoj.Tool, "khoj")
	}
	if khoj.Endpoint == "" {
		t.Fatal("manifest.khoj.endpoint is empty")
	}
	d := strings.ToLower(khoj.Description)
	for _, want := range []string{"search", "answer", "propos", "never commit"} {
		if !strings.Contains(d, want) {
			t.Errorf("khoj description %q is missing %q", khoj.Description, want)
		}
	}
}

func TestInputSchemaMatchesTheQuestionnaire(t *testing.T) {
	c := load(t)
	vitals := c.Operations["phc.op.vitals-record"]
	schema := vitals.InputSchema()
	props := schema["properties"].(map[string]any)
	for _, want := range []string{"systolic", "diastolic", "pulse", "override_reason"} {
		if _, ok := props[want]; !ok {
			t.Errorf("vitals schema has no %q", want)
		}
	}
	required := strings.Join(schema["required"].([]string), ",")
	if !strings.Contains(required, "systolic") {
		t.Errorf("systolic is required on the form but not in the schema: %v", required)
	}
	if strings.Contains(required, "weight") {
		t.Error("weight is optional on the form but required in the schema")
	}

	reg := c.Operations["phc.op.patient-register"].InputSchema()
	sex := reg["properties"].(map[string]any)["sex"].(map[string]any)
	if _, ok := sex["enum"]; !ok {
		t.Error("a choice question did not become an enum")
	}
}
