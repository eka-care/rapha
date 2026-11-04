/** The divider between the second panel and the work beside it.
 *
 *  A separator a person can drag, with the pointer captured so the drag
 *  survives leaving the 5px strip -- without capture, moving faster than
 *  React re-renders drops the drag halfway and the column stops under the
 *  cursor, which reads as the app being broken rather than as a missed
 *  event.
 *
 *  It is a real `separator` with a value, not a div with a mousedown. That
 *  is what makes it reachable at all for somebody who does not use a mouse:
 *  the arrows move it, Home and End take it to its limits, and the width it
 *  is at is announced rather than being a fact only visible to someone who
 *  can see the column.
 */
import { useRef } from "react";
import { MAX, MIN, nudge } from "./width";

export function Grip({ width, onWidth, onDone, label }: {
  width: number;
  /** Called continuously through the drag: the column follows the cursor
   *  rather than jumping to where it was let go. */
  onWidth: (px: number) => void;
  /** Called once at the end, which is when the choice is worth keeping. */
  onDone: (px: number) => void;
  label: string;
}) {
  const latest = useRef(width);

  return (
    <div
      className="grip"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={MIN}
      aria-valuemax={MAX}
      tabIndex={0}
      onKeyDown={(e) => {
        const next = nudge(width, e.key);
        if (next === null) return;
        e.preventDefault();
        onWidth(next);
        onDone(next);
      }}
      onPointerDown={(e) => {
        e.preventDefault();
        const el = e.currentTarget;
        el.setPointerCapture(e.pointerId);
        // The pointer's distance from the column's own left edge, so the
        // column's width is what the cursor is over -- not the cursor's
        // distance from wherever on the grip it happened to land.
        const left = el.getBoundingClientRect().left - width;
        const move = (ev: PointerEvent) => {
          latest.current = ev.clientX - left;
          onWidth(latest.current);
        };
        const up = () => {
          el.releasePointerCapture(e.pointerId);
          el.removeEventListener("pointermove", move);
          el.removeEventListener("pointerup", up);
          onDone(latest.current);
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
      }}
    />
  );
}
