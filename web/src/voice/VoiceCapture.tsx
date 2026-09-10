/** v2dd on screen: the microphone, the readback, and the fall back to typing.
 *
 *  This component cannot write. It has no client, no fetch and no commit. It
 *  hands values up to the panel, which puts them in editable fields, and a
 *  person taps the panel's own Commit button. That is the whole safety
 *  property and it is enforced by what is absent from this file.
 *
 *  Every button below exists because a declaration said so. mountsFor() reads
 *  the instrument declarations; nothing here knows what a systolic is.
 */
import { useEffect, useRef, useState } from "react";
import {
  available,
  captureValue,
  dictate,
  type Draft,
} from "../../../packages/voice/src/index.ts";
import type { Mount } from "./instruments";
import "./voice.css";

/** The flag the scribe declaration requires before anything may listen. */
const CONSENT = "capture.consented";

/** Recogniser error codes to the one thing the person should do next. The
 *  codes are the Web Speech API's; anything unlisted is shown as it came. */
function nextStep(reason: string): string {
  if (/not-allowed|denied/.test(reason))
    return "This page is not allowed to use the microphone. Click the icon at the left of the address bar, allow the microphone, and try again. Until then, type the values.";
  if (/audio-capture|no-speech-device/.test(reason))
    return "No microphone was found. Plug one in and reload, or type the values.";
  if (/service-not-allowed/.test(reason))
    return "The browser refused to start speech recognition. It only runs on https or localhost. Type the values here.";
  if (/network/.test(reason))
    return "Speech recognition in this browser needs the network and could not reach it. Type the values.";
  return "Type it instead. The keypad is the field below.";
}

export function VoiceCapture({
  mounts,
  operation,
  flags,
  payload,
  disabled,
  onValues,
  onText,
}: {
  mounts: Mount[];
  operation: string;
  /** Thread flags. The scribe declaration says capture only where consented. */
  flags: string[];
  payload: Record<string, unknown>;
  disabled?: boolean;
  onValues: (values: Record<string, number>, confidence: Record<string, number>) => void;
  onText: (link_id: string, text: string) => void;
}) {
  const [live, setLive] = useState<string | null>(null);
  const [heard, setHeard] = useState<Draft | null>(null);
  const [target, setTarget] = useState<string>("");
  const abort = useRef<AbortController | null>(null);
  const session = useRef<{ stop: () => void } | null>(null);

  // Leaving the panel stops the microphone. A capture that outlived its screen
  // would be a live mic with no indicator, which is the one thing this must
  // never be.
  useEffect(
    () => () => {
      abort.current?.abort();
      session.current?.stop();
    },
    [],
  );

  if (!mounts.length) return null;

  const supported = available();
  const consented = flags.includes(CONSENT);
  const stop = () => {
    abort.current?.abort();
    session.current?.stop();
  };

  const listen = async (m: Extract<Mount, { kind: "constrained-voice" }>) => {
    setHeard(null);
    const ctrl = new AbortController();
    abort.current = ctrl;
    setLive(m.id);
    const draft = await captureValue({
      fields: m.fields,
      instrument: m.id,
      operation,
      signal: ctrl.signal,
    });
    setLive(null);
    abort.current = null;
    setHeard(draft);
    if (Object.keys(draft.values).length === 0) {
      // Fail closed: nothing is guessed into a field, and the keypad for the
      // first field still waiting for a value takes the cursor.
      const next =
        m.fields.find((f) => payload[f.linkId] === undefined || payload[f.linkId] === "") ??
        m.fields[0];
      document.getElementById(`f-${next.linkId}`)?.focus();
      return;
    }
    onValues(draft.values, draft.confidence);
  };

  const startDictation = (m: Extract<Mount, { kind: "scribe" }>, linkId: string) => {
    setHeard(null);
    const base = String(payload[linkId] ?? "");
    const s = dictate({ onText: (t) => onText(linkId, base ? `${base} ${t}` : t) });
    session.current = s;
    setLive(m.id);
    void s.done.then(() => {
      session.current = null;
      setLive(null);
    });
  };

  return (
    <div className="v-bar">
      {live && (
        <div className="mic-live" role="status" aria-live="assertive">
          <span className="mic-dot" />
          Microphone live
          <button className="cq mic-stop" onClick={stop}>Stop</button>
        </div>
      )}

      {mounts.map((m) => {
        if (m.kind === "device") {
          return (
            <div className="v-row" key={m.id}>
              <span className="v-off">Device</span>
              <div className="f-hint">
                {m.title} is declared for {m.fields.join(", ") || "these fields"}, and no pairing
                code exists on this machine. Read the monitor and type the numbers.
              </div>
            </div>
          );
        }

        if (!supported) {
          return (
            <div className="v-row" key={m.id}>
              <span className="v-off">No microphone</span>
              <div className="f-hint">
                This browser has no speech recognition, so {m.title.toLowerCase()} is not offered.
                Chrome or Edge have it. Everything below can be typed, which is the same record.
              </div>
            </div>
          );
        }

        if (m.kind === "scribe") {
          const chosen = target || m.targets[0].link_id;
          if (!consented) {
            return (
              <div className="v-row" key={m.id}>
                <span className="v-off">Scribe off</span>
                <div className="f-hint">
                  Capture consent is not recorded on this thread, so nothing listens. Ask the
                  patient, record the consent, and the scribe appears here. Type the note meanwhile.
                </div>
              </div>
            );
          }
          return (
            <div className="v-row" key={m.id}>
              <button
                className={`cq v-mic${live === m.id ? " on" : ""}`}
                disabled={disabled || (live !== null && live !== m.id)}
                onClick={() => (live === m.id ? stop() : startDictation(m, chosen))}
              >
                {live === m.id ? "Stop dictating" : "Dictate"}
              </button>
              {m.targets.length > 1 && (
                <select
                  className="f-in v-pick"
                  value={chosen}
                  disabled={live === m.id}
                  onChange={(e) => setTarget(e.target.value)}
                >
                  {m.targets.map((q) => (
                    <option key={q.link_id} value={q.link_id}>into {q.text}</option>
                  ))}
                </select>
              )}
              <div className="f-hint">
                Prose only, into {m.targets.find((q) => q.link_id === chosen)?.text}. It arrives as a
                draft you edit. No number is ever taken this way.
              </div>
            </div>
          );
        }

        return (
          <div className="v-row" key={m.id}>
            <button
              className={`cq v-mic${live === m.id ? " on" : ""}`}
              disabled={disabled || (live !== null && live !== m.id)}
              onClick={() => (live === m.id ? stop() : void listen(m))}
            >
              {live === m.id ? "Listening, tap to stop" : m.title}
            </button>
            <div className="f-hint">
              Say one reading, for example the field name then the number. It is shown back for you
              to check and it is recorded only when you tap Commit.
            </div>
          </div>
        );
      })}

      {heard && Object.keys(heard.values).length > 0 && (
        <div className="v-heard">
          <div className="eyebrow">Heard, not recorded</div>
          {heard.transcript && <div className="transcript">"{heard.transcript}"</div>}
          <div className="v-vals">
            {Object.entries(heard.values).map(([id, v]) => (
              <span className="v-val" key={id}>
                {labelOf(mounts, id)} <b>{v}</b>
                <span className="v-conf">{Math.round((heard.confidence[id] ?? 0) * 100)}%</span>
              </span>
            ))}
          </div>
          <div className="f-hint">
            These are sitting in the fields below, marked unconfirmed. Read each one against what
            you measured, correct anything wrong, then tap Commit. Nothing is written until you do.
          </div>
        </div>
      )}

      {heard && Object.keys(heard.values).length === 0 && (
        <div className="v-heard bad">
          <div className="eyebrow">Nothing was taken from that</div>
          {heard.transcript && <div className="transcript">"{heard.transcript}"</div>}
          <div className="state-t">{heard.reason ?? "did not hear that clearly"}</div>
          <div className="f-hint">{nextStep(heard.reason ?? "")}</div>
        </div>
      )}
    </div>
  );
}

function labelOf(mounts: Mount[], linkId: string): string {
  for (const m of mounts) {
    if (m.kind === "constrained-voice" && m.labels[linkId]) return m.labels[linkId];
  }
  return linkId;
}
