/** The front desk. One box, and the patient is standing there.
 *
 *  docs/reference/front-desk/front-desk.html, option A, with
 *  one-sequence.html's rule underneath it: the clerk types once, into one
 *  field, and the local register and the patient directory answer into the
 *  same list. Whoever is chosen -- somebody we hold, somebody the directory
 *  suggests, or nobody yet -- ends on the SAME registration form, which is
 *  the spec's own non-goal ("no second registration form"; two forms drift
 *  apart).
 *
 *  WHY THE KEYBOARD IS THE POINT AND NOT A COURTESY. The clerk is talking to
 *  the patient while typing. Every reach for the mouse is a break in that
 *  conversation, and the desk's competition is a register book that needs no
 *  hands at all. So: the box has focus on arrival, the arrows move the
 *  selection, Enter takes it, and Tab jumps to the row that creates somebody
 *  new carrying what was already typed. That is the `↵` and `⇥` the mockup
 *  draws on its rows, and the cost line under it -- "returning: 1 keystroke
 *  run + Enter", "new: Tab, then 4 answers".
 *
 *  WHAT A ROW SAYS, AND WHERE IT LEADS. The selected row carries the key that
 *  takes it AND the station that key leads to, because `↵` alone told a clerk
 *  nothing about what was about to happen to the person in front of them. The
 *  word is the workflow's -- the step after the one this operation belongs to
 *  -- and the line under the name is every column the queue view declared,
 *  each under the word the bundle gives that stored value. Both are the
 *  mockup's row (`34 · female · Sonpur · last seen 18 Jun`, `↵ send to
 *  nurse`) built out of declarations instead of out of this file.
 *
 *  WHAT IS HERE BEFORE A KEY IS PRESSED. The screen used to say "Nobody
 *  searched for yet." A clerk arriving at their shift was told nothing: not
 *  who had scanned the poster by the door and was sitting in the waiting
 *  room, not how long the line was, not who had already been through this
 *  desk this morning. All three are in the rows the declared queue view
 *  already returns. See desk.arrivals for what earns its place and what does
 *  not; this screen's job is still the box, and the day disappears the
 *  instant anything is typed.
 *
 *  WHAT THIS SCREEN NEVER DOES. It does not write. Choosing a row opens an
 *  empty visit and puts values in the panel's ordinary editable fields; the
 *  panel's own tap, behind the guard, is still the only write. And it names
 *  nothing: the screen's own name, the create row's label, the station a row
 *  leads to and the operation it commits through all come from declarations,
 *  and what a row says about a person comes from the queue view's own
 *  columns.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../icons";
import { ABHA_LINKED, identified, mobileHint } from "../abha/sdk";
import { Lotus } from "../abha/Lotus";
import { ApiError, type Client } from "../api";
import { displayFor, questionnaire } from "../declarations";
import {
  arrivals, destination, directoryNote, firstStation,
  rows as deskRows, type Desk as DeskRules, type DeskRow, type Resolution,
} from "../desk";
import { OperationPanel } from "../form/Panel";
import { say } from "../announce";
import { labelColumns, marked, provenanceOf } from "../loops";
import { clock } from "../messages";
import { Failed, Loading } from "../parts";
import { createLabel, firstOperation } from "../search";
import type { Catalogue, QueueRow, ViewDecl } from "../types";
import { fields } from "../view/View";
import { title } from "../words";
import { walk } from "../validate";

/** What the chip under a filled field says, per kind of row. Neither of these
 *  is a station, a flag or a column: one is this centre's own register and
 *  the other is the patient directory, which are the two places a person can
 *  be found. */
const FROM_HERE = "Already registered here";
const FROM_DIRECTORY = "From the patient directory";

/** Long enough that a clerk typing a name does not fire six searches, short
 *  enough that the list is there before they stop typing. */
const SETTLE = 180;

export function Desk({ cat, decl, workflow, client, queue, loadingQueue, q, onOpenThread }: {
  cat: Catalogue;
  /** The queue view, which is what declares how a person is described here.
   *  Absent draws whatever a record carries, minus the plumbing. */
  decl?: ViewDecl;
  workflow?: string;
  client: Client;
  /** Today's rows off that same queue view, already read by the app for the
   *  rail's counts and the home screen. Read once and shared, because two
   *  reads of one view is two different numbers on one screen. */
  queue?: QueueRow[];
  /** Whether that read is still running. Without it the desk draws an empty
   *  facility -- nobody waiting, nobody seen -- which is a confident lie and
   *  looks exactly like a kernel that is down. */
  loadingQueue?: boolean;
  /** What the line column's call box was given, carried here in the address
   *  so that calling a token is a place you can arrive at, go back from and
   *  reload. It seeds the search and nothing else: the clerk sees the person
   *  that token belongs to and still chooses them, because a token is a
   *  claim about who is at the counter, not proof of it. */
  q?: string;
  onOpenThread: (thread: string) => void;
}) {
  const [typed, setTyped] = useState(q ?? "");
  const [found, setFound] = useState<Resolution | null>(null);
  const [pick, setPick] = useState(0);
  const [opening, setOpening] = useState<DeskRow | null>(null);
  /** The empty visit this desk opened. Kept across a cancel, so a clerk who
   *  picks the wrong person and comes back does not leave a second empty
   *  encounter on the line behind them. */
  const [thread, setThread] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  /** Whether a search is in flight. The list used to say "Still looking." for
   *  as long as the kernel took, which is a word where the answer is going to
   *  be rows: a skeleton in the shape of the rows says the same thing and
   *  says how many to expect. */
  const [searching, setSearching] = useState(false);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => { box.current?.focus(); }, []);

  // CALLING A SECOND TOKEN WHILE ALREADY HERE. The address changes, this
  // screen does not remount, and the seed above runs once -- so without this
  // the second call would silently do nothing, which is the same failure as
  // the first one and harder to see. An empty q is somebody who navigated to
  // the desk plainly and must not have their typing cleared.
  useEffect(() => { if (q) setTyped(q); }, [q]);

  // The search. Out of order answers are dropped rather than rendered: a
  // slower response to "kam" must not overwrite the answer to "kamala".
  const turn = useRef(0);
  useEffect(() => {
    const want = typed.trim();
    if (!want) { setFound(null); setSearching(false); return; }
    const mine = ++turn.current;
    setSearching(true);
    const timer = setTimeout(() => {
      client.patients(want).then(
        (got) => {
          if (turn.current !== mine) return;
          setFound(got); setError(null); setSearching(false);
          // SC 4.1.3: the list below the box changes under a person who is
          // still typing into it, and nothing moves their focus. The count is
          // the whole answer, so the count is what is said.
          const n = (got.local?.length ?? 0) + (got.suggestions?.length ?? 0);
          say(n === 1 ? "1 match." : `${n} matches.`);
        },
        (e) => {
          if (turn.current !== mine) return;
          setSearching(false);
          setError(e instanceof ApiError ? e : new ApiError(String(e), "This is a bug in the renderer."));
        },
      );
    }, SETTLE);
    return () => clearTimeout(timer);
  }, [typed, client]);

  /** Which operation a chosen row commits through. The SERVER's answer when
   *  a search has returned one; the workflow's own first operation before
   *  that, which is what the command palette's create button already uses.
   *  Neither is written down here. */
  const opId = found?.commits_through ?? firstOperation(cat, workflow);
  const op = opId ? cat.operations?.[opId] : undefined;
  const questions = useMemo(
    () => walk(questionnaire(op?.input)?.questions ?? []),
    [op?.input],
  );

  /** Where taking a row leads: the station after the one this operation
   *  belongs to. The workflow's word, never this file's. */
  const goes = useMemo(() => destination(cat, op, workflow), [cat, op, workflow]);

  const rules: DeskRules = useMemo(() => ({
    decl, questions, hint: mobileHint, freshLabel: createLabel(cat, workflow),
    display: displayFor, identified,
  }), [decl, questions, cat, workflow]);

  const rows = useMemo(() => deskRows(found, typed, rules), [found, typed, rules]);
  useEffect(() => { setPick(0); }, [typed]);

  const note = directoryNote(found);
  const freshAt = rows.findIndex((r) => r.kind === "fresh");
  const searched = typed.trim().length > 0;

  const choose = async (row: DeskRow) => {
    setError(null);
    try {
      const id = thread ?? (await client.openThread({})).id;
      setThread(id);
      setOpening(row);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), "This is a bug in the renderer."));
    }
  };

  return (
    <div className="desk">
      <p className="desk-s">
        Type what the patient tells you. This centre's register and the
        patient directory are searched together.
      </p>

      <input
        ref={box}
        className="desk-box"
        value={typed}
        placeholder="Name or mobile number"
        aria-label="Find the patient by name or mobile number"
        role="combobox"
        aria-expanded={rows.length > 0}
        aria-controls="desk-hits"
        aria-activedescendant={rows[pick] ? `desk-hit-${pick}` : undefined}
        autoComplete="off"
        onChange={(e) => setTyped(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); setTyped(""); return; }
          if (!rows.length) return;
          if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => (p + 1) % rows.length); }
          if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => (p - 1 + rows.length) % rows.length); }
          if (e.key === "Enter") { e.preventDefault(); void choose(rows[pick]); }
          // Tab moves the selection to the row that creates somebody new,
          // which is what the mockup's ⇥ marks. It does NOT trap: once that
          // row is already selected, a second Tab leaves the field the way
          // every other field on every other screen does.
          if (e.key === "Tab" && !e.shiftKey && freshAt >= 0 && pick !== freshAt) {
            e.preventDefault();
            setPick(freshAt);
          }
        }}
      />

      {error && <Failed error={error} what="search for this patient" onRetry={() => setError(null)} />}

      {/* THE LIST GOES WHILE THE FORM IS OPEN. The clerk has chosen who
          this is; a list of other people it might have been is now the
          loudest thing on the screen and answers a question already
          answered. It comes back on Cancel. */}
      {!opening && (<>
      <div className="desk-hits" id="desk-hits" role="listbox" aria-label="Who this might be">
        {rows.map((r, i) => (
          <button
            key={r.id}
            id={`desk-hit-${i}`}
            role="option"
            aria-selected={i === pick}
            data-active={i === pick}
            className={`desk-hit${r.kind === "fresh" ? " fresh" : ""}`}
            /* MOUSEDOWN ONLY KEEPS THE KEYBOARD WHERE IT IS; THE CLICK IS THE
               ACTION. Taking the row used to hang off mousedown alone, and a
               mousedown is something only a mouse produces: a clerk who
               tabbed onto this row and pressed Enter fired a `click` that
               nothing was listening for, so the row took the focus and then
               did nothing at all. The whole "new: Tab, then 4 answers" path
               was mouse only. preventDefault stays, because without it the
               box loses focus the instant a mouse comes near the list. */
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => { void choose(r); }}
          >
            <span className="desk-hit-b">
              <span className="desk-hit-n">
                {r.name}
                {/* The same mark the queue row wears, for the same reason and
                    never as the only carrier: it has its own accessible name.
                    A clerk confirming that this is the right person has one
                    more fact to go on, and it is a national identifier rather
                    than anything a bundle declared. */}
                {r.identified && <Lotus className="desk-hit-lotus" />}
              </span>
              {r.meta && <span className="desk-hit-m">{r.meta}</span>}
            </span>
            {/* The key that takes this row, and where it leads, written on
                it. Not a hover tooltip: a clerk learning the keyboard has to
                be able to see it while reading the row, and the whole design
                is that they never go looking. The station is the workflow's
                word; "sends to" is not a declaration's to give. */}
            <span className="desk-hit-k">
              <span aria-hidden="true">{i === pick ? "↵" : r.kind === "fresh" ? "⇥" : "↓"}</span>
              {i === pick && goes && (
                <>
                  <span className="u-sr"> sends to </span>
                  <span className="desk-hit-go">{goes}</span>
                </>
              )}
            </span>
          </button>
        ))}
        {!rows.length && searched && (searching
          ? <Loading what="who this might be" shape="rows" rows={3} />
          : (
            <div className="desk-empty" role="status">
              Nobody here by that name yet. Keep typing, or register them.
            </div>
          ))}
      </div>

      {/* What the directory said, once, quietly, and UNDER the people it is
          not about. It used to sit above them in warning colour on every
          single search, which in a deployment with no directory is a
          permanent alarm about a condition that will never change -- and the
          largest thing on a screen whose job is the patient. Colour here
          means clinical risk; a missing directory is not one. */}
      {note && <p className="desk-note">{note}</p>}
      </>)}

      {!searched && !opening && (
        <Day
          decl={decl}
          rows={queue ?? []}
          loading={!!loadingQueue}
          first={firstStation(cat, workflow)}
          onOpenThread={onOpenThread}
        />
      )}

      {/* IN PLACE, UNDER THE SEARCH BOX, not over the screen. The front
          desk is the one screen where a form is the whole job, and it was
          the screen drawing that form over a list of search results nobody
          needs any more. */}
      {op && thread && opening && (
        <div className="desk-form">
          <OperationPanel
            inline
            op={op}
            thread={thread}
            client={client}
            instruments={cat.instruments}
            /* A person we FOUND arrives with their values, and supplying them
               is also what keeps the identity journey from running: asking
               for a one time password to learn what is already on the screen
               is the anti-goal NHA tests for. Nobody yet gets no seed, so the
               journey runs and fills the form from their profile. */
            seed={opening.kind === "fresh" ? undefined : opening.values}
            /* What the clerk typed, on the row that creates somebody new. NOT
               a seed: a seed means somebody was found, and being found is
               what stops the identity journey. This is the mockup's "keeps
               what you typed as the name", and it has to survive the journey
               being skipped. */
            start={opening.kind === "fresh" ? opening.values : undefined}
            found={opening.kind === "fresh" ? undefined : {
              source: opening.kind === "known" ? FROM_HERE : FROM_DIRECTORY,
              evidence: opening.evidence,
              confidence: opening.confidence,
            }}
            mobile={opening.mobile}
            onDone={() => { setOpening(null); setThread(null); onOpenThread(thread); }}
            onCancel={() => setOpening(null)}
          />
        </div>
      )}
    </div>
  );
}

/** The shift, before anything is typed.
 *
 *  Two short lists and the day's one number. Which rows go in which list is
 *  desk.arrivals' answer and the reasoning is there; this draws them. Every
 *  word on a row is the queue view's own -- the number, the name, the mark
 *  that says somebody arrived by themselves -- read through the same
 *  `fields()` the queue list uses, so the desk and the queue cannot come to
 *  disagree about one patient.
 */
function Day({ decl, rows, loading, first, onOpenThread }: {
  decl?: ViewDecl;
  rows: QueueRow[];
  loading: boolean;
  first?: string;
  onOpenThread: (thread: string) => void;
}) {
  const day = useMemo(() => arrivals(rows, first), [rows, first]);
  const provenance = provenanceOf(decl);
  const labelCols = labelColumns(decl);

  if (loading) return <Loading what="who is already here" shape="rows" rows={3} />;

  const line = (row: QueueRow) => {
    const f = fields(decl, row, labelCols, provenance?.column);
    const wears = marked(row, provenance);
    return (
      <button className="desk-wr" key={row.thread} onClick={() => onOpenThread(row.thread)}>
        {f.token && (
          <span
            className={`ticket desk-wr-tk${wears ? " mark" : ""}`}
            aria-label={wears ? `${f.token}, ${provenance!.label}` : undefined}
          >
            <Icon name="ticket" className="i tk-i" />
            {f.token}
          </span>
        )}
        {/* A thread nobody has registered yet has no name. This is exactly
            the row this list exists for: somebody who arrived, took a number
            and has not been to the desk. `fields()` says what to call them,
            for every surface at once. */}
        <span className={`desk-wr-nm${f.named ? "" : " u-mute"}`}>{f.name}</span>
        {(row.flags ?? []).includes(ABHA_LINKED) && <Lotus className="desk-hit-lotus" />}
        <span className="desk-wr-at">{title(row.station) || clock(row.opened_at)}</span>
      </button>
    );
  };

  return (
    <section className="desk-day">
      <h2 className="desk-day-h">
        Waiting here
        <span className="desk-day-c">{day.waiting.length}</span>
      </h2>
      {day.waiting.length
        ? <div className="desk-day-l">{day.waiting.map(line)}</div>
        : (
          <p className="desk-day-e">
            Nobody is waiting at this desk. Anybody who arrives at the poster by
            the door appears here.
          </p>
        )}

      <h2 className="desk-day-h">
        Already sent on today
        <span className="desk-day-c">{day.sent.length}</span>
      </h2>
      {day.sent.length
        ? <div className="desk-day-l">{day.sent.map(line)}</div>
        : <p className="desk-day-e">Nobody has been through this desk today yet.</p>}

      <p className="desk-day-n">
        {day.all} came in today. {day.moving.length} are still waiting.
      </p>
    </section>
  );
}
