/** The three views inside the Scribe tab: what was said, what was written,
 *  and what to write it in.
 *
 *  Owner, 2026-11-04: "under scribe there should be further tabs, for
 *  transcript, notes, templates", with the templates loaded from Eka's
 *  library, and "the choose template doesn't do much". It did one thing: a
 *  dropdown on the recording bar that changed which form a recording filled.
 *  The Templates tab is where that choice now lives, beside the thing it was
 *  missing -- Eka's own note templates, which write the recording up as a
 *  note in a shape a clinician already knows.
 *
 *  THESE DRAW AND NOTHING ELSE. Which template, which session and where the
 *  recording is all come from usePane.ts; the titles are the workspace's and
 *  the bundle's, never typed here.
 */
import { Icon } from "../icons";
import { Loading } from "../parts";
import type { Templates } from "./client";
import { MOST_NOTES, type Library, type Sub } from "./usePane";
import type { Phase } from "./ScribeBar";
import type { ScribeSession } from "./session";

export function SubTabs({ open, notes, onPick }: {
  open: Sub; notes: number; onPick: (s: Sub) => void;
}) {
  const tabs: { id: Sub; title: string; n?: number }[] = [
    { id: "notes", title: "Notes", n: notes },
    { id: "transcript", title: "Transcript" },
    { id: "templates", title: "Templates" },
  ];
  return (
    <div className="stabs" role="tablist" aria-label="Scribe">
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={t.id === open}
                className={`stab${t.id === open ? " on" : ""}`} onClick={() => onPick(t.id)}>
          {t.title}
          {!!t.n && <span className="stab-n">{t.n}</span>}
        </button>
      ))}
    </div>
  );
}

/** What was said. Words a service wrote down, so it says where they are in
 *  their life: not yet recorded, still being transcribed, or here. */
export function Transcript({ session, phase }: { session: ScribeSession | null; phase: Phase }) {
  if (session?.transcript) {
    return (
      <div className="tx">
        {session.transcript.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)}
      </div>
    );
  }
  const busy = phase === "recording" || phase === "uploading" || phase === "waiting";
  return (
    <p className="tx-empty">
      {phase === "recording" ? "Recording. The words appear here once it is transcribed."
        : busy ? "Transcribing."
        : "Nothing recorded yet. Start a session and the words appear here."}
    </p>
  );
}

/** What the recording became, as words: one card per library template asked
 *  for, with a line saying so while one is still being written. The forms it
 *  filled are drawn by the encounter, below this, because those are forms. */
export function WrittenNotes({ session, lib, titles, phase }: {
  session: ScribeSession | null;
  lib: string[];
  titles: Record<string, string>;
  phase: Phase;
}) {
  const written = session?.notes ?? [];
  const have = new Set(written.map((n) => n.template));
  const waiting = lib.filter((id) => !have.has(id));
  return (
    <>
      {written.map((n) => (
        <section className="nt" key={n.template}>
          <div className="nt-h">
            <Icon name="doc" className="i sm" />
            <span className="nt-t">{n.title}</span>
            <button type="button" className="cq ml-auto"
                    onClick={() => void navigator.clipboard?.writeText(n.text).catch(() => {})}>
              Copy
            </button>
          </div>
          <div className="nt-b">{n.text}</div>
        </section>
      ))}
      {waiting.map((id) => (
        <section className="nt" key={id}>
          <div className="nt-wait">
            <span className="sc-spin" aria-hidden="true" />
            {phase === "ready"
              ? `Writing the ${titles[id] ?? "note"}.`
              : `The ${titles[id] ?? "note"} is written once the recording is transcribed.`}
          </div>
        </section>
      ))}
    </>
  );
}

/** Choose what a recording becomes. A library template is drawn by its title
 *  alone: Eka's `desc` is the instruction the model is given, three pages of
 *  it, and it is not a description a person reads.
 *
 *  Choose what a recording becomes. Two different things, kept apart because
 *  they are different: a FORM is the questions an operation asks, filled in
 *  for somebody to check and commit; a NOTE is Eka's template, written as
 *  text. A recording fills one form and may also be written up as up to
 *  MOST_NOTES notes. */
export function Templates({ menu, library, op, lib, phase, onOp, onLib }: {
  menu: Templates | null;
  library: Library;
  op: string;
  lib: string[];
  phase: Phase;
  onOp: (id: string) => void;
  onLib: (id: string) => void;
}) {
  const recording = phase === "recording" || phase === "uploading" || phase === "waiting";
  return (
    <div className="tp">
      <section>
        <h3 className="tp-h">Fill a form</h3>
        <p className="tp-sub">
          The recording fills this form for you to check. Changing it after the recording
          is transcribed fills the new one from the same words.
        </p>
        {!menu ? <Loading what="the forms" shape="rows" rows={2} />
          : menu.choose.length === 0 ? <p className="tx-empty">Nothing here can be filled from a recording.</p>
          : (
            <div className="tp-list">
              {menu.choose.map((c) => (
                <button key={c.operation} type="button" className="tp-card"
                        aria-pressed={c.operation === op} onClick={() => onOp(c.operation)}>
                  <span className="tp-name">{c.title}
                    {c.operation === op && <span className="tp-state">Chosen</span>}
                  </span>
                </button>
              ))}
            </div>
          )}
      </section>

      <section>
        <h3 className="tp-h">Write a note</h3>
        <p className="tp-sub">
          Eka&apos;s own note templates. Choose up to {MOST_NOTES}: the recording is written up
          in each, as text to read and copy.
          {recording ? " Chosen now, they are written when it is transcribed." : ""}
        </p>
        {!library ? <Loading what="Eka's templates" shape="rows" rows={3} />
          : "error" in library ? <p className="tx-empty">{library.error}</p>
          : library.items.length === 0 ? <p className="tx-empty">Eka has no templates for this workspace.</p>
          : (
            <div className="tp-list">
              {library.items.map((t) => (
                <button key={t.id} type="button" className="tp-card"
                        aria-pressed={lib.includes(t.id)} onClick={() => onLib(t.id)}>
                  <span className="tp-name">{t.title}
                    {lib.includes(t.id) && <span className="tp-state">Chosen</span>}
                  </span>
                </button>
              ))}
            </div>
          )}
      </section>
    </div>
  );
}
