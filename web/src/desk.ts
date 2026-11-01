/** The front desk, worked out without a browser.
 *
 *  One box. The clerk types what the patient says; the local register and the
 *  patient directory are asked at the same time and answer into the same
 *  list. Choosing anybody on that list opens the registration form ALREADY
 *  FILLED, and the clerk corrects rather than types. That is the whole design
 *  and it is the one in docs/reference/front-desk/one-sequence.html and
 *  front-desk.html, option A.
 *
 *  WHY THE VALUES ARE SAFE TO PUT ON A FORM AND NOT SAFE TO COMMIT. A
 *  directory hit is a SUGGESTION, which kernel/directory.py's own docstring
 *  is explicit about: "values for the register form, with the field the match
 *  came from beside each one. A person reads it, edits it if it is wrong, and
 *  taps commit." So nothing in this file writes, nothing it produces is an
 *  assertion, and every row it returns ends at the same guarded commit the
 *  panel has always done. The suggestion even arrives with its confidence
 *  capped under the renderer's SURE threshold, so the fields draw unconfirmed
 *  on purpose.
 *
 *  WHAT THIS FILE MAY NOT KNOW. It may not name a station, a flag, a
 *  capability, a bundle or a column, so it never asks a record for "village"
 *  or "token". What a row leads with and what it says underneath come from
 *  the queue view's own `columns:`, in the order the view declared them --
 *  the same rule view/View.tsx follows for a queue row, for the same reason.
 *  And which operation a chosen row commits through is the SERVER's answer,
 *  carried on the search response as `commits_through`, so the desk cannot
 *  disagree with the kernel about what registering is.
 */
import type { Catalogue, Display, Operation, Payload, QueueRow, ViewDecl, Workflow } from "./types";
import { human, title as titleCase } from "./words.ts";

/** One directory profile, as values for the register form. The shape
 *  kernel/directory.Suggestion serialises to. */
export type Suggestion = {
  directory_id: string;
  values: Record<string, unknown>;
  /** Per link_id, where that value came from. Shown beside the field. */
  evidence?: Record<string, string>;
  /** Per link_id, 0 to 1, and deliberately capped under the renderer's SURE
   *  threshold by the kernel: a directory match is somebody with a similar
   *  name or the same phone, which is the case that must not pass unread. */
  confidence?: Record<string, number>;
};

/** What GET /patients/search answers. Always 200, even with no directory:
 *  `reachable` false and a `reason` sit beside whatever the local register
 *  found. A clerk looking for somebody who is already in today's line must
 *  not be shown a failure about a directory they were not relying on. */
export type Resolution = {
  query: string;
  local: Record<string, unknown>[];
  suggestions: Suggestion[];
  reachable: boolean;
  reason: string;
  commits_through: string;
};

/** A row on the desk.
 *
 *  `known` is somebody this facility already holds. `suggested` is somebody
 *  the directory knows and we do not. `fresh` is nobody yet: the row that
 *  keeps what was typed and opens the identity journey.
 *
 *  All three carry `values`, because all three end on the same form. That is
 *  the non-goal in the spec made structural: "No second registration form.
 *  Both routes to a profile end on the same screen."
 */
export type DeskRow = {
  kind: "known" | "suggested" | "fresh";
  /** Stable across keystrokes, so the keyboard selection does not jump. */
  id: string;
  name: string;
  meta: string;
  values: Payload;
  evidence?: Record<string, string>;
  confidence?: Record<string, number>;
  /** A mobile number the clerk already typed, handed to the identity journey
   *  so nobody types it twice. Only ever on a `fresh` row: a person we have
   *  already found is not asked for a one time password. */
  mobile?: string;
  /** Whether the record this row is about already carries a national health
   *  account. Drawn as the lotus beside the name, the same mark the queue row
   *  wears, because a clerk about to commit somebody else's record to the day
   *  needs every corroborating fact the row can carry. Decided by the one
   *  documented exception in this renderer and injected, not tested here. */
  identified?: boolean;
};

/** Everything the desk draws a row out of that it may not know by itself.
 *
 *  Gathered into one argument rather than six positional ones. Each member is
 *  a declaration or a rule from somewhere this file may not import: `hint`
 *  and `identified` are the ABHA exception, which lives in abha/; `display`
 *  is what a bundle calls one of its own stored codes; `decl` is the queue
 *  view; `freshLabel` is the declared verb of the operation that creates.
 */
export type Desk = {
  decl?: ViewDecl;
  questions: { link_id: string; answer_option?: { value: string }[] }[];
  hint: (typed: string) => string | undefined;
  freshLabel: string;
  /** What a declared value is CALLED. Without it a row drew the stored code,
   *  so a centre's antenatal patient read `anc` on the one line a clerk uses
   *  to decide whether this is the right person. */
  display: Display;
  /** Whether a record carries a national health account. */
  identified: (record: Record<string, unknown>) => boolean;
};

/** Plumbing, not something to show a clerk. The same test view/View.tsx
 *  applies to a queue row's subject. */
const PLUMBING = /(^|_)id$|_date$|_by$/;

const text = (v: unknown) => (v === null || v === undefined ? "" : String(v));

/** Which keys describe a person, in the order the view declared them.
 *
 *  A view that declares no columns falls back to whatever the record carries
 *  minus the plumbing, which is what a bundle with a short view declaration
 *  has always got.
 */
export function describing(decl: ViewDecl | undefined, record: Record<string, unknown>): string[] {
  const declared = (decl?.columns ?? []) as string[];
  const keys = declared.length ? declared : Object.keys(record).filter((k) => !PLUMBING.test(k));
  return keys.filter((k) => text(record[k]) !== "");
}

/** What a desk row leads with, and what it says underneath.
 *
 *  Not view/View.tsx's `fields()`, although it reads the same declaration the
 *  same way. That one also has to pull the number out into its own square and
 *  append the station a thread is standing at; a patient record has neither a
 *  thread nor a station, so there is no number to lift and nothing to append.
 *  Sharing the half that is common would leave both callers reading a
 *  function whose other half is about the one thing they do not have.
 */
export function lead(
  decl: ViewDecl | undefined,
  record: Record<string, unknown>,
  /** What a declared value is called. A row that says `anc` where the queue
   *  beside it says RCH is two screens disagreeing about one patient, and
   *  this is the row a clerk reads before committing somebody else's record
   *  to the day. */
  display: Display = (_k, v) => v,
): { name: string; meta: string } {
  const keys = describing(decl, record);
  return {
    name: keys.length ? text(record[keys[0]]) : "",
    // EVERY other column the view declared that this record carries, not the
    // first three. The mockup's row is `34 · female · Sonpur · last seen 18
    // Jun`, and the point of the line is that a clerk can be SURE this is the
    // person in front of them before they commit the day to it. Capped at
    // five so one richly declared view cannot run the line off the row.
    meta: keys.slice(1, 6).map((k) => display(k, text(record[k]))).join(" · "),
  };
}

/** Which workflow this screen is about: the one the facility named, or the
 *  only one there is. The same fallback search.firstOperation makes, for the
 *  same reason. */
function workflowOf(cat: Catalogue, workflow?: string): Workflow | undefined {
  return (workflow && cat.workflows?.[workflow]) || Object.values(cat.workflows ?? {})[0];
}

/** The station a patient reaches first. The workflow's first step, and the
 *  only thing on this screen that says which arrivals the desk has not met
 *  yet: a thread standing there has not been sent on. */
export function firstStation(cat: Catalogue, workflow?: string): string | undefined {
  return workflowOf(cat, workflow)?.steps?.[0]?.station;
}

/** WHAT THIS SCREEN IS CALLED.
 *
 *  It was called "Register a new patient", which is the declared title of the
 *  operation the panel commits through -- so the screen wore the name of one
 *  of the two things it does, and wore it while the clerk was searching for
 *  somebody who is already registered.
 *
 *  A screen's name has to come from a declaration like every other word here,
 *  and the declaration that already says what this place is, is the
 *  workflow's: its FIRST STEP is the station a patient reaches first, and
 *  this screen is that station. So a health centre's desk is named after the
 *  centre's own first station and a laboratory's bench after its own, with no
 *  word typed here and no second declaration invented.
 *
 *  Empty when the workflow declares no steps, and the caller falls back to
 *  what it drew before rather than to a word of its own.
 */
export function deskTitle(cat: Catalogue, workflow?: string): string {
  return titleCase(firstStation(cat, workflow) ?? "");
}

/** WHERE TAKING A ROW SENDS THIS PERSON, in the workflow's own word.
 *
 *  The mockup draws the selected row as `↵ send to nurse`, and the spec's
 *  first goal is that a returning patient reaches the nurse without the clerk
 *  typing a full record. The row said `↵` and nothing else, so the one thing
 *  a clerk needed to know about the key -- where it leads -- was the one
 *  thing it did not say.
 *
 *  Read off the workflow: the step after the one the chosen operation belongs
 *  to. A step the workflow declares CONDITIONAL is skipped, because a
 *  conditional step is one a patient may not walk at all and naming it would
 *  promise a destination nobody can be sure of. Empty when the operation ends
 *  the line, and then the row says nothing rather than guessing.
 */
export function destination(
  cat: Catalogue, op: Operation | undefined, workflow?: string,
): string {
  const steps = workflowOf(cat, workflow)?.steps ?? [];
  const at = steps.findIndex((s) => s.station === op?.station);
  if (at < 0) return "";
  return human(steps.slice(at + 1).find((s) => !s.applies_when)?.station ?? "");
}

/** WHAT IS ON THIS SCREEN BEFORE A KEY IS PRESSED.
 *
 *  The desk used to say "Nobody searched for yet.", which tells a clerk
 *  arriving at their shift nothing at all. The spec's goals name the poster
 *  queue and the day's numbers, and both are already in the rows the declared
 *  queue view returns. Three facts come out of them and nothing else does:
 *
 *   - WHO IS HERE AND HAS NOT BEEN SENT ON. A thread standing at the
 *     workflow's first step has not been registered. That is the person who
 *     scanned the poster by the door and is sitting in the waiting room, and
 *     the desk is the only place anybody finds out. The spec: "Self
 *     registration by poster takes the clerk out of the loop entirely" -- but
 *     only if the clerk can see them.
 *   - HOW MANY ARE IN THE LINE, which is the one number a clerk is asked all
 *     day and the one they cannot see from a search box.
 *   - WHO THIS DESK HAS ALREADY SENT ON TODAY, newest first, so a patient
 *     being registered twice in one morning is caught by eye before a second
 *     record exists. Nothing merges two.
 *
 *  It is not a dashboard and it is not allowed to become one: three numbers
 *  and two short lists, and this function caps both.
 */
export type Arrivals = {
  /** Standing at the first step: arrived, not sent on. */
  waiting: QueueRow[];
  /** Past the first step and still walking the line. */
  moving: QueueRow[];
  /** Past the first step, newest first, capped. */
  sent: QueueRow[];
  /** Everybody the queue returned, including those whose line has finished. */
  all: number;
};

export function arrivals(
  rows: QueueRow[], first: string | undefined, take = 4,
): Arrivals {
  const waiting = first ? rows.filter((r) => r.station === first) : [];
  const past = rows.filter((r) => r.station !== first);
  const newest = [...past].sort((a, b) => String(b.opened_at).localeCompare(String(a.opened_at)));
  return {
    waiting: waiting.slice(0, take),
    moving: past.filter((r) => r.station),
    sent: newest.slice(0, take),
    all: rows.length,
  };
}

/** The record, as THIS form's own questions ask for it.
 *
 *  Asked of the questions and not of a field list, for the reason
 *  abha/sdk.ts's demographicsFrom states and proves: a value a form cannot
 *  show is worse than no value, because a `choice` whose answer is not one of
 *  its own options renders as an empty select over a payload that still
 *  carries the answer, and that is a commit nobody read.
 *
 *  It also means the desk never enumerates a field. A bundle that asks for a
 *  district gets a district here with no edit, and a bundle that does not ask
 *  is not told.
 */
export function answers(
  record: Record<string, unknown>,
  questions: { link_id: string; answer_option?: { value: string }[] }[],
): Payload {
  const out: Payload = {};
  for (const q of questions) {
    const value = text(record[q.link_id]);
    if (!value) continue;
    const options = q.answer_option?.map((o) => o.value);
    if (options && !options.includes(value)) continue;
    out[q.link_id] = value;
  }
  return out;
}

/** The row for somebody nobody has found.
 *
 *  Two different things can have been typed and they go to different places.
 *  A mobile number is handed to the identity journey, which is what the
 *  journey's own `mobile` argument is for, so the patient is not asked to
 *  read their number out twice. Anything else is kept as the name, which is
 *  the first column the view declared -- the same convention loops.ts already
 *  uses when it labels the sort by `decl.columns[0]`.
 *
 *  `hint` is abha/sdk.ts's mobileHint, passed in rather than imported, so
 *  this file stays free of the one exception and the check can drive it.
 */
export function fresh(typed: string, d: Desk): DeskRow {
  const want = typed.trim();
  const mobile = d.hint(want);
  const nameKey = ((d.decl?.columns ?? []) as string[])[0];
  return {
    kind: "fresh",
    id: "fresh",
    name: d.freshLabel,
    meta: want,
    values: !mobile && nameKey && want ? { [nameKey]: want } : {},
    ...(mobile ? { mobile } : {}),
  };
}

/** Everybody the desk can offer, in the order a clerk should read them.
 *
 *  Ours first, then the directory's, then the row that creates. Find before
 *  create, which is §2.9 and is also the one anti-goal with a permanent cost:
 *  a second ABHA number for one person is a mistake the patient carries for
 *  life, because nothing merges two.
 *
 *  The fresh row is last and is always present once something has been typed,
 *  including when the directory could not be asked. A clerk whose directory
 *  is down must still be able to register the person standing in front of
 *  them, and a desk that offers nothing is a desk that sends them away.
 */
export function rows(found: Resolution | null, typed: string, d: Desk): DeskRow[] {
  const out: DeskRow[] = [];
  if (found) {
    for (const record of found.local) {
      const { name, meta } = lead(d.decl, record, d.display);
      out.push({
        kind: "known",
        id: `known:${text(record.id) || name}`,
        name, meta,
        values: answers(record, d.questions),
        identified: d.identified(record),
      });
    }
    for (const s of found.suggestions) {
      const { name, meta } = lead(d.decl, s.values, d.display);
      out.push({
        kind: "suggested",
        id: `suggested:${s.directory_id}`,
        name, meta,
        values: answers(s.values, d.questions),
        evidence: s.evidence,
        confidence: s.confidence,
        identified: d.identified(s.values),
      });
    }
  }
  if (typed.trim()) out.push(fresh(typed, d));
  return out;
}

/** What to say about the directory, or nothing.
 *
 *  Three states and a clerk needs them apart, which kernel/directory.py's
 *  Resolution docstring is explicit about: "one means nobody matched, the
 *  other means I could not look, and a clerk who cannot tell them apart
 *  registers a duplicate."
 *
 *  ONE SENTENCE, LEADING WITH THE FACT THE CLERK NEEDS. It used to be two,
 *  and the first of them was about a directory the clerk never asked for:
 *  "The patient directory could not be asked: no patient directory is
 *  configured or reachable. Only this centre's own register was searched." In
 *  a deployment with no directory that is permanently true, so it was drawn
 *  on every search, hundreds of times a day, in warning colour, above the
 *  patient. What a clerk actually has to know is which register answered;
 *  WHY the other one did not is the clause after the colon, and it is still
 *  the kernel's own words rather than a sentence invented here.
 */
export function directoryNote(found: Resolution | null): string {
  if (!found) return "";
  if (found.reachable) return "";
  const said = found.reason.trim();
  // The kernel's clause is a fragment and nothing promises it ends in a stop,
  // so the sentence is finished here rather than run on. A reason that
  // already carries one does not get a second.
  if (!said) return "Only this centre's own register was searched: the patient directory could not be asked.";
  return `Only this centre's own register was searched: ${/[.!?]$/.test(said) ? said : `${said}.`}`;
}
