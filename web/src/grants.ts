/** Whether a capability grant is inert, and why.
 *
 *  Pure functions over declarations, in their own file (not Roles.tsx)
 *  because a .check.ts may never import a .tsx: this is what roles.check.ts
 *  imports, and Roles.tsx re-exports `inert` for anything reading it there.
 */
import type { Catalogue } from "./types";

/** A capability the workflow gives no way to exercise.
 *
 *  `drawn_by` refuses any operation this workflow has no step for, so granting
 *  visit.household to a clinic role does nothing at all -- phc.op.household-visit
 *  stands at `community` and the outpatient line has no such station. That is
 *  the guard that stopped it appearing as a button on every clinic encounter.
 *  A switch that silently does nothing is worse than one that explains itself.
 */
export function inert(cap: string, cat: Catalogue): boolean {
  const wf = Object.values(cat.workflows ?? {})[0];
  const drawn = new Set((wf?.steps ?? []).flatMap((s) => s.operations));
  return !Object.values(cat.operations ?? {})
    .some((op) => op.capability === cap && drawn.has(op.id));
}

/** The one sentence explaining an inert switch, built from the operation's
 *  own station and the workflow's own title -- never a hard coded string, so
 *  a bundle whose workflow calls its line something else, or whose stations
 *  are its own words, gets a true sentence with no change here. */
export function inertReason(cap: string, cat: Catalogue): string {
  const op = Object.values(cat.operations ?? {}).find((o) => o.capability === cap);
  const wf = Object.values(cat.workflows ?? {})[0];
  const line = (wf?.title ?? "This line").toLowerCase();
  const station = op?.station ?? "that";
  return `The ${line} has no ${station} station.`;
}
