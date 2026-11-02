/** Turning a declaration id into words, and nothing more.
 *
 *  Its own file because it is pure and has no React in it: messages.check.ts
 *  runs under plain node, and ui.tsx cannot be loaded there. ui.tsx re-exports
 *  both, so every existing import still reads `from "./ui"`.
 */

/** Words that are LETTERS, not words, and must never be sentence cased.
 *
 *  A screen that says "Abha pending" and "Ncd" is a screen that has not read
 *  what it is printing. Every one of these is a name in India's health
 *  system or a unit a clinician reads a hundred times a day, and getting the
 *  case wrong is the first thing a doctor notices and the last thing they
 *  forgive.
 *
 *  They are here, in the one function that cases a word, and not sprinkled
 *  through the screens: `title()` and `human()` are what every label goes
 *  through, so the list only has to be right once. It is about SPELLING, not
 *  about meaning -- nothing here decides what a screen shows, only how the
 *  letters are set, which is why it is not a declaration.
 */
const ACRONYMS = new Set([
  // the national programme and its registries
  "abha", "abdm", "abc", "hpr", "hfr", "phr", "nhpr",
  // who works where
  "asha", "anm", "mo", "cho", "phc", "chc", "hwc", "ui",
  // what gets recorded
  "ncd", "rch", "anc", "pnc", "tb", "hiv", "ors", "bmi", "bp", "lmp", "edd",
  "cbc", "kft", "lft", "ecg", "usg", "ot", "opd", "ipd", "id", "qr", "otp",
  // units and codes
  "spo2", "hb", "ml", "mg", "kg", "cm", "fhir", "loinc", "snomed", "icd",
]);

/** How a single word is set: an acronym in capitals, anything else left as
 *  it came. SpO2 is the one that is neither, and it is spelled out. */
const SHAPED: Record<string, string> = { spo2: "SpO2", hiv: "HIV", mo: "MO" };

const word = (w: string) => {
  const key = w.toLowerCase();
  if (!ACRONYMS.has(key)) return w;
  return SHAPED[key] ?? key.toUpperCase();
};

/** Declaration ids are machine names. Nothing but the declaration knows a
 *  human label, so when one is missing this is the least-worst fallback. */
export const human = (id: string | null | undefined) =>
  (id ?? "")
    .replace(/^[a-z0-9]+\.(op|view|wf|inst|metric|schema)\./, "")
    .replace(/[-_.]/g, " ")
    .replace(/[^\s]+/g, word);

/** Same, for somewhere a label starts a line. The first word is capitalised
 *  unless it is an acronym, which `human` has already set in capitals. */
export const title = (id: string | null | undefined) => {
  const s = human(id);
  const first = s.split(" ")[0] ?? "";
  if (first && ACRONYMS.has(first.toLowerCase())) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
};
