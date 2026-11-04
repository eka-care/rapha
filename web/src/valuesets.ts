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
/** An option is a standalone label a person picks from, so it is set to
 *  start a line and the letters that are names rather than words are set in
 *  capitals. "asha" and "mo" are a worker and a doctor; a menu offering them
 *  in lower case is a menu nobody proofread. See words.ts: the spelling
 *  table is there, once, and not in any screen. */
import { human, sentence, spell } from "./words.ts";

/** What a picker SHOWS. The stored value is always the code beside it.
 *
 *  A DECLARATION THAT CARRIES NO WORD still has to be read by somebody. The
 *  fallback used to hand back the stored code exactly as stored, so a
 *  pregnancy form offered "last_menstrual_period", "dating_scan" and
 *  "best_estimate" in a menu a nurse picks from. That is a variable name on
 *  a clinical form, and no amount of casing rescues it: the underscores are
 *  the giveaway. `human()` is the same fallback the rest of this renderer
 *  uses for an id nothing declared a word for, and it has been here all
 *  along -- this one place was not reaching for it.
 *
 *  It is still a fallback and still second best. The right fix for any
 *  particular option is a `display` in the declaration, which wins outright. */
const shown = (display: string, declared: boolean) =>
  sentence(spell(declared ? display : human(display)));

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
    return q.answer_option.map((o) => ({ value: o.value, display: shown(o.display || o.value, !!o.display) }));
  }
  const found = q.answer_value_set ? sets[q.answer_value_set] : undefined;
  if (!found) return [];
  // Sorted by what a person reads, not by the code. A code order is a random
  // order on screen.
  return Object.entries(found.concepts)
    .map(([code, c]) => ({ value: code, display: shown(c.display || code, !!c.display) }))
    .sort((a, b) => a.display.localeCompare(b.display));
}
