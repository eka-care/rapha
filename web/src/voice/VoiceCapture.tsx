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
 *  The values come from the medical scribe service, through the kernel, which
 *  is web/src/scribe/reading.ts and is the only thing this file calls that
 *  touches a network. The browser's own speech recognition used to do it and
 *  does not any more: see that file for the owner's decision and for the
 *  consent the upload inherits.
 *
 *  The service answers the form's own questions and leaves out what was not
 *  one of them, with the words each value came from beside it. This file no
 *  longer re-reads the transcript with a number grammar: that refused a whole
 *  reading over "what do I get" and binned five good numbers with it. What it
 *  does instead is hold the answer to the fields this instrument declares,
 *  which is `narrow()`, so a declaration that names three fields cannot fill
 *  six.
 */
import { useEffect, useRef, useState } from "react";
import { canRecord, recordReading, type Reading } from "../scribe/reading";
import { narrow, type ScribeDraft } from "../scribe/session";
import type { Mount } from "./instruments";
import "./voice.css";

export function VoiceCapture({
  mounts,
  operation,
  thread,
  payload,
  disabled,
  ids,
  onDraft,
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
  onDraft: (draft: ScribeDraft) => void;
}) {
  const [live, setLive] = useState<{ id: string; sending: boolean } | null>(null);
  const [heard, setHeard] = useState<{ draft: ScribeDraft | null; transcript: string;
                                      reason: string } | null>(null);
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
    const r = recordReading(thread, operation);
    reading.current = r;
    setLive({ id: m.id, sending: false });

    void r.heard.then((h) => {
      if (reading.current !== r) return;          // the panel closed; say nothing
      reading.current = null;
      setLive(null);
      if (!h.transcript && !h.reason) return;     // stopped by hand: nothing to report
      // Narrowed to what THIS instrument declares. The service filled the
      // operation's form; the declaration says which of those questions a
      // spoken reading may answer, and a field outside it is named rather
      // than filled.
      const drafted = h.draft ? narrow(h.draft, m.fields.map((f) => f.linkId)) : null;
      const filled = drafted && Object.keys(drafted.values).length > 0;
      setHeard({ draft: drafted, transcript: h.transcript,
                 reason: filled ? "" : (h.reason ?? "Nothing in that was for this form.") });
      if (!filled) {
        // Fail closed: nothing is guessed into a field, and the keypad for the
        // first field still waiting for a value takes the cursor.
        const next =
          m.fields.find((f) => payload[f.linkId] === undefined || payload[f.linkId] === "") ??
          m.fields[0];
        document.getElementById(`${ids}-${next.linkId}`)?.focus();
        return;
      }
      onDraft(drafted!);
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

      {heard?.draft && Object.keys(heard.draft.values).length > 0 && (
        <div className="v-heard">
          <div className="eyebrow">Heard, not recorded</div>
          <div className="v-vals">
            {Object.entries(heard.draft.values).map(([id, v]) => (
              <span className="v-val" key={id}>
                {labelOf(mounts, id)} <b>{String(v)}</b>
                {/* The words, not a percentage. The service scores no field,
                    so a number here would be invented; what it does give is
                    what it heard, which is the thing worth reading back. */}
                {heard.draft!.evidence[id] && (
                  <span className="v-conf">"{heard.draft!.evidence[id]}"</span>
                )}
              </span>
            ))}
          </div>
          {heard.draft.unfilled.length > 0 && (
            <div className="f-hint">
              Not for this form: {heard.draft.unfilled.map((id) => labelOf(mounts, id)).join(", ")}
            </div>
          )}
        </div>
      )}

      {heard && !(heard.draft && Object.keys(heard.draft.values).length > 0) && (
        <div className="v-heard bad">
          <div className="eyebrow">Nothing was taken from that</div>
          {heard.transcript && <div className="transcript">"{heard.transcript}"</div>}
          <div className="state-t">{heard.reason}</div>
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
