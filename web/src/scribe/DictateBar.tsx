/** What dictation looks like while it is happening.
 *
 *  One strip, fixed to the bottom of the screen, because the thing a person
 *  needs to see while talking is not near the field -- their eyes are on the
 *  patient -- and it must not move the form underneath them when it appears.
 *
 *  It names the field the words are going into. That sentence is the whole
 *  safety of the gesture: the shortcut rests on the person's idea of where
 *  the cursor is matching ours, and the moment to correct that belief is
 *  before they speak rather than after a paragraph has landed in the wrong
 *  box.
 */
import { useEffect, useRef } from "react";
import { Icon } from "../icons";
import { listening } from "./dictate";
import "./scribe.css";
import type { Dictation } from "./useDictation";

export function DictateBar({ state, onDismiss }: {
  state: Dictation;
  onDismiss: () => void;
}) {
  const loose = useRef<HTMLTextAreaElement>(null);

  // The words with nowhere to go are selected the moment they appear, so the
  // one thing a person wants to do with them -- copy -- is one keystroke.
  useEffect(() => {
    if (state.phase === "loose") loose.current?.select();
  }, [state.phase]);

  if (state.phase === "idle") return null;

  if (state.phase === "loose") {
    return (
      <div className="dict dict-loose" role="dialog" aria-label="What was heard">
        <div className="dict-h">
          Nothing had the cursor, so these words are yours to copy.
        </div>
        <textarea ref={loose} className="f-in" rows={3} readOnly value={state.text} />
        <div className="dict-acts">
          <button type="button" className="cq" onClick={onDismiss}>Done</button>
        </div>
      </div>
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
      {state.phase === "listening" ? (
        <>
          <span className="dict-dot" aria-hidden="true" />
          <span>{listening(state.field)}</span>
          {/* Hands-free has no key held down, so it is the one state that
              has to say how it ends. A hold ends when the hand does. */}
          {state.handsfree && <span className="dict-hint">press again to stop</span>}
        </>
      ) : (
        <>
          <Icon name="spark" className="i sm" />
          <span>Writing that down…</span>
        </>
      )}
    </div>
  );
}
