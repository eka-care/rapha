/** Run: node --experimental-strip-types src/thread/commands.check.ts   (from web/) */
import assert from "node:assert/strict";
import { commands, type Verb } from "./commands.ts";

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const TABS = [
  { id: "messages", title: "Messages" },
  { id: "scribe", title: "Scribe" },
  { id: "past", title: "Earlier visits" },
];
const noop = () => {};
const base = { tabs: TABS, open: "messages", goTab: noop, railFolded: true, toggleRail: noop };
const labels = (v: Verb[]) => v.map((x) => x.label);

// -- a verb that cannot run is not offered --------------------------------
ok(!labels(commands(base)).includes("Start recording"),
   "no microphone without consent: a command that would be refused is not listed");
ok(labels(commands({ ...base, record: noop })).includes("Start recording"),
   "and it is there the moment it would work");
ok(!labels(commands(base)).includes("Go to Messages"),
   "the tab you are already looking at is not somewhere to go");
ok(labels(commands({ ...base, open: "scribe" })).includes("Go to Messages"),
   "and the one you are not looking at is");
ok(!labels(commands(base)).includes("Open the patient record"),
   "a visit that belongs to no continuing record cannot open one");

// -- the words are the caller's -------------------------------------------
const renamed = commands({ ...base, tabs: [{ id: "x", title: "Ledger" }] });
ok(labels(renamed).includes("Go to Ledger"),
   "a tab's own title is its command: nothing here spells the tab names");

// -- the rail control says which way it goes ------------------------------
ok(labels(commands(base)).some((l) => l.startsWith("Show the panels")),
   "folded, the command opens it");
ok(labels(commands({ ...base, railFolded: false })).some((l) => l.startsWith("Hide the panels")),
   "open, the same command closes it, rather than two commands one of which does nothing");

// -- it is a list of things to RUN, not a list of words --------------------
let ran = "";
const live = commands({
  ...base, open: "scribe",
  record: () => { ran = "mic"; },
  goTab: (id) => { ran = `tab:${id}`; },
});
live.find((v) => v.key === "record")!.run();
ok(ran === "mic", "the microphone verb starts the microphone");
live.find((v) => v.key === "tab:messages")!.run();
ok(ran === "tab:messages", "and a tab verb opens that tab, by its own id");

// Keys are what React draws the list by, and a duplicate silently drops a row.
const keys = commands({ ...base, open: "scribe", record: noop, openRecord: noop }).map((v) => v.key);
assert.equal(new Set(keys).size, keys.length, "two commands share a key");
checks++;

console.log(`ok   the slash menu's own verbs: ${checks} checks`);
