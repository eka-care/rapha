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
import type { Payload, ViewDecl } from "./types";

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
export function lead(decl: ViewDecl | undefined, record: Record<string, unknown>): {
  name: string; meta: string;
} {
  const keys = describing(decl, record);
  return {
    name: keys.length ? text(record[keys[0]]) : "",
    meta: keys.slice(1, 4).map((k) => text(record[k])).join(" · "),
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
export function fresh(
  typed: string,
  decl: ViewDecl | undefined,
  hint: (typed: string) => string | undefined,
  label: string,
): DeskRow {
  const want = typed.trim();
  const mobile = hint(want);
  const nameKey = ((decl?.columns ?? []) as string[])[0];
  return {
    kind: "fresh",
    id: "fresh",
    name: label,
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
export function rows(
  found: Resolution | null,
  typed: string,
  decl: ViewDecl | undefined,
  questions: { link_id: string; answer_option?: { value: string }[] }[],
  hint: (typed: string) => string | undefined,
  freshLabel: string,
): DeskRow[] {
  const out: DeskRow[] = [];
  if (found) {
    for (const record of found.local) {
      const { name, meta } = lead(decl, record);
      out.push({
        kind: "known",
        id: `known:${text(record.id) || name}`,
        name, meta,
        values: answers(record, questions),
      });
    }
    for (const s of found.suggestions) {
      const { name, meta } = lead(decl, s.values);
      out.push({
        kind: "suggested",
        id: `suggested:${s.directory_id}`,
        name, meta,
        values: answers(s.values, questions),
        evidence: s.evidence,
        confidence: s.confidence,
      });
    }
  }
  if (typed.trim()) out.push(fresh(typed, decl, hint, freshLabel));
  return out;
}

/** What to say about the directory, or nothing.
 *
 *  Three states and a clerk needs them apart, which kernel/directory.py's
 *  Resolution docstring is explicit about: "one means nobody matched, the
 *  other means I could not look, and a clerk who cannot tell them apart
 *  registers a duplicate."
 */
export function directoryNote(found: Resolution | null): string {
  if (!found) return "";
  if (found.reachable) return "";
  // The kernel's sentence, finished. `reason` is a clause the directory
  // handed back and nothing promises it ends in a full stop, so running the
  // next sentence straight onto it produced "...or reachable Only this
  // centre's own register was searched."
  const said = found.reason.trim();
  if (!said) return "The patient directory could not be asked. Only this centre's own register was searched.";
  // A colon, because the kernel's clause continues this sentence rather than
  // starting its own: after a full stop it read "could not be asked. no
  // patient directory is configured". And the clause is finished with a stop
  // of its own, because nothing promises it carries one and without it the
  // next sentence ran straight onto the end of it.
  const whole = /[.!?]$/.test(said) ? said : `${said}.`;
  return `The patient directory could not be asked: ${whole} Only this centre's own register was searched.`;
}
