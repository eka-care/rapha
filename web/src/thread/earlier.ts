/** What this patient's earlier visits say about today's, in three shapes.
 *
 *  All three come from the artifact this screen is built from: a carry
 *  forward strip under the name, a trend in the right rail, and the people
 *  who have actually been near this visit. Pure, so `earlier.check.ts` runs them
 *  under plain node with no browser and no kernel.
 *
 *  NOTHING HERE NAMES A FIELD. The artifact's strip names a blood pressure
 *  and a weight, because it was a drawing. This cannot: which values carry is
 *  decided by which values both visits recorded, in the order the
 *  questionnaire declared them, and a bundle with no blood pressure in it
 *  gets a strip of whatever it does record. The one clinical judgement on
 *  screen -- that a value is out of range -- is the kernel's `crit`, which
 *  the questionnaire's own range decided.
 */
import { wrote } from "../types.ts";
import type { Kv } from "../messages";

/** One visit, reduced to the values it committed. */
export type Visit = { thread: string; when: string; values: Kv[] };

/** One line of the carry forward strip: the same question, twice. */
export type Carried = {
  link_id: string;
  label: string;
  then: string;
  now: string;
  /** The kernel flagged today's value outside the declared range. */
  crit: boolean;
};

/** How many fit on the strip before it stops being a glance. Four columns at
 *  238px each is the artifact's own shape, and a fifth wraps to a second row
 *  that reads as a second thing. */
export const STRIP = 4;

/** The values this visit recorded that the visit before it also recorded.
 *
 *  Both directions matter. A value only today has nothing to carry and the
 *  field itself is on the thread; a value only last time is not what this
 *  visit is about. What is left is the comparison a clinician makes in their
 *  head on every follow up.
 */
export function carriedForward(now: Visit | null, before: Visit | null): Carried[] {
  if (!now || !before) return [];
  const then = new Map(before.values.map((v) => [v.link_id, v]));
  const out: Carried[] = [];
  for (const v of now.values) {
    const was = then.get(v.link_id);
    if (!was || was.value === "" || v.value === "") continue;
    // ONLY WHAT CHANGED. This strip is an arrow between two visits, and an
    // arrow from a value to itself says nothing: a returning patient's
    // header read "sam -> sam, 28 -> 28, male -> male" above the record,
    // which is four rows of furniture over the one row that moved. A name
    // and a sex do not change between Tuesday and Friday; a blood pressure
    // does, and that is the only thing worth an arrow.
    if (was.value === v.value) continue;
    out.push({ link_id: v.link_id, label: v.label, then: trim(was.value, v.value),
               now: v.value, crit: v.crit });
  }
  return out.slice(0, STRIP);
}

/** The earlier value without the unit the later one already carries.
 *
 *  "148 mm[Hg] → 186 mm[Hg]" says the unit twice in six words. Only an
 *  identical trailing word goes, so a value whose unit CHANGED between visits
 *  keeps both, which is the one case where saying it twice is the point.
 */
function trim(then: string, now: string): string {
  const unit = /\s\S+$/.exec(now)?.[0];
  return unit && then.endsWith(unit) ? then.slice(0, -unit.length) : then;
}

/** The first value worth drawing a line through: one that is a number on
 *  every visit that recorded it, and that at least two visits recorded.
 *
 *  Declared order decides, not this file's opinion of which vital matters.
 */
export function trendable(visits: Visit[]): string | null {
  const counts = new Map<string, number>();
  const order: string[] = [];
  for (const visit of visits) {
    for (const v of visit.values) {
      if (number(v.value) === null) continue;
      if (!counts.has(v.link_id)) order.push(v.link_id);
      counts.set(v.link_id, (counts.get(v.link_id) ?? 0) + 1);
    }
  }
  return order.find((id) => (counts.get(id) ?? 0) >= 2) ?? null;
}

export type Point = { when: string; value: number; crit: boolean };

/** That value across the visits, oldest first. A visit that did not record it
 *  is absent rather than zero: a gap in a line is a visit, and a zero is a
 *  reading nobody took. */
export function series(visits: Visit[], linkId: string): Point[] {
  const out: Point[] = [];
  for (const visit of visits) {
    const v = visit.values.find((x) => x.link_id === linkId);
    const n = v ? number(v.value) : null;
    if (n !== null) out.push({ when: visit.when, value: n, crit: v!.crit });
  }
  return out;
}

/** The bar heights for a sparkline, 0 to 1, so the lowest reading is still a
 *  bar and not a gap. One reading is a full bar: there is no range to show. */
export function heights(points: Point[]): number[] {
  const values = points.map((p) => p.value);
  const low = Math.min(...values), high = Math.max(...values);
  const span = high - low;
  // A floor, not a scale from zero: the lowest reading is still a reading and
  // a two millimetre stub reads as missing data rather than as a low number.
  return points.map((p) => (span === 0 ? 1 : 0.38 + ((p.value - low) / span) * 0.62));
}

/** A number out of a drawn value. The value carries its unit, because the
 *  thread draws it to be read ("138 mm[Hg]"), so the digits are taken off the
 *  front and anything that does not start with digits is not a number. */
function number(value: string): number | null {
  const hit = /^-?\d+(\.\d+)?/.exec(String(value).trim());
  if (!hit) return null;
  const n = Number(hit[0]);
  return Number.isFinite(n) ? n : null;
}

export type Member = { actor: string; role: string; did: string };

/** Who has been near this visit, in the order they arrived.
 *
 *  The artifact draws the ASHA and the ANM who cover the patient's
 *  habitation. NOTHING IN THIS PRODUCT DECLARES THAT: a catchment mapping a
 *  village to a named worker is a declaration nobody has written, and a card
 *  naming a health worker who may not exist is worse than no card. So this
 *  draws the people who are actually on the record, which is the half of that
 *  idea the kernel can prove.
 */
export function team(
  audit: { actor: string | null; outcome: string; operation: string }[],
  titleOf: (operation: string) => string,
  roleOf: (actor: string) => string,
): Member[] {
  const seen = new Map<string, Member>();
  for (const row of audit) {
    if (!row.actor || !wrote(row.outcome)) continue;
    const actor = row.actor.replace(/^user:/, "");
    if (!seen.has(actor))
      seen.set(actor, { actor, role: roleOf(row.actor), did: titleOf(row.operation) });
  }
  return [...seen.values()];
}

// ---------------------------------------------------------------- catchment

/** A centre's own declaration of who covers which habitation. */
export type Catchment = {
  /** Which of the subject's columns names the habitation. */
  column: string;
  areas: { area: string; anm: string; villages: Record<string, string> }[];
};

export type Covers = { area: string; anm: string; asha: string; village: string };

/** Who covers this patient, from the village already on their record.
 *
 *  THE SCREEN IS TOLD THE COLUMN AND NOTHING ELSE. It does not know what a
 *  sub-centre is, that an ANM runs one, or that an ASHA covers a habitation
 *  within it: it looks a value up in the centre's own declaration and draws
 *  what comes back. A centre that declares no catchment has none here, and a
 *  village nobody declared is not guessed at.
 *
 *  An empty `asha` is a real answer and is kept: a habitation with nobody
 *  assigned is the thing worth seeing, and dropping the row would hide it.
 */
export function covers(catchment: Catchment | null | undefined,
                       subject: Record<string, unknown> | undefined): Covers | null {
  if (!catchment?.column) return null;
  const village = String(subject?.[catchment.column] ?? "").trim();
  if (!village) return null;
  for (const area of catchment.areas ?? []) {
    if (village in (area.villages ?? {}))
      return { area: area.area, anm: area.anm, asha: area.villages[village], village };
  }
  return null;
}
