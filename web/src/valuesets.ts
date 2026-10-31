/** What a bound choice offers, and nothing about any particular concept.
 *
 *  A question whose ANSWER carries the concept declares `answer_value_set` and
 *  no `answer_option`: the codes live in the value set, and writing them into
 *  the questionnaire would be the same list twice, free to disagree with
 *  itself. So something has to turn the slug into options, and this is it.
 *
 *  Pure, and the value sets are a parameter. Two reasons, and both are the
 *  reason `kernel/terminology.py` takes a terminology as an argument too: a
 *  check can pass a fake, and this file runs under plain node as well as in
 *  the browser, where the files arrive by different routes. `declarations.ts`
 *  supplies the real ones.
 *
 *  Nothing here names a concept, a code system or a value set. The slug comes
 *  off the question.
 */
export type Concept = { display?: string };
export type ValueSet = { slug: string; system: string; concepts: Record<string, Concept> };
export type Option = { value: string; display: string };

export function optionsFrom(
  q: { answer_option?: { value: string }[]; answer_value_set?: string },
  sets: Record<string, ValueSet>,
): Option[] {
  // The form's own list wins when it has one, because a question declares one
  // or the other and a question with both is a question contradicting itself.
  if (q.answer_option?.length) {
    return q.answer_option.map((o) => ({ value: o.value, display: o.value }));
  }
  const found = q.answer_value_set ? sets[q.answer_value_set] : undefined;
  if (!found) return [];
  // Sorted by what a person reads, not by the code. A code order is a random
  // order on screen.
  return Object.entries(found.concepts)
    .map(([code, c]) => ({ value: code, display: c.display || code }))
    .sort((a, b) => a.display.localeCompare(b.display));
}
