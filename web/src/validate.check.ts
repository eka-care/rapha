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
import { raisedFlags, validate } from "./validate.ts";

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

console.log(`ok   web validator matches catalogue/validate.py on ${CASES.length} cases`);
