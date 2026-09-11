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
  | { kind: "linked"; number: string; address: string; name: string }
  /** The patient is registered, tokened and seen with ABHA pending. This is a
   *  first class outcome and not an error: a patient who cannot finish the
   *  journey at the counter must never be a patient who cannot be seen. */
  | { kind: "skipped"; identifier: string; identifier_type: string }
  | { kind: "failed"; reason: string }
  | { kind: "closed" };

// ------------------------------------------------------------ the result

const NUMBER_KEYS = ["abha_number"];
const ADDRESS_KEYS = ["abha_address", "phr_address", "health_id"];
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
      else if (ADDRESS_KEYS.includes(key)) take("address", value);
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

/** One plain sentence per outcome. Every one of them says what happens next,
 *  because every one of them has a next, including the failures. */
export function sentence(outcome: AbhaOutcome | null, loading: string): string {
  if (!outcome) return loading;
  switch (outcome.kind) {
    case "linked":
      return `The journey returned ${outcome.number || outcome.address || "an identifier"}. ` +
        "It is in the form below and nothing is recorded yet: read it back to the patient, " +
        "answer the two questions the journey does not answer, then tap Continue and tick " +
        "the box. Linking an ABHA cannot be undone.";
    case "skipped":
      return "Skipped. The patient is registered, has a token and will be seen. " +
        "The visit carries ABHA pending and joins the unlinked worklist, which is a first " +
        "class path and not a failure.";
    case "failed":
      return `${outcome.reason} The patient is registered, has a token and will be seen. ` +
        "The visit carries ABHA pending. Do not retry while the queue waits.";
    case "closed":
      return "The journey was closed before it finished. The patient is registered, has a " +
        "token and will be seen, with ABHA pending. Reopen it from this thread at any time.";
  }
}

/** The script did not load. Says which of the three it is, and the keyboard
 *  path is in every one of them, because a blank modal is the one outcome that
 *  is not allowed. */
export function loadFailure(config: AbhaConfig | null, detail: string): string {
  if (!config)
    return "This kernel did not answer with an ABHA configuration, so the journey cannot " +
      "be opened. Register the patient without one: they keep their token and their place " +
      `in the queue. (${detail})`;
  return `The ABHA SDK did not load from ${config.script}. That is usually no network from ` +
    "this browser, or unpkg being unreachable. The patient is registered and will be seen " +
    `with ABHA pending; link it at the next contact. (${detail})`;
}

/** Which environment is loaded, in words nobody can misread. Production sends
 *  real one time passwords to real phones and creates permanent national
 *  health accounts, so it says so. */
export function environmentLine(config: AbhaConfig): { text: string; danger: boolean } {
  return config.environment === "production"
    ? { text: "PRODUCTION ABHA. Real OTPs, real permanent accounts.", danger: true }
    : { text: "Staging ABHA SDK. Nothing here creates a real account.", danger: false };
}
