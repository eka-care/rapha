/** The loop rules. Pure, so they are checkable without a browser.
 *
 *  `thread.actions` is already filtered by the kernel: an action whose
 *  precondition is unmet or whose capability is not held is absent, never
 *  disabled. So everything here is a question of weight, not permission.
 */

import type { Operation, Question, QueueRow, SectionResult, ViewDecl, Workflow } from "./types";

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

/** A thread somebody opened recently. Lives here rather than in a component
 *  because keep() is pure and runs under plain node: a .check.ts may not
 *  import a .tsx, and this type used to be declared in one. */
export type Recent = { id: string; name: string };

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

/** The one declared badge tone that means clinical risk.
 *
 *  In this system colour means clinical risk and nothing else, so exactly one
 *  of the tones a view may put on a flag is allowed to be red: a programme is
 *  not a risk and an overdue wait is not a risk. The tone itself is the
 *  bundle's decision, flag by flag; which tone red belongs to is this
 *  renderer's, and it is written once, here. */
export const RISK_TONE = "crit";

/** Which of a workflow's states nobody asserted.
 *
 *  A workflow declares how each state is decided. `{stored: true}` means a
 *  person said so and the kernel kept it: that is somebody's decision.
 *  Everything else -- `exists`, `all_of`, `gte` -- is the kernel reading the
 *  records it already holds and working the state out. The queue draws the
 *  second kind dashed, so a guess never looks like a decision.
 *
 *  A workflow this renderer has not been given answers "nothing is derived",
 *  which draws every label solid. That is the safer way round: a dashed label
 *  claims the machine guessed, and saying that about a clinician's own tick
 *  would be a lie. */
export function derivedStates(wf: Pick<Workflow, "states"> | undefined): Set<string> {
  const out = new Set<string>();
  for (const [state, how] of Object.entries(wf?.states ?? {})) {
    const asserted = !!how && typeof how === "object" && "stored" in how;
    if (!asserted) out.add(state);
  }
  return out;
}

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

/** Which of a view's declared columns are LABELS rather than details.
 *
 *  A queue row draws most of its columns as a line of text under the name --
 *  who the person is -- and the mockup draws one of them as a pill on the
 *  right: the programme they are enrolled in. The view declares the columns
 *  and says nothing about which is which, so the distinction has to come from
 *  somewhere, and the only honest source is the form that collects the
 *  answer.
 *
 *  The rule, and what it rests on. A column is a label when its question
 *  offers a CLOSED set of answers and does not REQUIRE one. Both halves
 *  matter and both are the declaration's own words:
 *
 *    - Closed, because a filter chip over free text is a chip per village,
 *      and a line nobody can filter is a line nobody reads.
 *    - Not required, because that is how a declaration says a person may not
 *      have one. Everybody has a name, an age, a sex and a village, and those
 *      are required; nobody is obliged to be on a programme. An enrolment you
 *      may not have is not a description of you, and that is exactly the
 *      difference between a pill and a line of text.
 *
 *  So this renderer still learns nothing about what the programmes ARE, or
 *  even that the column is a programme. It is told that one column is
 *  optional and closed, and it draws optional closed things as labels.
 *
 *  THE COST, NAMED. A bundle that made its programme required would lose the
 *  pill and get a word in the detail line instead, and a bundle that added a
 *  second optional closed column would get a second pill without asking. The
 *  alternative was a view saying which of its columns are labels, which is a
 *  declaration that does not exist; this reads one that does.
 */
export function labelColumns(
  decl: Pick<ViewDecl, "columns"> | undefined,
  ask: (linkId: string) => Pick<Question, "required" | "answer_option" | "answer_value_set"> | null,
): string[] {
  return (decl?.columns ?? []).filter((column) => {
    const q = ask(column);
    if (!q || q.required) return false;
    return !!q.answer_option?.length || !!q.answer_value_set;
  });
}

export type Filter = { flag: string } | { station: string } | { column: string; value: string } | null;

/** The filter chips this bundle's queue declaration earns: one per declared
 *  badge (a flag worth calling out), and one per station actually present in
 *  today's rows. A bundle that declares no badges offers no flag filter. */
export function filterOptions(
  decl: Pick<ViewDecl, "badges"> | undefined,
  rows: QueueRow[],
  /** The declared columns that are labels. One chip per value actually
   *  present, because a chip for a programme nobody in the room is on is a
   *  chip that can only ever say nought. */
  labels: string[] = [],
): { flags: string[]; stations: string[]; labels: { column: string; values: string[] }[] } {
  return {
    flags: Object.keys(decl?.badges ?? {}),
    stations: [...new Set(rows.map((r) => r.station).filter((s): s is string => !!s))],
    labels: labels
      .map((column) => ({
        column,
        values: [...new Set(rows.map((r) => String(r.subject?.[column] ?? "")).filter(Boolean))].sort(),
      }))
      .filter((l) => l.values.length > 0),
  };
}

/** Filters a copy of `rows` by the chosen flag or station; `null` means no
 *  filter and hands every row back, never a subset picked at random. */
export function filterRows(rows: QueueRow[], filter: Filter): QueueRow[] {
  if (!filter) return rows;
  if ("flag" in filter) return rows.filter((r) => r.flags.includes(filter.flag));
  if ("column" in filter) {
    return rows.filter((r) => String(r.subject?.[filter.column] ?? "") === filter.value);
  }
  return rows.filter((r) => r.station === filter.station);
}
