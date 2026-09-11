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
 *  The rule this file holds is the instrument rule: a recording may fill a
 *  narrative or structured field and may never fill a number, so a draft value
 *  for a numeric question is dropped here as well as being absent from what the
 *  kernel sends. Two gates, because a misheard number is silent, plausible and
 *  unrecoverable.
 */
import type { Payload, Question, Questionnaire } from "../types";
import { walk } from "../validate.ts";      // the extension is for node: scribe.check.ts runs this outside vite

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
  transcript: string;
};

export type ScribeSession = {
  session: string;
  status: ScribeStatus;
  reason: string;
  drafts: ScribeDraft[];
};

// ----------------------------------------------------------------- the pure half

/** One recording fills more than one form: the declaration names the consult
 *  and the prescription. The panel is per operation, so a session outlives the
 *  panel that started it and the next panel finds it here. Module level, so a
 *  reload loses it, which costs one re-recording and costs the record nothing.
 */
const LIVE = new Map<string, string>();

export const remember = (thread: string, session: string) => LIVE.set(thread, session);
export const forget = (thread: string) => LIVE.delete(thread);
export const liveSession = (thread: string) => LIVE.get(thread);

export const draftFor = (s: ScribeSession | null, operation: string): ScribeDraft | null =>
  s?.drafts.find((d) => d.operation === operation) ?? null;

/** The other forms this recording filled, which are not on this screen. Named
 *  rather than silently dropped: a doctor who recorded once should not have to
 *  guess that the prescription is waiting under the next action. */
export const elsewhere = (s: ScribeSession | null, operation: string): string[] =>
  (s?.drafts ?? []).map((d) => d.operation).filter((id) => id !== operation);

/** The link_ids a recording is allowed to fill on this form: narrative and
 *  structured, never a number. Same rule as web/src/voice/instruments.ts
 *  applies in the other direction, and it is the renderer's own, not a
 *  courtesy extended to whatever the server sent. */
export function narrative(schema: Questionnaire): Set<string> {
  return new Set(
    walk(schema.questions)
      .filter((q: Question) => q.type === "text" || q.type === "structured")
      .map((q: Question) => q.link_id),
  );
}

export type Applied = {
  /** Goes straight into the empty fields, marked unconfirmed. */
  fill: Record<string, unknown>;
  /** A field the person already typed into. Their text stands; the drafted
   *  text is offered beside it and taken only by a tap. */
  held: { link_id: string; value: unknown }[];
  /** A value for a question a recording may not fill. Should be empty: the
   *  server fills no numeric field either. Shown if it ever is not. */
  refused: string[];
};

export function apply(draft: ScribeDraft | null, allowed: Set<string>, payload: Payload): Applied {
  const out: Applied = { fill: {}, held: [], refused: [] };
  for (const [link_id, value] of Object.entries(draft?.values ?? {})) {
    if (!allowed.has(link_id)) {
      out.refused.push(link_id);
    } else if (typed(payload[link_id])) {
      out.held.push({ link_id, value });
    } else {
      out.fill[link_id] = value;
    }
  }
  return out;
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
