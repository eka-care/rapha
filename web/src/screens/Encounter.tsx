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
import type { Catalogue, Facility, Operation, Payload, ThreadView } from "../types";
import { Composer } from "../thread/Composer";
import { ScribeBar } from "../scribe/ScribeBar";
import { ScribeStart } from "../scribe/Start";
import { mergeDrafts, type Opened } from "../scribe/session";
import { Stream } from "../thread/Thread";
import { Carry, Team, Trend, usePast, visitOf } from "../thread/Past";
import { Line } from "../view/View";
import { RAIL, railFolded, railShown, setRailFolded, setRailShown, type RailId } from "./rail";
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

/** Which icon an action's capture instrument earns, and the reason this is a
 *  table rather than a guess at the call site: scripts/check_instruments.py
 *  holds it against the one instrument vocabulary, so an instrument added to
 *  the kernel and not drawn here fails the gate instead of rendering nothing.
 *
 *  It used to be a pill reading SCRIBE in eight and a half point capitals.
 *  That named our own vocabulary at a clinician, which is not information.
 *  The icon says the same thing in the one way that is useful: a microphone
 *  means speak, a page means type, a gauge means the machine reads it. */
const TAG: Record<string, string> = {
  scribe: "mic", form: "doc", device: "vitals", "constrained-voice": "mic",
};

export function Encounter({
  thread, cat, ctx, client, said, asking, catchment, onSay, onChanged, onOpenSubject,
}: {
  thread: ThreadView;
  cat: Catalogue;
  /** This centre's own declaration of who covers which habitation. */
  catchment?: Facility["catchment"];
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
  /** THE RAIL IS THE PERSON'S, not the screen's. What it shows and whether
   *  it is there at all is a setting on this device, because a doctor who
   *  wants one panel is not deciding anything about the centre. The control
   *  panel sets the same two values; see screens/rail.ts. */
  const [shown, setShown] = useState<RailId[]>(() => railShown());
  const [folded, setFolded] = useState(() => railFolded());
  const drop = (id: RailId) => {
    const next = shown.filter((x) => x !== id);
    setShown(next);
    setRailShown(next);
  };
  const fold = (now: boolean) => { setFolded(now); setRailFolded(now); };

  const [editing, setEditing] = useState<{ op: Operation; start: Payload } | null>(null);
  const [carried, setCarried] = useState<{ thread: string; payload: Payload } | null>(null);
  const [scribing, setScribing] = useState<string | null>(null);
  /** The action somebody tapped, waiting on how they want to record it.
   *  Tapping an action no longer opens a form: it opens the way in, and the
   *  form is one of the two doors there. */
  const [starting, setStarting] = useState<Operation | null>(null);
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
  /** What the header line already says, so the rail does not say it again. */
  const onHeader = useMemo(
    () => new Set<string>([head.name, ...head.meta].filter(Boolean)), [head]);
  const msgs = useMemo(() => messages(thread, ctx, said), [thread, ctx, said]);
  const line = useMemo(() => agentLine(thread, ctx), [thread, ctx]);

  // §33: the declared rule in loops.ts decides the order, not this screen.
  const { primary, overflow } = useMemo(() => weigh(thread.actions, thread.closes), [thread.actions, thread.closes]);
  const ranked = useMemo(() => (primary ? [primary, ...overflow] : overflow), [primary, overflow]);
  const offered = ranked.slice(0, QUICK);

  /** Which actions this station may speak, from the bundle's own `scribe`
   *  key. An action not on it opens its form directly, because offering a
   *  microphone that fills nothing is worse than offering none. */
  const speakable = new Set(cat.scribe?.[thread.station ?? ""]?.choose ?? []);
  const nudges = cat.scribe?.[thread.station ?? ""]?.nudges ?? [];
  /** THE ONE WAY A PANEL OPENS, so the rule above cannot be skipped by a
   *  call site added later. It used to be three call sites, each repeating
   *  the seed, and a fourth without it would have cost a patient a second
   *  one time password in silence. */
  const openPanel = (op: Operation) => setModal({ op, seed: carry(op) });
  const take = (op: Operation) => {
    if (speakable.has(op.id)) setStarting(op);
    else openPanel(op);
  };

  /** WHAT CAN STILL BE CORRECTED, and the three conditions are the kernel's
   *  own, said again here so the screen does not offer a control that would
   *  be refused: the visit is still open, the operation is not irreversible,
   *  and this is the LAST thing that operation recorded. Older lines on the
   *  thread are the history of the correction and are not themselves
   *  editable. kernel/proposals.amend enforces all three; this only decides
   *  where a button is drawn.
   */
  const editable = useMemo(() => {
    if (!thread.station) return new Set<string>();
    const latest = new Map<string, string>();
    for (const m of msgs) {
      if (m.kind !== "posted") continue;
      if (cat.operations[m.operation]?.irreversibility === "irreversible") continue;
      latest.set(m.operation, m.id);
    }
    return new Set(latest.values());
  }, [msgs, thread.station, cat.operations]);

  const spine = cat.workflows?.[thread.workflow]?.spine;
  const spineId = spine && typeof thread.subject?.id === "string" ? thread.subject.id : "";
  /** This patient's earlier visits, for the strip under the name and the
   *  trend in the rail. Empty until they arrive, and empty forever for a
   *  first visit, which is why both draw nothing rather than a frame with
   *  nothing in it. */
  const past = usePast(thread, cat, spineId);
  const todayVisit = useMemo(() => visitOf(thread, cat), [thread, cat]);

  return (
    <div className={`chatgrid${folded ? " folded" : ""}`}>
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
          editable={editable}
          onEdit={(m) => {
            const op = cat.operations[m.operation];
            if (op) setEditing({ op, start: m.payload as Payload });
          }}
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
                          onClick={() => take(op)}
                        >
                          {/* The icon says how this is recorded, so the tag
                              that used to say it in small capitals is gone.
                              A lock still earns words: an irreversible write
                              is the one thing a glyph must not carry alone. */}
                          <span className="p-i" aria-hidden="true">
                            <Icon name={(op.irreversibility === "irreversible" ? "lock"
                                      : TAG[op.instrument] ?? "doc") as never} className="i sm" />
                          </span>
                          <span className="p-b">
                            <span className="p-l">{op.title}</span>
                            {op.summary && <span className="p-s">{op.summary}</span>}
                          </span>
                          {op.irreversibility === "irreversible" && (
                            <span className="p-tag irr">Needs confirming</span>
                          )}
                          <Icon name="refer" className="i sm p-go" />
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
        {/* AFTER THE CHOICE, NEVER BEFORE IT. A person picks what they are
            about to record on the thread; this is what that tap opens, and
            from here speaking is the way in and the form is the way round.
            The examples are the bundle's, never typed here. */}
        {starting && !scribing && (
          <ScribeStart
            title={starting.title}
            nudges={nudges}
            reason={consented ? undefined : "Capture consent is not recorded on this visit"}
            onStart={() => { setScribing(starting.id); setStarting(null); }}
            onType={() => { openPanel(starting); setStarting(null); }}
            onCancel={() => setStarting(null)}
          />
        )}

        {scribing && (
          <ScribeBar thread={thread.id} station={thread.station ?? ""} pick={scribing}
                     onDrafts={(s) => setDrafts((all) => mergeDrafts(all, s.drafts, s.session))}
                     onClose={() => { setScribing(null); setDrafts([]); }} />
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
          onAction={(op) => take(op)}
          /* The composer's microphone is the shortcut past the choice, for
             somebody who already knows what they are doing: it opens on
             whatever this station recorded last. */
          onStartScribe={() => setScribing("")}
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

      {folded ? (
        <button type="button" className="rail-open" onClick={() => fold(false)}
                aria-label="Show the panels beside this visit">
          <Icon name="chev" className="i sm" />
        </button>
      ) : (
        <aside className="panel" aria-label="Beside this visit">
          <div className="rail-top">
            <button type="button" className="rail-fold" onClick={() => fold(true)}>
              <Icon name="chev" className="i sm" />
              Hide
            </button>
          </div>

          {/* WHAT USED TO BE HERE: the 16 raw capability codes this caller
              holds, and the audit trail. Both are true and neither is a
              clinician's. A nurse reading our capability ids beside a
              patient's name is reading our schema, and the trail is every
              row we wrote, which is a developer's view of their afternoon.
              They belong behind the control panel, and this rail is for
              what the thread cannot say. */}
          {shown.includes("state") && (
            <Panel id="state" onDrop={drop}>
              <div className="card-h">
                <div className="card-t">Where they are</div>
                <span className="badge b-mute ml-auto">
                  {thread.station ? title(human(thread.station)) : "Finished"}
                </span>
              </div>
              <Line line={thread.line} />
              {thread.nudge && <div className="nudge" style={{ margin: "0 12px 12px" }}>{thread.nudge}</div>}
            </Panel>
          )}

          {shown.includes("details") && (
            <Panel id="details" onDrop={drop} bare>
              <Details thread={thread} cat={cat} spine={spine ?? null} already={onHeader} />
            </Panel>
          )}

          {shown.includes("trend") && (
            <Panel id="trend" onDrop={drop} bare>
              <Trend now={todayVisit} visits={past} />
            </Panel>
          )}

          {shown.includes("team") && (
            <Panel id="team" onDrop={drop} bare>
              <Team thread={thread} cat={cat} catchment={catchment} />
            </Panel>
          )}

          {shown.length === 0 && (
            <p className="rail-none">
              Nothing here. Add panels back in the control panel.
            </p>
          )}
        </aside>
      )}

      {editing && (
        <>
          <div className="scrim" onClick={() => setEditing(null)} />
          <OperationPanel
            op={editing.op} thread={thread.id} client={client} amending
            instruments={cat.instruments} flags={thread.flags} start={editing.start}
            onDone={() => { setEditing(null); onChanged(); }}
            onCancel={() => setEditing(null)}
          />
        </>
      )}

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

/** The frame around one rail panel, carrying the one control a person needs
 *  on it: take this away. `bare` is for a panel that draws its own card and
 *  may draw nothing at all -- the remove button must not be the only thing
 *  left when there is no trend yet. */
function Panel({ id, onDrop, bare, children }: {
  id: RailId; onDrop: (id: RailId) => void; bare?: boolean;
  children: React.ReactNode;
}) {
  const name = RAIL.find((r) => r.id === id)?.title ?? id;
  return (
    <div className={`rail-slot${bare ? " bare" : " card"}`}>
      {children}
      <button type="button" className="rail-drop" aria-label={`Remove ${name}`}
              onClick={() => onDrop(id)}>
        <Icon name="plus" className="i sm" />
      </button>
    </div>
  );
}

const TONE: Record<string, string> = { crit: "b-crit", warn: "b-warn", ok: "b-ok", mute: "b-mute" };

/** §25: what is known about the subject. Headed with the word the workflow
 *  declares as its spine, never with the title of the operation that typed
 *  the values in -- that is provenance, and provenance lives on the thread. */
function Details({ thread, cat, spine, already }: {
  thread: ThreadView; cat: Catalogue; spine: string | null;
  /** The values the header above has ALREADY printed, so this card does not
   *  print them a second time nine inches below. A patient's name, age and
   *  village were on the header, in this card, and in the change strip
   *  between them, which is three places for one fact on one screen.
   *
   *  Matched on the VALUE and not the field name, because the header
   *  composes its line out of whatever the declaration gave it and this
   *  card must not have to guess which fields those were. */
  already: Set<string>;
}) {
  const rows = useMemo(() => {
    const queue = queueViewFor(cat, thread.workflow);
    const subject = thread.subject ?? {};
    const keys = (queue?.columns ?? []).filter((k) => subject[k]);
    const extra = Object.keys(subject).filter(
      (k) => !keys.includes(k) && !/(^|_)id$|_date$|_by$|^status$/.test(k) && subject[k]);
    return [...keys, ...extra]
      .map((k) => ({ label: title(human(k)), value: String(subject[k]) }))
      .filter((r) => !already.has(r.value));
  }, [thread.subject, thread.workflow, cat, already]);

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
