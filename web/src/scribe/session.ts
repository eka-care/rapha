/** The consultation recording, from this browser to the kernel and back again.
 *
 *  This is not the voice path and it must not be confused with it.
 *  `packages/voice` is a constrained number grammar that runs in the browser
 *  and never leaves it. This is audio, uploaded, transcribed by a service, and
 *  returned as a draft. The Eka credentials are the kernel's and are never
 *  here: this file posts a blob to `/scribe/sessions` and reads what comes
 *  back, which is `api/scribe.py:public()` and carries no transaction id.
 *
 *  Everything here is pure and is what `scribe.check.ts` runs; the three calls
 *  themselves are in client.ts.
 *
 *  The rule this file holds is the tick rule: the kernel may fill any question
 *  its instrument declares, numbers included, but a non-text value it filled
 *  is not committed on the strength of the recording alone. It needs a
 *  person's tick, and editing it to something else -- rather than ticking it
 *  -- makes it the person's number, not a heard one.
 */
import type { Payload } from "../types";

export type ScribeStatus = "running" | "ready" | "failed" | "withdrawn";

export type ScribeDraft = {
  instrument: string;
  operation: string;
  values: Record<string, unknown>;
  /** Per link_id, 0 to 1. Eka reports no per field score, so every one of
   *  these is 0: the panel draws anything under 0.9 as unconfirmed, which is
   *  exactly what a scribe draft is. Zero here means "not scored" and not
   *  "nought per cent sure", and web/src/Form.tsx says so in words rather than
   *  drawing a percentage nobody measured. The only confidence Eka's response
   *  carries is a boolean about whether a diagnosis matched a code, and
   *  audio_matrix is about the recording rather than the words. */
  confidence: Record<string, number>;
  /** The words each value was taken from, shown beside the field. */
  evidence: Record<string, string>;
  /** Non-text values: each needs a person's tick before Commit. */
  tick: string[];
  /** Heard, but not a value this form can hold. Named, never guessed into a field. */
  unfilled: string[];
  transcript: string;
};

export type ScribeSession = {
  session: string;
  status: ScribeStatus;
  reason: string;
  drafts: ScribeDraft[];
  transcript: string;
  operations: string[];
};

// ----------------------------------------------------------------- the pure half

/** A draft open in a panel, with the key that panel is mounted under. */
export type Opened = { draft: ScribeDraft; key: string; n: number };

/** Fold a ready session's drafts into the panels already open. A draft
 *  replaces only the panel for its own operation, under a new key so that
 *  panel remounts with fresh payload and ticks rather than keeping the old
 *  values and reading the new ones as typed. Panels for other operations,
 *  possibly half edited, stay exactly as they are. */
export function mergeDrafts(current: Opened[], incoming: ScribeDraft[], session: string): Opened[] {
  const out = [...current];
  for (const draft of incoming) {
    const i = out.findIndex((o) => o.draft.operation === draft.operation);
    const n = i < 0 ? 0 : out[i].n + 1;
    const next = { draft, n, key: `${session}:${draft.operation}:${n}` };
    if (i < 0) out.push(next);
    else out[i] = next;
  }
  return out;
}

export const draftFor = (s: ScribeSession | null, operation: string): ScribeDraft | null =>
  s?.drafts.find((d) => d.operation === operation) ?? null;

/** The other forms this recording filled, which are not on this screen. Named
 *  rather than silently dropped: a doctor who recorded once should not have to
 *  guess that the prescription is waiting under the next action. */
export const elsewhere = (s: ScribeSession | null, operation: string): string[] =>
  (s?.drafts ?? []).map((d) => d.operation).filter((id) => id !== operation);

export type Applied = {
  /** Goes straight into the empty fields, marked unconfirmed. */
  fill: Record<string, unknown>;
  /** A field the person already typed into. Their text stands; the drafted
   *  text is offered beside it and taken only by a tap. */
  held: { link_id: string; value: unknown }[];
  /** Kept for type compatibility with callers that still read it. The kernel
   *  fills only what its instrument declares, so this is always empty. */
  refused: string[];
};

export function apply(draft: ScribeDraft | null, payload: Payload): Applied {
  const out: Applied = { fill: {}, held: [], refused: [] };
  for (const [link_id, value] of Object.entries(draft?.values ?? {})) {
    if (typed(payload[link_id])) out.held.push({ link_id, value });
    else out.fill[link_id] = value;
  }
  return out;
}

/** The ticked fields still owed before Commit: values the kernel heard that
 *  have not been ticked, and have not been typed over either -- typing over
 *  one makes it the person's number, not a heard one, and it drops off this
 *  list without ever being ticked. */
export function mustTick(draft: ScribeDraft | null, ticked: Set<string>, payload: Payload): string[] {
  return (draft?.tick ?? []).filter(
    (id) => !ticked.has(id) && JSON.stringify(payload[id]) === JSON.stringify(draft!.values[id]),
  );
}

/** The operation a doctor filled from a recording last time, at this station.
 *  Not a preference worth losing to a private window or a cleared cache: a
 *  wrong guess costs one extra tap, on the picker this restores. */
const KEY = (role: string, station: string) => `scribe.template.${role}.${station}`;

export function lastTemplate(role: string, station: string): string | null {
  try { return localStorage.getItem(KEY(role, station)); } catch { return null; }
}

export function rememberTemplate(role: string, station: string, op: string) {
  try { localStorage.setItem(KEY(role, station), op); } catch { /* private mode */ }
}

/** Whether a person has already put something in this field. An empty string,
 *  an empty list and an empty row all count as nothing. */
function typed(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (Array.isArray(value)) return value.some((v) => typed(v));
  if (typeof value === "object") return Object.values(value as object).some((v) => typed(v));
  return String(value).trim() !== "";
}

/** What the thread should say while this is happening, in words that do not
 *  promise anything. Every one of them ends the same way on purpose: the
 *  keyboard is always the answer and it is never a downgrade.
 */
export function sentence(status: ScribeStatus | "idle" | "recording" | "uploading",
                         reason = ""): string {
  switch (status) {
    case "recording":
    case "uploading":
      // The live indicator and the spinner above already say this in a word.
      return "";
    case "running":
      // The spinner beside this already says it.
      return "";
    case "ready":
      // The fields are marked unconfirmed. Saying it again here is decoration.
      return "";
    case "failed":
      return reason || "No draft. Type the note.";
    case "withdrawn":
      // This control stops one recording and discards it. Keeping capture
      // off for the rest of the visit is a flag, written by the consultation
      // form's own stop question, which is a pill away and not this screen's
      // to explain.
      return "Discarded. Anything already confirmed stands.";
    default:
      return "";
  }
}

/** What the browser will actually record in. Chrome and Edge give webm/opus,
 *  Safari gives mp4. An empty string means "whatever you have": the kernel
 *  reads the Content-Type and names the file accordingly. */
export function pickMime(supported: (t: string) => boolean): string {
  return ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find(supported) ?? "";
}

/** The microphone was refused, or there is not one. The recogniser's codes in
 *  web/src/voice say the same things; these are getUserMedia's. */
export function reasonFor(name: string): string {
  if (/NotAllowed|Security/.test(name))
    return "Microphone blocked. Allow it in the address bar, or type the note.";
  if (/NotFound|Overconstrained/.test(name))
    return "No microphone. Type the note.";
  if (/NotReadable|Aborted/.test(name))
    return "Another app holds the microphone. Type the note.";
  if (/undefined|not a function|mediaDevices/.test(name))
    return "Recording needs https or localhost. Type the note.";
  return `The microphone did not start (${name}). Type the note.`;
}

/** A drafted value as one readable line, whatever shape it is. */
export function preview(value: unknown): string {
  if (Array.isArray(value)) return value.map(preview).join("; ");
  if (value && typeof value === "object")
    return Object.values(value as Record<string, unknown>).filter(Boolean).map(String).join(" ");
  return String(value ?? "");
}
