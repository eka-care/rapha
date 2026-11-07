/** How wide the second panel is allowed to be, and remembering what a
 *  person chose.
 *
 *  Pure, so the rule is checkable without a browser. The clamp is the whole
 *  of the logic and it is the part that matters: a drag with no floor lets
 *  somebody reduce the column to a sliver they then cannot grab again, and a
 *  drag with no ceiling lets them push the visit beside it off the screen.
 *  Neither is recoverable without clearing storage, because the bad width is
 *  the one that gets remembered.
 */

/** Below this the names in the column start truncating to initials, which is
 *  the point at which the line stops being readable at a glance. Measured
 *  against the longest seeded name rather than picked off a grid. */
export const MIN = 200;

/** Above this the column is wider than the thread beside it on a 1280px
 *  screen, which is the laptop a primary health centre actually has. */
export const MAX = 480;

export const DEFAULT = 280;

export function clampWidth(px: number): number {
  if (!Number.isFinite(px)) return DEFAULT;
  return Math.min(MAX, Math.max(MIN, Math.round(px)));
}

const KEY = "phc.panel.width";

export function readWidth(): number {
  try {
    const v = localStorage.getItem(KEY);
    // A BLANK VALUE IS NOT A ZERO. `Number("")` is 0, not NaN, so a stored
    // empty string went through the clamp and came back as the minimum --
    // the column silently shrank to its narrowest on load and stayed there,
    // because that is then what got saved. Anything that is not a number is
    // treated as nothing stored. width.check.ts found this.
    if (v === null || v.trim() === "") return DEFAULT;
    const px = Number(v);
    return Number.isFinite(px) ? clampWidth(px) : DEFAULT;
  } catch {
    // A private window, or site data turned off. The default is a working
    // column, so there is nothing to report and nothing to recover.
    return DEFAULT;
  }
}

export function saveWidth(px: number): void {
  try { localStorage.setItem(KEY, String(clampWidth(px))); } catch { /* private window */ }
}

/** Where a keyboard drag lands. A divider that can only be moved with a
 *  mouse is a divider a person using the keyboard cannot move at all, and
 *  the column it sizes holds the whole day's work. */
export const STEP = 16;

export function nudge(px: number, key: string): number | null {
  if (key === "ArrowLeft") return clampWidth(px - STEP);
  if (key === "ArrowRight") return clampWidth(px + STEP);
  if (key === "Home") return MIN;
  if (key === "End") return MAX;
  return null;
}
