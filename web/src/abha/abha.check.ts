/** One runnable check for the ABHA journey's pure half.
 *
 *  Run: node --experimental-strip-types src/abha/abha.check.ts   (from web/)
 *
 *  What it cannot check is the SDK itself, which needs a browser and a
 *  network. What it does check is the part that would be silently wrong: which
 *  field of a six-shaped success payload is the identifier, and that a journey
 *  that did not end in a link produces no payload at all.
 *
 *  The payload shapes below were read off the loaded staging bundle on
 *  2026-09-11, not invented: `getMockAuthVerifyResponse` is the SDK's own
 *  declaration of its success shape, and `onAbhaSuccess({response: ""})` is a
 *  real branch in it.
 */
import assert from "node:assert/strict";
import { environmentLine, identifierFrom, payloadFor, type AbhaOutcome } from "./sdk.ts";

// The shape the SDK's own mock declares, trimmed to what matters here.
const success = {
  response: {
    skip_state: "abha_end",
    method: 2,
    txn_id: "t-1",
    data: {
      tokens: { sess: "SESSION-TOKEN", refresh: "REFRESH-TOKEN" },
      profile: {
        fln: "Lakshmi Devi", mobile: "9876543210", oid: "oid-1",
        abha_number: "12-3456-7890-1234", kyc_verified: true,
        "health-ids": [{ abha_address: "lakshmi.devi@sbx" }],
      },
    },
  },
};

const found = identifierFrom(success);
assert.equal(found.number, "12-3456-7890-1234", "the ABHA number is under data.profile");
assert.equal(found.address, "lakshmi.devi@sbx", "the address is inside health-ids, one level further down");
assert.equal(found.name, "Lakshmi Devi");

// A token is not an identifier and must never be mistaken for one.
assert.ok(!Object.values(found).some((v) => /TOKEN/.test(v)), "no token reaches the form");

// The webview branch stringifies the same payload. Ours does not, but a
// bridge would, and reading it as a plain string would put "[object Object]"
// on a patient row.
assert.deepEqual(identifierFrom(JSON.stringify(success)), found, "a stringified payload reads the same");

// Two real branches that carry nothing. Neither may throw and neither may
// invent an identifier.
assert.deepEqual(identifierFrom({ response: "" }), { number: "", address: "", name: "" });
assert.deepEqual(identifierFrom(undefined), { number: "", address: "", name: "" });

// The questionnaire's payload, filled from the result rather than typed. One
// key, and it is the only one the journey knows. `method` and `consent_given`
// are answered by the person who watched the journey: the success payload says
// neither, and filling them here would record the software's guess as the
// clerk's answer. `consent_given` is `required` on the schema, so an unticked
// box is a blocked commit rather than a fabricated yes.
const linked: AbhaOutcome = { kind: "linked", ...found };
assert.deepEqual(payloadFor(linked), { abha_number: "12-3456-7890-1234" });

assert.equal(
  payloadFor({ kind: "linked", number: "", address: "a@sbx", name: "" }).abha_number, "a@sbx",
  "an address is written when there is no number, rather than an empty row",
);

// Everything that is not a link writes nothing. This is the property that
// matters: a skipped, failed or closed journey must not put a half filled
// irreversible payload in front of a person.
for (const outcome of [
  { kind: "skipped", identifier: "", identifier_type: "aadhaar_number" },
  { kind: "failed", reason: "gateway down." },
  { kind: "closed" },
] as AbhaOutcome[]) {
  assert.deepEqual(payloadFor(outcome), {}, `${outcome.kind} fills no field`);
}

// The environment is a chip on staging and a warning on production. It used to
// be a sentence in both, which a clinician skipped, so the one that matters was
// as easy to skip as the one that does not.
assert.deepEqual(
  environmentLine({ environment: "staging" } as never),
  { text: "staging", danger: false },
);
const prod = environmentLine({ environment: "production" } as never);
assert.equal(prod.danger, true, "production is drawn as a warning");
assert.ok(prod.text.split(" ").length <= 8, "and it is one short line, not a disclaimer");

console.log("ok   abha: the identifier is read off the journey, and only a link fills the form");
