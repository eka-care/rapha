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

/** A VALUE off a row, spelled but not reshaped.
 *
 *  `human` is for an id and does two things to get there: it strips a
 *  declaration's prefix and turns separators into spaces. On a value that
 *  is ruinous -- an encounter called "enc-002" comes out as "enc 002" --
 *  so this does only the half that is always safe, which is setting a word
 *  that is an acronym in capitals. "anc" becomes ANC; a name, a village, a
 *  phone number and an id all come back exactly as they went in.
 */
export const spell = (v: string | null | undefined) =>
  (v ?? "").replace(/[^\s]+/g, (w) => (ACRONYMS.has(w.toLowerCase()) ? word(w) : w));

/** A SENTENCE the kernel composed, set so it starts like one.
 *
 *  `title` is for an id: it strips a declaration's prefix and turns its
 *  separators into spaces, which is right for "phc.op.record-vitals" and
 *  wrong for a line of prose that happens to begin with a station's name.
 *  This touches the first letter and nothing else, and leaves an acronym
 *  alone because ABHA does not become Abha.
 */
export const sentence = (s: string | null | undefined) => {
  const t = (s ?? "").trim();
  const first = t.split(/[\s:]/)[0] ?? "";
  if (!t || ACRONYMS.has(first.toLowerCase())) return t;
  // A SYMBOL SOMEBODY CASED ON PURPOSE. The list above holds the letters
  // this product knows by name; a unit the terminology sent carries its case
  // in itself, and a capital anywhere after the first letter of the first
  // word is how it says so. mmHg is not MmHg, mL is not ML, pH is not PH,
  // and a clinician notices that before they notice anything else.
  if (/^[a-z][a-zA-Z]*[A-Z]/.test(first)) return t;
  return t.charAt(0).toUpperCase() + t.slice(1);
};

/** Which glyph stands for a role, by the same licence as the casing table
 *  above: this decides how a declared word is DRAWN, never which words
 *  appear. Delete a role from the bundle and nothing on any screen changes;
 *  the entry simply stops being reached, exactly as "asha" does.
 *
 *  A role list set in one typeface and no picture is a list nobody scans.
 *  The glyph is the part a person recognises before they have read anything,
 *  which at a centre where English is a second language is most of the work
 *  the label was supposed to do. Anything unlisted falls back to a person,
 *  which is what every role is.
 */
const ROLE_GLYPH: Record<string, string> = {
  // who sees the patient
  mo: "clip", cho: "clip", doctor: "clip",
  nurse: "vitals", anm: "vitals",
  // who works the bench
  lab: "box", "lab-incharge": "box", "lab incharge": "box",
  pharmacist: "box", pharmacy: "box",
  // who meets them at the door, and who goes to them
  frontdesk: "id", reception: "id", registration: "id",
  asha: "users", community: "users",
  // who is only looking
  demo: "eye", admin: "cog", observer: "eye",
};

/** The glyph for a role id, as an `IconName`. Typed as a string here because
 *  this file is loaded by checks that run under plain node, where a .tsx
 *  import cannot follow; the caller narrows it. */
export const roleGlyph = (id: string | null | undefined): string =>
  ROLE_GLYPH[(id ?? "").toLowerCase().replace(/[_.]/g, "-")] ?? "user";

/** What a patient is called before anybody has asked. One word for it, used by
 *  the line, the home screen and the search, so three screens cannot disagree. */
export const NO_NAME = "No name yet";
