/** The colour law's arithmetic, on its own: pure functions, no JSX, no React
 *  import. Moved out of ViewRenderer.tsx (Vernier's colour-law dimension
 *  found the arithmetic was guarded by nothing executable -- a check may
 *  never import a .tsx, so as long as toneOf lived in one, inverting it or
 *  deleting it left every .check.ts, tsc and the build green) so that
 *  design.check.ts can import and RUN it, the same pattern this repo already
 *  uses for grants.ts/grants.check.ts and voice/instruments.ts/voice.check.ts.
 *
 *  ViewRenderer.tsx re-exports everything here so existing imports (Home.tsx,
 *  home.check.ts's own regex on ViewRenderer.tsx) stay valid unchanged.
 *  Shell.tsx's rowTone calls toneOf per row instead of recomputing the same
 *  arithmetic a second time -- that duplicate was itself unguarded, since it
 *  lived in a second .tsx no check could import either.
 */
import type { QueueRow, ViewDecl } from "./types";

export type Tone = "over" | "act" | null;

export function elapsedMinutes(row: { entered_at?: string | null; opened_at?: string }): number | null {
  const at = row.entered_at ?? row.opened_at;
  if (!at) return null;
  const ms = Date.now() - new Date(at).getTime();
  return Number.isFinite(ms) ? ms / 60000 : null;
}

export function toneOf(
  decl: Pick<ViewDecl, "target_minutes" | "escalate_minutes"> | undefined,
  row: { entered_at?: string | null; opened_at?: string },
): Tone {
  if (decl?.target_minutes == null) return null;
  const minutes = elapsedMinutes(row);
  if (minutes == null) return null;
  const escalate = decl.escalate_minutes ?? decl.target_minutes * 2;
  if (minutes >= escalate) return "act";
  if (minutes >= decl.target_minutes) return "over";
  return null;
}

/** The age cell's own word, so colour is never the only channel: "18m over"
 *  for amber, "41m · act now" for red, a plain "6m" otherwise. Null when
 *  the row carries no timestamp at all (nothing to read back). */
export function ageLabel(row: { entered_at?: string | null; opened_at?: string }, tone: Tone): string | null {
  const minutes = elapsedMinutes(row);
  if (minutes == null) return null;
  const m = Math.max(0, Math.round(minutes));
  if (tone === "act") return `${m}m · act now`;
  if (tone === "over") return `${m}m over`;
  return `${m}m`;
}

/** Grafts item 3's fix, rendered: over-threshold rows sort to the top of an
 *  unambiguous vertical list. Stable beyond tone: two rows of the same tone
 *  keep their original order. */
export function sortByTone(rows: QueueRow[], decl?: Pick<ViewDecl, "target_minutes" | "escalate_minutes">): { row: QueueRow; tone: Tone }[] {
  const rank = (t: Tone) => (t === "act" ? 0 : t === "over" ? 1 : 2);
  return rows
    .map((row, i) => ({ row, i, tone: toneOf(decl, row), minutes: elapsedMinutes(row) ?? -1 }))
    .sort((a, b) => rank(a.tone) - rank(b.tone) || b.minutes - a.minutes || a.i - b.i)
    .map(({ row, tone }) => ({ row, tone }));
}

/** The act budget: one act element per plate, full stop. The rest are still
 *  exactly as over-threshold (still sorted up, still carry [data-over] and
 *  their own true "Nm over" reading), they are simply not the second red
 *  element on the same screen -- the header's own "+N act now" is where they
 *  are counted, never a hidden row. Returns the demoted tone per row and the
 *  true act total for that header line. */
export function budgetAct(decorated: { row: QueueRow; tone: Tone }[]): { row: QueueRow; tone: Tone; shown: Tone }[] {
  let used = 0;
  return decorated.map(({ row, tone }) => {
    if (tone !== "act") return { row, tone, shown: tone };
    used += 1;
    return { row, tone, shown: used === 1 ? "act" : "over" };
  });
}
