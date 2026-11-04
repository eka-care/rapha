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

/** The question, with the patient's clinical details in front of it.
 *
 *  THE OWNER CHOSE THIS on 2026-11-04: "@rapha how do I treat this patient?"
 *  means nothing to an assistant that has been told nothing, so the details go
 *  with it. What goes is what treatment depends on: age, sex and the rest of
 *  the header line, and the values recorded in this visit. What does not go is
 *  who the person is: not the name and not the ABHA number, because no answer
 *  depends on either and both identify them.
 *
 *  The whole text is what the assistant is sent AND what the person sees in
 *  the chat, so nothing leaves the page that is not on the screen.
 */
export function withPatient(
  question: string,
  about: string[],
  readings: { label: string; value: string; crit: boolean }[],
): string {
  const lines: string[] = [];
  const who = about.filter(Boolean).join(", ");
  if (who) lines.push(`Patient: ${who}.`);
  if (readings.length) {
    lines.push("Recorded this visit: "
      + readings.map((r) => `${r.label} ${r.value}${r.crit ? " (flagged)" : ""}`).join("; ") + ".");
  }
  return lines.length ? `${lines.join("\n")}\n\n${question}` : question;
}
