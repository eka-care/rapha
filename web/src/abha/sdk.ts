/** The ABHA web SDK, the parts of it that are pure.
 *
 *  Everything in this file was read off the loaded bundle in a browser on
 *  2026-09-11, not from the reference, because the reference and the shipped
 *  script disagree in four places. What the script actually does:
 *
 *  - `initAbhaApp(a)` reads `{clientId, containerId, urlParams, method, theme,
 *    data, appVersion, onSuccess, onError, onAbhaClose}` off its one argument,
 *    and reads `onKYCSuccess`, `onConsentSuccess`, `onSkipAbha` and
 *    `onAppointmentBookedSuccess` off the same object. There is no
 *    `onAbhaFailure` prop: the string does not appear in the bundle at all.
 *    The caller's `onSuccess` is what the SDK internally calls onAbhaSuccess.
 *  - It RETURNS its own unmount function, and sets `window.closeAbhaApp` to
 *    the same function as its last statement. That is why `closeAbhaApp` is
 *    undefined before the first mount. It also stays defined after unmounting,
 *    so its presence proves nothing; the returned function is the handle to
 *    keep.
 *  - `clientId` is a platform name, not an API credential. The bundle branches
 *    on "www-eka", "androidp", "patient-app-ios", "androiddoc",
 *    "doctor-app-ios", "doctor-ipad-ios", "doc-web" and "ext", and everything
 *    else falls through to a "phr" default.
 *  - The staging package sets its own environment inside initAbhaApp
 *    (`setEnv({..., env: "DEV"})`), so which package is loaded is which
 *    environment. There is no environment argument to pass.
 *
 *  The live enum values, read off `window` after the staging script loaded:
 *
 *    ABHA_INIT_FLOW        scan-share | scan-share-kiosk | abha-kyc | consent |
 *                          abha-registration
 *    ABHA_AUTH_FLOW_METHOD phr_address | mobile | abha_number | aadhaar_number |
 *                          registration_type
 *    ABHA_V3_SKIP_STATES   abha_end | confirm_mobile_otp | abha_create |
 *                          abha_select | request_mobile_otp
 *    REGISTRATION_TYPE     login | create
 *
 *  Note that ABHA_INIT_FLOW is `data.flow` and is NOT the `method` argument.
 *  The method strings in the bundle are `login_or_create_abha` (the store's own
 *  default), `login_abha_with_mobile` and `login_with_abha`. The reference's
 *  `create_abha_with_mobile` does not appear in the shipped staging script.
 */

/** The operation whose payload this journey fills. The second hard-code in
 *  this renderer, and it is the same kind as the first (web/src/messages.ts's
 *  ABHA regex): ABHA is a national identifier with one national journey, not a
 *  facility's concept, so there is no declaration for a bundle to disagree
 *  with. A bundle that does not declare this operation simply never mounts it.
 */
export const ABHA_OP = "phc.op.abha-link";

/** What an operation emits when it has just made a patient who has no national
 *  account yet. It is the bundle's own word for "an ABHA belongs here", and it
 *  is what decides whether the create-on-miss opens the journey: the health
 *  centre's registration emits it, the laboratory's accession does not, and
 *  neither file mentions the other. */
export const ABHA_PENDING = "abha.pending";

/** The bundle's own word for "this person has a national account". The third
 *  hard-code in this file and the same kind as the two above: `abha.linked` is
 *  decided by whether a patient row carries an ABHA number, which is a fact
 *  about the national identifier and not a facility's judgement, so no bundle
 *  can declare it differently. The queue draws the lotus beside a name when a
 *  row carries it. ui.check.ts asserts a workflow still declares this state,
 *  because a rename would make the lotus silently disappear rather than fail.
 */
export const ABHA_LINKED = "abha.linked";

/** GET /abha/config. The server names the environment; the browser does not
 *  choose it and no credential is in here. */
export type AbhaConfig = {
  environment: "staging" | "production";
  package: string;
  script: string;
  css: string;
  client_id: string;
  theme: unknown;
  hip_id: string | null;
};

export type AbhaOutcome =
  /** `raw` is the success payload exactly as the SDK fired it, kept because
   *  the identifier is not all of it: the profile underneath carries the
   *  demographics a registration form asks for. Read with demographicsFrom,
   *  never indexed. */
  | { kind: "linked"; number: string; address: string; name: string; raw: unknown }
  /** The patient is registered, tokened and seen with ABHA pending. This is a
   *  first class outcome and not an error: a patient who cannot finish the
   *  journey at the counter must never be a patient who cannot be seen. */
  | { kind: "skipped"; identifier: string; identifier_type: string }
  | { kind: "failed"; reason: string }
  | { kind: "closed" };

// ------------------------------------------------------------ the result

const NUMBER_KEYS = ["abha_number"];
/** `health-ids` is an array, and the bundle fills it BOTH ways: three call
 *  sites build `[profile.abha_address]`, a list of plain strings, and the
 *  branch the mock declares builds a list of objects. So it is an address key
 *  AND it is walked into. */
const ADDRESS_KEYS = ["abha_address", "phr_address", "health_id", "health-ids"];
const NAME_KEYS = ["fln", "name", "full_name"];

/** Pull the identifier out of whatever the journey handed back.
 *
 *  Six call sites in the bundle fire onAbhaSuccess and they do not agree on a
 *  shape. The one seen most is
 *  `{response: {skip_state, method, txn_id, data: {tokens, profile: {...,
 *  abha_number, "health-ids": []}}}}`; one fires `{response: ""}`; and the
 *  native webview branch fires a JSON STRING rather than an object. So this
 *  walks the payload for the first non-empty value under a known key instead
 *  of indexing a path that four of the six would miss.
 */
export function identifierFrom(result: unknown): { number: string; address: string; name: string } {
  const found = { number: "", address: "", name: "" };
  const seen = new Set<unknown>();

  const take = (slot: "number" | "address" | "name", value: unknown) => {
    if (Array.isArray(value)) return value.forEach((v) => take(slot, v));
    const text = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
    if (text && !found[slot]) found[slot] = text;
  };

  const walk = (node: unknown) => {
    if (typeof node === "string") {
      // The webview branch stringifies. Ours does not, but a caller that
      // proxies this through a bridge would arrive here.
      const text = node.trim();
      if (text.startsWith("{")) {
        try {
          walk(JSON.parse(text));
        } catch {
          /* a plain string, not a payload */
        }
      }
      return;
    }
    if (!node || typeof node !== "object" || seen.has(node)) return;
    seen.add(node);
    // Object.entries covers an array too, with its indices as the keys, so
    // there is one traversal here and not two.
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      if (NUMBER_KEYS.includes(key)) take("number", value);
      else if (ADDRESS_KEYS.includes(key)) { take("address", value); walk(value); }
      else if (NAME_KEYS.includes(key)) take("name", value);
      else walk(value);
    }
  };

  walk(result);
  return found;
}

/** What the journey produced, as this operation's questionnaire asks for it.
 *
 *  ONE field, and it is the only one the journey actually knows.
 *
 *  `method` and `consent_given` are the questionnaire's other two answers and
 *  this function deliberately fills neither, because the journey does not say.
 *  The success payload carries no create-or-link flag: the branch that fires it
 *  has already settled `skip_state` to `abha_end`, which a new account and an
 *  existing one both reach. And nothing in the payload is the patient saying
 *  yes. Prefilling either one would be the software answering a question on a
 *  person's behalf and then recording the answer as theirs, which is the same
 *  lie the hand built form told, moved one screen later. The clerk watched the
 *  journey and is the better witness; `consent_given` is `required`, so the
 *  commit stays blocked until a person ticks it.
 */
export function payloadFor(outcome: AbhaOutcome): Record<string, unknown> {
  if (outcome.kind !== "linked") return {};
  return { abha_number: outcome.number || outcome.address };
}

// ------------------------------------------------------------ the words

/** The script did not load. One sentence, and it is the next step: a blank
 *  modal with no way out is the one outcome that is not allowed. The detail
 *  goes to the console, not to the clerk. */
export function loadFailure(config: AbhaConfig | null): string {
  return config
    ? "The ABHA SDK did not load. Register without one."
    : "This kernel has no ABHA configuration. Register without one.";
}

/** Which environment is loaded. Staging is a chip. Production is a warning,
 *  because it sends a real OTP to a real phone and creates a permanent
 *  national health account. */
export function environmentLine(config: AbhaConfig): { text: string; danger: boolean } {
  return config.environment === "production"
    ? { text: "Production: real OTPs, real accounts.", danger: true }
    : { text: "staging", danger: false };
}

// ------------------------------------------------------- the demographics

/** The ABHA profile, read off the loaded staging bundle
 *  (@eka-care/abha-stg@0.1.126) on 2026-09-11 and not off the reference. Its
 *  own `getMockAuthVerifyResponse` is the declaration of the success shape,
 *  and every branch that fires onAbhaSuccess builds `data.profile` out of
 *  exactly these keys:
 *
 *    fln fn mn ln gen dob mobile oid uuid profile_photo abha_number
 *    kyc_verified pincode address state_code state_name district_code
 *    district_name sub_district_code sub_district_name town_code town_name
 *    village_code village_name ward_code ward_name health-ids
 *
 *  So it is not four fields. It is a name in four spellings, a gender code, a
 *  date of birth and a whole address down to the ward.
 *
 *  Two traps, both real in that bundle:
 *  - `gen` is the code, not the word: the SDK's own picker is
 *    `[{id:"M",name:"Male"},{id:"F",name:"Female"},{id:"O",name:"Other"}]`.
 *  - `dob` is assembled as `${year}-${month}-${day}` from three fields that
 *    may all be missing, so a real payload can carry the literal string
 *    "undefined-NaN-NaN". One branch passes the gateway's `date_of_birth`
 *    straight through instead, which is day first. Hence the strict parse
 *    below: anything that is not plainly a date produces no age at all.
 */
const PROFILE_KEYS = [
  "fln", "fn", "mn", "ln", "gen", "dob", "mobile", "abha_number",
  "pincode", "address", "state_name", "district_name", "sub_district_name",
  "town_name", "village_name", "ward_name",
];

/** The profile, wherever in the payload it is. Same reason identifierFrom
 *  walks: six call sites fire onAbhaSuccess and the wrapper around the profile
 *  is not the same in all of them. */
export function profileFrom(result: unknown): Record<string, string> {
  const found: Record<string, string> = {};
  const seen = new Set<unknown>();
  const walkIt = (node: unknown) => {
    if (typeof node === "string") {
      const text = node.trim();
      if (text.startsWith("{")) {
        try { walkIt(JSON.parse(text)); } catch { /* a plain string */ }
      }
      return;
    }
    if (!node || typeof node !== "object" || seen.has(node)) return;
    seen.add(node);
    for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
      if (PROFILE_KEYS.includes(key)) {
        const text = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
        if (text && !found[key]) found[key] = text;
      } else walkIt(value);
    }
  };
  walkIt(result);
  return found;
}

const GENDERS: Record<string, string> = { M: "male", F: "female", O: "other" };

/** Completed years, or nothing. A date this cannot read plainly is not
 *  guessed at: an age is a required answer on the form and a wrong one is
 *  worse than an empty one. */
export function ageFrom(dob: string): string {
  const parts = /^(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})$/.exec(dob.trim());
  if (!parts) return "";
  const [, a, m, b] = parts;
  const [y, d] = a.length === 4 ? [a, b] : [b, a];
  if (y.length !== 4) return "";
  const born = new Date(Number(y), Number(m) - 1, Number(d));
  if (born.getMonth() !== Number(m) - 1 || born.getDate() !== Number(d)) return "";
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const before =
    now.getMonth() < born.getMonth() ||
    (now.getMonth() === born.getMonth() && now.getDate() < born.getDate());
  if (before) age -= 1;
  return age >= 0 && age <= 150 ? String(age) : "";
}

/** Profile key to questionnaire answer. The right hand side is this bundle's
 *  vocabulary and the left is the national one; a bundle that asks for a
 *  district gets a district here without anybody editing this file, and a
 *  bundle that does not ask is not told. */
const DEMOGRAPHICS: Record<string, (p: Record<string, string>) => string> = {
  name: (p) => p.fln || [p.fn, p.mn, p.ln].filter(Boolean).join(" "),
  age: (p) => ageFrom(p.dob ?? ""),
  date_of_birth: (p) => p.dob ?? "",
  sex: (p) => GENDERS[(p.gen ?? "").toUpperCase()] ?? "",
  gender: (p) => GENDERS[(p.gen ?? "").toUpperCase()] ?? "",
  phone: (p) => p.mobile ?? "",
  mobile: (p) => p.mobile ?? "",
  village: (p) => p.village_name ?? "",
  town: (p) => p.town_name ?? "",
  ward: (p) => p.ward_name ?? "",
  sub_district: (p) => p.sub_district_name ?? "",
  district: (p) => p.district_name ?? "",
  state: (p) => p.state_name ?? "",
  pincode: (p) => p.pincode ?? "",
  address: (p) => p.address ?? "",
};

/** What an authenticated ABHA journey can answer on THIS questionnaire.
 *
 *  Asked of the questions rather than of a field list, because a value the
 *  form cannot show is worse than no value: a `choice` whose answer is not one
 *  of its own options renders as an empty select over a payload that still
 *  carries the answer, which is a commit nobody read. So an answer is written
 *  only when the question exists, the question has no option list or the value
 *  is on it, and the profile actually carried it.
 *
 *  Nothing here can fill a consent or a confirm. Those are not demographics,
 *  they are a person saying yes, and a journey cannot say it for them: the
 *  left hand column above is the whole of what this can write.
 */
export function demographicsFrom(
  result: unknown,
  questions: { link_id: string; type: string; answer_option?: { value: string }[] }[],
): Record<string, string> {
  const profile = profileFrom(result);
  const out: Record<string, string> = {};
  for (const q of questions) {
    const value = DEMOGRAPHICS[q.link_id]?.(profile) ?? "";
    if (!value) continue;
    const options = q.answer_option?.map((o) => o.value);
    if (options && !options.includes(value)) continue;
    out[q.link_id] = value;
  }
  return out;
}

/** What the clerk typed in the palette, if it was a mobile number, so that
 *  nobody types it twice. The SDK's own `handleIdentifier` strips spaces and
 *  dashes and accepts +91, and `isValidMobile` is the leading digit rule
 *  below; this is the same test, run before the journey is opened rather than
 *  after, because a search string that is a name must not become an
 *  identifier. */
export function mobileHint(typed: string | undefined): string | undefined {
  const digits = (typed ?? "").replace(/[\s-]/g, "").replace(/^\+?91/, "");
  return /^[6-9]\d{9}$/.test(digits) ? digits : undefined;
}
