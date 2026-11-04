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
import { readPaper } from "./client";
import type { ScribeDraft } from "../scribe/session";
import type { Mount } from "../voice/instruments";
import "./paper.css";

/** What the file picker will offer. The kernel refuses anything else again,
 *  before a byte leaves the machine; this is so the picker does not show a
 *  person a spreadsheet they are about to be told off for choosing. */
const TAKES = "image/jpeg,image/png,image/heic,image/webp,application/pdf";

export function Scan({ mounts, operation, disabled, onDraft }: {
  /** Every document mount for this operation. Normally one; the loop is
   *  because a bundle may declare more than one way in and this file does
   *  not get to decide that. */
  mounts: Mount[];
  operation: string;
  disabled?: boolean;
  onDraft: (draft: ScribeDraft) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const box = useRef<HTMLInputElement>(null);

  const docs = mounts.filter((m) => m.kind === "document");
  if (!docs.length) return null;

  const take = async (file: File | undefined) => {
    if (!file) return;
    setFailed(null);
    setBusy(true);
    try {
      onDraft(await readPaper(operation, file));
    } catch (e) {
      // The kernel's own sentence, which already ends by saying what to do
      // instead. Rewriting it here would be a second copy to keep in step
      // with a service this file knows nothing about.
      setFailed(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
      // So the same picture can be chosen again after a failure. Without
      // this the input holds the file and the change event never fires.
      if (box.current) box.current.value = "";
    }
  };

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
        {busy ? "Reading the paper…" : "Photograph the paper"}
      </button>
      {/* WHAT IT WILL AND WILL NOT DO, before anybody photographs anything.
          A reader that silently leaves a field empty teaches a person to
          distrust the fields it does fill. */}
      <span className="scan-say">
        {busy
          ? "This takes about half a minute. Nothing is saved until you tap."
          : "Fills what it reads, for you to check. Who wrote it is still yours to type."}
      </span>
      {failed && <div className="f-bad block">{failed}</div>}
    </div>
  );
}
