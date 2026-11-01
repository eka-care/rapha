/** v2dd on screen: the microphone, the readback, and the fall back to typing.
 *
 *  This component cannot write. It has no client, no fetch and no commit. It
 *  hands values up to the panel, which puts them in editable fields, and a
 *  person taps the panel's own Commit button. That is the whole safety
 *  property and it is enforced by what is absent from this file.
 *
 *  Every button below exists because a declaration said so. mountsFor() reads
 *  the instrument declarations; nothing here knows what a systolic is.
 *
 *  The words come from the medical scribe service, through the kernel, which
 *  is web/src/scribe/reading.ts and is the only thing this file calls that
 *  touches a network. The browser's own speech recognition used to do it and
 *  does not any more: see that file for the owner's decision and for the
 *  consent the upload inherits. What reaches a field is still decided here,
 *  by the number grammar, and still needs a tap.
 */
import { useEffect, useRef, useState } from "react";
import { toDraft, type Draft } from "../../../packages/voice/src/index.ts";
import { canRecord, recordReading, type Reading } from "../scribe/reading";
import type { Mount } from "./instruments";
import "./voice.css";

export function VoiceCapture({
  mounts,
  operation,
  thread,
  payload,
  disabled,
  ids,
  onValues,
}: {
  /** Every mount except the scribe: a scribe is a whole consultation and
   *  web/src/scribe/ScribeBar draws it. Mixing the two controls on one bar is
   *  exactly the confusion this file must not create, even now that both sets
   *  of words come from the same service. */
  mounts: Mount[];
  operation: string;
  /** The visit this reading belongs to. The upload is refused without its
   *  recording consent, which is the kernel's check and not this file's. */
  thread: string;
  payload: Record<string, unknown>;
  disabled?: boolean;
  /** The Form prefix, so the cursor lands in this panel's field and not in
   *  another panel's field with the same link_id. */
  ids: string;
  onValues: (values: Record<string, number>, confidence: Record<string, number>) => void;
}) {
  const [live, setLive] = useState<{ id: string; sending: boolean } | null>(null);
  const [heard, setHeard] = useState<Draft | null>(null);
  const reading = useRef<Reading | null>(null);

  // Leaving the panel stops the microphone and keeps nothing. A capture that
  // outlived its screen would be a live mic with no indicator, which is the
  // one thing this must never be.
  useEffect(() => () => {
    const r = reading.current;
    reading.current = null;
    r?.abandon();
  }, []);

  if (!mounts.length) return null;

  const stop = () => {
    setLive((l) => (l ? { ...l, sending: true } : l));
    reading.current?.stop();
  };

  const listen = (m: Extract<Mount, { kind: "constrained-voice" }>) => {
    setHeard(null);
    const meta = { instrument: m.id, operation };
    const r = recordReading(thread, operation);
    reading.current = r;
    setLive({ id: m.id, sending: false });

    void r.heard.then((h) => {
      if (reading.current !== r) return;          // the panel closed; say nothing
      reading.current = null;
      setLive(null);
      // The grammar still decides. A transcript it will not parse fills no
      // field, exactly as before: the service is a better microphone, not a
      // new authority. Nought is "this engine does not score words", which
      // toDraft reads as unknown rather than as certainty.
      const draft: Draft = h.transcript
        ? toDraft(h.transcript, 0, m.fields, meta)
        : { ...meta, values: {}, confidence: {}, reason: h.reason ?? "" };
      if (!h.transcript && !h.reason) return;     // stopped by hand: nothing to report
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
    });
  };

  return (
    <div className="v-bar">
      {live && (
        <div className="mic-live" role="status" aria-live="assertive">
          <span className="mic-dot" />
          {live.sending ? "Transcribing" : "Microphone live"}
          {!live.sending && <button className="cq mic-stop" onClick={stop}>Stop</button>}
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

        if (m.kind !== "constrained-voice") return null;   // no other kind mounts here

        if (!canRecord()) {
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
              className={`cq v-mic${live?.id === m.id ? " on" : ""}`}
              disabled={disabled || live?.sending || (live !== null && live.id !== m.id)}
              onClick={() => (live?.id === m.id ? stop() : listen(m))}
            >
              {live?.id === m.id
                ? (live.sending ? "Transcribing" : "Listening, tap to stop")
                : m.title}
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
          <div className="f-hint">Type the values.</div>
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
