/** Whether a capability grant is inert, and why.
 *
 *  Pure functions over declarations, in their own file (not Roles.tsx)
 *  because a .check.ts may never import a .tsx: this is what grants.check.ts
 *  imports.
 */
import type { Catalogue } from "./types";

/** What this centre does not run, as the kernel serves it at GET /facility:
 *  `{capability: the plugin withholding it}` and `{plugin: its title}`. The
 *  renderer holds no opinion about either and types neither. */
export type Withheld = { withheld: Record<string, string>; without: Record<string, string> };

/** A capability that would do nothing if it were granted, and there are two
 *  reasons, one declared by the workflow and one by the facility.
 *
 *  `drawn_by` refuses any operation this workflow has no step for, so granting
 *  visit.household to a clinic role does nothing at all -- phc.op.household-visit
 *  stands at `community` and the outpatient line has no such station. That is
 *  the guard that stopped it appearing as a button on every clinic encounter.
 *  A switch that silently does nothing is worse than one that explains itself.
 *
 *  The second reason is the plugins this centre does not run. That decision is
 *  the KERNEL'S: api/main.py `caller()` subtracts a withheld capability once,
 *  before anything reads the set, and the guard refuses every use of it by
 *  name. Deciding grantability from the workflow alone -- which is all this
 *  function could see until `GET /facility` was read by a screen -- meant a
 *  centre with the laboratory off still offered `lab.order` as a live switch,
 *  an administrator granted it, and the guard then refused every use with a
 *  sentence about a plugin. That was contradiction 25, and this is the screen
 *  stopping deciding something the kernel had already decided.
 */
export function inert(cap: string, cat: Catalogue, facility: Withheld): boolean {
  if (facility.withheld[cap]) return true;
  // ponytail: first workflow only, correct while a bundle declares one. A
  // second workflow would mark every capability the first one draws as
  // inert for the second; upgrade to check across all of cat.workflows.
  const wf = Object.values(cat.workflows ?? {})[0];
  const drawn = new Set((wf?.steps ?? []).flatMap((s) => s.operations));
  return !Object.values(cat.operations ?? {})
    .some((op) => op.capability === cap && drawn.has(op.id));
}

/** The one sentence explaining an inert switch, built from the operation's
 *  own station, the workflow's own title or the plugin's own title -- never a
 *  hard coded string, so a bundle whose workflow calls its line something
 *  else, or whose plugins are its own words, gets a true sentence with no
 *  change here.
 *
 *  A facility's refusal is reported before the workflow's, because it is the
 *  one an administrator can undo: a station a line does not have is a
 *  declaration to change, and a plugin that is off is a facility's own choice.
 */
export function inertReason(cap: string, cat: Catalogue, facility: Withheld): string {
  const plugin = facility.withheld[cap];
  if (plugin) {
    return `This centre does not run ${facility.without[plugin] ?? plugin}.`;
  }
  const op = Object.values(cat.operations ?? {}).find((o) => o.capability === cap);
  const wf = Object.values(cat.workflows ?? {})[0];
  const line = (wf?.title ?? "This line").toLowerCase();
  const station = op?.station ?? "that";
  return `The ${line} has no ${station} station.`;
}
