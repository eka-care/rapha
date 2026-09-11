/** What one row of a structured answer is made of.
 *
 *  A structured question (`medications`, `investigations`, `dispenses`,
 *  `diagnosis`) has no sub schema in the questionnaire, which is why the form
 *  used to draw one free text box per row and the cards read the answer back
 *  as a run-on string. bundles/LAB-LOG.md 13 records that gap.
 *
 *  The sub fields are declared, though, one layer up: the operation atom's
 *  `mapping` says `per_item: medications` and then `medication: {item: [...]}`,
 *  and kernel/mapping.py reads exactly those keys off each item. So the
 *  columns that will be written are the fields to offer, and the first name in
 *  each alias list is the one the kernel looks for first.
 *
 *  Nothing here names an operation, a resource or a bundle. An operation whose
 *  atom declares no mapping for that question gets an empty list back, and the
 *  form falls to the free text row it always drew, which kernel/mapping.py
 *  still reads as `{code: <it>}`.
 *
 *  Pure. messages.check.ts asserts it against the compiled catalogue.
 */
import type { MappingRecord, Operation } from "./types";
import { title } from "./words.ts";

export type ItemField = { key: string; label: string; resource: string };

/** The sources that read a key off an item, in kernel/mapping.py's grammar.
 *  `minus` is `item` with the sign flipped on the way to the store, which is
 *  the adapter's business and not a different question to ask. */
const ITEM_SOURCES = ["item", "minus"];

export function itemFields(op: Operation | undefined, link_id: string): ItemField[] {
  const out: ItemField[] = [];
  const seen = new Set<string>();
  for (const record of (op?.mapping ?? []) as MappingRecord[]) {
    if (record.per_item !== link_id) continue;
    for (const source of Object.values(record.fields ?? {})) {
      for (const kind of ITEM_SOURCES) {
        const keys = source?.[kind];
        if (!Array.isArray(keys) || !keys.length) continue;
        const key = String(keys[0]);
        if (seen.has(key)) break;
        seen.add(key);
        out.push({ key, label: title(key), resource: record.resource });
        break;
      }
    }
  }
  return out;
}

/** One row as the fields the mapping named. A row that came back from the
 *  kernel as a bare string keeps its text under the first field, because that
 *  is where kernel/mapping.py would have looked for it. */
export function toRow(value: unknown, fields: ItemField[]): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  const text = value === undefined || value === null ? "" : String(value);
  return fields.length ? { [fields[0].key]: text } : { code: text };
}

/** True when nothing has been typed into any of this row's fields. An empty
 *  row is not sent: an empty medication_request is a row that says nothing. */
export const blankRow = (row: Record<string, unknown>): boolean =>
  Object.values(row).every((v) => v === undefined || v === null || String(v).trim() === "");
