/** What the agent has to say before anybody asks it anything.
 *
 *  §71: the AI feeling comes from persistent context, intelligent ordering,
 *  inline suggestions, provenance and state awareness. Not from gradients,
 *  glow, purple or sparkles. So this file produces sentences and questions,
 *  and every one of them is composed from declarations and live rows.
 *
 *  Pure, and no React, so agent.check.ts can run it under plain node. Nothing
 *  here names a station, a flag or a view: the words come from the bundle.
 */
import type { QueueRow, TaskRow, ViewDecl, ViewResult } from "./types";
import { human, NO_NAME } from "./words.ts";

export type Loaded = { decl: ViewDecl; result: ViewResult };

/** A run of text, optionally somewhere to go. The brief is built of these
 *  rather than of a string, so a number in it can be a link without this
 *  module knowing what a link is. */
export type Span = { text: string; go?: string };

const queues = (loaded: Loaded[]) => loaded.filter((l) => l.decl.kind === "queue");
const rowsOf = (l: Loaded) => (l.result.rows ?? []) as QueueRow[];
const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/** Where the line is thickest right now: the station holding the most people,
 *  and how many. Stations come from the rows, so a bundle with different ones
 *  gets its own answer and this file never learns their names. */
export function busiest(loaded: Loaded[]): { station: string; count: number } | null {
  const tally = new Map<string, number>();
  for (const l of queues(loaded)) {
    for (const r of rowsOf(l)) {
      if (!r.station) continue;
      tally.set(r.station, (tally.get(r.station) ?? 0) + 1);
    }
  }
  let best: { station: string; count: number } | null = null;
  for (const [station, count] of tally) {
    if (!best || count > best.count) best = { station, count };
  }
  return best;
}

/** How many people carry a flag this bundle's queue declaration calls out.
 *  A flag with no declared badge is not "attention", it is just state, which
 *  is the difference between a signal and a status. */
export function needingAttention(loaded: Loaded[]): number {
  let n = 0;
  for (const l of queues(loaded)) {
    const called = new Set(Object.keys(l.decl.badges ?? {}));
    for (const r of rowsOf(l)) {
      if ((r.flags ?? []).some((f) => called.has(f))) n++;
    }
  }
  return n;
}

/** §5, and the prototype's shift brief: what the facility looks like right
 *  now, in sentences, with the numbers clickable.
 *
 *  The prototype wrote one of these per role by hand. That cannot survive a
 *  second bundle, so this composes the same shape from the rows: how many are
 *  here, where the queue is thickest, what is flagged, what is outstanding.
 */
export function brief(loaded: Loaded[]): Span[] {
  const people = new Set<string>();
  for (const l of queues(loaded)) for (const r of rowsOf(l)) people.add(r.thread);

  if (!people.size) {
    return [{ text: "Nobody is in the facility yet. The first registration starts the day." }];
  }

  const out: Span[] = [{ text: `${plural(people.size, "person", "people")} ` }];
  const busy = busiest(loaded);
  const queue = queues(loaded)[0];
  if (busy && busy.count > 1) {
    out.push({ text: "are here. The longest line is at " });
    out.push({ text: human(busy.station), go: queue ? `#/views/${queue.decl.id}` : undefined });
    out.push({ text: `, with ${busy.count} waiting. ` });
  } else {
    out.push({ text: "are here. " });
  }

  const flagged = needingAttention(loaded);
  if (flagged) {
    // "1 person in the facility. 1 of them carries a flag" is how a template
    // reads when nobody checked it against a small number.
    out.push({
      text: flagged === people.size
        ? (flagged === 1 ? "That one carries a flag worth reading" : "Every one of them carries a flag worth reading")
        : `${flagged} of them ${flagged === 1 ? "carries" : "carry"} a flag worth reading`,
    });
    if (queue) {
      out.push({ text: ", in " });
      out.push({ text: queue.decl.title ?? human(queue.decl.id), go: `#/views/${queue.decl.id}` });
    }
    out.push({ text: ". " });
  }

  const tasks = loaded
    .filter((l) => l.decl.kind === "tasklist")
    .flatMap((l) => (l.result.rows ?? []) as TaskRow[]);
  const outstanding = tasks.reduce((n, t) => n + (t.count ?? 0), 0);
  if (outstanding) {
    const worst = [...tasks].sort((a, b) => (b.count ?? 0) - (a.count ?? 0))[0];
    out.push({ text: `${plural(outstanding, "thing")} still ${outstanding === 1 ? "needs" : "need"} somebody, mostly ` });
    out.push({ text: worst.title.toLowerCase() });
    out.push({ text: "." });
  }
  return out;
}

/** The chips under the ask box. The prototype hard-coded three questions per
 *  role; these are the facility's own declared worklists and lists, which is
 *  the same idea and survives a bundle it has never seen.
 *
 *  A tasklist row is already a sentence about something outstanding, so it
 *  makes a better question than a view id ever would. */
export function facilityAsks(loaded: Loaded[], limit = 4): string[] {
  const asks: string[] = [];
  for (const l of loaded.filter((x) => x.decl.kind === "tasklist")) {
    for (const t of (l.result.rows ?? []) as TaskRow[]) {
      if (t.count > 0) asks.push(t.title);
    }
  }
  for (const l of queues(loaded)) {
    if (rowsOf(l).length) asks.push(l.decl.title ?? human(l.decl.id));
  }
  return [...new Set(asks)].slice(0, limit);
}

/** On a thread. Kernel concepts only: a record, a previous visit, what is
 *  outstanding. No bundle word appears, which is why these are safe to write
 *  down here and the facility's own questions above are not. */
export function threadAsks(opts: { hasHistory: boolean; flags: string[] }): string[] {
  const asks = ["Summarise this record"];
  if (opts.hasHistory) asks.push("What changed since last time?");
  if (opts.flags.length) asks.push("Why is this flagged?");
  asks.push("What is still outstanding?");
  return asks;
}


/** The line, station by station, in declaration order. One column per station
 *  the workflow declares, whoever is standing in it, and whether it is the
 *  thickest point. Nothing here is a station's name: the order comes from the
 *  workflow's own steps and the labels from the rows. */
export type Column = {
  station: string;
  /** `alerts` is the declared flags behind `alert`, and it exists because of
   *  SC 1.4.1: a person drawn in the critical tone and nothing else is a
   *  person whose state is carried by colour alone, which is no state at all
   *  to anybody who cannot see it or cannot tell that red from this grey. The
   *  words are the flags the kernel sent; this file does not read them. */
  people: { thread: string; name: string; initials: string; token?: string; alert: boolean; alerts: string[]; opened_at?: string }[];
  /** The earliest arrival among the people here, so the screen can say how long
   *  the longest wait is without a second pass over the rows. */
  oldest?: string;
  jam: boolean;
};

export function line(loaded: Loaded[], stations: string[], badges: Record<string, string>): Column[] {
  const called = new Set(Object.entries(badges).filter(([, s]) => s === "crit").map(([f]) => f));
  const at = new Map<string, Column["people"]>();
  for (const l of queues(loaded)) {
    for (const r of rowsOf(l)) {
      if (!r.station) continue;
      const cols = (l.decl.columns ?? []).length
        ? (l.decl.columns as string[]).map((c) => r.subject?.[c])
        : Object.values(r.subject ?? {});
      // The first declared column is the name. Taking the next column that has a
      // value drew an unnamed patient as their token number, twice.
      const first = cols[0];
      const tokenCol = (l.decl.columns ?? []).find((c) => /token/i.test(c) && r.subject?.[c] != null && r.subject?.[c] !== "")
        ?? Object.keys(r.subject ?? {}).find((k) => /token/i.test(k) && r.subject?.[k] != null && r.subject?.[k] !== "");
      const tokenVal = tokenCol ? r.subject?.[tokenCol] : undefined;
      const token = tokenVal === undefined || tokenVal === null || tokenVal === "" ? undefined : String(tokenVal);
      const name = typeof first === "string" && first.trim() ? first : NO_NAME;
      const list = at.get(r.station) ?? [];
      const alerts = (r.flags ?? []).filter((f) => called.has(f));
      list.push({
        thread: r.thread, name, initials: name === NO_NAME ? "?" : initialsOf(name), token, opened_at: r.opened_at,
        alert: alerts.length > 0, alerts,
      });
      at.set(r.station, list);
    }
  }
  const most = Math.max(0, ...[...at.values()].map((p) => p.length));
  return stations.map((station) => {
    const people = at.get(station) ?? [];
    const oldest = people.map((p) => p.opened_at).filter((t): t is string => !!t).sort()[0];
    return { station, people, oldest, jam: people.length > 1 && people.length === most };
  });
}

export const initialsOf = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";
