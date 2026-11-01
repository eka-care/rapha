/** Run: node --experimental-strip-types src/auth/client.check.ts   (from web/)
 *
 *  The session rules, against the user agents and the statuses they are for.
 */
import assert from "node:assert/strict";
import { apiBase, clientIdFor, gateApplies, loginBase, worthRefreshing } from "./client.ts";

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15";
const ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36";
const WINDOWS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

ok(clientIdFor(MAC, false) === "doc-web", "a laptop is the web client");
ok(clientIdFor(MAC, true) === "doctor-ipad-ios",
   "an iPad reports itself a Macintosh, and touch is the only thing that tells them apart");
ok(clientIdFor(IPHONE, false) === "doctor-app-ios", "an iPhone is the iOS client");
ok(clientIdFor(ANDROID, false) === "androiddoc", "an Android is the Android client");
ok(clientIdFor(WINDOWS, false) === "doc-web", "anything else is the web client");
ok(clientIdFor("", false) === "doc-web", "and so is a browser that says nothing");

// The order matters: an iPhone's user agent contains neither Macintosh nor
// Android, but an iPad's contains Macintosh, so a test for touch that ran
// after the iPhone test would still be right and one that ran after Android
// would not. Pinned so a reordering cannot pass.
ok(clientIdFor("iPhone Macintosh", true) === "doctor-ipad-ios",
   "Macintosh with touch wins, which is nectar's own order");

ok(worthRefreshing(401), "an expired token is worth a refresh");
ok(worthRefreshing(403), "and so is a refused one");
ok(worthRefreshing("FETCH_ERROR"),
   "and a fetch that threw: cross origin, an expired session LOOKS like CORS");
ok(!worthRefreshing(200), "a good answer is not refreshed");
ok(!worthRefreshing(404), "and neither is a missing route");
ok(!worthRefreshing(500), "nor the server's own error, which a new token does not fix");

ok(apiBase("PROD") === "https://api.eka.care", "PROD is production");
ok(apiBase("DEV") === "https://api.dev.eka.care", "anything else is not");
ok(apiBase(undefined) === "https://api.dev.eka.care",
   "and an unset environment is NOT production, which is the safe direction");
ok(loginBase("PROD").includes("login.eka.care"), "and sign-in follows the same switch");
ok(loginBase(undefined).includes("login.dev.eka.care"), "both ways");

// -- where the gate applies -----------------------------------------------
ok(!gateApplies("localhost"), "localhost never receives the cookie, so the gate would lock a developer out of their own screen");
ok(!gateApplies("127.0.0.1"), "and neither does the loopback address");
ok(!gateApplies("[::1]") && !gateApplies("::1"), "in either spelling");
ok(!gateApplies("phc.localhost"), "nor a name under it");
ok(gateApplies("nishant.eka.care"), "a dev subdomain of eka.care DOES receive it, so the gate is on");
ok(gateApplies("abdm.eka.care"), "and so does production");
ok(gateApplies("phc.example.org"),
   "and anywhere else is on too: a deployment that is not localhost gets the gate, "
   + "rather than losing it by being somewhere this file did not think of");

console.log(`ok   session rules: ${checks} checks`);
