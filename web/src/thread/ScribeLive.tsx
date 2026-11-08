/** Scribe at work, in the conversation.
 *
 *  Recording a consultation takes minutes and the person recording it still has
 *  a patient to look after, so the recorder does not take the screen. It shows
 *  up here instead, as a message from Scribe in the same log as everyone else:
 *  recording with a clock, then writing, then a draft waiting to be read.
 *  Nothing reaches the record from this card. Review and posting stay on the
 *  Scribe tab, where the note is a form someone reads before they sign it. */
import { Icon } from "../icons";
import type { Phase } from "../scribe/ScribeBar";

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export function ScribeLive({ phase, seconds, drafts, onStop, onPause, onResume, onOpen }: {
  phase: Phase; seconds: number; drafts: number; onStop: () => void; onPause: () => void; onResume: () => void; onOpen: () => void;
}) {
  const live = phase === "recording" || phase === "paused";
  const busy = phase === "uploading" || phase === "waiting";
  const ready = phase === "ready" && drafts > 0;
  const failed = phase === "failed";
  if (!live && !busy && !ready && !failed) return null;
  return (
    <div className="lg2 scribe-live" role="status" aria-live="polite">
      <div className="lg2-who" style={{ color: "var(--color-agent)" }}>Scribe<time>now</time></div>
      <div className="lg2-body">
        {live && <>
          <div className="lg2-t">
            <span className={`rec-dot${phase === "paused" ? " held" : ""}`} aria-hidden="true" />
            {phase === "paused" ? "Paused" : "Recording"} <span className="sl-clock">{mmss(seconds)}</span>
          </div>
          <p className="lg2-txt">Scribe is listening. Carry on with the visit; the notes will appear here when you stop.</p>
          <div className="sl-do">
            <button type="button" className="btn btn-b" onClick={onStop}>Stop and write notes</button>
            <button type="button" className="btn btn-g" onClick={phase === "paused" ? onResume : onPause}>{phase === "paused" ? "Continue" : "Pause"}</button>
            <button type="button" className="btn btn-g" onClick={onOpen}>Open Scribe</button>
          </div>
        </>}
        {busy && <>
          <div className="lg2-t"><Icon name="spark" className="i sm" /> Writing notes from the recording</div>
          <div className="sl-sk" aria-hidden="true"><i style={{ width: "78%" }} /><i style={{ width: "60%" }} /><i style={{ width: "68%" }} /></div>
        </>}
        {failed && <>
          <div className="lg2-t">Scribe could not write the notes</div>
          <p className="lg2-txt">Nothing was posted. Open Scribe to try again, or fill the note in by hand.</p>
          <div className="sl-do">
            <button type="button" className="btn btn-b" onClick={onOpen}>Open Scribe</button>
          </div>
        </>}
        {ready && <>
          <div className="lg2-t">
            Draft {drafts === 1 ? "note" : "notes"} ready
            <span className="badge b-mute">Not posted yet</span>
          </div>
          <p className="lg2-txt">
            {drafts === 1 ? "One note was" : `${drafts} notes were`} written from the recording. Read {drafts === 1 ? "it" : "them"} before posting.
          </p>
          <div className="sl-do">
            <button type="button" className="btn btn-b" onClick={onOpen}>Review and post</button>
          </div>
        </>}
      </div>
    </div>
  );
}
