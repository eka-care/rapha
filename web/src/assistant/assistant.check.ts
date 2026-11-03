/** The medical assistant's start-up rules, with no package and no browser. */
import assert from "node:assert/strict";
import { assistantConfig } from "./config.ts";

const ok = (m: string) => console.log("  ok  " + m);

{
  const none = assistantConfig({});
  assert.equal(none.ready, false, "no agent id, no assistant: there is no default agent");
  assert.equal(assistantConfig({ VITE_AGENT_ID: "   " }).ready, false, "a blank id is no id");
  ok("assistant: without an agent id it is off, not guessed");
}

{
  const c = assistantConfig({ VITE_AGENT_ID: "a1" });
  assert.ok(c.ready);
  if (c.ready) {
    assert.equal(c.environment, "development", "the safe environment is the default");
    assert.equal(c.authToken, undefined, "no token means a guest");
  }
  const bad = assistantConfig({ VITE_AGENT_ID: "a1", VITE_ENVIRONMENT: "prod" });
  assert.equal(bad.ready, false, "an environment it does not know is refused, not rounded");
  const tok = assistantConfig({ VITE_AGENT_ID: "a1", VITE_ENVIRONMENT: "staging", VITE_AUTH_TOKEN: " " });
  assert.ok(tok.ready && tok.authToken === undefined, "a blank token is a guest");
  ok("assistant: environment is one of three, and a blank token is a guest");
}

console.log("assistant: all checks passed");
