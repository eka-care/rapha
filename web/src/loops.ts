/** The loop rules. Pure, so they are checkable without a browser.
 *
 *  `thread.actions` is already filtered by the kernel: an action whose
 *  precondition is unmet or whose capability is not held is absent, never
 *  disabled. So everything here is a question of weight, not permission.
 */

import type { Operation, QueueRow, SectionResult, ViewDecl, Workflow } from "./types";

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

/** What an earlier commit on a thread hands to the next panel opened on it.
 *
 *  One thing does this today and it is the expensive one. A registration runs
 *  the ABHA journey; the journey hands back a national identifier that
 *  registration itself does not write, because the link operation does. The
 *  panel produced it and handed it up, and the screen above dropped it, so
 *  the clerk who opened the link panel next was shown the journey again and
 *  the patient was asked to read a SECOND one time password off a handset to
 *  say a number the screen had been holding for minutes. That is the cost the
 *  whole front desk exists to remove, and it was being paid one screen later.
 *
 *  Two guards, and both are about somebody else's record rather than tidiness.
 *
 *  THE THREAD. A value learned on one visit is offered only on that visit.
 *  The screen holding it is not keyed by thread id, so walking from one
 *  patient to the next reuses it, and an identifier kept loose would seed the
 *  next person's form. One patient's ABHA number on another patient's record
 *  is the anti-goal in the spec: nothing merges two, and the patient carries
 *  the mistake permanently.
 *
 *  THE QUESTIONS. Filtered against the questionnaire the panel is about to
 *  open rather than handed over whole, so the operation that ASKS for an
 *  identifier gets it and the rest are not told. A payload key a form does
 *  not ask for is a commit the kernel refuses, and nothing here may decide
 *  which operation wants what.
 *
 *  Nothing is returned rather than an empty object, because an empty seed is
 *  still a seed: it would tell the panel this person had already been
 *  identified and suppress the journey that is the only way to identify them.
 *  See abha/sdk.ts's runsJourney.
 */
export function carriedInto(
  carried: { thread: string; payload: Record<string, unknown> } | null,
  thread: string,
  questions: { link_id: string }[],
): Record<string, unknown> | undefined {
  if (!carried || carried.thread !== thread) return undefined;
  const asks = new Set(questions.map((q) => q.link_id));
  const useful = Object.entries(carried.payload).filter(([id]) => asks.has(id));
  return useful.length ? Object.fromEntries(useful) : undefined;
}

/** Which of a view's columns are LABELS rather than details.
 *
 *  The view's own answer, and nothing worked out. A label is drawn as a pill
 *  on the row and earns a filter chip; everything else goes into the line of
 *  text under the name.
 *
 *  THIS USED TO BE A GUESS AND IT IS WORTH SAYING WHAT THE GUESS WAS, because
 *  it was a good one and still wrong. A column whose question offered a
 *  closed set of answers and did not require one was taken to be something a
 *  person may or may not have, and therefore a label. That picked exactly the
 *  right column in this bundle. It would have picked a second one the moment
 *  a bundle declared another optional choice, and lost the pill entirely if a
 *  centre made its programme compulsory -- neither of which anybody would
 *  have been told about. The view says it outright now.
 *
 *  Intersected with `columns`, because a label is a column drawn differently
 *  and not a second source of fields. The declaration lint refuses a label
 *  naming a column the view does not carry, so this intersection should never
 *  remove anything; it is here so that a renderer reading an older or
 *  hand-edited catalogue draws fewer pills rather than reaching for a field
 *  no row has.
 */
export function labelColumns(decl: Pick<ViewDecl, "columns" | "labels"> | undefined): string[] {
  const columns = decl?.columns ?? [];
  return (decl?.labels ?? []).filter((label) => columns.includes(label));
}

/** How a row reached this queue, if the view says so, and nothing about what
 *  that means.
 *
 *  Returns the declaration's own three parts or null. Intersected with
 *  `columns` for the same reason labelColumns is: the declaration lint
 *  refuses provenance naming a column the view does not carry, so this should
 *  never remove anything, and it is here so a renderer reading an older or
 *  hand-edited catalogue draws no mark rather than reaching for a field no
 *  row has. A view that declares none gets null, and the mark and the chip
 *  are both simply absent.
 */
export function provenanceOf(
  decl: Pick<ViewDecl, "columns" | "provenance"> | undefined,
): { column: string; mark: string; label: string } | null {
  const p = decl?.provenance;
  if (!p?.column || !p.mark || !p.label) return null;
  return (decl?.columns ?? []).includes(p.column) ? { ...p } : null;
}

/** Whether this row wears the mark: its provenance column carries exactly the
 *  declared value. String-compared, because a column is whatever the store
 *  put in it and a number that arrived as a number must still match. */
export function marked(
  row: Pick<QueueRow, "subject">,
  provenance: { column: string; mark: string } | null,
): boolean {
  if (!provenance) return false;
  return String(row.subject?.[provenance.column] ?? "") === provenance.mark;
}

export type Filter = { flag: string } | { station: string } | { column: string; value: string } | null;

/** The filter chips this bundle's queue declaration earns: one per declared
 *  badge (a flag worth calling out), and one per station actually present in
 *  today's rows. A bundle that declares no badges offers no flag filter. */
export function filterOptions(
  decl: Pick<ViewDecl, "badges" | "columns" | "provenance"> | undefined,
  rows: QueueRow[],
  /** The declared columns that are labels. One chip per value actually
   *  present, because a chip for a programme nobody in the room is on is a
   *  chip that can only ever say nought. */
  labels: string[] = [],
): {
  flags: string[];
  stations: string[];
  labels: { column: string; values: string[] }[];
  /** The provenance chip, when the view declares one AND somebody in the room
   *  actually wears the mark. Same rule as a label value, for the same
   *  reason: a chip that can only say nought is clutter on a strip a phone
   *  already has to scroll. It is one chip and not two, because the ordinary
   *  way in is the absence of the mark and "everybody else" is what the All
   *  chip beside it already means. */
  provenance: { column: string; value: string; label: string } | null;
} {
  const prov = provenanceOf(decl);
  return {
    flags: Object.keys(decl?.badges ?? {}),
    stations: [...new Set(rows.map((r) => r.station).filter((s): s is string => !!s))],
    provenance: prov && rows.some((r) => marked(r, prov))
      ? { column: prov.column, value: prov.mark, label: prov.label }
      : null,
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
