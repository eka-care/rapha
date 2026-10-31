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
import type { Questionnaire } from "./types";
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

export function questionnaire(id: string | undefined): Questionnaire | null {
  return (id && forms[id]) || null;
}

/** What a choice offers: the form's own list, or the value set the question
 *  bound its answer to, expanded by the kernel. */
export const options = (
  q: { answer_option?: { value: string }[]; answer_value_set?: string },
): Option[] => optionsFrom(q, sets);
