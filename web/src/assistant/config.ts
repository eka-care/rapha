/** What the medical assistant needs to start, read from the build.
 *
 *  Pure, so `assistant.check.ts` runs it under plain node with no package and
 *  no browser. Nothing here is written down: the agent, the environment and
 *  the token all come from `import.meta.env`, and a missing agent is an
 *  answer ("not set up"), not a default.
 *
 *  THE TOKEN, SAID PLAINLY. This app's Eka session is a cookie on
 *  `.eka.care`; the browser never holds a bearer token for it, and the page
 *  cannot read the cookie. So there is nothing here to hand the assistant on
 *  anybody's behalf, on localhost or anywhere else. The assistant therefore
 *  starts as a GUEST. `VITE_AUTH_TOKEN` is honoured only so a developer can
 *  test the signed-in path; it is read at build time, so it is the same token
 *  for everyone who loads that build, and it must never be set on a real
 *  deployment. Per-clinician sign-in needs Eka to hand this app a token (the
 *  way nectar's host hands one to a microfrontend), and that is not decided.
 */

/** The pills the widget opens with, as `label|prompt` lines (its own format,
 *  five at most). Its built-in ones are the developer docs'. These are
 *  questions any clinician asks about any patient, so none names a condition,
 *  a drug or a station. The wording is a first draft for the owner. */
export const STARTERS = [
  "Dose and cautions|What is the usual adult dose, and what are the cautions?",
  "Red flags|What red flags should make me refer this patient?",
  "What to consider|What else should I consider for this presentation?",
  "What to tell them|What should I tell the patient to watch for?",
].join("\n");

export type AssistantEnvironment = "development" | "staging" | "production";

const ENVIRONMENTS: readonly string[] = ["development", "staging", "production"];

export type AssistantConfig =
  | { ready: true; agentId: string; environment: AssistantEnvironment; authToken: string | undefined }
  | { ready: false; why: string };

export function assistantConfig(env: Record<string, string | undefined>): AssistantConfig {
  const agentId = env.VITE_AGENT_ID?.trim();
  if (!agentId) {
    return { ready: false, why: "The medical assistant is not set up on this build." };
  }
  const asked = env.VITE_ENVIRONMENT?.trim();
  if (asked && !ENVIRONMENTS.includes(asked)) {
    return { ready: false, why: "The medical assistant is set to an environment it does not know." };
  }
  return {
    ready: true,
    agentId,
    environment: (asked as AssistantEnvironment | undefined) ?? "development",
    authToken: env.VITE_AUTH_TOKEN?.trim() || undefined,
  };
}
