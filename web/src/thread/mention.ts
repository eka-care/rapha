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
export function patientContext(
  about: string[],
  readings: { label: string; value: string; crit: boolean }[],
  /** Words that identify the person (their name), kept out of every value. */
  hide: string[] = [],
): string {
  // A visit's values include what the front desk typed to register the person:
  // their name and phone number sit beside the pulse. Identity is judged by
  // what a label SAYS it is and by whether a value repeats the name, so it
  // holds for any centre's own wording.
  const identity = /\b(name|mobile|phone|abha|aadhaar|email|address)\b/i;
  const names = hide.map((h) => h.trim().toLowerCase()).filter(Boolean);
  readings = readings.filter((r) => !identity.test(r.label)
    && !names.some((n) => r.value.toLowerCase().includes(n)));
  const lines: string[] = [];
  const who = about.filter(Boolean).join(", ");
  if (who) lines.push(`Patient: ${who}.`);
  if (readings.length) {
    lines.push("Recorded this visit: "
      + readings.map((r) => `${r.label} ${r.value}${r.crit ? " (flagged)" : ""}`).join("; ") + ".");
  }
  return lines.join("\n");
}

/** The same details in front of a question, as one text. */
export function withPatient(
  question: string,
  about: string[],
  readings: { label: string; value: string; crit: boolean }[],
  hide: string[] = [],
): string {
  const c = patientContext(about, readings, hide);
  return c ? `${c}\n\n${question}` : question;
}
