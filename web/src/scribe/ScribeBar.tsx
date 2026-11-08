/** Recording a consultation, from the encounter. The browser records; the
 *  kernel holds the credentials; the doctor confirms.
 *
 *  Deliberately not the microphone in web/src/voice. That one is a number
 *  grammar running inside this browser, for one reading at a time, and it is
 *  drawn as a small button beside the field it fills. This is a whole
 *  consultation leaving the machine, so it is a bar of its own between the
 *  thread and the composer, in different words and a different colour, and it
 *  says what it is doing the entire time.
 *
 *  It belongs to the encounter rather than to a form because a doctor records
 *  first and decides what it fills afterwards: the template picker chooses the
 *  operation, and switching it after the fact refills from the same transcript
 *  instead of asking for the consultation twice.
 *
 *  This component cannot write. It has no client and it never calls commit or
 *  confirm: it hands the ready session up, the encounter opens each draft in
 *  the same panel every operation uses, and a person taps that panel's Commit.
 *
 *  Addendum E.3 lives here too: the encounter disables the microphone without
 *  consent on the thread (and the kernel refuses without it besides), the
 *  indicator is on screen for as long as the mic is, and Discard drops the
 *  audio rather than merely stopping it.
 */
import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import type { ApiError } from "../api";
import { dropSession, pollSession, refill, startSession, writeNote } from "./client";
import { pickMime, reasonFor, sentence, type ScribeSession } from "./session";
import "./scribe.css";

const POLL_MS = 3000;

export type Phase = "idle" | "recording" | "paused" | "uploading" | "waiting" | "ready" | "failed" | "withdrawn";

export type Status = { phase: Phase; seconds: number };

export function ScribeBar({ thread, op, lib, full, children, onStatus, onByHand, onDrafts, onClose, controls: ctl }: {
  /** Lets the composer, the thread and the rail drive this recording from outside the tab. */
  controls?: { current: { stop: () => void; pause: () => void; resume: () => void } | null };
  thread: string;
  /** The form the recording will fill, or "" for none. Choosing one is not
   *  required: a recording with nothing chosen is a transcript. Changing it on
   *  a transcribed recording refills from the same transcript. */
  op: string;
  /** Library templates to have a note written in. They go up with the
   *  recording, or are asked for once it is transcribed. */
  lib: string[];
  /** Drawn as the Transcript tab's own panel -- the daffodil, the controls and
   *  whatever `children` is -- rather than as a bar above another view. The
   *  recorder is mounted either way, so changing tab never stops a recording. */
  full?: boolean;
  /** The transcript, drawn under the controls in the full view. */
  children?: React.ReactNode;
  /** Where the recording is, for the call to action and the tabs to say. */
  onStatus?: (s: Status) => void;
  /** Offered when recording failed or was withdrawn: the form, by hand. */
  onByHand?: () => void;
  /** Called with every ready session, including after a template switch. */
  onDrafts: (s: ScribeSession) => void;
  onClose: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [note, setNote] = useState("");
  const [seconds, setSeconds] = useState(0);

  /** The choices as they are NOW. The upload runs from the recorder's onstop,
   *  set up when recording began, and a template switched mid-consultation
   *  would be lost reading state through that closure. */
  const chosen = useRef({ template: op, lib });
  chosen.current = { template: op, lib };

  const phaseRef = useRef<Phase>("idle");
  phaseRef.current = phase;
  useEffect(() => { onStatus?.({ phase, seconds }); }, [phase, seconds]);   // eslint-disable-line react-hooks/exhaustive-deps

  /** One outcome per recording. Two polls can be in flight at once, and both
   *  can come back ready: seen in a browser, where the second one reported a
   *  draft over the one the first had just handed up. */
  const taken = useRef(false);

  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const keep = useRef(true);            // false once withdrawn: the blob is never sent
  const timers = useRef<number[]>([]);
  const alive = useRef(true);

  const clear = () => {
    timers.current.forEach((t) => clearInterval(t));
    timers.current = [];
  };
  const halt = () => {
    keep.current = false;
    try {
      rec.current?.stop();
    } catch { /* already stopped */ }
    rec.current?.stream?.getTracks().forEach((t) => t.stop());
    rec.current = null;
    chunks.current = [];
    clear();
  };

  // Leaving the encounter stops the microphone and drops what it had. A
  // capture that outlived its screen would be a live mic with no indicator.
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      halt();
    };
  }, []);

  const fail = (e: unknown) => {
    if (!alive.current) return;
    setPhase("failed");
    setNote(`${(e as ApiError).message} ${(e as ApiError).next ?? ""}`.trim());
  };

  /** THE RECORDING STARTS WHEN THIS MOUNTS. Pressing the call to action is
   *  the whole of the asking: nothing is chosen first, because choosing a
   *  template is not required, and a screen that waits for a choice before it
   *  listens has made the person do something they did not need to. */
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void begin();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** THE FORM CHANGED, on the Templates tab. With a transcript in hand that
   *  refills it from the same words. At any other point it only changes what
   *  the upload will name: a template choice never starts the microphone. */
  const lastOp = useRef(op);
  useEffect(() => {
    if (op === lastOp.current) return;
    lastOp.current = op;
    if (!op || !session || phaseRef.current !== "ready") return;
    void refill(session.session, [op]).then((next) => {
      if (!alive.current) return;
      setSession(next);
      onDrafts(next);
    }).catch(fail);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op]);

  /** A LIBRARY TEMPLATE CHOSEN AFTER THE FACT is written from the transcript
   *  already held, one at a time, and never twice: a note that is on the
   *  session is not asked for again. Asked for BEFORE the recording went up,
   *  it rode with the audio and is already here. */
  const writing = useRef(new Set<string>());
  useEffect(() => {
    if (phase !== "ready" || !session) return;
    const have = new Set((session.notes ?? []).map((n) => n.template));
    const next = lib.find((id) => !have.has(id) && !writing.current.has(id));
    if (!next) return;
    writing.current.add(next);
    void writeNote(session.session, next).then((s) => {
      if (!alive.current) return;
      setSession(s);
      onDrafts(s);
    }).catch(fail).finally(() => writing.current.delete(next));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lib, phase, session]);

  /** Poll until the kernel says ready or failed. The webhook only shortens
   *  this; it is not required, and nothing here assumes one arrived. */
  const collect = async (id: string) => {
    clear();
    taken.current = false;
    const tick = async () => {
      if (!alive.current) return;
      try {
        const s = await pollSession(id);
        if (!alive.current) return;
        if (s.status !== "running") {
          if (taken.current) return;
          taken.current = true;
          clear();
          setSession(s);
          if (s.status === "ready") {
            setPhase("ready");
            // Ready with drafts says nothing; ready with a reason says why
            // there are none. Clearing this unconditionally is what hid a
            // missing reader behind "Nothing to fill".
            setNote(s.drafts.length ? "" : s.reason);
            onDrafts(s);
          } else {
            setPhase(s.status);
            setNote(sentence(s.status, s.reason));
          }
        }
      } catch (e) {
        clear();
        fail(e);
      }
    };
    timers.current.push(setInterval(tick, POLL_MS) as unknown as number);
    await tick();
  };

  const begin = async () => {
    taken.current = false;
    setNote("");
    setSession(null);
    if (typeof window.MediaRecorder !== "function") {
      // A browser without it is a fall back to the keyboard rather than a
      // stack trace on a doctor's screen. getUserMedia's own absence is caught
      // below, in the same words.
      setPhase("failed");
      setNote(reasonFor("MediaRecorder is not a function"));
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setPhase("failed");
      setNote(reasonFor((e as Error)?.name || String(e)));
      return;
    }
    if (!alive.current) {
      // Closed while the browser was asking for the microphone.
      stream.getTracks().forEach((t) => t.stop());
      return;
    }
    const mime = pickMime((t) => !!window.MediaRecorder?.isTypeSupported?.(t));
    const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    rec.current = r;
    chunks.current = [];
    keep.current = true;
    r.ondataavailable = (e: BlobEvent) => e.data?.size && chunks.current.push(e.data);
    r.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      const parts = chunks.current;
      chunks.current = [];
      if (!keep.current || !parts.length) return;      // withdrawn: nothing is sent
      void upload(new Blob(parts, { type: mime || parts[0].type }));
    };
    r.start();
    setSeconds(0);
    setPhase("recording");
    timers.current.push(setInterval(() => setSeconds((s) => s + 1), 1000) as unknown as number);
  };

  /** Pausing keeps the recording and stops the clock: what is said while it
   *  is paused is not captured, and the seconds do not run. */
  const pause = () => {
    try { rec.current?.pause(); } catch { return; }
    clear();
    setPhase("paused");
  };
  const resume = () => {
    try { rec.current?.resume(); } catch { return; }
    setPhase("recording");
    timers.current.push(setInterval(() => setSeconds((s) => s + 1), 1000) as unknown as number);
  };

  const stop = () => {
    clear();
    setPhase("uploading");
    try {
      rec.current?.stop();                 // onstop uploads
    } catch {
      setPhase("failed");
      setNote("The recorder stopped badly. Type the note.");
    }
  };

  const upload = async (blob: Blob) => {
    try {
      const { template: op, lib } = chosen.current;
      const s = await startSession(thread, blob, op ? [op] : [], lib);
      // Discarded or closed while the upload was in the air: the kernel has
      // it now, so tell it to keep nothing rather than poll for a draft.
      if (!keep.current || !alive.current) return void dropSession(s.session).catch(() => {});
      setSession(s);
      setPhase("waiting");
      await collect(s.session);
    } catch (e) {
      fail(e);
    }
  };

  /** The patient asked to stop. Capture stops here and the audio from this
   *  point is discarded: a recording still running is dropped unsent, and a
   *  job already at the service is told to keep nothing. */
  const withdraw = async () => {
    const id = session?.session;
    halt();
    taken.current = true;                  // a poll already in flight lands nowhere
    setPhase("withdrawn");
    setNote(sentence("withdrawn"));
    if (id) {
      try {
        await dropSession(id);
      } catch { /* it is already unreachable; nothing here kept a copy either */ }
    }
  };

  /** Closing the bar ends the recording's life: the mic stops, and a session
   *  the kernel still holds is told to keep nothing. Drafts already handed up
   *  stay in their panels, because those are the encounter's now. */
  const close = () => {
    const id = session?.session;
    halt();
    if (id) void dropSession(id).catch(() => {});
    onClose();
  };

  if (ctl) ctl.current = { stop, pause, resume };

  const over = phase === "failed" || phase === "withdrawn";

  const said =
    phase === "recording" ? `Recording ${mmss(seconds)}`
    : phase === "paused" ? `Paused ${mmss(seconds)}`
    : phase === "uploading" || phase === "waiting" ? "Transcribing"
    : phase === "ready" ? "Ready"
    : "";
  const hint = sentence(phase === "waiting" ? "running" : phase, note);

  const live = phase === "recording";
  const paused = phase === "paused";
  const busy = phase === "uploading" || phase === "waiting";

  const controls = (
    <span className="sc-rec-do">
      {live && <button className="sc-quiet" onClick={pause}>Pause</button>}
      {paused && <button className="sc-quiet" onClick={resume}>Continue</button>}
      {(live || paused) && <button className="sc-stop" onClick={stop}>Stop</button>}
      {over && <button className="sc-quiet" onClick={() => void begin()}>Record again</button>}
      {over && onByHand && <button className="sc-quiet" onClick={onByHand}>Fill it in by hand</button>}
      {(live || busy || paused || phase === "ready") && (
        <button className="sc-quiet" onClick={() => void withdraw()}>Discard</button>
      )}
      <button className="sc-quiet icon" onClick={close} aria-label="Close">
        <Icon name="plus" className="i sm" />
      </button>
    </span>
  );

  if (full) {
    // THE DAFFODIL IS THE LISTENING. It turns while the microphone is open and
    // while the words are being written down, and it holds still -- breathing,
    // not frozen -- while paused, so a pause reads as a pause and not as a
    // hang. The same mark the dictation strip uses, larger.
    const turning = live || busy;
    return (
      <div className={`sc-full${live ? " on" : ""}`} role="status" aria-live="polite">
        <div className="sc-daff">
          <span className={`dict-bloom big${turning ? "" : " still"}${paused ? " paused" : ""}`}
                aria-hidden="true">
            <Icon name="mark" className="i" />
          </span>
          <div className="sc-daff-said">{said || "Ready to record"}</div>
          {hint && <div className="sc-daff-hint">{hint}</div>}
          {controls}
        </div>
        {children}
      </div>
    );
  }

  return (
    <div className={`sc-rec${live ? " on" : ""}`} role="status" aria-live="polite">
      <span className="sc-rec-state">
        {live ? (
          <span className="sc-pulse" aria-hidden="true" />
        ) : busy ? (
          <span className="sc-spin" aria-hidden="true" />
        ) : (
          <span className="sc-rec-dot" aria-hidden="true" />
        )}
        {said && <span className="sc-rec-said">{said}</span>}
      </span>
      {controls}
      {hint && <span className="sc-rec-note">{hint}</span>}
    </div>
  );
}

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
