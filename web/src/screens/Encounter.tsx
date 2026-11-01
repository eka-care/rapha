/** §8, rebuilt to the prototype: the thread on the left inside one card, and
 *  three stacked panels on the right.
 *
 *  The right rail being several CARDS rather than one list is most of the
 *  difference between a workspace and a properties panel: each has its own
 *  eyebrow, title and badge, and says what kind of thing it holds.
 *
 *  What the agent offers is a row of action cards inside its own message
 *  (§21), ink-filled for the one that closes this station's step. Every word
 *  on them is the operation's own declaration.
 */
import { useMemo, useState } from "react";
import { threadAsks } from "../agent";
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { displayFor, questionnaire } from "../declarations";
import { walk } from "../validate";
import { Icon } from "../icons";
import { carriedInto, weigh } from "../loops";
import { agentLine, header, messages, queueViewFor, type Ctx, type Said } from "../messages";
import type { Catalogue, Operation, Payload, ThreadView } from "../types";
import { Composer } from "../thread/Composer";
import { ScribeBar } from "../scribe/ScribeBar";
import { mergeDrafts, type Opened } from "../scribe/session";
import { Stream } from "../thread/Thread";
import { Carry, Team, Trend, usePast, visitOf } from "../thread/Past";
import { Line } from "../view/View";
import { human, title } from "../words";
import { initialsOf } from "../agent";

/** How many actions the agent's node offers.
 *
 *  ONE. `weigh()` already decides which of them closes this station, and that
 *  decision is the declaration's; drawing six of them put the one thing the
 *  doctor is here to do in a list of six equal buttons, which is a menu
 *  rather than a next step. The rest are not hidden: the count and the way to
 *  reach them are on the line under it, and the composer's `/` opens all of
 *  them. */
const QUICK = 1;

/** Which tag an action's capture instrument earns. The words are the
 *  declaration's `instrument`, not a table of operations. */
const TAG: Record<string, string> = {
  scribe: "scribe", form: "form", device: "form", "constrained-voice": "form",
};

export function Encounter({
  thread, cat, ctx, client, said, asking, onSay, onChanged, onOpenSubject,
}: {
  thread: ThreadView;
  cat: Catalogue;
  ctx: Ctx;
  client: Client;
  said: Said[];
  asking: boolean;
  onSay: (text: string) => void;
  onChanged: () => void;
  onOpenSubject: (subjectId: string) => void;
}) {
  const [modal, setModal] = useState<{ op: Operation; seed?: Payload } | null>(null);
  /** What a commit on this screen learned that a LATER panel will be asked
   *  for again.
   *
   *  One thing does this today and it is the expensive one. A registration
   *  runs the ABHA journey, and the journey hands back an identifier that
   *  registration itself does not write -- the link operation does. Until now
   *  the panel produced it, handed it up, and this screen dropped it on the
   *  floor, so the clerk who opened the link panel next was shown the journey
   *  again and the patient was asked to read a second one time password off a
   *  handset to say a number the screen had held minutes earlier. That is the
   *  exact cost the front desk exists to remove.
   *
   *  Kept with the thread it was learned on. This component is not keyed by
   *  thread id, so walking from one visit to another reuses the instance, and
   *  an identifier kept loose would be offered to the next patient's form.
   *  One person's national health number on another person's record is not a
   *  typo, it is the anti-goal: nothing merges two ABHA numbers and the
   *  patient carries the mistake permanently. */
  const [carried, setCarried] = useState<{ thread: string; payload: Payload } | null>(null);
  const [scribing, setScribing] = useState(false);
  const [drafts, setDrafts] = useState<Opened[]>([]);
  // The microphone is gated on the scribe instrument's own `requires:`, not a
  // flag named here: a bundle that spells its consent differently is gated by
  // its own spelling. The kernel refuses without it besides.
  const consentFlag = Object.values(cat.instruments ?? {})
    .map((i) => i as { kind?: string; requires?: string })
    .find((i) => i.kind === "scribe")?.requires;
  const consented = !consentFlag || (thread.flags ?? []).includes(consentFlag);

  /** The rule itself is loops.carriedInto, where a check can run it: the
   *  guard that keeps one patient's identifier off another patient's form is
   *  not something to leave as an expression nothing can execute. */
  const carry = (op: Operation): Payload | undefined =>
    carriedInto(carried, thread.id, walk(questionnaire(op.input)?.questions ?? [])) as Payload | undefined;

  const head = useMemo(() => header(thread, queueViewFor(cat, thread.workflow), displayFor), [thread, cat]);
  const msgs = useMemo(() => messages(thread, ctx, said), [thread, ctx, said]);
  const line = useMemo(() => agentLine(thread, ctx), [thread, ctx]);

  // §33: the declared rule in loops.ts decides the order, not this screen.
  const { primary, overflow } = useMemo(() => weigh(thread.actions, thread.closes), [thread.actions, thread.closes]);
  const ranked = useMemo(() => (primary ? [primary, ...overflow] : overflow), [primary, overflow]);
  const offered = ranked.slice(0, QUICK);

  const spine = cat.workflows?.[thread.workflow]?.spine;
  const spineId = spine && typeof thread.subject?.id === "string" ? thread.subject.id : "";
  /** This patient's earlier visits, for the strip under the name and the
   *  trend in the rail. Empty until they arrive, and empty forever for a
   *  first visit, which is why both draw nothing rather than a frame with
   *  nothing in it. */
  const past = usePast(thread, cat, spineId);
  const todayVisit = useMemo(() => visitOf(thread, cat), [thread, cat]);

  return (
    <div className="chatgrid">
      <div className="card chatcard">
        <header className="pt-head">
          <span className="avatar">{initialsOf(head.name)}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="pt-name">{head.name}</div>
            <div className="pt-meta">{head.meta.join(" · ")}</div>
            <div className="pt-chips">
              {head.identity && (
                <span className="id-badge">
                  <span className="id-lab">{head.identity.label}</span>
                  <span className="id-val">{head.identity.value}</span>
                </span>
              )}
              {thread.station && <span className="badge b-ink">{human(thread.station)}</span>}
              {head.badges.map((b) => (
                <span className={`badge ${TONE[b.style] ?? "b-mute"}`} key={b.text}>{b.text}</span>
              ))}
              {spineId && (
                <button className="chip" onClick={() => onOpenSubject(spineId)}>
                  <Icon name="folder" className="i sm" />
                  All visits
                </button>
              )}
            </div>
          </div>
        </header>

        <Carry now={todayVisit} visits={past} />

        <Stream
          msgs={msgs} thread={thread} client={client} ctx={ctx}
          instruments={cat.instruments} onDone={onChanged}
        >
          {/* §21: the agent's own message, and the actions it is offering. */}
          {(line.sentences.length > 0 || offered.length > 0) && (
            <div className="msg">
              <div className="m-av agent" aria-hidden="true"><Icon name="spark" className="i sm" /></div>
              <div className="m-b" style={{ width: "100%" }}>
                <div className="m-meta">Agent · now</div>
                <div className="bubble">
                  {line.sentences.join(" ")}
                  {offered.length > 0 && (
                    <div className="props">
                      {offered.map((op, i) => (
                        <button
                          className={`prop${i === 0 ? " primary" : ""}`}
                          key={op.id}
                          onClick={() => setModal({ op, seed: carry(op) })}
                        >
                          <Icon name={op.irreversibility === "irreversible" ? "lock" : "refer"} className="i sm" />
                          <span className="p-b">
                            <span className="p-l">{op.title}</span>
                            {op.summary && <span className="p-s">{op.summary}</span>}
                          </span>
                          <span className={`p-tag ${op.irreversibility === "irreversible" ? "irr" : TAG[op.instrument] ?? ""}`}>
                            {op.irreversibility === "irreversible" ? "confirm" : human(op.instrument)}
                          </span>
                        </button>
                      ))}
                      {ranked.length > QUICK && (
                        <div className="fl-e">
                          {ranked.length - QUICK} more with <span className="kbd">/</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </Stream>

        {/* The station comes off the thread view, the same field the header
            badge draws; a thread past its last station has none. */}
        {scribing && (
          <ScribeBar thread={thread.id} station={thread.station ?? ""}
                     onDrafts={(s) => setDrafts((all) => mergeDrafts(all, s.drafts, s.session))}
                     onClose={() => { setScribing(false); setDrafts([]); }} />
        )}
        {drafts.map(({ draft: d, key }) => {
          const op = cat.operations[d.operation];
          return op ? (
            <div key={key} style={{ padding: "0 15px 12px", maxHeight: "42vh", overflowY: "auto", flexShrink: 0 }}>
              <OperationPanel op={op} thread={thread.id} client={client} draft={d}
                instruments={cat.instruments} flags={thread.flags} inline
                onDone={() => { setDrafts((all) => all.filter((x) => x.draft.operation !== d.operation)); onChanged(); }}
                onCancel={() => setDrafts((all) => all.filter((x) => x.draft.operation !== d.operation))} />
            </div>
          ) : null;
        })}

        <Composer
          about={head.name}
          actions={ranked}
          roles={Object.keys(cat.bundles ?? {})}
          asking={asking}
          onSay={onSay}
          onAction={(op) => setModal({ op, seed: carry(op) })}
          onStartScribe={() => setScribing(true)}
          micReason={consented ? undefined : "Capture consent is not recorded on this visit"}
          quick={
            <>
              {threadAsks({ hasHistory: !!spineId, flags: thread.flags }).slice(0, 2).map((q) => (
                <button className="chip" key={q} onClick={() => onSay(q)}>{q}</button>
              ))}
            </>
          }
        />
      </div>

      <aside className="panel" aria-label="Context">
        <div className="card">
          <div className="card-h">
            <div className="card-t">Patient state</div>
            <span className="badge b-mute ml-auto">
              {thread.station ? human(thread.station) : "Complete"}
            </span>
          </div>
          <Line line={thread.line} />
          {thread.nudge && <div className="nudge" style={{ margin: "0 12px 12px" }}>{thread.nudge}</div>}
        </div>

        <Details thread={thread} cat={cat} spine={spine ?? null} />

        <Trend now={todayVisit} visits={past} />

        <Team thread={thread} cat={cat} />

        {/* WHAT USED TO BE HERE: the 16 raw capability codes this caller holds,
            and the audit trail. Both are true and neither is a clinician's.
            A nurse reading our capability ids beside a patient's name is
            reading our schema, and the trail is every row we wrote, which is
            a developer's view of their afternoon. They belong behind the
            control panel, and this rail is for what the thread cannot say. */}
      </aside>

      {modal && (
        <>
          <div className="scrim" onClick={() => setModal(null)} />
          <OperationPanel
            op={modal.op} thread={thread.id} client={client}
            instruments={cat.instruments} flags={thread.flags} seed={modal.seed}
            onDone={(got) => {
              if (got) setCarried({ thread: thread.id, payload: got });
              setModal(null);
              onChanged();
            }}
            onCancel={() => setModal(null)}
          />
        </>
      )}
    </div>
  );
}

const TONE: Record<string, string> = { crit: "b-crit", warn: "b-warn", ok: "b-ok", mute: "b-mute" };

/** §25: what is known about the subject. Headed with the word the workflow
 *  declares as its spine, never with the title of the operation that typed
 *  the values in -- that is provenance, and provenance lives on the thread. */
function Details({ thread, cat, spine }: { thread: ThreadView; cat: Catalogue; spine: string | null }) {
  const rows = useMemo(() => {
    const queue = queueViewFor(cat, thread.workflow);
    const subject = thread.subject ?? {};
    const keys = (queue?.columns ?? []).filter((k) => subject[k]);
    const extra = Object.keys(subject).filter(
      (k) => !keys.includes(k) && !/(^|_)id$|_date$|_by$|^status$/.test(k) && subject[k]);
    return [...keys, ...extra].map((k) => ({ label: title(human(k)), value: String(subject[k]) }));
  }, [thread.subject, thread.workflow, cat]);

  // WHAT USED TO BE HERE: every committed record's values, drawn again. The
  // thread beside this rail already carries each of them, with who recorded
  // it and when, so this was the same afternoon printed twice -- and it was
  // most of the page. The identity rows below stay: a name, an age and a
  // village are what the thread does NOT repeat.
  if (!rows.length) return null;
  return (
    <div className="card">
      <div className="card-h">
        <div className="card-t">{spine ? title(human(spine)) : "Details"}</div>
      </div>
      <div style={{ padding: "10px 12px", display: "grid", gap: 12 }}>
        {rows.length > 0 && (
          <div>{rows.map((r) => <div className="kv" key={r.label}><span>{r.label}</span><b>{r.value}</b></div>)}</div>
        )}
      </div>
    </div>
  );
}
