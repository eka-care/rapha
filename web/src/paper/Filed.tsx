/** The papers already on this patient's record.
 *
 *  A document uploaded here is not a row in this kernel. It is a file on the
 *  patient's own Eka record, put there by the medical records SDK, and it is
 *  theirs rather than this visit's: it was on the record before today and it
 *  will be there after. So it is read back from the record rather than from
 *  our store, and this component is the only thing in the product that lists
 *  something this kernel does not hold.
 *
 *  WHY THAT IS RIGHT RATHER THAN A SHORTCUT. The alternative is a copy of the
 *  document list in our own database, which would be a second list that can
 *  disagree with the first, go stale, and survive a patient asking Eka to
 *  delete something. The record is the record.
 *
 *  Nothing here can write and nothing here can delete. A paper attached in
 *  error is removed from the patient's own record, by whoever owns it, which
 *  is not this facility.
 */
import { useCallback, useEffect, useState } from "react";
import { Icon } from "../icons";
import { listPapers, type FiledPaper } from "./client";

export function Filed({ patient, reload }: {
  /** The patient's Eka identifier, or null when this centre has not
   *  published them and there is therefore no record to read. */
  patient: string | null;
  /** Bumped by whoever just added one, so the list refetches without this
   *  component having to poll a service over somebody's mobile data. */
  reload: number;
}) {
  const [rows, setRows] = useState<FiledPaper[] | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    if (!patient) { setRows([]); return; }
    try {
      setRows(await listPapers(patient));
      setFailed(null);
    } catch (e) {
      // SAID, NOT SWALLOWED. An empty list and an unreachable service look
      // identical on screen, and one of them means "this patient has no
      // papers" while the other means "we do not know".
      setFailed(e instanceof Error ? e.message : String(e));
    }
  }, [patient]);

  useEffect(() => { void fetchRows(); }, [fetchRows, reload]);

  if (!patient) return null;
  if (failed) {
    return <div className="f-hint">Could not read this patient's papers just now. {failed}</div>;
  }
  if (rows === null) return <div className="f-hint">Reading this patient's papers…</div>;
  if (!rows.length) return null;

  return (
    <section className="filed">
      <div className="eyebrow">On the patient's record</div>
      {rows.map((r) => (
        <a className="filed-row" key={r.id} href={r.url ?? undefined}
           target="_blank" rel="noreferrer">
          <Icon name="doc" className="i sm" />
          <span className="filed-t">{r.title}</span>
          {/* What the service made of it, in words. "Read" is the useful
              fact: it is the difference between a picture somebody has to
              open and a document whose numbers are known. */}
          {r.read && <span className="badge">Read</span>}
          <span className="filed-d">{r.on}</span>
        </a>
      ))}
    </section>
  );
}
