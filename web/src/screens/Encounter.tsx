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
import { questionnaire } from "../declarations";
import { Icon } from "../icons";
import { weigh } from "../loops";
import { agentLine, header, messages, queueViewFor, valuesOf, type Ctx, type Said } from "../messages";
import type { Catalogue, Operation, Payload, ThreadView } from "../types";
import { Composer } from "../thread/Composer";
import { ScribeBar } from "../scribe/ScribeBar";
import { mergeDrafts, type Opened } from "../scribe/session";
import { Stream } from "../thread/Thread";
import { Line } from "../view/View";
import { human, title } from "../words";
import { initialsOf } from "../agent";

const QUICK = 6;   // §33

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
  const [scribing, setScribing] = useState(false);
  const [drafts, setDrafts] = useState<Opened[]>([]);
  // The microphone is gated on the scribe instrument's own `requires:`, not a
  // flag named here: a bundle that spells its consent differently is gated by
  // its own spelling. The kernel refuses without it besides.
  const consentFlag = Object.values(cat.instruments ?? {})
    .map((i) => i as { kind?: string; requires?: string })
    .find((i) => i.kind === "scribe")?.requires;
  const consented = !consentFlag || (thread.flags ?? []).includes(consentFlag);

  const head = useMemo(() => header(thread, queueViewFor(cat, thread.workflow)), [thread, cat]);
  const msgs = useMemo(() => messages(thread, ctx, said), [thread, ctx, said]);
  const line = useMemo(() => agentLine(thread, ctx), [thread, ctx]);

  // §33: the declared rule in loops.ts decides the order, not this screen.
  const { primary, overflow } = useMemo(() => weigh(thread.actions, thread.closes), [thread.actions, thread.closes]);
  const ranked = useMemo(() => (primary ? [primary, ...overflow] : overflow), [primary, overflow]);
  const offered = ranked.slice(0, QUICK);

  const spine = cat.workflows?.[thread.workflow]?.spine;
  const spineId = spine && typeof thread.subject?.id === "string" ? thread.subject.id : "";

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
                          onClick={() => setModal({ op })}
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
          onAction={(op) => setModal({ op })}
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
            <div>
              <div className="eyebrow">Visit</div>
              <div className="card-t" style={{ marginTop: 2 }}>Patient state</div>
            </div>
            <span className="badge b-mute ml-auto">
              {thread.station ? human(thread.station) : "Complete"}
            </span>
          </div>
          <Line line={thread.line} />
          {thread.nudge && <div className="nudge" style={{ margin: "0 12px 12px" }}>{thread.nudge}</div>}
        </div>

        <Details thread={thread} cat={cat} spine={spine ?? null} />

        <div className="card">
          <div className="card-h">
            <div className="card-t">Capabilities held</div>
            <span className="badge b-mute ml-auto">{thread.held.length}</span>
          </div>
          <div className="caps">
            {(cat.capabilities ?? []).map((c) => (
              <span className={`cap${thread.held.includes(c) ? " on" : ""}`} key={c}>{c}</span>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-h">
            <div className="card-t">Audit trail</div>
            <span className="badge b-mute ml-auto">{thread.audit.length}</span>
          </div>
          <div className="audit">
            {thread.audit.length === 0 && <div className="fl-e">Nothing yet.</div>}
            {[...thread.audit].reverse().map((a) => (
              <div className="au" key={a.id}>
                <b>{a.operation.split(".").pop()}</b>
                <span className="ml-auto">{a.outcome.split(":")[0]}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {modal && (
        <>
          <div className="scrim" onClick={() => setModal(null)} />
          <OperationPanel
            op={modal.op} thread={thread.id} client={client}
            instruments={cat.instruments} flags={thread.flags} seed={modal.seed}
            onDone={() => { setModal(null); onChanged(); }}
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

  const recorded = useMemo(() => {
    const out: { id: string; title: string; values: ReturnType<typeof valuesOf> }[] = [];
    for (const a of thread.audit) {
      if (!/^(committed|confirmed|allowed)/.test(a.outcome)) continue;
      const op = cat.operations?.[a.operation];
      const presents = op?.presents ?? "event";
      if (presents !== "event" && presents !== "artifact") continue;
      if (spine && (op?.writes ?? []).includes(spine)) continue;
      // The real questionnaire resolver, so a value keeps its label and unit.
      // Passing () => null here dropped both and the panel read "Systolic 186".
      const values = valuesOf({ operations: cat.operations ?? {}, schema: questionnaire, badges: {} },
                              a.operation, a.payload);
      if (values.length) out.push({ id: a.id, title: op?.title ?? human(a.operation), values });
    }
    return out.reverse();
  }, [thread.audit, cat, spine]);

  if (!rows.length && !recorded.length) return null;
  return (
    <div className="card">
      <div className="card-h">
        <div className="card-t">{spine ? title(human(spine)) : "Details"}</div>
      </div>
      <div style={{ padding: "10px 12px", display: "grid", gap: 12 }}>
        {rows.length > 0 && (
          <div>{rows.map((r) => <div className="kv" key={r.label}><span>{r.label}</span><b>{r.value}</b></div>)}</div>
        )}
        {recorded.map((r) => (
          <div key={r.id}>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{r.title}</div>
            {r.values.map((v) => (
              <div className={`kv${v.crit ? " crit" : ""}`} key={v.link_id}>
                <span>{v.label}</span><b>{v.value}</b>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
