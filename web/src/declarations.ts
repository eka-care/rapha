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
