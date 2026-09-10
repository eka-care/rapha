/**
 * The constrained voice grammar. Spoken words in, a typed number out, or nothing.
 *
 * This is not dictation. Ambient speech recognition is worst exactly where it
 * matters most: "one forty over ninety" misheard as "one fourteen over ninety"
 * is silent, plausible and unrecoverable. So the grammar here is bounded on
 * purpose. It recognises a small number of shapes and refuses everything else,
 * because a refusal falls back to the keypad and a guess does not fall back
 * to anything.
 *
 * Two rules follow from that and are not negotiable:
 *   - a phrase with more than one plausible reading is rejected, never guessed.
 *   - a value outside the questionnaire's physiological range is rejected here.
 *     An out of range reading is real sometimes, and then it is typed, because
 *     catalogue/validate.py demands an override reason for it and a voice
 *     capture cannot supply one.
 *
 * Nothing in this file writes anything. It is pure, which is why the check in
 * grammar.check.ts can run it with no browser.
 */

export type FieldSpec = {
  linkId: string;
  type: "integer" | "decimal";
  /** spoken names, lowercase. One or two words each. */
  aliases: string[];
  /** UCUM unit from the questionnaire, e.g. "mm[Hg]", "kg". */
  unit?: string;
  /** physiological range from the questionnaire. Outside it we refuse. */
  range?: { low: number; high: number };
  /** the field a following "over" belongs to: systolic pairs with diastolic. */
  pairsWith?: string;
};

export type Parsed =
  | { ok: true; values: Record<string, number>; confidence: Record<string, number> }
  | { ok: false; reason: string };

/** An explicit reading, e.g. "one hundred forty". Below 0.9 on purpose: every
 *  voice value is highlighted for re-reading, there is no trusted tier. */
const EXPLICIT = 0.85;
/** A colloquial compound, e.g. "one forty". Understood, but the exact shape
 *  the spec warns about, so it reads back louder. */
const COMPOUND = 0.65;

const ONES: Record<string, number> = {
  zero: 0, oh: 0, o: 0, nought: 0, one: 1, two: 2, three: 3, four: 4,
  five: 5, six: 6, seven: 7, eight: 8, nine: 9,
};
const TEENS: Record<string, number> = {
  ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
};
const TENS: Record<string, number> = {
  twenty: 20, thirty: 30, forty: 40, fourty: 40, fifty: 50, sixty: 60,
  seventy: 70, eighty: 80, ninety: 90,
};
/** Spoken unit words to the UCUM unit the questionnaire uses. A word that maps
 *  to a different unit than the field's is a mismatch and is refused, never
 *  converted: nobody wants a silent pounds to kilograms in a vitals record. */
const UNITS: Record<string, string> = {
  kilo: "kg", kilos: "kg", kilogram: "kg", kilograms: "kg", kg: "kg", kgs: "kg",
  pound: "[lb_av]", pounds: "[lb_av]", lbs: "[lb_av]",
  degree: "Cel", degrees: "Cel", celsius: "Cel", centigrade: "Cel",
  fahrenheit: "[degF]",
  percent: "%",
  millimetres: "mm[Hg]", millimeters: "mm[Hg]", mercury: "mm[Hg]",
  beats: "/min", bpm: "/min",
};
/** Dropped before parsing. Deliberately short: an unknown word inside a number
 *  phrase is a parse failure, and that is the safe outcome. */
const FILLER = new Set([
  "uh", "um", "er", "the", "a", "is", "was", "its", "it's", "at", "of", "and",
  "please", "patient", "patients", "her", "his", "their", "reading", "value",
  "per", "minute", "mm", "hg",
]);

export function tokens(transcript: string): string[] {
  return transcript
    .toLowerCase()
    .replace(/(\d)\s*\/\s*(\d)/g, "$1 over $2")   // "140/90"
    .replace(/[^a-z0-9./]+/g, " ")
    .split(" ")
    .filter((t) => t.length > 0 && !FILLER.has(t));
}

/** A pure number phrase to a value. Returns null when the phrase has no single
 *  reading, which is the point of the whole module. */
export function parseNumberPhrase(
  words: string[],
): { value: number; confidence: number } | null {
  if (words.length === 0) return null;
  if (words.length === 1 && /^\d+\.\d+$/.test(words[0])) {
    return { value: Number(words[0]), confidence: EXPLICIT };
  }

  const at = words.indexOf("point");
  if (at !== -1) {
    const whole = parseInteger(words.slice(0, at));
    const digits = words.slice(at + 1);
    if (!whole || digits.length === 0) return null;
    let frac = "";
    for (const w of digits) {
      if (/^\d+$/.test(w)) frac += w;
      else if (w in ONES) frac += String(ONES[w]);
      else return null;              // "point twenty five" has two readings
    }
    return { value: Number(`${whole.value}.${frac}`), confidence: whole.confidence };
  }
  return parseInteger(words);
}

function parseInteger(words: string[]): { value: number; confidence: number } | null {
  const n = words.length;
  if (n === 0) return null;

  // Digits as spoken by the recogniser, e.g. "140".
  if (n === 1 && /^\d+$/.test(words[0])) {
    return { value: Number(words[0]), confidence: EXPLICIT };
  }

  const small = under100(words);
  if (small !== null) return { value: small, confidence: EXPLICIT };

  // "one hundred forty", "two hundred"
  if (n >= 2 && words[1] === "hundred" && words[0] in ONES) {
    const rest = n === 2 ? 0 : under100(words.slice(2));
    if (rest === null) return null;
    return { value: ONES[words[0]] * 100 + rest, confidence: EXPLICIT };
  }

  // The colloquial compound: "one forty", "one forty five", "one fourteen",
  // "one oh five". Only a leading 1 to 9 followed by something under 100, so
  // "sixty two five" has no reading and is refused rather than resolved.
  if (n >= 2 && words[0] in ONES && ONES[words[0]] > 0) {
    const rest = under100(words.slice(1));
    if (rest !== null && rest >= 10) {
      return { value: ONES[words[0]] * 100 + rest, confidence: COMPOUND };
    }
    // "one oh five": the zero word is what disambiguates it.
    if (n === 3 && words[1] in ONES && ONES[words[1]] === 0 && words[2] in ONES) {
      return { value: ONES[words[0]] * 100 + ONES[words[2]], confidence: COMPOUND };
    }
  }
  return null;
}

/** 0 to 99 in the four shapes people actually say. null means no single reading. */
function under100(words: string[]): number | null {
  if (words.length === 1) {
    const w = words[0];
    if (/^\d+$/.test(w) && Number(w) < 100) return Number(w);
    if (w in TEENS) return TEENS[w];
    if (w in TENS) return TENS[w];
    if (w in ONES) return ONES[w];
    return null;
  }
  if (words.length === 2 && words[0] in TENS && words[1] in ONES && ONES[words[1]] > 0) {
    return TENS[words[0]] + ONES[words[1]];
  }
  return null;
}

type Slot = { field: FieldSpec; words: string[]; unit?: string };

/**
 * Parse a whole utterance against the fields on screen.
 *
 * fields is what the renderer is showing. When it holds exactly one field the
 * speaker may leave it unnamed ("one forty" into the systolic box). When it
 * holds several, an unnamed number is ambiguous and is refused.
 */
export function parse(transcript: string, fields: FieldSpec[]): Parsed {
  const words = tokens(transcript);
  if (words.length === 0) return { ok: false, reason: "nothing was heard" };

  const byAlias = new Map<string, FieldSpec>();
  for (const f of fields) {
    for (const a of [f.linkId, ...f.aliases]) byAlias.set(a.toLowerCase(), f);
  }
  const byId = new Map(fields.map((f) => [f.linkId, f]));

  const slots: Slot[] = [];
  let current: FieldSpec | undefined = fields.length === 1 ? fields[0] : undefined;
  let pending: string[] = [];
  let unit: string | undefined;

  const flush = (): string | null => {
    if (pending.length === 0) return null;
    if (!current) return `heard "${pending.join(" ")}" but not which field it is for`;
    slots.push({ field: current, words: pending, unit });
    pending = [];
    unit = undefined;
    return null;
  };

  for (let i = 0; i < words.length; i++) {
    // Longest alias first, so "systolic bp" beats "bp".
    let matched: FieldSpec | undefined;
    let width = 0;
    for (const w of [3, 2, 1]) {
      const phrase = words.slice(i, i + w).join(" ");
      const f = byAlias.get(phrase);
      if (f) {
        matched = f;
        width = w;
        break;
      }
    }
    if (matched) {
      const err = flush();
      if (err) return { ok: false, reason: err };
      current = matched;
      i += width - 1;
      continue;
    }

    const word = words[i];
    if (word === "over" || word === "on") {
      const pair = current?.pairsWith;
      const err = flush();
      if (err) return { ok: false, reason: err };
      if (!pair || !byId.has(pair)) {
        return { ok: false, reason: `"over" does not apply to this field` };
      }
      current = byId.get(pair);
      continue;
    }
    if (word in UNITS) {
      unit = UNITS[word];
      continue;
    }
    pending.push(word);
  }
  const err = flush();
  if (err) return { ok: false, reason: err };
  if (slots.length === 0) return { ok: false, reason: "no number was heard" };

  const values: Record<string, number> = {};
  const confidence: Record<string, number> = {};
  for (const slot of slots) {
    const id = slot.field.linkId;
    if (id in values) {
      return { ok: false, reason: `heard two values for ${id}; say one at a time` };
    }
    const got = parseNumberPhrase(slot.words);
    if (!got) {
      return { ok: false, reason: `could not read "${slot.words.join(" ")}" as one number` };
    }
    if (slot.unit && slot.field.unit && slot.unit !== slot.field.unit) {
      return {
        ok: false,
        reason: `${id} is recorded in ${slot.field.unit}, not what was said`,
      };
    }
    if (slot.field.type === "integer" && !Number.isInteger(got.value)) {
      return { ok: false, reason: `${id} is a whole number` };
    }
    const r = slot.field.range;
    if (r && (got.value < r.low || got.value > r.high)) {
      // Real, but it needs an override reason, and a microphone cannot give one.
      return {
        ok: false,
        reason: `heard ${got.value} for ${id}, outside ${r.low} to ${r.high}. Use the keypad.`,
      };
    }
    values[id] = got.value;
    confidence[id] = got.confidence;
  }
  return { ok: true, values, confidence };
}

/** Extra spoken names the questionnaire text does not contain. */
const SPOKEN: Record<string, string[]> = {
  systolic: ["systolic", "bp", "b p", "blood pressure", "pressure", "upper"],
  diastolic: ["diastolic", "lower"],
  pulse: ["pulse", "heart rate", "hr"],
  spo2: ["spo2", "sats", "saturation", "oxygen"],
  weight: ["weight", "wt"],
  temperature: ["temperature", "temp", "fever"],
};

type Question = {
  link_id: string;
  text: string;
  type: string;
  styling_metadata?: { phc?: { unit?: string; range?: { low: number; high: number } } };
};

/**
 * Build the field specs from the CARE questionnaire the operation names, so
 * the ranges and units have one definition and it is not this file. Only
 * integer and decimal questions come back: those are the discrete values voice
 * is allowed near.
 */
export function fieldsFrom(schema: { questions: Question[] }): FieldSpec[] {
  const fields: FieldSpec[] = [];
  for (const q of schema.questions) {
    if (q.type !== "integer" && q.type !== "decimal") continue;
    const phc = q.styling_metadata?.phc ?? {};
    const aliases = new Set(SPOKEN[q.link_id] ?? []);
    aliases.add(q.text.toLowerCase());
    fields.push({
      linkId: q.link_id,
      type: q.type,
      aliases: [...aliases],
      unit: phc.unit,
      range: phc.range,
      pairsWith: q.link_id === "systolic" ? "diastolic" : undefined,
    });
  }
  return fields;
}
