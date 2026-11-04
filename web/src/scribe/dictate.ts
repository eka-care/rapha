/** Speaking into whatever field has the cursor.
 *
 *  THE RULE THIS SERVES. Rapha is a scribe-first product: no form may exist
 *  that cannot be filled by voice. A form that can only be typed into is the
 *  product admitting its own claim is decoration, and at a rural primary
 *  health centre it is also the literacy argument -- the people using this
 *  are faster speaking than typing, in a script the keyboard fights.
 *
 *  THE SHAPE, which is Heidi's and which the owner asked for by name: one
 *  key, held, anywhere in the product. Whatever field has the cursor gets
 *  what was said. Nothing focused and the words come back as text to copy,
 *  rather than the shortcut silently doing nothing.
 *
 *  Everything in this file is pure, so the rules can be checked without a
 *  microphone or a browser. What needs either is useDictation.ts.
 */

/** The default key. The owner's choice, and Heidi's: the rupee sign.
 *
 *  IT IS A SETTING, not a constant, and that is deliberate. There is no
 *  rupee key on a plain US or UK keyboard. On an Indian layout this is a
 *  good key and a piece of local identity; on a machine that shipped with a
 *  different layout it would be a shortcut nobody can press, and a shortcut
 *  nobody can press is the whole feature gone with no error to explain it.
 *  So the default is the rupee and the key is changeable.
 */
export const DEFAULT_KEY = "₹";

const KEY_SETTING = "phc.dictate.key";

export function dictateKey(): string {
  try {
    const v = localStorage.getItem(KEY_SETTING);
    return v && v.length > 0 ? v : DEFAULT_KEY;
  } catch {
    return DEFAULT_KEY;
  }
}

export function setDictateKey(key: string): void {
  try { localStorage.setItem(KEY_SETTING, key || DEFAULT_KEY); } catch { /* private window */ }
}

/** How long a press has to last before it counts as holding rather than
 *  tapping. Below this, two presses in a row are the hands-free gesture.
 *  220ms is about where a deliberate hold separates from a tap; it is short
 *  enough that holding never feels like waiting. */
export const HOLD_MS = 220;

/** How close two taps must be to be one double press. The platform
 *  convention is around 500ms and there is no reason to differ. */
export const DOUBLE_MS = 500;

export type Press = { at: number; released?: number };

/** What a sequence of presses means. Pure, so the gesture is checkable
 *  without a keyboard.
 *
 *  - `hold`: the key is still down and has been for long enough.
 *  - `handsfree`: two taps, close together. Recording continues until the
 *    key is pressed again.
 *  - `stop`: a press while hands-free is running.
 *  - null: nothing yet, which is the case while a first tap waits to see
 *    whether a second one follows.
 */
export function gesture(
  presses: Press[], now: number, running: "hold" | "handsfree" | null,
): "hold" | "handsfree" | "stop" | null {
  const last = presses[presses.length - 1];
  if (!last) return null;
  // A press of any kind ends hands-free. Checked first: while it is running,
  // the key means stop and nothing else, so a double press to end it cannot
  // be read as a double press to start it again.
  if (running === "handsfree" && last.released === undefined) return "stop";
  if (last.released === undefined && now - last.at >= HOLD_MS) return "hold";
  const before = presses[presses.length - 2];
  if (
    running === null
    && before?.released !== undefined
    && last.released !== undefined
    && last.at - before.at <= DOUBLE_MS
    && last.released - last.at < HOLD_MS
    && before.released - before.at < HOLD_MS
  ) return "handsfree";
  return null;
}

/** Whether dictated words can go into this element.
 *
 *  A text input, a textarea, or anything marked editable. Deliberately NOT a
 *  select, a checkbox, a radio or a number input: speech into a closed
 *  choice is a different problem -- the words have to be matched against the
 *  declared options -- and dictating "one twenty" into a number field would
 *  insert the characters rather than the value. Both are worth doing and
 *  neither is this. A field this refuses is treated as nothing focused, so
 *  the words still come back as text rather than vanishing.
 */
export function isTarget(el: Element | null): el is HTMLInputElement | HTMLTextAreaElement | HTMLElement {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "TEXTAREA") return !(el as HTMLTextAreaElement).disabled
                               && !(el as HTMLTextAreaElement).readOnly;
  if (tag === "INPUT") {
    const input = el as HTMLInputElement;
    if (input.disabled || input.readOnly) return false;
    return ["text", "search", "tel", "url", "email", ""].includes(input.type);
  }
  return (el as HTMLElement).isContentEditable === true;
}

/** Where the words go in what is already there.
 *
 *  At the cursor, replacing whatever is selected, with a space put in only
 *  where one is needed. Appending to the end instead looks the same on an
 *  empty field and is wrong on every other one: a person who dictates a
 *  correction into the middle of a sentence gets it on the end, which is the
 *  behaviour that teaches people to clear the field before speaking.
 */
export function insert(
  current: string, start: number, end: number, said: string,
): { value: string; caret: number } {
  const words = said.trim();
  if (!words) return { value: current, caret: end };
  const before = current.slice(0, start);
  const after = current.slice(end);
  // A space before, unless we are at the start of the field or just after
  // one, or just after an opening bracket.
  const lead = before && !/[\s([{]$/.test(before) ? " " : "";
  // A space after, unless what follows already begins with one or with
  // punctuation that closes up against the word.
  const tail = after && !/^[\s.,;:!?)\]}]/.test(after) ? " " : "";
  const middle = lead + words + tail;
  return { value: before + middle + after, caret: before.length + lead.length + words.length };
}

/** What the indicator says while the microphone is open.
 *
 *  It names the field, because the whole gesture rests on the person's idea
 *  of where the cursor is matching ours, and the one moment to correct that
 *  belief is before they speak rather than after. With no field, it says
 *  what will happen to the words instead of pretending something is
 *  listening on their behalf.
 */
export function listening(fieldLabel: string | null): string {
  return fieldLabel ? `Listening — goes into ${fieldLabel}` : "Listening — the words will be yours to copy";
}

/** The field's own name, for that sentence. Read off the accessible name the
 *  form already gives every field, never off a list of field names kept
 *  here: this file may not know what any particular form asks. */
export function labelFor(el: Element | null, doc?: Document): string | null {
  if (!el) return null;
  const aria = el.getAttribute("aria-label");
  if (aria?.trim()) return aria.trim();
  const by = el.getAttribute("aria-labelledby");
  const owner = doc ?? (typeof document === "undefined" ? undefined : document);
  if (by && owner) {
    const text = by.split(/\s+/)
      .map((id) => owner.getElementById(id)?.textContent?.trim() ?? "")
      .filter(Boolean).join(" ");
    if (text) return text;
  }
  if (el.id && owner) {
    const lab = owner.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab?.textContent?.trim()) return lab.textContent.trim();
  }
  const wrapping = el.closest("label");
  if (wrapping) {
    // The label's own words, less whatever the field itself contributes.
    const own = wrapping.textContent?.trim();
    if (own) return own.split("\n")[0].trim() || null;
  }
  const placeholder = el.getAttribute("placeholder");
  return placeholder?.trim() || null;
}
