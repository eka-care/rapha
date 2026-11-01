/** One place that says out loud what just happened.
 *
 *  WCAG 2.2 SC 4.1.3 (AA): when something changes without moving focus, a
 *  person who cannot see the screen has to be told. Every asynchronous thing
 *  this product does was silent: a save completing, the queue coming back
 *  with a different number in it, the agent answering, a recording starting.
 *  A sighted clerk sees the row appear; a screen reader user is left holding
 *  the sentence they were given before the read began.
 *
 *  WHY A STORE AND NOT A CONTEXT. The region has to be in the document BEFORE
 *  the text lands in it, or the assistive technology has nothing to watch, so
 *  it is mounted once by the app and never conditionally. Every other module
 *  therefore needs to reach a region it does not render. A context would put
 *  a provider and a hook through five components to deliver one string.
 *
 *  Nothing here invents a word. `say` is handed a sentence by the caller, and
 *  a caller's sentence is built out of declarations and counts the same way
 *  everything else on screen is.
 */

type Listener = (said: { text: string; at: number }) => void;

const listeners = new Set<Listener>();

/** Say something, politely: it waits for whatever is being read to finish.
 *
 *  The timestamp is the whole trick. Saving twice says "Saved." twice, and a
 *  live region whose text did not change is not re-read, so the second save
 *  would be silent. React re-renders on the new object either way. */
export function say(text: string): void {
  if (!text) return;
  const said = { text, at: Date.now() };
  for (const l of listeners) l(said);
}

export function onSay(l: Listener): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
