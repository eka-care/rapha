/** WHEN A LIST NEEDS A SEARCH BOX, decided from the list and nothing else.
 *
 *  shadcn draws a closed choice two ways and the difference is not
 *  decoration. A short list of short words is a menu: you open it, you see
 *  all of it, you pick. A long list, or a list of long names, is a thing you
 *  have to hunt through, and hunting by eye down eleven lines of "Glucose
 *  [Mass/volume] in Capillary blood by Glucometer" is slower and more
 *  error-prone than typing four letters.
 *
 *  The rule is here, pure and checked, rather than in a component, because it
 *  is a judgement about the data and the data is declared. Nothing below
 *  knows what any particular list holds.
 */

/** More options than a person takes in at a glance. */
export const MANY = 8;

/** Longer than a glance can tell two entries apart by their beginnings. The
 *  same number form/span.ts uses to decide a picker is a wide one, and for
 *  the same reason: past it, the name is a phrase rather than a word. */
export const LONG = 28;

/** Whether this list is hunted through rather than read. */
export function needsSearch(displays: string[]): boolean {
  if (displays.length > MANY) return true;
  return displays.some((d) => d.length > LONG);
}

/** Which options survive what has been typed into the search box.
 *
 *  Every word of the query has to appear somewhere in the option, in any
 *  order, anywhere in the string -- not as a prefix. A clinician looking for
 *  capillary glucose types "glucose capillary", and the option is called
 *  "Glucose [Mass/volume] in Capillary blood by Glucometer": a prefix match
 *  finds it, a both-words match finds it, and the order they thought of them
 *  in is not something to hold against them.
 */
export function matches(displays: { value: string; display: string }[], query: string) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return displays;
  return displays.filter((o) => {
    const hay = o.display.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}
