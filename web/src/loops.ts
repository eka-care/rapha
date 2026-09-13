/** The loop rules. Pure, so they are checkable without a browser.
 *
 *  `thread.actions` is already filtered by the kernel: an action whose
 *  precondition is unmet or whose capability is not held is absent, never
 *  disabled. So everything here is a question of weight, not permission.
 */
import type { Recent } from "./Shell.tsx";
import type { Operation, QueueRow, SectionResult, ViewDecl } from "./types";

/** One filled button, everything else one level down.
 *
 *  Two things of equal visual weight means we have not decided which is the
 *  point. The kernel already says which operation ends this station's task;
 *  when it is not on offer (its precondition is unmet, or the line is
 *  complete) the step's own ordering has put the next thing first.
 */
/** Whether a thread's own current actions are still offering an operation, by
 *  id. Six denials landed on an already-registered patient because a surface
 *  opened `phc.op.patient-register` by id instead of by membership in
 *  `thread.actions` — the guard's own predicate, already applied. Every
 *  screen that opens an operation on a thread already in progress must go
 *  through this: it hands back the kernel's own Operation object from
 *  `actions`, or undefined, so there is no way to hold onto an operation the
 *  current list does not contain. */
export function offered(id: string, actions: Operation[]): Operation | undefined {
  return actions.find((a) => a.id === id);
}

export function weigh(
  actions: Operation[],
  closes: string | null,
): { primary?: Operation; overflow: Operation[] } {
  const primary = actions.find((op) => op.id === closes) ?? actions[0];
  return { primary, overflow: actions.filter((op) => op.id !== primary?.id) };
}

/** What a role is offered once its task at a station is done.
 *
 *  Two shapes, because there are two kinds of role: one that starts new
 *  subjects (it holds the workflow's opener) and one that works a queue. The
 *  difference is derived from the declarations, not from a list of job titles.
 */
export type Cue =
  | { kind: "open"; op: Operation; label: string }
  | { kind: "next"; thread: string; label: string }
  | { kind: "empty"; label: string };

/** Whether arriving at a thread should open this operation's instrument
 *  straight away, rather than draw a button that offers to.
 *
 *  Everything correctable opens. An irreversible operation does not: opening a
 *  national identity journey over the screen every time someone arrives is how
 *  a person learns to dismiss it, and dismissing is the habit that makes the
 *  confirm step meaningless.
 */
export function opensOnArrival(op: Operation | undefined): boolean {
  return !!op && op.irreversibility !== "irreversible";
}

/** Whether a committed operation's card belongs open on this screen.
 *
 *  The nurse opening onto reception's six-row registration form is workflow
 *  fragmentation: someone else's completed context, above her own task. It
 *  collapses to one line she can expand. Once the line is complete there is no
 *  current station and nothing collapses, because the whole visit is the
 *  subject then.
 */
export function mine(op: Operation, station: string | null): boolean {
  return station === null || op.station === station;
}

export function cue(a: {
  station: string | null;
  opener: Operation | null;
  queue: QueueRow[];
  /** The thread whose loop just closed. It may still be in the queue result,
   *  which was read before the commit; offering it back is a loop with no
   *  exit. */
  closed: string;
}): Cue {
  if (a.opener) return { kind: "open", op: a.opener, label: a.opener.title };
  const waiting = a.queue.filter((r) => r.station === a.station && r.thread !== a.closed);
  const first = waiting[0];
  if (!first) {
    return { kind: "empty", label: a.station ? `Nobody waiting at ${a.station}` : "Nobody waiting" };
  }
  const name = typeof first.subject.name === "string" && first.subject.name
    ? first.subject.name
    : String(first.subject.token ?? first.thread);
  return { kind: "next", thread: first.thread, label: name };
}

/** The documents a thread produced, from the summary view's own sections.
 *
 *  A section that reads a resource is a kind of document; a section that shows
 *  a kernel structure (the line, the flags, the actions, the audit) is not.
 *  These are also ABDM's units — Prescription, DiagnosticReport,
 *  OPConsultation — so the rail and the ABHA share sheet list the same things.
 *
 *  Audit is deliberately excluded even though it has rows. The guard writes
 *  audit before execute, so there are rows for denials and rejected proposals:
 *  events that produced no document. Those belong in the visit collation. The
 *  rail is what exists; the collation is what happened.
 */
export function records(sections: SectionResult[]): { title: string; count: number }[] {
  return sections
    .filter((s) => s.resource && s.rows.length > 0)
    .map((s) => ({ title: s.title, count: s.rows.length }));
}

/** Recents the kernel still serves. A reseed changes every thread id, and the
 *  list survives it in localStorage, so the sidebar filled with dead tokens
 *  that 404 on click. Filtering on read is cheaper than any bookkeeping. */
export function keep(rs: Recent[], live: string[]): Recent[] {
  const known = new Set(live);
  return rs.filter((r) => known.has(r.id));
}

// -------------------------------------------------------------- sort/filter
//
// Recents' sort and filter controls, and the two pure functions behind them.
// Both are worked out from the queue view's own declaration (`columns` for
// the name to sort by, `badges` for the flags to filter by) so that pointing
// this at a different bundle changes the controls with no edit here. Nothing
// below names a station, a flag id, or a bundle.

export type SortKey = "recent" | "name" | "station";

/** The sort menu this bundle's queue declaration earns. "Recent" and
 *  "Station" need no declaration (every QueueRow carries `opened_at` and
 *  `station`); "Name" is offered only when the view declared a first column,
 *  labelled with that column's own word. */
export function sortOptions(decl: Pick<ViewDecl, "columns"> | undefined): { key: SortKey; label: string }[] {
  const opts: { key: SortKey; label: string }[] = [{ key: "recent", label: "Recent" }];
  if (decl?.columns?.length) opts.push({ key: "name", label: decl.columns[0] });
  opts.push({ key: "station", label: "Station" });
  return opts;
}

/** Sorts a copy of `rows`; never mutates and never hands back `rows` itself,
 *  so a caller that needs the new order cannot be fooled by object identity.
 *  "Name" reads the declared first column, because that is the only field
 *  this code is told is a name. */
export function sortRows(rows: QueueRow[], key: SortKey, decl: Pick<ViewDecl, "columns"> | undefined): QueueRow[] {
  const nameCol = decl?.columns?.[0];
  const get = (r: QueueRow): string => {
    if (key === "station") return r.station ?? "";
    if (key === "name") return String(r.subject?.[nameCol ?? ""] ?? "");
    return r.opened_at ?? "";
  };
  const sorted = [...rows].sort((a, b) => get(a).localeCompare(get(b)));
  return key === "recent" ? sorted.reverse() : sorted;
}

export type Filter = { flag: string } | { station: string } | null;

/** The filter chips this bundle's queue declaration earns: one per declared
 *  badge (a flag worth calling out), and one per station actually present in
 *  today's rows. A bundle that declares no badges offers no flag filter. */
export function filterOptions(
  decl: Pick<ViewDecl, "badges"> | undefined,
  rows: QueueRow[],
): { flags: string[]; stations: string[] } {
  return {
    flags: Object.keys(decl?.badges ?? {}),
    stations: [...new Set(rows.map((r) => r.station).filter((s): s is string => !!s))],
  };
}

/** Filters a copy of `rows` by the chosen flag or station; `null` means no
 *  filter and hands every row back, never a subset picked at random. */
export function filterRows(rows: QueueRow[], filter: Filter): QueueRow[] {
  if (!filter) return rows;
  if ("flag" in filter) return rows.filter((r) => r.flags.includes(filter.flag));
  return rows.filter((r) => r.station === filter.station);
}
