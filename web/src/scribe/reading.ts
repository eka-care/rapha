/** One spoken reading, transcribed by the same service that writes the notes.
 *
 *  The owner's decision of 2026-11-01: every aspect of scribing goes through
 *  the medical scribe service. This file is what that decision cost on the
 *  vitals station. The button used to drive the browser's own speech
 *  recognition, which is Google's service wearing a browser API, and on a
 *  health centre's line it answers `network` and the nurse is told to type.
 *  There is no version of this product where the words come from one vendor
 *  at the counter and another in the consulting room.
 *
 *  What this does NOT change, because it is the whole safety property of the
 *  voice instrument: a number heard is a number in an editable field, drawn
 *  as unconfirmed, committed by a tap and validated exactly as a typed one.
 *  Nothing here commits.
 *
 *  WHAT COMES BACK IS THE SERVICE'S OWN ANSWER FOR THIS FORM, not its raw
 *  transcript. The template it filled is built from the operation's declared
 *  questions, so it answers the questions and ignores everything else said in
 *  the room, with the words it took each value from beside it. A number
 *  grammar used to re-read the transcript here and refused the whole reading
 *  over a stray phrase, which is a worse reading of the same recording and
 *  threw away the evidence. `narrow()` holds the answer to the fields this
 *  instrument declares.
 *
 *  Consent is not re-implemented here and must not be. The upload is the
 *  kernel's own `/scribe/sessions`, which refuses a visit without
 *  `capture.consented` before a byte leaves this machine; its refusal is what
 *  this returns as the reason. A second consent check written in a browser is
 *  a second consent check to keep in step.
 *
 *  The audio is dropped the moment the words are read. A blood pressure said
 *  out loud is not a consultation and nothing is served by the kernel holding
 *  it, so every outcome here ends in the same withdrawal the patient's own
 *  stop button sends.
 */
import { dropSession, pollSession, startSession } from "./client";
import { heardFrom, pickMime, reasonFor, type Heard } from "./session";
import { ApiError } from "../api";

/** How long the service is given before the nurse is told to type instead.
 *  A reading is a few seconds of audio; a minute is already generous. */
const POLL_MS = 1500;
const TRIES = 40;

/** A microphone nobody stopped. The indicator is on screen the whole time,
 *  and this is the backstop under it. */
const CAP_MS = 30_000;

/** Whether this browser can record at all. False puts the keyboard on screen
 *  instead of a button that would fail after somebody spoke into it. */
export function canRecord(): boolean {
  return typeof window !== "undefined"
    && typeof window.MediaRecorder === "function"
    && !!navigator.mediaDevices?.getUserMedia;
}

export type Reading = {
  /** Stop the microphone and send what was said to be transcribed. */
  stop: () => void;
  /** Stop, send nothing, and keep nothing. Leaving the panel does this. */
  abandon: () => void;
  /** The words, or the reason there are none. Resolves once, always. */
  heard: Promise<Heard>;
};

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function recordReading(thread: string, operation: string): Reading {
  let settle!: (h: Heard) => void;
  const heard = new Promise<Heard>((r) => (settle = r));
  let done = false;
  const finish = (h: Heard) => {
    if (done) return;
    done = true;
    settle(h);
  };

  let keep = true;
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let cap: ReturnType<typeof setTimeout> | undefined;

  const stopTracks = () => stream?.getTracks().forEach((t) => t.stop());

  const send = async (blob: Blob) => {
    let id = "";
    try {
      let s = await startSession(thread, blob, [operation]);
      id = s.session;
      for (let i = 0; i < TRIES && s.status === "running" && keep; i++) {
        await wait(POLL_MS);
        s = await pollSession(id);
      }
      if (keep) finish(heardFrom(s, operation));
    } catch (e) {
      // The kernel's own words, which on a visit with no consent are the
      // refusal itself. Shown as they came rather than paraphrased here.
      finish({ transcript: "", reason: e instanceof ApiError ? e.message : "The reading went nowhere. Type the values." });
    } finally {
      if (id) void dropSession(id).catch(() => { /* already unreachable */ });
    }
  };

  const begin = async () => {
    if (typeof window.MediaRecorder !== "function" || !navigator.mediaDevices?.getUserMedia)
      return finish({ transcript: "", reason: reasonFor("mediaDevices is not a function") });
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      return finish({ transcript: "", reason: reasonFor((e as Error)?.name || String(e)) });
    }
    if (!keep) return stopTracks();            // the panel closed while it asked

    const mime = pickMime((t) => !!window.MediaRecorder?.isTypeSupported?.(t));
    const parts: Blob[] = [];
    const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder = r;
    r.ondataavailable = (e: BlobEvent) => e.data?.size && parts.push(e.data);
    r.onstop = () => {
      stopTracks();
      if (!keep) return;                        // abandoned: the blob is never sent
      if (!parts.length) return finish({ transcript: "", reason: "Nothing was recorded. Type the values." });
      void send(new Blob(parts, { type: mime || parts[0].type }));
    };
    r.start();
    cap = setTimeout(() => stop(), CAP_MS);
  };

  const halt = () => {
    clearTimeout(cap);
    try {
      recorder?.stop();                         // onstop sends, or does not
    } catch {
      stopTracks();
      finish({ transcript: "", reason: "The recorder stopped badly. Type the values." });
    }
  };

  const stop = () => halt();
  const abandon = () => {
    keep = false;
    halt();
    stopTracks();
    finish({ transcript: "", reason: "" });
  };

  void begin();
  return { stop, abandon, heard };
}
