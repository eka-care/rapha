/** Which steps of the tour apply right now, and where each one points.
 *
 *  Pure, so `tour.check.ts` runs it with no browser: the deciding is which
 *  steps have something to point AT, and that is the whole of the rule.
 *
 *  A TOUR MAY NOT POINT AT NOTHING. Every step names a real element by the
 *  class the renderer already gives it; a step whose element is not on this
 *  screen is dropped rather than drawn in the middle of the page explaining
 *  a control nobody can see. A laboratory running this kernel has no
 *  microphone on its composer and gets no step about recording, with no edit
 *  here.
 */
export type Step = {
  id: string;
  /** The element this step is about, as the renderer's own class. */
  at: string;
  title: string;
  body: string;
};

/** The tour, in the order somebody meets the product.
 *
 *  Five, because a tour nobody finishes taught nobody anything. Each one is a
 *  thing a person does on their first morning, not a feature list.
 */
export const STEPS: Step[] = [
  {
    id: "line",
    at: ".sb-list",
    title: "Today's line",
    body: "Everyone waiting, and the station they are at. Tap somebody to open their visit.",
  },
  {
    id: "call",
    at: ".sb-call",
    title: "Call a number",
    body: "Type the number on their slip. It finds them without a name.",
  },
  {
    id: "patients",
    at: ".tb-nav",
    title: "Everyone else",
    body: "Patients is the whole register: a person, and every visit they have had.",
  },
  {
    id: "ask",
    at: ".hero-ask",
    title: "Ask, or search",
    body: "One box for a name, a number, or a question. It answers here.",
  },
  {
    id: "flow",
    at: ".flow",
    title: "Where the line is heavy",
    body: "Each station, how many are at it, and who. It updates as people move.",
  },
];

/** The steps that have something on screen to point at, in declared order. */
export function applicable(steps: Step[], present: (selector: string) => boolean): Step[] {
  return steps.filter((s) => present(s.at));
}

/** Where the card goes: under the target when there is room beneath it,
 *  above it when there is not. Returned as numbers so the check can read
 *  them without a browser. */
export function place(
  box: { top: number; left: number; width: number; height: number },
  screen: { width: number; height: number },
  card: { width: number; height: number },
): { top: number; left: number } {
  const gap = 12;
  const below = box.top + box.height + gap;
  const top = below + card.height <= screen.height - gap
    ? below
    : Math.max(gap, box.top - card.height - gap);
  // Centred on the target, then pulled back inside the screen.
  const wanted = box.left + box.width / 2 - card.width / 2;
  const left = Math.max(gap, Math.min(wanted, screen.width - card.width - gap));
  return { top, left };
}
