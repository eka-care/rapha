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
import { available, captureValue, type Draft } from "../../../packages/voice/src/index.ts";
import type { Mount } from "./instruments";
import "./voice.css";

/** Recogniser error codes to the one thing the person should do next. The
 *  codes are the Web Speech API's; anything unlisted is shown as it came. */
function nextStep(reason: string): string {
  if (/not-allowed|denied/.test(reason))
    return "Allow the microphone in the address bar, or type the values.";
  if (/audio-capture|no-speech-device/.test(reason))
    return "No microphone. Type the values.";
  if (/service-not-allowed/.test(reason))
    return "Speech needs https or localhost. Type the values.";
  if (/network/.test(reason))
    return "Speech recognition could not reach the network. Type the values.";
  return "Type the values.";
}

export function VoiceCapture({
  mounts,
  operation,
  payload,
  disabled,
  ids,
  onValues,
}: {
  /** Every mount except the scribe: a scribe is a recording that leaves this
   *  machine, and web/src/scribe/Recorder draws it. Mixing the two controls on
   *  one bar is exactly the confusion this file must not create. */
  mounts: Mount[];
  operation: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
  /** The Form prefix, so the cursor lands in this panel's field and not in
   *  another panel's field with the same link_id. */
  ids: string;
  onValues: (values: Record<string, number>, confidence: Record<string, number>) => void;
}) {
  const [live, setLive] = useState<string | null>(null);
  const [heard, setHeard] = useState<Draft | null>(null);
  const abort = useRef<AbortController | null>(null);

  // Leaving the panel stops the microphone. A capture that outlived its screen
  // would be a live mic with no indicator, which is the one thing this must
  // never be.
  useEffect(() => () => abort.current?.abort(), []);

  if (!mounts.length) return null;

  const supported = available();
  const stop = () => abort.current?.abort();

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
      document.getElementById(`${ids}-${next.linkId}`)?.focus();
      return;
    }
    onValues(draft.values, draft.confidence);
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
        if (m.kind === "scribe") return null;   // web/src/scribe draws that one
        if (m.kind === "device") {
          return (
            <div className="v-row" key={m.id}>
              <span className="v-off">Device</span>
              <div className="f-hint">Not paired. Type the numbers.</div>
            </div>
          );
        }

        if (!supported) {
          return (
            <div className="v-row" key={m.id}>
              <span className="v-off">No microphone</span>
              <div className="f-hint">Type the values.</div>
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
