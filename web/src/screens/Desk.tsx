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
 *  WHAT THIS SCREEN NEVER DOES. It does not write. Choosing a row opens an
 *  empty visit and puts values in the panel's ordinary editable fields; the
 *  panel's own tap, behind the guard, is still the only write. And it names
 *  nothing: the heading, the create row's label and the operation it commits
 *  through all come from declarations, and what a row says about a person
 *  comes from the queue view's own columns.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { mobileHint } from "../abha/sdk";
import { ApiError, type Client } from "../api";
import { questionnaire } from "../declarations";
import { directoryNote, rows as deskRows, type DeskRow, type Resolution } from "../desk";
import { OperationPanel } from "../form/Panel";
import { Failed } from "../parts";
import { createLabel, firstOperation } from "../search";
import type { Catalogue, ViewDecl } from "../types";
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

export function Desk({ cat, decl, workflow, client, onOpenThread }: {
  cat: Catalogue;
  /** The queue view, which is what declares how a person is described here.
   *  Absent draws whatever a record carries, minus the plumbing. */
  decl?: ViewDecl;
  workflow?: string;
  client: Client;
  onOpenThread: (thread: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const [found, setFound] = useState<Resolution | null>(null);
  const [pick, setPick] = useState(0);
  const [opening, setOpening] = useState<DeskRow | null>(null);
  /** The empty visit this desk opened. Kept across a cancel, so a clerk who
   *  picks the wrong person and comes back does not leave a second empty
   *  encounter on the line behind them. */
  const [thread, setThread] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => { box.current?.focus(); }, []);

  // The search. Out of order answers are dropped rather than rendered: a
  // slower response to "kam" must not overwrite the answer to "kamala".
  const turn = useRef(0);
  useEffect(() => {
    const want = typed.trim();
    if (!want) { setFound(null); return; }
    const mine = ++turn.current;
    const timer = setTimeout(() => {
      client.patients(want).then(
        (got) => { if (turn.current === mine) { setFound(got); setError(null); } },
        (e) => { if (turn.current === mine) setError(e instanceof ApiError ? e : new ApiError(String(e), "This is a bug in the renderer.")); },
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

  const rows = useMemo(
    () => deskRows(found, typed, decl, questions, mobileHint, createLabel(cat, workflow)),
    [found, typed, decl, questions, cat, workflow],
  );
  useEffect(() => { setPick(0); }, [typed]);

  const note = directoryNote(found);
  const freshAt = rows.findIndex((r) => r.kind === "fresh");

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

      {note && <div className="desk-note" role="status">{note}</div>}
      {error && <Failed error={error} what="search for this patient" onRetry={() => setError(null)} />}

      <div className="desk-hits" id="desk-hits" role="listbox" aria-label="Who this might be">
        {rows.map((r, i) => (
          <button
            key={r.id}
            id={`desk-hit-${i}`}
            role="option"
            aria-selected={i === pick}
            data-active={i === pick}
            className={`desk-hit${r.kind === "fresh" ? " fresh" : ""}`}
            onMouseDown={(e) => { e.preventDefault(); void choose(r); }}
          >
            <span className="desk-hit-b">
              <span className="desk-hit-n">{r.name}</span>
              {r.meta && <span className="desk-hit-m">{r.meta}</span>}
            </span>
            {/* The key that takes this row, written on it. Not a hover
                tooltip: a clerk learning the keyboard has to be able to see
                it while reading the row, and the whole design is that they
                never go looking. */}
            <span className="desk-hit-k" aria-hidden="true">
              {i === pick ? "↵" : r.kind === "fresh" ? "⇥" : "↓"}
            </span>
          </button>
        ))}
        {!rows.length && (
          <div className="desk-empty">
            {typed.trim() ? "Still looking." : "Nobody searched for yet."}
          </div>
        )}
      </div>

      {op && thread && opening && (
        <>
          <div className="scrim" onClick={() => setOpening(null)} />
          <OperationPanel
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
            found={opening.kind === "fresh" ? undefined : {
              source: opening.kind === "known" ? FROM_HERE : FROM_DIRECTORY,
              evidence: opening.evidence,
              confidence: opening.confidence,
            }}
            mobile={opening.mobile}
            onDone={() => { setOpening(null); setThread(null); onOpenThread(thread); }}
            onCancel={() => setOpening(null)}
          />
        </>
      )}
    </div>
  );
}
