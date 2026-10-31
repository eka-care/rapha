/** Where the renderer gets a questionnaire from.
 *
 *  Honest gap: kernel/contracts.py ROUTES has no questionnaire route, so the
 *  declarations are compiled into the bundle from questionnaires/*.json at
 *  build time. That is fine for one machine and wrong for a kernel: the
 *  moment the API serves them, replace the body of questionnaire() with a
 *  fetch and delete the glob. Nothing else in the app reads these files.
 */
import type { Questionnaire } from "./types";

const files = import.meta.glob("../../questionnaires/*.json", { eager: true, import: "default" }) as Record<
  string,
  Questionnaire
>;

export const QUESTIONNAIRES: Record<string, Questionnaire> = Object.fromEntries(
  Object.entries(files).map(([path, q]) => [path.split("/").pop()!.replace(/\.json$/, ""), q]),
);

export function questionnaire(id: string | undefined): Questionnaire | null {
  return (id && QUESTIONNAIRES[id]) || null;
}

/** The value sets, read the same way and for the same reason.
 *
 *  A question that binds its answer to a value set declares no
 *  `answer_option`, so until now a bound choice drew an empty dropdown. The
 *  laboratory result's analyte and unit have been in that state since the day
 *  they were bound: the API grew a `/valuesets/{slug}` route whose own
 *  docstring says "without this route the third binding form would be a column
 *  nothing could fill from a screen", and nothing on the screen ever called
 *  it.
 *
 *  These files are generated, read only and offline, which is the whole point
 *  of hosting the terminology locally, so reading them the way the
 *  questionnaires are read costs nothing and needs no network. When the API
 *  serves declarations, this and questionnaire() become the same fetch.
 */
import { optionsFrom, type Option, type ValueSet } from "./valuesets.ts";

const sets = import.meta.glob("../../terminology/*.json", { eager: true, import: "default" }) as Record<
  string,
  ValueSet
>;

export const VALUE_SETS: Record<string, ValueSet> = Object.fromEntries(
  Object.entries(sets).map(([path, v]) => [path.split("/").pop()!.replace(/\.json$/, ""), v]),
);

export type { Option };

/** What a choice offers on this machine's screens: the form's own list, or the
 *  value set the question bound its answer to. */
export const options = (
  q: { answer_option?: { value: string }[]; answer_value_set?: string },
): Option[] => optionsFrom(q, VALUE_SETS);

