/** The end of a task, and the start of the next one.
 *
 *  A loop with no visible close leaves a clerk looking at a patient who is no
 *  longer their problem. This card is that close: what happened, where the
 *  patient went, and the single thing to do next. The undo is quiet and is
 *  present only while the operation is still correctable.
 */
import type { Cue } from "./loops";

export function CloseCard({ what, wentTo, cue, onCue }: {
  /** The operation's own title, from its declaration. */
  what: string;
  /** The station the thread is at now, or null once the line is complete. */
  wentTo: string | null;
  cue: Cue;
  onCue: () => void;
}) {
  return (
    <div className="close">
      <div className="close-h">
        {what}{wentTo ? ` → ${wentTo}` : ""}
      </div>
      {cue.kind === "empty" ? (
        <div className="close-e">{cue.label}</div>
      ) : (
        <button className="btn btn-b" autoFocus onClick={onCue}>
          {cue.kind === "open" ? cue.label : `Next: ${cue.label}`}
        </button>
      )}
    </div>
  );
}
