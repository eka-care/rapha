/** Run: node --experimental-strip-types src/thread/fold.check.ts   (from web/)
 *
 *  What the thread folds together, checked where it is decided.
 */
import assert from "node:assert/strict";
import { blocks, split, FOLD_EARLIER, KEEP_OPEN, TALK_GAP, type Block } from "./fold.ts";
import type { Msg } from "../messages.ts";

let checks = 0;
const ok = (cond: unknown, what: string) => { checks++; assert.ok(cond, `FAIL ${what}`); };

const t = (min: number) => new Date(Date.UTC(2026, 10, 3, 9, min)).toISOString();

let n = 0;
const no = (actor: string, min = 0): Msg =>
  ({ kind: "denied", id: `d${++n}`, at: t(min), title: "Record vitals", actor,
     reason: "Already recorded.", old: false });
const say = (actor: string, min: number, text = "hello"): Msg =>
  ({ kind: "said", id: `s${++n}`, at: t(min), who: actor === "agent" ? "agent" : "user", text, actor });
const kept = (): Msg =>
  ({ kind: "posted", id: `p${++n}`, at: t(0), title: "Record vitals", actor: "meena",
     operation: "x", tags: [], values: [], payload: {}, edited: false });

// -- refusals -------------------------------------------------------------
const run = blocks([no("agent"), no("agent"), no("agent")]);
ok(run.length === 1 && run[0].kind === "refusals" && run[0].rows.length === 3,
   "three refusals in a row are one row, not three");

const parted = blocks([no("agent"), kept(), no("agent")]);
ok(parted.length === 3, "a refusal, a record and a refusal are three events: only a RUN folds");

ok(blocks([no("agent")])[0].kind === "refusals",
   "the agent guessing wrong once is still noise, and still folds");
ok(blocks([no("meena")])[0].kind === "one",
   "a refusal of something a PERSON did is news, and keeps its own row");
const sides = blocks([no("agent"), no("meena")]);
ok(sides.length === 2, "a machine's refusal and a person's never fold together");

// -- talk -----------------------------------------------------------------
const turn = blocks([say("meena", 0), say("meena", 1), say("meena", 2)]);
ok(turn.length === 1 && turn[0].kind === "turn" && turn[0].msgs.length === 3,
   "three lines typed in a row are one turn with one header");
ok(blocks([say("meena", 0), say("mo", 1)]).length === 2,
   "two people talking are two turns, however close together");
ok(blocks([say("meena", 0), say("meena", 1 + TALK_GAP / 60000)]).length === 2,
   "the same person, twenty minutes later, has said two things");
ok(blocks([say("meena", 0), kept(), say("meena", 1)]).length === 3,
   "a record between two lines breaks the turn: something happened in between");

// -- the older part of a long visit ---------------------------------------
const many = (count: number): Block[] =>
  blocks(Array.from({ length: count }, (_, i) => say(`p${i}`, i)));

const short = split(many(KEEP_OPEN + FOLD_EARLIER - 1));
ok(short.earlier.length === 0, "a visit that nearly fits is drawn whole: a control hiding two rows is furniture");
const long = split(many(KEEP_OPEN + FOLD_EARLIER + 5));
ok(long.recent.length === KEEP_OPEN, "what stays drawn is the foot of the list, which is what is being read");
ok(long.earlier.length === FOLD_EARLIER + 5, "and everything above it is behind the control, not dropped");
ok(split([]).recent.length === 0, "an empty visit folds nothing");

console.log(`ok   what the thread folds together: ${checks} checks`);
