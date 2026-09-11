/** One runnable check: the client validator says exactly what the server says.
 *
 *  Run: node --experimental-strip-types src/validate.check.ts   (from web/)
 *  It needs python3 on PATH, because it diffs against the real
 *  catalogue/validate.py rather than against a copy of its expectations.
 */
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import { enabled, prune, raisedFlags, validate, walk } from "./validate.ts";

const root = fileURLToPath(new URL("../../", import.meta.url));
const load = (id: string) => JSON.parse(readFileSync(`${root}questionnaires/${id}.json`, "utf8"));

const CASES: [string, Record<string, unknown>][] = [
  ["phc.schema.vitals-v1", {}],
  ["phc.schema.vitals-v1", { systolic: 140, diastolic: 90, pulse: 78 }],
  ["phc.schema.vitals-v1", { systolic: 400, diastolic: 90, pulse: 78 }],
  ["phc.schema.vitals-v1", { systolic: 400, diastolic: 90, pulse: 78, override_reason: "cuff reads high, repeated" }],
  ["phc.schema.vitals-v1", { systolic: "one forty", diastolic: 90, pulse: 78 }],
  ["phc.schema.vitals-v1", { systolic: "140", diastolic: "90", pulse: "78", spo2: 91 }],
  ["phc.schema.vitals-v1", { systolic: 140, diastolic: 90, pulse: 78, temperature: 100 }],
  ["phc.schema.vitals-v1", { systolic: 140, diastolic: 90, pulse: 78, temperature: 38.9 }],
  ["phc.schema.vitals-v1", { systolic: 140, diastolic: 90, pulse: 78, bp: 140 }],
  ["phc.schema.vitals-v1", { systolic: 140, diastolic: 90, pulse: 78, weight: "12.5" }],
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "martian", phone: "9", village: "V" }],
  ["phc.schema.register-v1", { name: "A", age: 200, sex: "female", phone: "9", village: "V" }],
  ["phc.schema.register-v1", { name: "A", age: "41.5", sex: "female", phone: "9", village: "V" }],
  ["phc.schema.consult-v1", {}],
  ["phc.schema.dispense-v1", {}],
  // The consent questions. A flag with no critical band is the second form of
  // raisedFlags, and until these cases existed the browser and the server
  // disagreed about it with nothing to notice.
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "female", phone: "9", village: "V", capture_consent: true }],
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "female", phone: "9", village: "V", capture_declined: true }],
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "female", phone: "9", village: "V", capture_consent: true, capture_declined: true }],
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "female", phone: "9", village: "V", capture_consent: "yes" }],
  ["phc.schema.register-v1", { name: "A", age: 41, sex: "female", phone: "9", village: "V", capture_consent: false }],
  ["phc.schema.consult-v1", { assessment: "viral fever", capture_stop: true }],
];

const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(root.replace(/\/$/, ""))})
from catalogue import validate as V
out = []
for schema_id, payload in json.load(sys.stdin):
    schema = V.load(schema_id)
    out.append({"problems": V.make_validator(schema)({"id": schema_id}, payload),
                "flags": sorted(V.flags(schema, payload))})
print(json.dumps(out))
`;

const expected = JSON.parse(
  execFileSync("python3", ["-c", py], { input: JSON.stringify(CASES), encoding: "utf8" }),
);

CASES.forEach(([id, payload], i) => {
  const schema = load(id);
  const mine = { problems: validate(schema, payload).map((p) => p.message), flags: raisedFlags(schema, payload).sort() };
  assert.deepEqual(mine, expected[i], `case ${i} ${id} ${JSON.stringify(payload)}`);
  // Every problem must carry the link_id it belongs to, or the form cannot
  // put the message under the right field.
  for (const p of validate(schema, payload)) {
    assert.ok(p.message.startsWith(p.link_id), `problem not attributable: ${p.message}`);
  }
});

// ------------------------------------------------------------ enable_when
//
// The server does not read enable_when (bundles/LAB-LOG.md 13), so there is
// nothing to diff against here: these assert the renderer's own promise, that
// a question the payload switched off is neither asked nor sent.

const panel = load("lab.schema.panel-result-v1");
const analytes = (payload: Record<string, unknown>) =>
  walk(panel.questions).filter((q) => enabled(q, payload)).map((q) => q.link_id);

// Nothing chosen: no analyte is asked, and the panel question itself still is.
assert.deepEqual(analytes({}), ["panel", "override_reason"]);
assert.deepEqual(analytes({ panel: "cbc" }),
  ["panel", "haemoglobin", "wbc", "platelets", "override_reason"]);
assert.deepEqual(analytes({ panel: "bmp" }),
  ["panel", "glucose", "creatinine", "sodium", "potassium", "override_reason"]);

// Switching the panel takes the other panel's answers with it, because the
// server would accept them: a glucose on a CBC commits.
assert.deepEqual(prune(panel, { panel: "bmp", glucose: 90, haemoglobin: 13 }),
  { panel: "bmp", glucose: 90 });
assert.deepEqual(prune(panel, { panel: "cbc", haemoglobin: 13 }),
  { panel: "cbc", haemoglobin: 13 });
// Nothing chosen yet means nothing analyte-shaped survives.
assert.deepEqual(prune(panel, { haemoglobin: 13 }), {});

// `exists`, the other operator in the questionnaires.
const labResult = load("phc.schema.lab-result-v1");
const override = walk(labResult.questions).find((q) => q.link_id === "override_reason")!;
assert.equal(enabled(override, {}), false);
assert.equal(enabled(override, { value: 4.2 }), true);

// A question that is both required and conditional is asked anyway: the
// server asks for it regardless, so hiding it would build a form that cannot
// be committed and will not say why.
const req = { link_id: "r", text: "r", type: "string", required: true,
  enable_when: [{ question: "panel", operator: "equals", answer: "cbc" }] };
assert.deepEqual(prune({ ...panel, questions: [...panel.questions, req] },
  { panel: "bmp", r: "kept" }), { panel: "bmp", r: "kept" });

// An operator this renderer has never heard of must not hide anything: a
// hidden required field is a form that cannot be completed and will not say
// why.
assert.equal(enabled({ link_id: "x", text: "x", type: "string",
  enable_when: [{ question: "panel", operator: "matches-regex", answer: "c.*" }] }, {}), true);

console.log(`ok   web validator matches catalogue/validate.py on ${CASES.length} cases`);
console.log("ok   enable_when hides the questions the chosen panel does not use");
