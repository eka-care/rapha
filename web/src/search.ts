/** What the command palette offers, worked out without a browser.
 *
 *  Find first, create only on miss. The rows are the threads the declared
 *  queue views returned and the views the bundle declared, in that order;
 *  creating anything is one button at the bottom of an empty result, and it
 *  says what creating costs.
 *
 *  There is no patient list in this file and no station in it. A queue view
 *  with `scope: all` would make the palette search the whole register with no
 *  change here; today the bundles declare only `scope: today`, so the palette
 *  searches today. That is a declaration to add, not code to write.
 */
import type { Catalogue, QueueRow, ViewDecl, ViewResult } from "./types";
import { title } from "./words.ts";

export type Row =
  | { kind: "ask"; id: string; name: string; meta: string; group: string }
  | { kind: "thread"; id: string; name: string; meta: string; group: string; row: QueueRow }
  | { kind: "view"; id: string; name: string; meta: string; group: string; view: ViewDecl }
  | { kind: "home"; id: string; name: string; meta: string; group: string };

/** The prototype's own test for a question rather than a name. */
export const isAsk = (q: string) =>
  /\?|^(how|what|which|who|when|why|show|list|count|find all|any )/i.test(q) && q.length > 4;

const text = (v: unknown) => (v === null || v === undefined ? "" : String(v));

/** One row per thread on every queue view the role may open, deduplicated,
 *  matched on any column the view declared and on the thread id. */
export function rows(
  q: string,
  queues: { decl: ViewDecl; result: ViewResult }[],
  nav: ViewDecl[],
): Row[] {
  const query = q.trim();
  const lo = query.toLowerCase();
  const out: Row[] = [];

  if (query && isAsk(query)) {
    out.push({ kind: "ask", id: `ask:${query}`, name: query, meta: "Ask the agent, workspace scope", group: "Ask the agent" });
  }

  const seen = new Set<string>();
  for (const { decl, result } of queues) {
    const group = query ? "Matches" : decl.title ?? title(decl.id);
    for (const row of (result.rows ?? []) as QueueRow[]) {
      if (seen.has(row.thread)) continue;
      const cols = (decl.columns?.length ? decl.columns : Object.keys(row.subject ?? {}))
        .map((k) => text(row.subject?.[k]))
        .filter(Boolean);
      const hay = [...cols, row.thread].join(" ").toLowerCase();
      if (query && !hay.includes(lo)) continue;
      seen.add(row.thread);
      out.push({
        kind: "thread", id: row.thread, name: cols[0] || row.thread,
        meta: [...cols.slice(1), row.station ? title(row.station) : "Complete"].join(" · "),
        group, row,
      });
    }
  }

  const go: Row[] = [
    { kind: "home", id: "home", name: "Home", meta: "Your shift at a glance", group: "Go to" },
    ...nav.map((v) => ({
      kind: "view" as const, id: v.id, name: v.title ?? title(v.id),
      meta: v.summary ?? v.kind, group: "Go to", view: v,
    })),
  ];
  out.push(...go.filter((r) => !query || r.name.toLowerCase().includes(lo)));

  return out;
}

/** What "Register new patient" actually runs: open an empty thread, then the
 *  first operation of the workflow's first step. Which operation that is, is
 *  the bundle's answer and not this renderer's. */
export function firstOperation(cat: Catalogue, workflow?: string): string | undefined {
  const wfs = Object.values(cat.workflows ?? {});
  const wf = (workflow && cat.workflows?.[workflow]) || wfs[0];
  return wf?.steps?.[0]?.operations?.[0];
}

/** What the create-on-miss button says. The declared verb of the operation it
 *  is about to open, so the PHC reads "Register" and the laboratory reads
 *  "Accession" with nothing in this renderer knowing either word. */
export function createLabel(cat: Catalogue, workflow?: string): string {
  const op = firstOperation(cat, workflow);
  return cat.operations?.[op ?? ""]?.short ?? "Open a new thread";
}
