/** Turning a declaration id into words, and nothing more.
 *
 *  Its own file because it is pure and has no React in it: messages.check.ts
 *  runs under plain node, and ui.tsx cannot be loaded there. ui.tsx re-exports
 *  both, so every existing import still reads `from "./ui"`.
 */

/** Declaration ids are machine names. Nothing but the declaration knows a
 *  human label, so when one is missing this is the least-worst fallback. */
export const human = (id: string | null | undefined) =>
  (id ?? "").replace(/^[a-z0-9]+\.(op|view|wf|inst|metric|schema)\./, "").replace(/[-_.]/g, " ");

/** Same, for somewhere a label starts a line. */
export const title = (id: string | null | undefined) => {
  const s = human(id);
  return s.charAt(0).toUpperCase() + s.slice(1);
};
