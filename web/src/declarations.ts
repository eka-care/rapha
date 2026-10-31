/** Where the renderer gets a questionnaire from: the kernel.
 *
 *  This file used to be a Vite glob over `questionnaires/*.json` and
 *  `terminology/*.json`, with its own docstring saying what was wrong with
 *  that: "the moment the API serves them, replace the body of
 *  questionnaire() with a fetch and delete the glob". The API serves them
 *  now, at `GET /questionnaires/` and at the `GET /valuesets/{slug}` route
 *  that had been written and never called, so the globs are gone and the
 *  forms are the kernel's answer like everything else on a screen.
 *
 *  Why a registry and not an async accessor. `questionnaire()` is read inside
 *  render, in four screens and the form panel, to label a value a colleague
 *  committed hours ago. Making it a promise would turn every one of those
 *  into a loading state for data the app already has. So the declarations are
 *  fetched once, before the first screen draws (app/App.tsx waits on
 *  `load()`), and read synchronously after that. An unfetched registry
 *  answers null, which is exactly what a missing questionnaire answered
 *  before.
 *
 *  Nothing here names a questionnaire, a value set, a concept or a code. The
 *  slugs come off the operations and the questions the kernel sent.
 */
import type { Question, Questionnaire } from "./types";
import { walk } from "./validate.ts";
import { optionsFrom, type Option, type ValueSet } from "./valuesets.ts";

export type { Option };

/** What the two routes answer. Narrower than `Client`, so load() can be
 *  handed a fake in a check without a kernel. */
export type Source = {
  questionnaires: () => Promise<{ questionnaires: Record<string, Questionnaire> }>;
  valueset: (slug: string) => Promise<{ concepts: { value: string; display: string; system: string }[] }>;
};

let forms: Record<string, Questionnaire> = {};
let sets: Record<string, ValueSet> = {};

/** Every value set the questions the kernel sent bind their answers to. Read
 *  off the forms rather than listed here: a new bound question needs no edit
 *  in this file, and a value set no question binds is never fetched. */
export const boundSets = (got: Record<string, Questionnaire>): string[] =>
  [...new Set(Object.values(got)
    .flatMap((q) => walk(q.questions ?? []))
    .map((q) => q.answer_value_set)
    .filter((s): s is string => !!s))].sort();

/** Fetch the declarations this kernel serves. Called once, before the first
 *  screen draws.
 *
 *  A value set that fails to expand is left out rather than failing the whole
 *  load: the question it binds then draws an empty picker, which is what it
 *  drew before any of this existed, and the form still opens. The alternative
 *  is a blank workspace because one slug is unbound, which is worse.
 *
 *  The ceiling, named because it does not bite today and will. `GET
 *  /valuesets/{slug}` clamps its expansion at 200 concepts, and this asks for
 *  200, so every value set in this build (the largest is nine) arrives whole.
 *  The day one is larger -- which is the day the local terminology file is
 *  replaced by the NRCeS release behind the same seam -- a picker will be
 *  silently short, with no sign on screen that anything was left out. The fix
 *  is to search as the clinician types through the route's `q` parameter,
 *  which already exists and which nothing calls, not to raise the number.
 */
export async function load(source: Source): Promise<{ forms: number; sets: number }> {
  const got = (await source.questionnaires()).questionnaires ?? {};
  const slugs = boundSets(got);
  const expanded = await Promise.all(slugs.map((slug) =>
    source.valueset(slug).then(
      (v) => [slug, {
        slug,
        system: v.concepts[0]?.system ?? "",
        concepts: Object.fromEntries(v.concepts.map((c) => [c.value, { display: c.display }])),
      }] as [string, ValueSet],
      () => null,
    )));
  forms = got;
  sets = Object.fromEntries(expanded.filter(Boolean) as [string, ValueSet][]);
  return { forms: Object.keys(forms).length, sets: Object.keys(sets).length };
}

/** The first declared question anywhere that asks for this answer.
 *
 *  Only `displayFor` below needs it, so it is not exported: a view says which
 *  of its columns are labels, and nothing has to ask a questionnaire what a
 *  column means any more.
 *
 *  First match wins across the forms. Two forms that ask for the same answer
 *  in two different shapes is a bundle contradicting itself, and picking one
 *  of them is a better failure than refusing to draw.
 */
function questionFor(linkId: string): Question | null {
  for (const form of Object.values(forms)) {
    const found = walk(form.questions ?? []).find((q) => q.link_id === linkId);
    if (found) return found;
  }
  return null;
}

/** What a declared answer is CALLED.
 *
 *  The option's own display when the declaration carries one, and the stored
 *  value itself when it does not. Today this bundle's questions list bare
 *  values, so a programme draws as its own code; the day a question binds a
 *  value set or carries displays, the word on screen improves here with no
 *  edit in any screen.
 */
export function displayFor(linkId: string, value: string): string {
  const q = questionFor(linkId);
  if (!q) return value;
  return options(q).find((o) => o.value === value)?.display || value;
}

export function questionnaire(id: string | undefined): Questionnaire | null {
  return (id && forms[id]) || null;
}

/** What a choice offers: the form's own list, or the value set the question
 *  bound its answer to, expanded by the kernel. */
export const options = (
  q: { answer_option?: { value: string }[]; answer_value_set?: string },
): Option[] => optionsFrom(q, sets);
