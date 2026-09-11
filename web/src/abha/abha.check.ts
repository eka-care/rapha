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
import { readFileSync } from "node:fs";
import {
  ABHA_PENDING, ageFrom, demographicsFrom, environmentLine, identifierFrom, mobileHint,
  payloadFor, type AbhaOutcome,
} from "./sdk.ts";

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
const linked: AbhaOutcome = { kind: "linked", raw: success, ...found };
assert.deepEqual(payloadFor(linked), { abha_number: "12-3456-7890-1234" });

assert.equal(
  payloadFor({ kind: "linked", raw: null, number: "", address: "a@sbx", name: "" }).abha_number, "a@sbx",
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

// -------------------------------------------------- the profile, and the form

/** The profile as the staging bundle builds it. Every key below appears in
 *  `getMockAuthVerifyResponse` in @eka-care/abha-stg@0.1.126, read off the
 *  script on 2026-09-11. It is not four fields: the journey knows the name in
 *  four spellings, the gender as a code, a date of birth and an address down
 *  to the ward. */
const profile = {
  fln: "Lakshmi Devi", fn: "Lakshmi", mn: "", ln: "Devi",
  gen: "F", dob: "1990-04-17", mobile: "9876543210",
  oid: "oid-1", uuid: "uuid-1", profile_photo: "data:image/png;base64,AAAA",
  abha_number: "12-3456-7890-1234", kyc_verified: true,
  pincode: "560103", address: "12, Second Cross",
  state_code: "29", state_name: "Karnataka",
  district_code: "572", district_name: "Bengaluru Urban",
  sub_district_code: "5723", sub_district_name: "Bengaluru South",
  town_code: "", town_name: "",
  village_code: "6011", village_name: "Kadugodi",
  ward_code: "", ward_name: "",
  "health-ids": ["lakshmi.devi@sbx"],
};
const full = { response: { skip_state: "abha_end", method: 2, txn_id: "t-2", data: { tokens: { sess: "S", refresh: "R" }, profile } } };

// Three branches of the bundle build `health-ids` as a list of plain strings
// rather than a list of objects. Reading only the object shape lost the
// address on those, silently, and an address is the identifier when there is
// no number.
assert.equal(identifierFrom(full).address, "lakshmi.devi@sbx", "health-ids may be a list of strings");

// The real registration questionnaire, so this check fails if a link_id is
// renamed rather than passing against a copy of it that nobody updated.
const register = JSON.parse(
  readFileSync(new URL("../../../questionnaires/phc.schema.register-v1.json", import.meta.url), "utf8"),
) as { questions: { link_id: string; type: string; answer_option?: { value: string }[] }[] };

const filled = demographicsFrom(full, register.questions);
assert.equal(filled.name, "Lakshmi Devi");
assert.equal(filled.sex, "female", "`gen` is the code M/F/O, and the form asks for the word");
assert.equal(filled.phone, "9876543210");
assert.equal(filled.village, "Kadugodi", "village_name, not the code and not the district");

// Not asked by this questionnaire, so not answered, however much the profile
// carries. A form gets the answers it asks for and no stowaways.
for (const absent of ["district", "state", "pincode", "address", "date_of_birth"]) {
  assert.ok(!(absent in filled), `${absent} is not on this form and is not written to it`);
}

// THE RULE. A journey fills demographics; it never fills a consent, a
// declaration, or a confirm. Those are a person saying yes and no gateway can
// say it for them. Asked here with the questions themselves, so a schema that
// grows another consent is covered without editing this line.
for (const q of register.questions) {
  if (/consent|declin|confirm/.test(q.link_id)) {
    assert.ok(!(q.link_id in filled), `${q.link_id} is never prefilled by the journey`);
  }
}
assert.ok(!("capture_consent" in filled) && !("capture_declined" in filled));

// A value the form could not display is worse than no value: a choice whose
// answer is off its own option list renders as an empty select over a payload
// that still carries it.
const oddSex = register.questions.map((q) =>
  q.link_id === "sex" ? { ...q, answer_option: [{ value: "F" }, { value: "M" }] } : q);
assert.ok(!("sex" in demographicsFrom(full, oddSex)), "an answer the question does not offer is dropped");

// Thin and string payloads. Neither throws, neither invents.
assert.deepEqual(demographicsFrom({ response: "" }, register.questions), {});
assert.deepEqual(demographicsFrom(undefined, register.questions), {});
assert.deepEqual(demographicsFrom("not json at all", register.questions), {});
assert.deepEqual(
  demographicsFrom(JSON.stringify(full), register.questions), filled,
  "the webview branch stringifies, and reads back the same",
);

// A profile with nothing in it fills nothing, rather than filling blanks.
assert.deepEqual(demographicsFrom({ response: { data: { profile: { fln: "", gen: "", mobile: "" } } } }, register.questions), {});

// An age is derived, never guessed. The bundle assembles `dob` as
// `${year}-${month}-${day}` from three fields that can all be missing, so a
// real payload carries strings like these, and one gateway branch passes a day
// first date straight through.
const today = new Date();
const back = (years: number, days = 0) => {
  const d = new Date(today.getFullYear() - years, today.getMonth(), today.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
assert.equal(ageFrom(back(30)), "30", "a birthday today has been reached");
assert.equal(ageFrom(back(30, 1)), "29", "a birthday tomorrow has not");
const dayFirst = back(30).split("-").reverse().join("-");
assert.equal(ageFrom(dayFirst), "30", "the gateway's own date_of_birth is day first");
for (const junk of ["", "undefined-NaN-NaN", "1990", "31-02-1990", "not a date", "0000-00-00"]) {
  assert.equal(ageFrom(junk), "", `${junk || "an empty dob"} produces no age at all`);
}

// What the clerk typed into the palette, handed to the journey only when it is
// actually a mobile number. A name must never become an identifier.
assert.equal(mobileHint("9876543210"), "9876543210");
assert.equal(mobileHint(" +91 98765-43210 "), "9876543210", "the SDK strips spaces, dashes and +91 too");
for (const typed of ["Lakshmi", "", undefined, "1234567890", "98765", "12-3456-7890-1234"]) {
  assert.equal(mobileHint(typed), undefined, `"${typed ?? ""}" is not handed over as a mobile`);
}


// Which create-on-miss opens the journey is the operation's own `emits`, so
// the health centre's registration gets it and the laboratory's accession does
// not, with neither bundle naming the other. If this ever stops holding, a
// technologist accessioning a referral is shown a national identity journey.
const catalogue = JSON.parse(
  readFileSync(new URL("../../../catalogue/catalogue.json", import.meta.url), "utf8"),
) as { operations: Record<string, { emits: string[] }> };
assert.ok(catalogue.operations["phc.op.patient-register"].emits.includes(ABHA_PENDING));
assert.ok(!catalogue.operations["lab.op.referral-accession"].emits.includes(ABHA_PENDING));

console.log("ok   abha: the profile fills the registration form, and never a consent");
