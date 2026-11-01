/** The product tour: five things a person does on their first morning.
 *
 *  Which steps run, and where each card goes, are in tour.ts under a check.
 *  This draws them.
 *
 *  IT POINTS AT WHAT IS ACTUALLY THERE. Each step names an element by the
 *  class the renderer already gives it, the element is measured, and a step
 *  whose element is missing is dropped before the tour starts. So a tour
 *  never explains a control that is not on screen, and a bundle without one
 *  simply has a shorter tour.
 *
 *  It is shown once, remembered per browser, and the one place it can be
 *  started again is the control panel. Nothing reopens it on its own: a tour
 *  that comes back is an interruption, and this one is a courtesy.
 */
import { useEffect, useRef, useState } from "react";
import { applicable, place, STEPS } from "./guide";

const SEEN = "phc.tour.seen";

export function seenTour(): boolean {
  try { return localStorage.getItem(SEEN) === "1"; } catch { return true; }
}
export function rememberTour() {
  try { localStorage.setItem(SEEN, "1"); } catch { /* private window */ }
}

export function Tour({ onClose }: { onClose: () => void }) {
  const [at, setAt] = useState(0);
  const [box, setBox] = useState<DOMRect | null>(null);
  const card = useRef<HTMLDivElement>(null);
  /** The steps with something on screen to point at.
   *
   *  MEASURED AFTER THE PAGE EXISTS, not while this component first renders.
   *  Computed in the initialiser it found none of them -- the rail and the
   *  home screen are siblings that had not mounted yet -- so the tour marked
   *  itself seen and never appeared again. `null` is "not looked yet", which
   *  is a different thing from "nothing to point at".
   */
  const [steps, setSteps] = useState<typeof STEPS | null>(null);
  useEffect(() => {
    const look = () => setSteps(applicable(STEPS, (sel) => !!document.querySelector(sel)));
    // One frame, so a screen still painting is not asked what it has.
    const id = requestAnimationFrame(look);
    return () => cancelAnimationFrame(id);
  }, []);

  const step = steps?.[at];

  useEffect(() => {
    if (!step) return;
    const el = document.querySelector(step.at);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    const measure = () => setBox(el.getBoundingClientRect());
    measure();
    addEventListener("resize", measure);
    addEventListener("scroll", measure, true);
    return () => {
      removeEventListener("resize", measure);
      removeEventListener("scroll", measure, true);
    };
  }, [step]);

  // Escape leaves, and the arrows walk it, because a tour that traps the
  // keyboard is the opposite of a tour.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); done(); }
      if (e.key === "ArrowRight") setAt((i) => Math.min(i + 1, (steps?.length ?? 1) - 1));
      if (e.key === "ArrowLeft") setAt((i) => Math.max(i - 1, 0));
    };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  });

  const done = () => { rememberTour(); onClose(); };

  if (steps === null) return null;              // not looked yet
  // Nothing on this screen to point at: say nothing rather than draw a tour
  // about a page somebody is not on, and do not spend the one showing on it.
  if (!step) { if (steps.length === 0) rememberTour(); return null; }

  const size = card.current?.getBoundingClientRect();
  const spot = box
    ? place(
        { top: box.top, left: box.left, width: box.width, height: box.height },
        { width: innerWidth, height: innerHeight },
        { width: size?.width ?? 320, height: size?.height ?? 150 },
      )
    : { top: innerHeight / 2 - 75, left: innerWidth / 2 - 160 };

  return (
    <>
      <div className="tour-scrim" onClick={done} />
      {box && (
        <div
          className="tour-ring"
          style={{ top: box.top - 6, left: box.left - 6,
                   width: box.width + 12, height: box.height + 12 }}
          aria-hidden="true"
        />
      )}
      <div
        className="tour-card"
        ref={card}
        role="dialog"
        aria-modal="true"
        aria-label={`Tour, step ${at + 1} of ${steps!.length}`}
        style={{ top: spot.top, left: spot.left }}
      >
        <div className="tour-n">{at + 1} of {steps!.length}</div>
        <h3 className="tour-t">{step.title}</h3>
        <p className="tour-b">{step.body}</p>
        <div className="tour-f">
          <button className="tour-skip" onClick={done}>Skip</button>
          {at > 0 && (
            <button className="tour-back" onClick={() => setAt(at - 1)}>Back</button>
          )}
          <button
            className="tour-next"
            onClick={() => (at + 1 < steps!.length ? setAt(at + 1) : done())}
          >
            {at + 1 < steps!.length ? "Next" : "Done"}
          </button>
        </div>
      </div>
    </>
  );
}
