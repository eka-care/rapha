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
  papers, add, adding, onAdd, thread, client, cat, flags, onDone,
}: {
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
  return (
    <div className="bgtab">
      {adding ? (
        <OperationPanel
          inline
          op={adding}
          thread={thread}
          client={client}
          instruments={cat.instruments}
          flags={flags}
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
