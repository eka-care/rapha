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
import { Lotus } from "../abha/Lotus";
import { useEffect, useMemo, useRef, useState } from "react";
import { threadAsks } from "../agent";
import type { Client } from "../api";
import { OperationPanel } from "../form/Panel";
import { displayFor, questionnaire } from "../declarations";
import { walk } from "../validate";
import { Icon } from "../icons";
import { carriedInto, weigh } from "../loops";
import { agentLine, header, messages, queueViewFor, type Ctx, type Said } from "../messages";
import type { Catalogue, Facility, Operation, Payload, Proposal, ThreadView } from "../types";
import { Composer } from "../thread/Composer";
import { commands } from "../thread/commands";
import { ScribeBar } from "../scribe/ScribeBar";
import { KeptNotes, Nudges, StartHere, SubTabs, Templates as TemplatesPane, TranscriptText } from "../scribe/Pane";
import { usePane } from "../scribe/usePane";
import { mergeDrafts, type Opened } from "../scribe/session";
import { ScribeLive } from "../thread/ScribeLive";
import { clearLiveScribe, setLiveScribe } from "../scribe/live";
import { Stream, operationFor } from "../thread/Thread";
import { patientContext } from "../thread/mention";
import { Carry, PastVisits, Team, Trend, usePast, visitOf } from "../thread/Past";
import { Background } from "../thread/Background";
import { Tabs, type Tab, type TabId } from "../thread/Tabs";
import { Line } from "../view/View";
import { RAIL, railFolded, railShown, setRailFolded, setRailShown, type RailId } from "./rail";
import { human, sentence, spell, title } from "../words";
import { initialsOf } from "../agent";
import { ABHA_PENDING } from "../abha/sdk";

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
/** The visit's tabs, named the way screens/rail.ts names its panels: by
 *  what they SHOW, not by the component or by our own word for the
 *  machinery. A clinician does not have a feature called "scribe"; they
 *  have a recording, and what they want is what it heard. */
const tabsFor = (past: number, papers: number): Tab[] => [
  { id: "messages", title: "Messages", icon: "chat" },
  { id: "scribe", title: "Scribe", icon: "mic" },
  /* Next to the recording, because both are ways something gets INTO this
     visit, and before the history, because this is what you read first. */
  { id: "context", title: "Papers", icon: "clip", count: papers },
  { id: "past", title: "Earlier visits", icon: "clock", count: past },
];

/** Why the microphone is unavailable, in one place. It was written out
 *  twice -- once on the composer and once nowhere, which is how the tab
 *  came to have a disabled button with no explanation beside it.
 *
 *  IT NO LONGER NAMES A PARTICULAR REASON. It used to say which flag was
 *  missing, in this bundle's own words, which was that bundle's reason
 *  wearing a generic control's clothes: the gate is whatever state the
 *  scribe instrument declares in `requires:`, and another bundle gating its
 *  scribe on something else got the health centre's sentence. This bundle
 *  declares no gate at all now, so nothing in this build can reach the
 *  sentence -- but the mechanism stays, because `requires:` is still a
 *  thing an instrument may declare. */
const MIC_WHY = "This visit is not ready to be recorded";

const TAG: Record<string, string> = {
  scribe: "mic", form: "doc", device: "vitals", "constrained-voice": "mic",
  // A paperclip, because what this operation takes is the paper itself.
  document: "clip",
};

export function Encounter({
  thread, cat, ctx, client, said, asking, catchment, onSay, onChanged, onOpenSubject,
  onAskRapha,
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
  /** `@rapha ...` in the composer: open the assistant at the side. */
  onAskRapha?: (question: string, context: { title: string; text: string }) => void;
}) {
  /** THE FORM IS NOT A POP-UP. One state for both ways a form opens -- a
   *  new record and a correction -- because both are drawn in the same
   *  place: at the foot of the conversation, in the thread, under the line
   *  that asked for them.
   *
   *  A modal was the most form-like thing this interface could do, on a
   *  product whose promise to a frontline worker is that there are no forms.
   *  It also covered the record the person was reading in order to fill it
   *  in: a correction opened on top of the card it was correcting.
   *
   *  `start` is a correction's existing answers, `seed` is what an earlier
   *  commit on this visit already learned; the two never arrive together. */
  const [form, setForm] = useState<
    { op: Operation; seed?: Payload; start?: Payload; amending?: boolean; proposal?: Proposal } | null>(null);
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

  /** Which tab of this visit is open. Not remembered across patients: a
   *  visit opens on its conversation, because that is where the next thing
   *  to do is, and arriving at a new patient inside last patient's draft
   *  would be the worst possible first screen. */
  const [tab, setTab] = useState<TabId>("messages");
  /** Which way of copying paper in is open, if any. Local to the tab:
   *  unlike every other form on this screen it does NOT belong at the
   *  foot of the conversation, because the thing it produces is read
   *  here and nowhere else. */
  const [adding, setAdding] = useState<Operation | null>(null);

  /** A FORM OPENED BELOW THE FOLD IS A BUTTON THAT DID NOTHING. On a visit
   *  with any history the foot of the thread is off screen, and the whole
   *  point of drawing the form there instead of over the top is lost if
   *  nobody can see it arrive. */
  const formBox = useRef<HTMLDivElement | null>(null);
  const opened = form ? `${form.op.id}:${form.amending ? "amend" : "new"}` : "";
  useEffect(() => {
    if (opened) formBox.current?.scrollIntoView({ block: "nearest" });
  }, [opened]);

  const [carried, setCarried] = useState<{ thread: string; payload: Payload } | null>(null);
  const [scribing, setScribing] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Opened[]>([]);
  /** The Scribe tab's three views share one thing to choose and one session
   *  to read. See scribe/usePane.ts. */
  const pane = usePane({ thread: thread.id, station: thread.station ?? "",
                         open: tab === "scribe", asked: scribing });

  // THE RECORDING DOES NOT TAKE THE SCREEN (owner, 2026-11-07). Somebody who
  // starts Scribe still has a patient in front of them, so the thread stays
  // where it is and Scribe reports in the log (thread/ScribeLive) and on its
  // own button. The recorder is still mounted on the Scribe tab, hidden, so
  // nothing here stops the microphone.
  const ctl = useRef<{ stop: () => void; pause: () => void; resume: () => void } | null>(null);
  const live = scribing !== null ? pane.status : null;


  // The microphone is gated on the scribe instrument's own `requires:`, not a
  // flag named here: a bundle that spells its consent differently is gated by
  // its own spelling. The kernel refuses without it besides.
  const consentFlag = Object.values(cat.instruments ?? {})
    .map((i) => i as { kind?: string; requires?: string })
    .find((i) => i.kind === "scribe")?.requires;
  const consented = !consentFlag || (thread.flags ?? []).includes(consentFlag);
  // THE SHORTCUT. Not a bare letter: this screen is mostly a text box, and
  // a bare key would start recording every time somebody typed it into the
  // composer. Not Cmd+K either -- App.tsx already opens the command
  // palette on that, and two things on one chord is a chord that does the
  // wrong one. The guard is the modifier rather than a check on where the
  // focus is, because a focus check is wrong the moment another input is
  // added to this screen.
  useEffect(() => {
    const hit = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.altKey) return;
      if (e.key.toLowerCase() !== "j") return;
      e.preventDefault();
      if (!consented || scribing !== null) return;
      setScribing("");
    };
    window.addEventListener("keydown", hit);
    return () => window.removeEventListener("keydown", hit);
  }, [consented, scribing]);

  /** The rule itself is loops.carriedInto, where a check can run it: the
   *  guard that keeps one patient's identifier off another patient's form is
   *  not something to leave as an expression nothing can execute. */
  const carry = (op: Operation): Payload | undefined =>
    carriedInto(carried, thread.id, walk(questionnaire(op.input)?.questions ?? [])) as Payload | undefined;

  const head = useMemo(() => header(thread, queueViewFor(cat, thread.workflow), displayFor), [thread, cat]);
  // Tell the rail, so there is a way back from anywhere else in the app.
  useEffect(() => {
    if (live && live.phase !== "idle") setLiveScribe({ thread: thread.id, name: head.name, phase: live.phase, seconds: live.seconds });
    else clearLiveScribe(thread.id);
  }, [thread.id, head.name, live?.phase, live?.seconds]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => clearLiveScribe(thread.id), [thread.id]);
  /** What the header line already says, so the rail does not say it again. */
  const onHeader = useMemo(
    () => new Set<string>([head.name, ...head.meta].filter(Boolean)), [head]);
  const msgs = useMemo(() => messages(thread, ctx, said), [thread, ctx, said]);
  const line = useMemo(() => agentLine(thread, ctx), [thread, ctx]);

  // §33: the declared rule in loops.ts decides the order, not this screen.
  const { primary, overflow } = useMemo(() => weigh(thread.actions, thread.closes), [thread.actions, thread.closes]);
  const ranked = useMemo(() => (primary ? [primary, ...overflow] : overflow), [primary, overflow]);

  /** PAPER FROM SOMEWHERE ELSE. Neither half names an operation: what goes
   *  in this tab is whatever the bundle declared as `presents: artifact`,
   *  which is a word from catalogue/vocab.THREAD_OBJECTS -- a closed list
   *  this renderer implements -- and not a word typed here. A bundle that
   *  declares none gets an empty tab and no button, which is correct: it
   *  has nothing of this kind to keep.
   *
   *  `records` is what has been copied in already; `canAdd` is the way to
   *  copy another, and it is empty for somebody whose role does not hold
   *  the capability, because thread.actions has already been filtered by
   *  the guard. */
  const papers = useMemo(
    () => msgs.filter((m) => m.kind === "posted"
                         && cat.operations[m.operation]?.presents === "artifact"),
    [msgs, cat]);
  const canAdd = useMemo(
    () => ranked.filter((op) => op.presents === "artifact"), [ranked]);
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
  const openPanel = (op: Operation) => {
    // A FORM IS NOTE STRUCTURING, AND NOTE STRUCTURING IS THE SCRIBE TAB'S.
    // Whichever tab the tap came from, the form opens where the recorder and
    // the drafts already are; the thread keeps the conversation.
    setTab("scribe");
    pane.setSub("notes");
    setForm({ op, seed: carry(op) });
  };
  const take = (op: Operation) => {
    // THE CALL TO ACTION STARTS THE RECORDING. Not a choice of how to record
    // first: the person pressed "Record vitals" or "Document a consultation"
    // and the next thing that happens is that the scribe is listening, on
    // the Transcript view, with this station's note already chosen. The form
    // by hand is still one tap away from there, and `/` still opens it.
    if (speakable.has(op.id)) {
      setTab("scribe");
      pane.setSub("transcript");
      if (consented && scribing === null) setScribing(op.id);
    } else openPanel(op);
  };

  /** WHAT THE CALL TO ACTION SAYS WHILE ITS RECORDING IS HAPPENING. The
   *  button that started it is the one place the person is looking, so it
   *  carries the state: recording with a clock, paused, transcribing. Only
   *  the action this recording is for changes; the others stay as they were. */
  const doing = (op: Operation): string | null => {
    if (scribing === null || (pane.op || scribing) !== op.id) return null;
    const { phase, seconds } = pane.status;
    const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    return phase === "recording" ? `Recording ${clock}`
         : phase === "paused" ? `Paused ${clock}`
         : phase === "uploading" || phase === "waiting" ? "Transcribing"
         : null;
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
  /** WHAT `/` CAN DO BESIDE RECORDING SOMETHING. The kernel decides the
   *  actions half of that menu; this is the screen's own half, and it is
   *  built in thread/commands.ts so what it offers can be checked without a
   *  browser. Every verb here is a control already on this screen: the
   *  point is that `/` is now the way to all of it without hunting for a
   *  pixel. */
  const verbs = useMemo(() => commands({
    tabs: tabsFor(past.length, papers.length),
    open: tab,
    goTab: (id) => setTab(id as TabId),
    // Absent, not disabled: the same rule the actions half keeps.
    record: consented ? () => { setTab("scribe"); setScribing(""); } : undefined,
    railFolded: folded,
    toggleRail: () => fold(!folded),
    openRecord: spineId ? () => onOpenSubject(spineId) : undefined,
  }), [past.length, papers.length, tab, consented, folded, spineId, onOpenSubject]);

  return (
    <div className={`chatgrid${folded ? " folded" : ""}`}>
      <div className="chatcard">
        <header className="pt-head">
          <span className="avatar">{initialsOf(head.name)}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            {/* THE PAGE'S HEADING. A visit used to wear two: a bar saying
                  "Encounter", which told a person nothing they did not
                  already know, and this, the one that names whose visit it
                  is. The bar is gone and the heading stayed. */}
            <h1 className="pt-name">
              {head.name}
              {head.token && (
                <span className="ticket pt-token" aria-label={`${title(head.tokenWord)} ${head.token}`}><Icon name="ticket" className="i tk-i" />{head.token}</span>
              )}
            </h1>
            <div className="pt-line">
            <div className="pt-meta">{head.meta.join(", ")}</div>
            <div className="pt-chips">
              {head.identity && (
                <span className="id-badge">
                  <Lotus className="id-lotus" />
                  <span className="id-lab">{head.identity.label}</span>
                  <span className="id-val">{head.identity.value}</span>
                </span>
              )}
              {head.badges.filter((b) => !(head.token && b.text === head.token) && b.text !== human(ABHA_PENDING)).map((b) => (
                <span className={`badge ${TONE[b.style] ?? "b-mute"}`} key={b.text}>{b.text}</span>
              ))}
              {/* NO CHIP FOR THE PATIENT'S RECORD. It sat here beside the
                  badges, which made leaving this visit look like one more
                  fact about the patient. It is a place you go, and places
                  are the rail's and the `/` menu's -- both of which still
                  offer it, on the owner's call, 2026-11-04. */}
            </div>
            </div>
          </div>
        </header>

        <Tabs
          open={tab}
          tabs={tabsFor(past.length, papers.length)}
          onPick={setTab}
          /* THE PANEL'S OWN SWITCH, in the row that spans the screen rather
             than inside the column it controls. It was a "Hide" row at the
             top of that column, which pushed every card in it below the
             card it sat beside -- the misalignment the owner reported. */
          trailing={
            <button
              type="button"
              className={`vtabs-fold${folded ? "" : " on"}`}
              aria-pressed={!folded}
              aria-label={folded ? "Show the panels beside this visit" : "Hide the panels beside this visit"}
              onClick={() => fold(!folded)}
            >
              <Icon name="sidebar" className="i sm" />
            </button>
          }
        />

        {tab === "context" && (
          <div className="vbody">
            <Background
              papers={papers} add={canAdd} adding={adding} onAdd={setAdding}
              thread={thread.id} client={client} cat={cat} flags={thread.flags}
              /* The subject as the kernel sent it. WHICH field of it holds
                 the identifier a paper is filed under is the instrument
                 declaration's, read where the mount is built, because no
                 screen may type a subject's field names. */
              subject={thread.subject ?? {}}
              onDone={() => { setAdding(null); onChanged(); }} />
          </div>
        )}

        {tab === "past" && <div className="vbody"><PastVisits visits={past} /></div>}

        {/* HIDDEN, NOT UNMOUNTED. The recorder lives in this tab, and a
            recording is the one thing on this screen that cannot survive
            being unmounted: React tearing the tab down stops the microphone
            and throws the audio away. Looking at the conversation while it
            runs -- which is what the call to action invites -- must not do
            that, so the tab is always here and only shown when it is open. */}
        {(
          <div className="vbody" hidden={!(tab === "scribe")}>
            <SubTabs open={pane.sub}
                     notes={drafts.length + pane.kept.length}
                     onPick={pane.setSub} />

            {/* RECORDING HAPPENS ON THE TRANSCRIPT VIEW. The recorder is
                mounted for as long as a recording exists, whichever view is
                open, so looking at the notes never stops it; it draws as the
                Transcript view's own panel -- the daffodil, pause and
                continue, stop -- when that view is open, and as a one line
                bar above the others. Owner, 2026-11-04. */}
            {scribing !== null && (
              <ScribeBar thread={thread.id} op={pane.op} lib={pane.lib} controls={ctl}
                         full={pane.sub === "transcript"}
                         onStatus={pane.setStatus}
                         onByHand={() => {
                           const o = cat.operations[pane.op] ?? cat.operations[scribing];
                           if (o) openPanel(o);
                         }}
                         onDrafts={(s) => {
                           setDrafts((all) => mergeDrafts(all, s.drafts, s.session));
                           pane.setSession(s);
                           // What came back is what to look at: the notes, not
                           // whichever view somebody had open while it was written.
                           if (s.drafts.length || s.notes?.length) pane.setSub("notes");
                         }}
                         onClose={() => {
                           setScribing(null); setDrafts([]);
                           pane.setSession(null); pane.setStatus({ phase: "idle", seconds: 0 });
                         }}>
                <TranscriptText session={pane.session} />
                {!pane.session?.transcript && <Nudges nudges={nudges} />}
              </ScribeBar>
            )}
            {scribing === null && pane.sub === "transcript" && (
              <StartHere onStart={() => setScribing("")} session={pane.session}
                         reason={consented ? undefined : MIC_WHY} />
            )}

            {pane.sub === "templates" && (
              <TemplatesPane menu={pane.menu} library={pane.library} op={pane.op} lib={pane.lib}
                             phase={pane.phase} onOp={pane.chooseOp} onLib={pane.toggleLib} />
            )}

            {pane.sub === "notes" && <>
            <KeptNotes kept={pane.kept} lib={pane.lib} phase={pane.phase}
                       pending={scribing === null ? [] : pane.lib.filter(
                         (id) => !(pane.session?.notes ?? []).some((n) => n.template === id))}
                       titles={Object.fromEntries(
                         "items" in (pane.library ?? {}) ? (pane.library as { items: { id: string; title: string }[] })
                           .items.map((t) => [t.id, t.title]) : [])} />
            {drafts.map(({ draft: d, key }) => {
              const op = cat.operations[d.operation];
              return op ? (
                <OperationPanel key={key} op={op} thread={thread.id} client={client} draft={d}
                  instruments={cat.instruments} flags={thread.flags} inline
                  onDone={() => { setDrafts((all) => all.filter((x) => x.draft.operation !== d.operation)); onChanged(); }}
                  onCancel={() => setDrafts((all) => all.filter((x) => x.draft.operation !== d.operation))} />
              ) : null;
            })}

            {/* THE FORM, ON THE SCRIBE TAB. Note structuring has one home:
                the recorder, the drafts it produced and a form somebody
                opened by hand are all the same thing -- an operation being
                filled in -- and they are all here. The thread only says that
                one is waiting. Owner, 2026-11-04. */}
            {form && (
              <div className="vform" ref={formBox}>
                <OperationPanel
                  key={`${form.op.id}:${form.amending ? "amend" : form.proposal?.id ?? "new"}`}
                  op={form.op} thread={thread.id} client={client} inline
                  amending={form.amending} proposal={form.proposal}
                  instruments={cat.instruments} flags={thread.flags}
                  seed={form.seed} start={form.start}
                  onDone={(got) => {
                    if (got && !form.amending) setCarried({ thread: thread.id, payload: got });
                    setForm(null);
                    onChanged();
                  }}
                  onCancel={() => setForm(null)}
                />
              </div>
            )}
            </>}
          </div>
        )}

        {tab === "messages" && <>
        <Carry now={todayVisit} visits={past} />

        <Stream
          msgs={msgs}
          editable={editable}
          onEdit={(m) => {
            const op = cat.operations[m.operation];
            if (op) { setTab("scribe"); setForm({ op, start: m.payload as Payload, amending: true }); }
          }}
          onReview={(m) => {
            setTab("scribe");
            setForm({ op: operationFor(m.proposal, cat.operations), proposal: m.proposal });
          }}
        >
          {scribing !== null && (
            <ScribeLive phase={pane.status.phase} seconds={pane.status.seconds} drafts={drafts.length}
                        onStop={() => ctl.current?.stop()}
                        onPause={() => ctl.current?.pause()} onResume={() => ctl.current?.resume()}
                        onOpen={() => { setTab("scribe"); pane.setSub(drafts.length ? "notes" : "transcript"); }} />
          )}
          {/* §21: the agent's own message, and the actions it is offering. */}
          {(line.sentences.length > 0 || offered.length > 0) && (
            <div className="lg2">
              <div className="lg2-who" style={{ color: "var(--color-agent)" }}>Agent<time>now</time></div>
              <div className="lg2-body">
                <p className="lg2-txt">{line.sentences.join(" ")}</p>
                  {offered.length > 0 && (
                    <div className="props">
                      {offered.map((op, i) => (
                        <button
                          className={`prop${i === 0 ? " primary" : ""}${doing(op) ? " rec" : ""}`}
                          key={op.id}
                          onClick={() => take(op)}
                          title={op.summary || op.title}
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
                            <span className="p-l">{doing(op) ?? op.title}</span>
                          </span>
                          {op.irreversibility === "irreversible" && (
                            <span className="p-tag irr">Needs confirming</span>
                          )}
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
          )}

        </Stream>

        {/* WHAT USED TO BE HERE: the recording bar and every draft it
            produced, stacked at the foot of the thread inside a 42vh
            scroller. A clinical note is the one thing on this screen a
            doctor has to READ BEFORE SIGNING, and it was the thing with the
            least room -- a form in a letterbox, under the conversation it
            came from. Both moved into the view beside the thread, which has
            the width, and the thread went back to being a thread. */}

        <Composer
          about={head.name}
          actions={ranked}
          roles={Object.keys(cat.bundles ?? {})}
          verbs={verbs}
          asking={asking}
          onSay={onSay}
          onAction={(op) => take(op)}
          /* The composer's microphone is the shortcut past the choice, for
             somebody who already knows what they are doing: it opens on
             whatever this station recorded last. */
          onStartScribe={() => setScribing("")}
          recording={scribing !== null && (pane.status.phase === "recording" || pane.status.phase === "paused")
            ? { seconds: pane.status.seconds, paused: pane.status.phase === "paused",
              onStop: () => ctl.current?.stop(), onPause: () => ctl.current?.pause(), onResume: () => ctl.current?.resume() } : null}
          working={scribing !== null && (pane.status.phase === "uploading" || pane.status.phase === "waiting")
            ? "Writing notes…" : undefined}
          onAskRapha={onAskRapha && ((q) => onAskRapha(q, {
            title: head.name,
            text: patientContext(head.meta, todayVisit.values, [head.name]),
          }))}
          micReason={consented ? undefined : MIC_WHY}
          quick={
            <>
              {threadAsks({ hasHistory: !!spineId, flags: thread.flags }).slice(0, 2).map((q) => (
                <button className="chip" key={q} onClick={() => onSay(q)}>{q}</button>
              ))}
            </>
          }
        />
        </>}
      </div>

      {!folded && (
        <aside className="panel" aria-label="Beside this visit">
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
              {thread.nudge && <div className="nudge" style={{ margin: "0 12px 12px" }}>{sentence(thread.nudge)}</div>}
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
      .map((k) => ({ label: title(human(k)), value: spell(String(subject[k])) }))
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
