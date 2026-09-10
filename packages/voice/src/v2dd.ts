/**
 * v2dd: voice to discrete data. The browser side of the constrained voice
 * instrument declared in bundles/phc/phc.inst.vitals-voice.md.
 *
 * The one rule this module exists to keep: voice is an input instrument and
 * never a commit path. Nothing here writes, proposes, or calls an API. It
 * hands back a Draft, which is a set of values for editable fields on screen,
 * and a person taps commit. That tap goes through the same guard and the same
 * validator a typed value goes through. There is deliberately no callback,
 * option or flag in this file that could commit anything: the safety property
 * is absent code, not a remembered convention.
 *
 * Fails closed. An empty Draft means: show the numeric keypad. That happens
 * when the recogniser is unavailable, hears nothing, errors, returns a low
 * confidence, or returns something the grammar refuses to guess at.
 *
 * Uses the browser Web Speech API, which needs no key and no server. Chrome
 * and Edge implement it; Firefox does not, and there `available()` is false
 * and the caller shows the keypad.
 */
import { parse, type FieldSpec } from "./grammar.ts";

/** Mirrors kernel/contracts.py Draft. Not a write and not a proposal. */
export type Draft = {
  instrument: string;
  operation: string;
  values: Record<string, number>;
  confidence: Record<string, number>;
  transcript?: string;
  /** why the keypad is being shown, when values is empty. For the operator. */
  reason?: string;
};

/** Below this the recogniser is not trusted at all and we go to the keypad.
 *  Above it, the value is still shown back and still needs a tap. */
export const FAIL_CLOSED_BELOW = 0.5;

/** Pure. The whole decision of what reaches the screen, testable with no
 *  browser: everything below is the microphone plumbing around this. */
export function toDraft(
  transcript: string,
  asrConfidence: number,
  fields: FieldSpec[],
  meta: { instrument: string; operation: string },
): Draft {
  const empty = (reason: string): Draft => ({
    ...meta, values: {}, confidence: {}, transcript, reason,
  });

  // Some engines report 0 when they decline to score. Treat it as unknown, not
  // as certainty, and let the grammar's own confidence carry the value.
  const asr = asrConfidence > 0 ? asrConfidence : 0.6;
  if (asr < FAIL_CLOSED_BELOW) return empty("did not hear that clearly");

  const got = parse(transcript, fields);
  if (!got.ok) return empty(got.reason);

  const confidence: Record<string, number> = {};
  for (const [id, c] of Object.entries(got.confidence)) {
    const combined = Math.min(asr, c);
    if (combined < FAIL_CLOSED_BELOW) return empty("did not hear that clearly");
    confidence[id] = combined;
  }
  return { ...meta, values: got.values, confidence, transcript };
}

type Recogniser = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: any) => void) | null;
  onerror: ((e: any) => void) | null;
  onend: (() => void) | null;
};

function recogniser(): Recogniser | null {
  const w = globalThis as any;
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return Ctor ? (new Ctor() as Recogniser) : null;
}

export function available(): boolean {
  return recogniser() !== null;
}

export type ListenOptions = {
  fields: FieldSpec[];
  instrument: string;
  operation: string;
  /** en-IN by default: the recogniser's Indian English acoustic model reads
   *  "one forty" and Indian names markedly better than en-US does. */
  lang?: string;
  timeoutMs?: number;
};

/**
 * Listen once for a value, and resolve with a Draft the caller must render.
 *
 * The caller's contract: draw every value in an editable field, highlight it
 * as unconfirmed, and commit only on a tap. An empty Draft means keypad.
 */
export function captureValue(opts: ListenOptions): Promise<Draft> {
  const meta = { instrument: opts.instrument, operation: opts.operation };
  const rec = recogniser();
  if (!rec) {
    return Promise.resolve({
      ...meta, values: {}, confidence: {},
      reason: "this browser has no speech recognition",
    });
  }
  rec.lang = opts.lang ?? "en-IN";
  rec.continuous = false;
  rec.interimResults = false;
  rec.maxAlternatives = 1;

  return new Promise<Draft>((resolve) => {
    let done = false;
    const finish = (d: Draft) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      try { rec.abort(); } catch { /* already stopped */ }
      resolve(d);
    };
    const timer = setTimeout(
      () => finish({ ...meta, values: {}, confidence: {}, reason: "heard nothing" }),
      opts.timeoutMs ?? 8000,
    );

    rec.onresult = (e: any) => {
      const alt = e.results?.[e.results.length - 1]?.[0];
      if (!alt) return finish({ ...meta, values: {}, confidence: {}, reason: "heard nothing" });
      finish(toDraft(String(alt.transcript ?? ""), Number(alt.confidence ?? 0), opts.fields, meta));
    };
    rec.onerror = (e: any) =>
      finish({ ...meta, values: {}, confidence: {}, reason: `microphone: ${e?.error ?? "error"}` });
    rec.onend = () =>
      finish({ ...meta, values: {}, confidence: {}, reason: "heard nothing" });

    rec.start();
  });
}

/**
 * Narrative dictation. A separate mode, and separate on purpose: this produces
 * draft prose for a text field, such as the history in a consultation note. It
 * is not allowed anywhere near a discrete value, which is why it returns text
 * and never a Draft, and why the scribe instrument may not attach to vitals.
 *
 * The text still lands in an editable field that a clinician reads and taps.
 */
export function dictate(opts: {
  lang?: string;
  onText?: (text: string) => void;
  timeoutMs?: number;
}): { stop: () => void; done: Promise<string> } {
  const rec = recogniser();
  if (!rec) return { stop: () => {}, done: Promise.resolve("") };
  rec.lang = opts.lang ?? "en-IN";
  rec.continuous = true;
  rec.interimResults = true;
  rec.maxAlternatives = 1;

  let text = "";
  let resolve!: (s: string) => void;
  const done = new Promise<string>((r) => (resolve = r));
  const stop = () => {
    try { rec.stop(); } catch { /* already stopped */ }
  };

  rec.onresult = (e: any) => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) text += e.results[i][0].transcript;
    }
    opts.onText?.(text);
  };
  rec.onerror = () => stop();
  rec.onend = () => resolve(text.trim());
  rec.start();
  if (opts.timeoutMs) setTimeout(stop, opts.timeoutMs);
  return { stop, done };
}
