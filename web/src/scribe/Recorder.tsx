/** Recording a consultation, on screen. The browser records; the kernel holds
 *  the credentials; the doctor confirms.
 *
 *  Deliberately not the microphone in web/src/voice. That one is a number
 *  grammar running inside this browser, for one reading at a time, and it is
 *  drawn as a small button beside the field it fills. This is a whole
 *  consultation leaving the machine, so it is drawn as a bar across the top of
 *  the screen that cannot be scrolled away from, in different words and a
 *  different colour, and it says what it is doing the entire time.
 *
 *  This component cannot write. It has no client and it never calls commit or
 *  confirm: it hands values up to the panel, which puts them in the same
 *  editable fields a person types into, marked unconfirmed, and a person taps
 *  the panel's own Commit. That is the whole safety property, and it is the
 *  same one the voice path has, for the same reason.
 *
 *  Addendum E.3 lives here in three places: the button is absent without
 *  consent on the thread (and the kernel refuses without it besides), the
 *  indicator is unmissable and the stop is always reachable, and withdrawal
 *  discards the audio from that point rather than merely stopping it.
 */
import { useEffect, useRef, useState } from "react";
import type { ApiError } from "../api";
import type { Payload, Questionnaire } from "../types";
import { human } from "../ui";
import type { Mount } from "../voice/instruments";
import { dropSession, pollSession, startSession } from "./client";
import {
  apply, draftFor, elsewhere, forget, liveSession, narrative, pickMime, preview,
  reasonFor, remember, sentence, type Applied, type ScribeSession,
} from "./session";
import "./scribe.css";

type Phase = "idle" | "recording" | "uploading" | "waiting" | "ready" | "failed" | "withdrawn";

const POLL_MS = 3000;

export function Recorder({
  mount, thread, operation, schema, payload, ids, disabled, onValues,
}: {
  mount: Extract<Mount, { kind: "scribe" }>;
  thread: string;
  operation: string;
  schema: Questionnaire;
  payload: Payload;
  /** The Form prefix, so a fallback puts the cursor in this panel's field. */
  ids: string;
  disabled?: boolean;
  onValues: (values: Record<string, unknown>, confidence: Record<string, number>) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [note, setNote] = useState("");
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [held, setHeld] = useState<Applied["held"]>([]);
  const [refused, setRefused] = useState<string[]>([]);
  const [seconds, setSeconds] = useState(0);

  /** The payload as it is NOW. `take` runs from inside a poll that was started
   *  several renders ago, and reading the prop through that closure would read
   *  the form as it was when the recording stopped: a doctor who typed while
   *  waiting would have had it overwritten. Seen happening in a browser, so it
   *  is a ref and not a prop read. */
  const latest = useRef(payload);
  latest.current = payload;

  /** One outcome per recording. Two polls can be in flight at once, and both
   *  can come back ready: seen in a browser, where the second one found the
   *  fields the first had just filled and reported the whole draft as text the
   *  doctor had already written. */
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

  // Leaving the panel stops the microphone and drops what it had. A capture
  // that outlived its screen would be a live mic with no indicator.
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      halt();
    };
  }, []);

  // A recording fills the consult and the prescription, and this panel is one
  // of them. If a session from this visit is still in flight, pick it up here
  // rather than making the doctor record twice.
  useEffect(() => {
    const id = liveSession(thread);
    if (!id || phase !== "idle") return;
    setPhase("waiting");
    void collect(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread]);

  const labels = new Map(
    (function all(qs: Questionnaire["questions"]): [string, string][] {
      return qs.flatMap((q) => [[q.link_id, q.text] as [string, string], ...all(q.questions ?? [])]);
    })(schema.questions),
  );

  const take = (s: ScribeSession) => {
    setSession(s);
    const draft = draftFor(s, operation);
    const got = apply(draft, narrative(schema), latest.current);
    setHeld(got.held);
    setRefused(got.refused);
    if (Object.keys(got.fill).length) {
      onValues(got.fill, Object.fromEntries(Object.keys(got.fill).map((k) => [k, draft?.confidence[k] ?? 0])));
    }
    setPhase(s.status === "ready" && !draft ? "failed" : (s.status as Phase));
    if (s.status === "ready" && !draft) {
      setNote(`The scribe heard nothing this form asks for.${
        elsewhere(s, operation).length
          ? ` It did fill ${elsewhere(s, operation).map(human).join(" and ")}.`
          : ""} Type the note.`);
    } else {
      setNote(sentence(s.status, s.reason));
    }
  };

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
          if (s.status !== "withdrawn") remember(thread, id);
          take(s);
        }
      } catch (e) {
        clear();
        setPhase("failed");
        setNote(`${(e as ApiError).message} ${(e as ApiError).next ?? ""}`);
      }
    };
    timers.current.push(setInterval(tick, POLL_MS) as unknown as number);
    await tick();
  };

  const record = async () => {
    taken.current = false;
    setNote("");
    setSession(null);
    setHeld([]);
    if (typeof window.MediaRecorder !== "function") {
      // Every browser this runs on has it, and a browser that does not is a
      // fall back to the keyboard rather than a stack trace on a doctor's
      // screen. getUserMedia's own absence is caught below, in the same words.
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
      const first = schema.questions.find((q) => !String(latest.current[q.link_id] ?? "").trim());
      document.getElementById(`${ids}-${(first ?? schema.questions[0]).link_id}`)?.focus();
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
    setNote(sentence("recording"));
    timers.current.push(setInterval(() => setSeconds((s) => s + 1), 1000) as unknown as number);
  };

  const stop = () => {
    clear();
    setPhase("uploading");
    setNote(sentence("uploading"));
    try {
      rec.current?.stop();                 // onstop uploads
    } catch {
      setPhase("failed");
      setNote("The recorder stopped badly and nothing was captured. Type the note.");
    }
  };

  const upload = async (blob: Blob) => {
    try {
      const s = await startSession(thread, blob);
      if (!alive.current) return;
      remember(thread, s.session);
      setSession(s);
      setPhase("waiting");
      setNote(sentence("running"));
      await collect(s.session);
    } catch (e) {
      if (!alive.current) return;
      setPhase("failed");
      setNote(`${(e as ApiError).message} ${(e as ApiError).next ?? ""}`);
    }
  };

  /** The patient asked to stop. Capture stops here and the audio from this
   *  point is discarded: a recording still running is dropped unsent, and a
   *  job already at the service is told to keep nothing. */
  const withdraw = async () => {
    const id = session?.session ?? liveSession(thread);
    halt();
    forget(thread);
    setPhase("withdrawn");
    setNote(sentence("withdrawn"));
    setHeld([]);
    if (id) {
      try {
        await dropSession(id);
      } catch { /* it is already unreachable; nothing here kept a copy either */ }
    }
  };

  /** The phases that already say the note in a block of their own. */
  const said: Phase[] = ["ready", "failed", "withdrawn"];
  const live = phase === "recording";
  const busy = phase === "uploading" || phase === "waiting";
  const other = elsewhere(session, operation);

  return (
    <div className="sc-bar">
      {live && (
        <div className="sc-live" role="status" aria-live="assertive">
          <span className="sc-dot" />
          <b>Recording the consultation</b>
          <span className="sc-clock">{mmss(seconds)}</span>
          <button className="cq sc-act" onClick={stop}>Stop and transcribe</button>
          <button className="cq sc-act" onClick={() => void withdraw()}>Patient asked to stop</button>
        </div>
      )}

      <div className="sc-row">
        <button
          className={`cq sc-rec${live ? " on" : ""}`}
          disabled={disabled || busy}
          onClick={() => (live ? stop() : void record())}
        >
          {live ? `Stop recording ${mmss(seconds)}` : busy ? "Working" : mount.title}
        </button>

        {(live || busy) && (
          <button className="cq" onClick={() => void withdraw()}>
            {live ? "Stop and discard" : "Stop waiting, discard the draft"}
          </button>
        )}

        <div className="f-hint" style={{ flex: "1 1 240px" }}>
          {/* The note is drawn in its own block once there is an outcome, so
              saying it twice here would be noise on the one screen where every
              extra sentence is between a doctor and the patient. */}
          {(note && !said.includes(phase) && note) ||
            `${mount.summary} Prose and lists only. No number is ever taken from a recording:
             those are typed or spoken into their own field.`}
        </div>
      </div>

      {busy && (
        <div className="sc-wait" role="status">
          <span className="sc-spin" />
          {phase === "uploading" ? "Uploading" : "The scribe is working"}
          <span className="f-hint">
            Nothing is waiting on this. Type the note now if you would rather: what you type stays,
            and a draft that arrives afterwards is offered beside it rather than over it.
          </span>
        </div>
      )}

      {session && phase === "ready" && (
        <div className="sc-heard">
          <div className="eyebrow">Drafted, not recorded</div>
          {draftFor(session, operation)?.transcript && (
            <div className="transcript">"{draftFor(session, operation)?.transcript}"</div>
          )}
          <div className="f-hint">{note}</div>
          {other.length > 0 && (
            <div className="f-hint">
              The same recording also drafted {other.map(human).join(" and ")}. Open{" "}
              {other.length === 1 ? "it" : "them"} from this thread and the draft is waiting there.
            </div>
          )}
        </div>
      )}

      {held.length > 0 && (
        <div className="sc-heard held">
          <div className="eyebrow">You had already written here</div>
          <div className="f-hint">
            Your text stands. The scribe's version is below and it goes nowhere unless you tap it.
          </div>
          {held.map((h) => (
            <div className="sc-held" key={h.link_id}>
              <b>{labels.get(h.link_id) ?? h.link_id}</b>
              <span>{preview(h.value)}</span>
              <button
                className="cq"
                onClick={() => {
                  onValues({ [h.link_id]: h.value }, { [h.link_id]: 0 });
                  setHeld((was) => was.filter((x) => x.link_id !== h.link_id));
                }}
              >
                Use the scribe's
              </button>
            </div>
          ))}
        </div>
      )}

      {refused.length > 0 && (
        <div className="sc-heard bad">
          <div className="eyebrow">Dropped</div>
          <div className="f-hint">
            The scribe returned {refused.join(", ")}, which a recording may not fill on this form.
            Nothing was put in {refused.length === 1 ? "that field" : "those fields"}. This is a bug
            in the kernel's scribe and it is worth reporting.
          </div>
        </div>
      )}

      {(phase === "failed" || phase === "withdrawn") && (
        <div className={`sc-heard${phase === "failed" ? " bad" : ""}`}>
          <div className="eyebrow">{phase === "failed" ? "No draft" : "Stopped"}</div>
          <div className="f-hint">{note}</div>
        </div>
      )}
    </div>
  );
}

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

