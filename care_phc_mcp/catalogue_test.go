package main

import (
	"strings"
	"testing"
)

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
