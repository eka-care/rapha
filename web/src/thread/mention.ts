/** `@rapha how do I treat this?` -- the line that is for the assistant.
 *
 *  Pure, so assistant.check.ts runs it with no browser. A mention anywhere in
 *  the line counts, the same way `@Priya please repeat BP` does; what is left
 *  once the word is taken out is the question. A bare mention with nothing
 *  after it is not a question yet, so it is not sent.
 */

/** The question, or null when the line is not addressed to the assistant. */
export function raphaQuestion(text: string, name: string): string | null {
  const at = new RegExp(`(^|\\s)@${name}(?=\\s|$|[,:?!.])`, "i");
  if (!at.test(text)) return null;
  const rest = text.replace(at, "$1").replace(/^[\s,:]+/, "").replace(/\s+/g, " ").trim();
  return rest || null;
}
