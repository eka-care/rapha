/** HOW WIDE A FIELD IS, decided from its declaration.
 *
 *  Every field on every form in this product was the same width as every
 *  other field on its line. A prescription row put "Amoxicillin only
 *  product" and "500" in two boxes of 148 pixels: the drug name, which is
 *  the only part of that row a person reads to know what it says, was cut
 *  off, and the three-digit dose had a hundred pixels of nothing after it.
 *  That is what made the forms look unaligned. They were aligned. They were
 *  aligned to the wrong thing.
 *
 *  A field's width is a property of what it holds, and what it holds is
 *  declared. A number is short. A closed choice is as wide as its longest
 *  option. Free prose takes the line. So the weight below is read off the
 *  question's own `type` and, for a choice, off the options the terminology
 *  returned -- never off a field's name, which this renderer may not know.
 *
 *  The weights are relative, not pixels. The row is a wrapping flex and each
 *  field's basis and growth are both its weight, so a line of fields divides
 *  the width in proportion and the leftover in the same proportion. Rows of
 *  one repeating group all have the same shape, so they all divide it the
 *  same way: the second medicine's dose sits under the first medicine's
 *  dose, which a grid of equal columns also did, and which a grid of equal
 *  columns was the only thing doing right.
 */

/** The narrowest a weighted field may be before the line wraps instead. One
 *  weight is about one and a half characters of the 14px field font, so a
 *  weight-2 numeric box holds four digits at its smallest. */
export const UNIT = 19;

/** What one weight is worth in characters, for the standalone fields that
 *  are not in a row and so have a ceiling rather than a share. */
export const CH = 4;

const WIDEST = 12;

/** A closed list is as wide as the longest thing it can say. Measured in
 *  characters of the display, because the display is what is drawn; the code
 *  underneath may be nine digits of SNOMED and is never seen. */
export function choiceWeight(longest: number): number {
  if (longest <= 10) return 3;
  if (longest <= 18) return 4;
  if (longest <= 28) return 6;
  // The longest closed list there is. Still short of prose: a picker shows
  // one line of one option, however long the list's longest name, and the
  // only control that earns the whole width of a form is one somebody is
  // going to write sentences in.
  return 10;
}

/** The weight of one question. `displays` is every option label this question
 *  can show, which the caller reads off the terminology; an unbound or
 *  inline-listed choice hands over what it declared.
 */
export function weightFor(type: string, displays: string[] = []): number {
  switch (type) {
    // A measurement, a dose, a count. Four characters covers every one of
    // them in this bundle and the field still grows with the line.
    case "integer":
    case "decimal":
      return 2;
    case "boolean":
      return 3;
    // A DATE BOX IS NOT A THREE-CHARACTER BOX. The browser's own control
    // draws the whole of "16/10/2026" and a calendar button beside it, and
    // at weight 3 (12 characters of ceiling, less the field's own padding)
    // the year was cut off: the form asked for a date and showed "16/10/20".
    case "date":
      return 5;
    case "choice":
      return choiceWeight(displays.reduce((n, d) => Math.max(n, d.length), 0));
    // Prose. A note, a complaint, a reason. It is the line.
    case "text":
      return WIDEST;
    // A string: a name, an address, an identifier. Half a line, so two of
    // them share one.
    default:
      return 6;
  }
}

/** The ceiling for a field that stands alone rather than in a row. A
 *  standalone number used to stretch the full 760px of the panel, which read
 *  as an invitation to write a sentence in it. In a row the weight is a
 *  share of the line; here there is no line to share, so it is a maximum and
 *  the field is free to be narrower.
 *
 *  Prose and the widest choices get no ceiling: `null` means the full width.
 */
export function capFor(weight: number): number | null {
  return weight >= WIDEST ? null : weight * CH;
}
