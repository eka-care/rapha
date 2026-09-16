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
import { currentRole, type ApiError } from "../api";
import { dropSession, pollSession, refill, startSession, templates, type Templates } from "./client";
import { lastTemplate, pickMime, reasonFor, rememberTemplate, sentence, type ScribeSession } from "./session";
import "./scribe.css";

const POLL_MS = 3000;
const LANGUAGE_NAMES: Record<string, string> = {
  "en-IN": "English", hinglish: "Hinglish", hi: "हिन्दी", ta: "தமிழ்", te: "తెలుగు",
};

type Phase = "idle" | "recording" | "uploading" | "waiting" | "ready" | "failed" | "withdrawn";

export function ScribeBar({ thread, station, onDrafts, onClose }: {
  thread: string;
  station: string;
  /** Called with every ready session, including after a template switch. */
  onDrafts: (s: ScribeSession) => void;
  onClose: () => void;
}) {
  const [menu, setMenu] = useState<Templates | null>(null);
  const [template, setTemplate] = useState<string>("");
  const [language, setLanguage] = useState("en-IN");
  const [phase, setPhase] = useState<Phase>("idle");
  const [session, setSession] = useState<ScribeSession | null>(null);
  const [note, setNote] = useState("");
  const [seconds, setSeconds] = useState(0);

  /** The picker as it is NOW. The upload runs from the recorder's onstop, set
   *  up when recording began, and a language changed mid-consultation would be
   *  lost reading state through that closure. */
  const chosen = useRef({ template, language });
  chosen.current = { template, language };

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

  useEffect(() => {
    templates(station).then((t) => {
      if (!alive.current) return;
      setMenu(t);
      const remembered = lastTemplate(currentRole(), station);
      const pick = t.choose.find((c) => c.operation === remembered)?.operation ?? t.default ?? "";
      setTemplate(pick);
      chosen.current.template = pick;
      if (pick) void begin();   // recording starts on the click that opened the bar
    }).catch((e) => { setPhase("failed"); setNote(String(e.message ?? e)); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [station]);

  const fail = (e: unknown) => {
    if (!alive.current) return;
    setPhase("failed");
    setNote(`${(e as ApiError).message} ${(e as ApiError).next ?? ""}`.trim());
  };

  const choose = async (op: string) => {
    setTemplate(op);
    chosen.current.template = op;
    rememberTemplate(currentRole(), station, op);
    if (phase === "idle") return void begin();
    if (session && phase === "ready") {
      try {
        const next = await refill(session.session, [op]);
        if (!alive.current) return;
        setSession(next);
        onDrafts(next);
      } catch (e) {
        fail(e);
      }
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
          setSession(s);
          if (s.status === "ready") {
            setPhase("ready");
            setNote("");
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
      const { template: op, language: lang } = chosen.current;
      const s = await startSession(thread, blob, [op], lang);
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

  const said =
    phase === "recording" ? `Recording ${mmss(seconds)}`
    : phase === "uploading" || phase === "waiting" ? "Transcribing"
    : phase === "ready" ? "Ready"
    : phase === "idle" && !template ? "Choose a template to record"
    : "";
  const hint = sentence(phase === "waiting" ? "running" : phase, note);

  return (
    <div className="scribe-bar" role="status" aria-live="polite">
      <span className={`scribe-dot ${phase === "recording" ? "on" : ""}`} aria-hidden />
      {said && <span className="scribe-phase">{said}</span>}
      <select aria-label="Template" value={template} onChange={(e) => void choose(e.target.value)}
              disabled={!menu || phase === "uploading" || phase === "waiting"}>
        {!template && <option value="">Choose a template</option>}
        {menu?.choose.map((c) => <option key={c.operation} value={c.operation}>{c.title}</option>)}
      </select>
      <select aria-label="Language" value={language} onChange={(e) => setLanguage(e.target.value)}
              disabled={phase !== "idle" && phase !== "recording"}>
        {(menu?.languages ?? ["en-IN"]).map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l] ?? l}</option>)}
      </select>
      {phase === "recording" && <button className="cq" onClick={stop}>Stop</button>}
      {(phase === "recording" || phase === "uploading" || phase === "waiting") && (
        <button className="cq" onClick={() => void withdraw()}>Discard</button>
      )}
      {phase === "ready" && session && session.drafts.length === 0 && (
        <details><summary>Nothing to fill. Transcript</summary><p>{session.transcript}</p></details>
      )}
      {hint && <span className="f-hint">{hint}</span>}
      <button className="cq" onClick={() => { halt(); onClose(); }} aria-label="Close scribe">×</button>
    </div>
  );
}

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
