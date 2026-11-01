/** The small shared pieces: the three states every screen can be in, and the
 *  boundary that keeps one broken screen from blanking the app.
 *
 *  §72 empty, §73 loading, §75 error. The rule those three sections share is
 *  that a screen is never blank and never says "something went wrong":
 *  ApiError already carries a `next` sentence saying what to do, so the error
 *  state's job is to show it, not to invent one.
 *
 *  THE LOADING STATE IS A SHAPE, NOT A WORD. A spinner says "wait"; a
 *  skeleton says "rows are coming, about six of them, each with a name and a
 *  time". Three properties hold it together, and each one is a defect this
 *  file shipped before:
 *
 *   - IT DOES NOT FLASH. A skeleton that appears for eighty milliseconds is
 *     worse than the blank it replaced, because the screen now moves twice.
 *     Nothing draws until SETTLE has passed, so a kernel on the same machine
 *     never shows one at all.
 *   - IT IS DECORATION. Every bar is aria-hidden, and the region around them
 *     carries role="status" with a sentence, so a screen reader is told the
 *     list is loading instead of being read a wall of empty boxes.
 *   - IT HONOURS LESS MOTION. The shimmer is an animation, and style/cards.css
 *     replaces it with a flat tint under prefers-reduced-motion. ui.check.ts
 *     asserts that escape exists rather than trusting the global reset.
 */
import { Component, useEffect, useState, type ReactNode } from "react";
import { onSay } from "./announce";
import { ApiError } from "./api";

/** SC 2.4.2: the name of this screen, in the browser's own tab.
 *
 *  A component and not an effect in the app, because the app decides what to
 *  draw before it knows what to call it, and a hook after a conditional
 *  return is a hook that does not always run. */
export function PageTitle({ title }: { title: string }) {
  useEffect(() => { document.title = title; }, [title]);
  return null;
}

/** SC 4.1.3's one region, mounted once by the app and never conditionally:
 *  assistive technology watches a region that was already in the document,
 *  so one that appears carrying its message arrives too late to be read.
 *
 *  TWO SLOTS, ALTERNATING. A live region whose text is unchanged is not
 *  announced again, so saving twice would say "Saved." once. Writing into
 *  whichever slot is empty makes every message a change.
 */
export function Announcer() {
  const [slots, setSlots] = useState<[string, string]>(["", ""]);
  useEffect(() => onSay(({ text }) => {
    setSlots(([a]) => (a ? ["", text] : [text, ""]));
  }), []);
  return (
    <>
      <div className="u-sr" role="status" aria-live="polite">{slots[0]}</div>
      <div className="u-sr" role="status" aria-live="polite">{slots[1]}</div>
    </>
  );
}

/** Long enough that a fast answer never draws a skeleton, short enough that a
 *  slow one is explained before anybody wonders. */
/** Keep Tab inside a thing that covers the screen.
 *
 *  A modal that does not hold the keyboard is a modal only for the mouse:
 *  Tab walks straight out of it into the page behind the scrim, where
 *  everything is still focusable and nothing is visible. This wraps the walk
 *  at both ends. It reads the focusable elements on each press rather than
 *  caching them, because a panel's fields appear and disappear as it is
 *  filled in and a cached list would send the keyboard to an element that is
 *  no longer there.
 */
export function trapTab(e: { key: string; shiftKey: boolean; preventDefault: () => void },
                        box: HTMLElement | null) {
  if (e.key !== "Tab" || !box) return;
  const able = [...box.querySelectorAll<HTMLElement>(
    'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),'
    + 'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')]
    .filter((el) => el.offsetParent !== null || el === document.activeElement);
  if (!able.length) return;
  const first = able[0], last = able[able.length - 1];
  const on = document.activeElement;
  if (e.shiftKey && (on === first || on === box)) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && on === last) { e.preventDefault(); first.focus(); }
}

export const SETTLE = 250;

/** True once `ms` has passed since this component mounted. */
function useSettled(ms = SETTLE): boolean {
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSettled(true), ms);
    return () => clearTimeout(t);
  }, [ms]);
  return settled;
}

/** One bar. Decoration: it carries no text and no name, because a screen
 *  reader reading six grey rectangles has been told nothing. */
function Bar({ w, h }: { w?: number | string; h: number }) {
  return <span className="sk" style={{ width: w ?? "100%", height: h }} />;
}

/** The shape of what is coming. A queue is rows, a thread is messages, a
 *  panel is its own blocks: three shapes, one primitive. */
export type Shape = "rows" | "messages" | "blocks" | "lines";

function Bones({ shape, rows }: { shape: Shape; rows: number }) {
  const n = Array.from({ length: rows }, (_, i) => i);
  if (shape === "messages") {
    return (
      <div className="sk-messages">
        {n.map((i) => (
          <div className={`sk-msg${i % 2 ? " mine" : ""}`} key={i}>
            <Bar w={28} h={28} />
            <div className="sk-msg-b">
              <Bar w={i % 2 ? "40%" : "28%"} h={9} />
              <Bar w={i % 2 ? "62%" : "84%"} h={44} />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (shape === "blocks") {
    return (
      <div className="sk-blocks">
        {n.map((i) => (
          <div className="sk-block" key={i}>
            <Bar w={i % 2 ? "46%" : "34%"} h={11} />
            <Bar h={13} />
            <Bar w="72%" h={13} />
          </div>
        ))}
      </div>
    );
  }
  if (shape === "lines") {
    return (
      <div className="sk-lines">
        {n.map((i) => <Bar key={i} w={i === rows - 1 ? "56%" : "100%"} h={12} />)}
      </div>
    );
  }
  return (
    <div className="sk-rows">
      {n.map((i) => (
        <div className="sk-row" key={i}>
          <Bar w={26} h={26} />
          <div className="sk-row-b">
            <Bar w={`${52 - (i % 3) * 9}%`} h={12} />
            <Bar w={`${34 - (i % 2) * 7}%`} h={9} />
          </div>
          <Bar w={44} h={10} />
        </div>
      ))}
    </div>
  );
}

/** §73: skeletons, never a full-page spinner.
 *
 *  `what` finishes the sentence "Loading ...", so it is the caller's word for
 *  the thing a person asked for and never a station, a flag or a bundle. */
export function Loading({ what, shape = "rows", rows = 4 }: {
  what: string; shape?: Shape; rows?: number;
}) {
  const settled = useSettled();
  // Before SETTLE the region is still announced -- a screen reader is slower
  // than the eye and an empty live region that fills later says nothing --
  // but nothing is drawn, so a fast answer replaces nothing.
  return (
    <div className="loading" role="status" aria-busy="true">
      <span className="u-sr">Loading {what}</span>
      {settled && <div aria-hidden="true"><Bones shape={shape} rows={rows} /></div>}
    </div>
  );
}

/** §75: what failed, whether the record changed, what to do next. The middle
 *  one is the part products usually drop. A read that failed changed nothing
 *  and should say so, because the alternative is a person re-entering data
 *  they already committed. */
export function Failed({
  error, what, onRetry,
}: { error: ApiError; what?: string; onRetry?: () => void }) {
  return (
    <div className="notice" role="alert">
      <div className="t-strong">{what ? `Unable to ${what}.` : "That did not go through."}</div>
      <div className="t-body">{error.message}</div>
      <div className="t-meta u-mute">Nothing was written.</div>
      <div className="t-body">{error.next}</div>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}

/** §72: an empty screen is an invitation to act, so it carries the action.
 *  role="status" because an empty list is the ANSWER to a read, and a person
 *  who cannot see the screen is otherwise left with the sentence they were
 *  given while it loaded. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty" role="status">
      <div className="t-strong">{title}</div>
      {children && <div className="t-body u-mute">{children}</div>}
    </div>
  );
}

export class Boundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="workspace-scroll">
        <div className="notice" role="alert">
          <div className="t-strong">This screen stopped drawing.</div>
          <div className="t-body">{this.state.err.message}</div>
          <div className="t-meta u-mute">Nothing was written. This is a bug in the renderer, not in your data.</div>
          <button className="btn" onClick={() => location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}
