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
      return "Recording this consultation. The patient agreed to it at the desk, and the indicator above stays on for as long as it runs.";
    case "uploading":
      return "Sending the recording to the kernel, which holds the credentials. The audio is deleted there as soon as it has been handed on.";
    case "running":
      return "The scribe is working on it. This usually takes under a minute. You do not have to wait: type the note and what you type is what is kept.";
    case "ready":
      return "The draft is in the fields below, marked unconfirmed. Read every value against what was said, correct anything wrong, and tap Commit. Nothing is recorded until you do.";
    case "failed":
      return reason || "The scribe could not produce a draft. Type the note.";
    case "withdrawn":
      // Honest about what this control does and does not do. It stops this
      // recording and discards it, which is the half of addendum E.3 a
      // renderer can do on its own. Keeping capture off for the rest of the
      // visit is a flag, and a flag is written by an operation: the
      // consultation form's own stop question. There is no one tap withdrawal
      // here because no bundle can declare an operation for one yet.
      return "Stopped. The recording was discarded and nothing from it was kept. To keep capture off for the rest of this visit, tick the patient's stop question on the consultation form and commit it. Anything already confirmed stands.";
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
    return "This page is not allowed to use the microphone. Click the icon at the left of the address bar, allow it, and try again. Until then, type the note: it is the same record.";
  if (/NotFound|Overconstrained/.test(name))
    return "No microphone was found on this machine. Plug one in and reload, or type the note.";
  if (/NotReadable|Aborted/.test(name))
    return "Something else on this machine is holding the microphone. Close it and try again, or type the note.";
  if (/undefined|not a function|mediaDevices/.test(name))
    return "This browser will not record on an insecure origin. It needs https or localhost. Type the note.";
  return `The microphone did not start (${name}). Type the note.`;
}

/** A drafted value as one readable line, whatever shape it is. */
export function preview(value: unknown): string {
  if (Array.isArray(value)) return value.map(preview).join("; ");
  if (value && typeof value === "object")
    return Object.values(value as Record<string, unknown>).filter(Boolean).map(String).join(" ");
  return String(value ?? "");
}
