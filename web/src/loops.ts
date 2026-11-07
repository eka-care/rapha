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
  if (decl?.columns?.length) opts.push({ key: "name", label: decl.columns[0].charAt(0).toUpperCase() + decl.columns[0].slice(1) });
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
  // The intersection applies only when the view actually declares columns.
  //
  // `/facility` sends a SHORT form of a view, with no `columns` on it, and
  // the command palette is handed that one; a screen reading the short form
  // falls back to whatever the subject carries, and the declaration about
  // that subject is still true. Requiring the column to be listed therefore
  // switched provenance OFF on exactly the screen that had no column list to
  // narrow, and the stored value went back to being drawn as a word. It did.
  const columns = decl?.columns ?? [];
  return columns.length === 0 || columns.includes(p.column) ? { ...p } : null;
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

/** One group of narrowings and the word above it. The word is this
 *  renderer's own -- a heading over a list of controls is the renderer's
 *  verb, the way a tab and a microphone are -- and every option under it is
 *  a declaration's. */
export type Narrowing = {
  /** Stable across renders, so a menu can key on it. */
  key: string;
  label: string;
  filter: Filter;
  /** How many of today's rows this would leave. A count that only appears on
   *  hover does not exist on a phone, so it is always drawn. */
  n: number;
  /** Whether the view's own badge tone says this one means clinical risk.
   *  Colour is allowed here and nowhere else. */
  risk?: boolean;
};

export type NarrowGroup = { title: string; items: Narrowing[] };

/** EVERY WAY TODAY'S LINE CAN BE NARROWED, in one list, from one
 *  declaration, for one control.
 *
 *  This exists because there were two. The list screen drew a strip of chips
 *  for the stations, the programmes and how somebody arrived, with the flags
 *  behind a button; the second panel drew its own menu of the programmes and
 *  the flags, counted off the same rows. Two controls over one question,
 *  disagreeing about which narrowings were worth offering, and neither one
 *  moved the other. The strip was also taller than the thing it filtered.
 *
 *  So the question has one home now -- the second panel, beside the people
 *  it narrows -- and this is what that control is built from. Nothing here
 *  is this renderer's judgement except the three headings, which are what a
 *  person reads to tell a place from a programme from a problem:
 *
 *    - where they are: the stations today's rows are actually at
 *    - what they are on: each declared label column's values, plus the
 *      declared provenance mark if anybody wears it
 *    - what is flagged: the view's own declared badges
 *
 *  A group with nothing in it is absent rather than empty. The "everybody"
 *  option is first and carries the whole count, because the way back from a
 *  narrowing has to be as easy to find as the narrowing was.
 */
export function narrowings(
  decl: Pick<ViewDecl, "badges" | "columns" | "labels" | "provenance"> | undefined,
  rows: QueueRow[],
  /** How a declared value is shown to a person. Passed in rather than
   *  imported so this module stays free of the value set reader, and so a
   *  caller with no display map still gets the raw declared value rather
   *  than nothing. */
  display: (column: string, value: string) => string,
  /** Turning a declared machine word -- a station, a state -- into one a
   *  person reads. Same reason. */
  humanise: (word: string) => string,
): NarrowGroup[] {
  const { flags, stations, labels, provenance } =
    filterOptions(decl, rows, labelColumns(decl));
  const groups: NarrowGroup[] = [];

  const where = stations.map((station) => ({
    key: `station:${station}`,
    label: humanise(station),
    filter: { station } as Filter,
    n: rows.filter((r) => r.station === station).length,
  }));
  if (where.length) groups.push({ title: "Where they are", items: where });

  const on: Narrowing[] = [];
  for (const { column, values } of labels) {
    for (const value of values) {
      on.push({
        key: `${column}:${value}`,
        label: display(column, value),
        filter: { column, value },
        n: rows.filter((r) => String(r.subject?.[column] ?? "") === value).length,
      });
    }
  }
  if (provenance) {
    on.push({
      key: `${provenance.column}:${provenance.value}`,
      label: provenance.label,
      filter: { column: provenance.column, value: provenance.value },
      n: rows.filter((r) =>
        String(r.subject?.[provenance.column] ?? "") === provenance.value).length,
    });
  }
  if (on.length) groups.push({ title: "What they are on", items: on });

  // Only a flag anybody is actually wearing. A station chip that says nought
  // is information -- "pharmacy is clear" is worth knowing -- but a flag
  // nobody carries is not a fact about the day, it is a fact about the
  // bundle, and this control is read while standing beside the line.
  const flagged = flags
    .map((flag) => ({
      key: `flag:${flag}`,
      label: humanise(flag),
      filter: { flag } as Filter,
      n: rows.filter((r) => r.flags.includes(flag)).length,
      risk: decl?.badges?.[flag] === RISK_TONE,
    }))
    .filter((f) => f.n > 0);
  if (flagged.length) groups.push({ title: "What is flagged", items: flagged });

  return groups;
}

/** Whether two filters are the same narrowing. Both are plain declared
 *  values, so this is a comparison and not a lookup. */
export function sameFilter(a: Filter, b: Filter): boolean {
  if (a === null || b === null) return a === b;
  if ("flag" in a) return "flag" in b && a.flag === b.flag;
  if ("station" in a) return "station" in b && a.station === b.station;
  return "column" in b && a.column === b.column && a.value === b.value;
}

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

/** The columns of the Lines table, each of which can be sorted. */
export type ColumnKey = "number" | "name" | "station" | "label" | "wait";
export type Sort = { key: ColumnKey; dir: "asc" | "desc" };

/** Sorts a copy of `rows` by one column, ascending or descending.
 *
 *  Token sorts as a number when both tokens are numbers, because "10" comes
 *  after "9". Name is the declared first column; programme is the first
 *  declared label column; a row with no station (it is done) sorts after every
 *  station going up. Waiting sorts by arrival, so ascending is the longest
 *  wait first. A tie falls back to arrival so the order never flickers. */
export function sortByColumn(
  rows: QueueRow[],
  key: ColumnKey,
  dir: "asc" | "desc",
  decl: Pick<ViewDecl, "columns" | "labels"> | undefined,
): QueueRow[] {
  const columns = decl?.columns ?? [];
  const tokenCol = columns.find((c) => /token/i.test(c));
  const nameCol = columns[0];
  const labelCol = (decl?.labels ?? []).find((l) => columns.includes(l));
  const text = (r: QueueRow, col: string | undefined) => String(col ? r.subject?.[col] ?? "" : "");
  const compare = (a: QueueRow, b: QueueRow): number => {
    switch (key) {
      case "number": {
        const x = text(a, tokenCol), y = text(b, tokenCol);
        const nx = Number(x), ny = Number(y);
        return x !== "" && y !== "" && Number.isFinite(nx) && Number.isFinite(ny)
          ? nx - ny : x.localeCompare(y);
      }
      case "name": return text(a, nameCol).localeCompare(text(b, nameCol));
      case "station": return (a.station ?? "\uffff").localeCompare(b.station ?? "\uffff");
      case "label": return text(a, labelCol).localeCompare(text(b, labelCol));
      default: return (a.opened_at ?? "").localeCompare(b.opened_at ?? "");
    }
  };
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) =>
    sign * compare(a, b) || (a.opened_at ?? "").localeCompare(b.opened_at ?? ""));
}
