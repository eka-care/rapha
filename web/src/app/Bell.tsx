/** What is waiting for somebody, where a person already looks for it.
 *
 *  THIS REPLACED A NAV ROW. The declared tasklist had a place of its own in
 *  the icon rail, between the line and the register, carrying a count that
 *  did not change for most of a shift. That is not a place: nobody navigates
 *  to "things that need me" the way they navigate to the line. It is an
 *  interruption, and an interruption belongs in the top right with a number
 *  on it, which is where every person using this has already been taught to
 *  look by every other piece of software they own.
 *
 *  EVERY WORD HERE IS DECLARED. A row's sentence is the view's own task
 *  title; the button's word is the operation's own `short`, read out of the
 *  catalogue. This file knows that a row may carry an operation and that an
 *  operation has a name. It does not know what a laboratory result is, and a
 *  bundle that declares different tasks gets different rows with no edit
 *  here.
 *
 *  A ROW IS A QUICK ACTION, NOT A LINK TO A LIST. The declaration already
 *  says which operation clears the task and which threads are waiting on it,
 *  so pressing the row opens the first of those visits with that operation
 *  ready, rather than putting a person on a filtered list to find it again.
 */
import { useEffect, useRef } from "react";
import { Icon } from "../icons";
import type { Catalogue, TaskRow } from "../types";

export function Bell({ rows, open, onOpen, onGo, cat }: {
  /** The declared tasklist's own rows, already loaded for the rail's counts
   *  so the bell and any list of the same tasks cannot disagree. */
  rows: TaskRow[];
  open: boolean;
  onOpen: (open: boolean) => void;
  /** Open a visit, with the operation that clears this task if there is one. */
  onGo: (thread: string, operation?: string | null) => void;
  cat: Catalogue;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  // WAITING IS A NUMBER OF THINGS, NOT A NUMBER OF ROWS. Two people waiting
  // on a result is two, under one sentence.
  const waiting = rows.reduce((n, r) => n + r.count, 0);

  // Click away and Escape both close it. A panel pinned to a corner that can
  // only be closed by pressing the thing that opened it is a panel a person
  // ends up navigating away from to get rid of.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) onOpen(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onOpen(false); };
    addEventListener("mousedown", away);
    addEventListener("keydown", key);
    return () => { removeEventListener("mousedown", away); removeEventListener("keydown", key); };
  }, [open, onOpen]);

  return (
    <div className="bell-wrap" ref={wrap}>
      <button
        type="button"
        className={`icon-btn bell${waiting ? " has" : ""}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        /* SC 4.1.2: the count is in the accessible name, because a screen
           reader given "Notifications" learns nothing a sighted person did
           not get from the badge. */
        aria-label={waiting === 1 ? "1 thing needs you" : `${waiting} things need you`}
        onClick={() => onOpen(!open)}
      >
        <Icon name="bell" className="i sm" />
        {waiting > 0 && <span className="bell-n">{waiting}</span>}
      </button>

      {open && (
        <div className="bell-panel" role="dialog" aria-label="What needs you">
          {rows.length === 0 ? (
            /* NOT "no notifications". At the end of a shift this sentence is
               the one piece of good news the product gets to deliver. */
            <div className="bell-clear">
              <Icon name="check" className="i sm" />
              Nothing is waiting on you.
            </div>
          ) : (
            rows.map((r) => {
              const op = r.operation ? cat.operations?.[r.operation] : undefined;
              const thread = r.threads[0];
              return (
                <button
                  key={r.title}
                  type="button"
                  className="bell-row"
                  disabled={!thread}
                  onClick={() => thread && onGo(thread, r.operation)}
                >
                  <span className="bell-c">{r.count}</span>
                  <span className="bell-t">{r.title}</span>
                  {op && <span className="bell-do">{op.short ?? op.title}</span>}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
