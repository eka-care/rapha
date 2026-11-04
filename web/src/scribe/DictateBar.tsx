/** What dictation looks like while it is happening.
 *
 *  TWO SHAPES, because there are two situations and they are not alike.
 *
 *  With a field under the cursor, this is a quiet strip at the foot of the
 *  screen: the daffodil turning, and the name of the field the words are
 *  going into. That sentence is the whole safety of the gesture -- the
 *  shortcut rests on the person's idea of where the cursor is matching
 *  ours, and the moment to correct that belief is before they speak rather
 *  than after a paragraph has landed in the wrong box. The strip is fixed
 *  rather than in the flow so it cannot push the form down under their
 *  hands the instant they start talking.
 *
 *  With no field, the words have nowhere to go, and that is not a footnote
 *  -- it is the whole result. So it takes the centre of the screen, which
 *  is the shape Fern's documentation assistant uses and the one the owner
 *  asked for. The transcript is the content, selected and ready to copy.
 *
 *  THE DAFFODIL IS THE PRODUCT'S OWN MARK and it turns while the microphone
 *  is open and while the words are being written down. Not a spinner: a
 *  spinner is a thing waiting, and the one piece of character this product
 *  has should be the thing doing the listening.
 */
import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { listening } from "./dictate";
import "./scribe.css";
import type { Dictation } from "./useDictation";

export function DictateBar({ state, onDismiss }: {
  state: Dictation;
  onDismiss: () => void;
}) {
  const loose = useRef<HTMLTextAreaElement>(null);
  const [copied, setCopied] = useState(false);

  // The words with nowhere to go are selected the moment they appear, so the
  // one thing a person wants to do with them is already half done.
  useEffect(() => {
    if (state.phase === "loose") { loose.current?.select(); setCopied(false); }
  }, [state.phase]);

  // Escape closes the centred panel, the way it closes everything else here.
  useEffect(() => {
    if (state.phase !== "loose") return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onDismiss(); };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, [state.phase, onDismiss]);

  if (state.phase === "idle") return null;

  if (state.phase === "loose") {
    const copy = async () => {
      try {
        await navigator.clipboard.writeText(state.text);
        setCopied(true);
      } catch {
        // Refused in some views. The text is already selected, so the
        // keyboard still works, and an error about something the person can
        // simply do is worse than saying nothing.
        loose.current?.select();
      }
    };
    return (
      <>
        <div className="dict-scrim" onClick={onDismiss} />
        <div className="dict-sheet" role="dialog" aria-modal="true" aria-label="What was heard">
          <div className="dict-sheet-h">
            <span className="dict-bloom still" aria-hidden="true">
              <Icon name="mark" className="i" />
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="dict-sheet-t">Here is what you said</div>
              <div className="dict-sheet-s">Nothing had the cursor, so it is yours to copy.</div>
            </div>
            <button type="button" className="dict-x ml-auto" onClick={onDismiss}
                    aria-label="Close">
              <Icon name="plus" className="i sm" />
            </button>
          </div>
          <textarea ref={loose} className="dict-said" rows={6} readOnly value={state.text} />
          <div className="dict-sheet-f">
            {/* The one thing worth teaching here, at the moment it would
                have helped: this is what the cursor is for. */}
            <span className="dict-learn">
              Put the cursor in a field first and the words go straight into it.
            </span>
            <button type="button" className="cq" onClick={onDismiss}>Done</button>
            <button type="button" className="cq rose" onClick={copy}>
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      </>
    );
  }

  if (state.phase === "failed") {
    return (
      <div className="dict dict-bad" role="status">
        <Icon name="alert" className="i sm" />
        <span>{state.why}</span>
        <button type="button" className="dict-x" onClick={onDismiss} aria-label="Dismiss">
          <Icon name="plus" className="i sm" />
        </button>
      </div>
    );
  }

  return (
    <div className="dict" role="status" aria-live="polite">
      {/* Turning while listening and still turning while the words are
          written down: both are the product working, and a person who sees
          it stop knows it is finished. */}
      <span className="dict-bloom" aria-hidden="true">
        <Icon name="mark" className="i" />
      </span>
      {state.phase === "listening" ? (
        <>
          <span>{listening(state.field)}</span>
          {/* Hands-free has no key held down, so it is the one state that
              has to say how it ends. A hold ends when the hand does. */}
          {state.handsfree && <span className="dict-hint">press again to stop</span>}
        </>
      ) : (
        <span>Writing that down…</span>
      )}
    </div>
  );
}
