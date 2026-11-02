/** Which panels sit beside an open visit, and whether the rail is there at
 *  all.
 *
 *  A PERSONAL SETTING, not a facility one, which is why it lives in this
 *  browser and not in the kernel. A doctor who wants the trend and nothing
 *  else is not making a decision about the centre; the next doctor to use
 *  the same room may want the opposite. Role grants and the recording
 *  prompts are the centre's and are saved there.
 *
 *  Each panel is named by what it SHOWS, not by the component that draws it,
 *  because these words appear on the control panel.
 */
export type RailId = "state" | "details" | "trend" | "team";

export const RAIL: { id: RailId; title: string; blurb: string }[] = [
  { id: "state", title: "Where they are",
    blurb: "The stations this visit has passed and the one it is at." },
  { id: "details", title: "Who they are",
    blurb: "Name, age, village and the rest of the identity the thread does not repeat." },
  { id: "trend", title: "How they are changing",
    blurb: "One measurement across this patient's visits." },
  { id: "team", title: "Who is covering them",
    blurb: "The worker for this habitation, and who is on the visit." },
];

const KEY = "phc.rail";

/** Everything, which is what somebody who has never opened the control
 *  panel sees. A new panel added later is on by default for the same
 *  reason: a setting nobody has touched should not hide something new. */
const ALL: RailId[] = RAIL.map((r) => r.id);

export function railShown(): RailId[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return ALL;
    const got = JSON.parse(raw) as unknown;
    if (!Array.isArray(got)) return ALL;
    const known = got.filter((id): id is RailId => ALL.includes(id as RailId));
    return known;
  } catch {
    // A private window, or site data the person has cleared. Showing
    // everything is the right answer to "we do not know".
    return ALL;
  }
}

export function setRailShown(ids: RailId[]) {
  try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch { /* private window */ }
}

const FOLD = "phc.rail.folded";

export const railFolded = () => {
  try { return localStorage.getItem(FOLD) === "1"; } catch { return false; }
};
export const setRailFolded = (folded: boolean) => {
  try { localStorage.setItem(FOLD, folded ? "1" : "0"); } catch { /* private window */ }
};
