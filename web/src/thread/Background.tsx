/** The Background tab: paper this centre did not write.
 *
 *  A patient arrives holding a discharge summary, an outside laboratory
 *  report, an old prescription from a camp. Until now it was read once at a
 *  desk and went home in the same bag. This keeps a copy on the visit, so
 *  whoever writes the note has already read it.
 *
 *  NOTHING CLINICAL IS NAMED HERE. What belongs in this tab is whatever the
 *  bundle declared as `presents: artifact` -- a word from the closed list in
 *  catalogue/vocab.THREAD_OBJECTS, which this renderer implements -- and the
 *  rows are drawn from whatever questions that operation's schema happens to
 *  ask. This file knows no field name, no operation id and no capability. A
 *  facility that declares no such operation gets an empty tab and no button,
 *  which is the truth about that facility.
 *
 *  IT IS A COPY AND IT SAYS SO. Every card is headed with who wrote the
 *  paper's being somebody else's, because the one way this feature does harm
 *  is by letting an outside claim read, a week later, as our own finding.
 */
import { useState } from "react";
import { Filed } from "../paper/Filed";
import { Scan } from "../paper/Scan";
import { mountsFor } from "../voice/instruments";
import { questionnaire } from "../declarations";
import type { Kv, Msg } from "../messages";
import { clock } from "../messages";
import { Icon } from "../icons";
import { OperationPanel } from "../form/Panel";
import type { Client } from "../api";
import type { Catalogue, Operation } from "../types";

/** Where a value stops being a field and becomes a document. Length, not a
 *  field name: the renderer may not know what the bundle called anything,
 *  and a pasted letter is recognisable without being told. */
const LONG = 120;

export function Background({
  papers, add, adding, onAdd, thread, client, cat, flags, patient, onDone,
}: {
  /** The patient's own Eka identifier, when this centre has published them.
   *  Handed down so a photographed paper is filed under the person it
   *  belongs to; see paper/Scan.tsx for what happens when there is none. */
  patient: string | null;
  papers: Msg[];
  /** The ways to copy one in that THIS person is offered. Already filtered
   *  by the guard, so an empty list means their role does not hold it. */
  add: Operation[];
  adding: Operation | null;
  onAdd: (op: Operation | null) => void;
  thread: string;
  client: Client;
  cat: Catalogue;
  flags: string[];
  onDone: () => void;
}) {
  // Bumped when a paper lands on the record, so the list beside it refetches.
  const [filed, setFiled] = useState(0);

  // THE UPLOAD DOES NOT NEED THE FORM. Attaching a document to the patient's
  // record is a complete act on its own -- the owner's point on 4 November
  // 2026, and obviously right: a discharge summary is useful on the record
  // whether or not a machine could read it and whether or not anybody types
  // a summary of it afterwards. So the control sits on the tab, above the
  // papers it adds to, and the form below stays what it always was: the way
  // to write down what a paper SAYS, for people who want that too.
  //
  // Which operation it belongs to is still the declaration's answer, not
  // this file's: `add` is what the guard offered this person, and the mount
  // is only drawn if a document instrument names it.
  const op = add[0];
  const schema = op ? questionnaire(op.input) : null;
  const scan = op && schema
    ? mountsFor(cat.instruments, op, schema).filter((m) => m.kind === "document")
    : [];

  return (
    <div className="bgtab">
      {!adding && op && scan.length > 0 && (
        <Scan mounts={scan} operation={op.id} patient={patient}
              onSaved={() => setFiled((n) => n + 1)}
              /* A reading on this path has no form open to fill, so it is
                 dropped rather than held: the paper is on the record, which
                 is what was asked for. Somebody who wants the numbers typed
                 up opens the form below, where a reading does fill it. */
              onDraft={() => { /* nothing to fill from here */ }} />
      )}
      {!adding && <Filed patient={patient} reload={filed} />}
      {adding ? (
        <OperationPanel
          inline
          op={adding}
          thread={thread}
          client={client}
          instruments={cat.instruments}
          flags={flags}
          patient={patient}
          onDone={onDone}
          onCancel={() => onAdd(null)}
        />
      ) : (
        <>
          {papers.length === 0 ? (
            <div className="state-empty">
              Nothing from outside this centre is on this visit.
            </div>
          ) : (
            papers.map((m) => (m.kind === "posted"
              ? <Paper key={m.id} m={m} head={cat.operations?.[m.operation]?.short} />
              : null))
          )}
          {/* One button per declared way in. Plural only because a bundle
              may declare more than one; the PHC declares one. */}
          {add.map((op) => (
            <button type="button" className="btn btn-g bg-add" key={op.id}
                    onClick={() => onAdd(op)}>
              <Icon name="plus" className="i sm" />
              {op.title}
            </button>
          ))}
        </>
      )}
    </div>
  );
}

/** `short` before `title`, because the atom's title is written to read as an
 *  ACTION in a menu ("Add background from elsewhere") and this is the
 *  heading of a document already saved. `short` is the bundle's own one word
 *  for the same thing and is the right length for a card. */
function Paper({ m, head }: { m: Msg & { kind: "posted" }; head?: string }) {
  return (
    <section className="card bg-card">
      <div className="card-h">
        <div className="card-t">{head || m.title}</div>
        {/* Who COPIED IT IN, and when. Not who wrote it: that is one of the
            answers below, in the bundle's own words. */}
        <span className="badge b-mute ml-auto">{m.actor} · {clock(m.at)}</span>
      </div>
      <div className="bg-v">
        {m.values.map((v) => <Line v={v} key={v.link_id} />)}
      </div>
    </section>
  );
}

function Line({ v }: { v: Kv }) {
  if (v.value.length > LONG || v.value.includes("\n")) {
    return (
      <div className="bg-long">
        <span className="bg-lab">{v.label}</span>
        <p className="bg-body">{v.value}</p>
      </div>
    );
  }
  return (
    <div className={`kv${v.crit ? " crit" : ""}`}>
      <span>{v.label}</span>
      <b>{v.value}</b>
    </div>
  );
}
