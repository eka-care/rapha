/** Photographing the paper a patient brought in.
 *
 *  This component cannot write. It has no client that commits, no proposal
 *  and no Store. It hands a draft up to the panel, which puts the values in
 *  editable fields, and a person taps the panel's own Commit button. That is
 *  the whole safety property and it is enforced by what is absent here.
 *
 *  It exists because the alternative was typing. A patient arrives holding a
 *  discharge summary or a laboratory report, and the honest truth about a
 *  busy centre is that paper which has to be retyped does not get retyped:
 *  it is read once at the desk and goes home in the same bag. So it is
 *  photographed, the kernel has it read, and what came off it opens in the
 *  fields somebody would have typed into.
 *
 *  THE BUTTON IS HERE BECAUSE A DECLARATION SAID SO. mountsFor() reads the
 *  instrument declarations and answers whether this operation has a document
 *  instrument at all. Nothing in this file names a field, an operation or a
 *  bundle, and which question each part of the paper lands in is the
 *  declaration's `fills`, read by the kernel and never by this.
 *
 *  `capture="environment"` is what turns the file picker into the back
 *  camera on a phone, which is the whole gesture on the device this is
 *  actually used on. On a laptop it stays a file picker, which is right:
 *  there is no camera worth photographing a document with.
 */
import { useRef, useState } from "react";
import { Icon } from "../icons";
import { ApiError } from "../api";
import { filePaper, readPaper } from "./client";
import type { ScribeDraft } from "../scribe/session";
import type { Mount } from "../voice/instruments";
import "./paper.css";

/** What the file picker will offer. The kernel refuses anything else again,
 *  before a byte leaves the machine; this is so the picker does not show a
 *  person a spreadsheet they are about to be told off for choosing. */
const TAKES = "image/jpeg,image/png,image/heic,image/webp,application/pdf";

export function Scan({ mounts, operation, patient, disabled, onDraft, onSaved }: {
  /** Every document mount for this operation. Normally one; the loop is
   *  because a bundle may declare more than one way in and this file does
   *  not get to decide that. */
  mounts: Mount[];
  operation: string;
  /** THE PATIENT'S OWN EKA IDENTIFIER, which the patient directory put on
   *  their row when this centre published them. The paper is filed under
   *  it, which is what makes the document follow the patient instead of
   *  living on this visit alone.
   *
   *  Null for somebody this centre has not published. That is not an error
   *  and is not fudged: there is nowhere to file the paper, so the control
   *  says so rather than quietly doing something else. */
  patient: string | null;
  disabled?: boolean;
  onDraft: (draft: ScribeDraft) => void;
  /** Called the moment the paper is on the patient's record, before any
   *  reading is attempted, so a screen that lists their papers can show it
   *  without waiting for a parse that may never come. */
  onSaved?: () => void;
}) {
  /** Where the act has got to. `saved` is the one that matters: the paper
   *  is on the patient's record from that moment and everything after it is
   *  a convenience. */
  const [phase, setPhase] = useState<"idle" | "saving" | "reading" | "saved">("idle");
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const busy = phase === "saving" || phase === "reading";
  const box = useRef<HTMLInputElement>(null);

  const docs = mounts.filter((m) => m.kind === "document");
  if (!docs.length) return null;

  const take = async (file: File | undefined) => {
    if (!file || !patient) return;
    setFailed(null);
    setNote(null);
    setPhase("saving");

    // STEP ONE IS THE WHOLE JOB. The paper goes onto the patient's record
    // and that is what somebody came here to do. If this fails, it failed;
    // if it works, nothing after it can take it away.
    let id: string;
    try {
      id = await filePaper(patient, file);
    } catch (e) {
      setFailed(e instanceof ApiError ? e.message : String(e));
      setPhase("idle");
      if (box.current) box.current.value = "";
      return;
    }
    setPhase("reading");
    if (box.current) box.current.value = "";
    onSaved?.();

    // STEP TWO IS A CONVENIENCE. The service may be able to read the paper
    // and fill the fields. It may not: a handwritten note from a camp is a
    // document and is not a table. Either way the paper is filed, so
    // nothing here is reported as a failure -- saying "it did not work"
    // about an upload that worked is how a person learns to distrust it.
    try {
      const draft = await readPaper(operation, id, patient);
      if (draft) {
        onDraft(draft as Parameters<typeof onDraft>[0]);
        setNote("Saved to the patient's record, and the fields below are "
                + "what it read. Check them against the paper.");
      } else {
        setNote("Saved to the patient's record. Nothing could be read off "
                + "it, so type what it says below.");
      }
    } catch {
      setNote("Saved to the patient's record. It could not be read just "
              + "now, so type what it says below.");
    } finally {
      setPhase("saved");
    }
  };

  // NOWHERE TO FILE IT. Said plainly, with the reason, because the fix is
  // one the person at the counter can actually carry out. A disabled button
  // with no sentence beside it is how somebody learns a feature is broken.
  if (!patient) {
    return (
      <div className="scan scan-cant">
        <Icon name="clip" className="i sm" />
        <span className="scan-say">
          Photographing the paper needs this patient on the patient directory,
          and they are not on it yet. Add them from the patient screen, or
          type what the paper says below.
        </span>
      </div>
    );
  }

  return (
    <div className="scan">
      <input
        ref={box} type="file" accept={TAKES} capture="environment"
        className="scan-in" disabled={disabled || busy}
        onChange={(e) => void take(e.target.files?.[0])}
      />
      <button
        type="button" className="cq scan-go" disabled={disabled || busy}
        onClick={() => box.current?.click()}
      >
        <Icon name={busy ? "spark" : "clip"} className="i sm" />
        {phase === "saving" ? "Saving…"
          : phase === "reading" ? "Reading…"
          : phase === "saved" ? "Add another" : "Add the paper"}
      </button>
      {/* WHAT IT WILL AND WILL NOT DO, before anybody photographs anything.
          A reader that silently leaves a field empty teaches a person to
          distrust the fields it does fill. */}
      <span className="scan-say">
        {phase === "saving" ? "Putting it on the patient's record…"
          : phase === "reading" ? "Saved. Seeing whether it can be read, which "
                                  + "takes about half a minute."
          : note ?? "Saved to the patient's record, and fills what it reads "
                    + "for you to check. Who wrote it is still yours to type."}
      </span>
      {failed && <div className="f-bad block">{failed}</div>}
    </div>
  );
}
