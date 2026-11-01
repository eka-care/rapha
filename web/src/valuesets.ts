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
  q: { answer_option?: { value: string; display?: string }[]; answer_value_set?: string },
  sets: Record<string, ValueSet>,
): Option[] {
  // The form's own list wins when it has one, because a question declares one
  // or the other and a question with both is a question contradicting itself.
  //
  // An inline option carries its own display, exactly as a bound concept
  // does, and this used to drop it and hand the stored code back as the word.
  // That is what made a queue read GENERAL: not a renderer deciding to shout,
  // but the one place a declared word could have arrived throwing it away. A
  // code set in sentence case reads as a misspelling, which is why the chip
  // was styled as a code -- the styling was right about the data and the data
  // was wrong. The fallback stays for a question that declares no display,
  // because an option with no word is still an option.
  if (q.answer_option?.length) {
    return q.answer_option.map((o) => ({ value: o.value, display: o.display || o.value }));
  }
  const found = q.answer_value_set ? sets[q.answer_value_set] : undefined;
  if (!found) return [];
  // Sorted by what a person reads, not by the code. A code order is a random
  // order on screen.
  return Object.entries(found.concepts)
    .map(([code, c]) => ({ value: code, display: c.display || code }))
    .sort((a, b) => a.display.localeCompare(b.display));
}
