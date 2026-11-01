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
 * when nothing was heard, the transcription failed, the confidence is low,
 * or the words are something the grammar refuses to guess at.
 *
 * This module no longer listens. It used to drive the browser's Web Speech
 * API, which is one vendor's speech service wearing a browser interface, and
 * on a health centre's line it answers `network` and the nurse is told to
 * type. The owner's decision of 2026-11-01 is that every aspect of scribing
 * goes through the medical scribe service, so the words now arrive from
 * web/src/scribe/reading.ts and this file is the pure half it feeds: the
 * decision about what a transcript is allowed to put in a field.
 *
 * That half is the one worth keeping. It is what refuses a plausible
 * mishearing, and it runs under plain node with no microphone and no network.
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
