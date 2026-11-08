/** The prototype's icon sheet, and the one helper that draws from it.
 *
 *  Copied verbatim from the <symbol> block of agentic-emr-prototype.html, less
 *  the station glyphs (desk, nurse, lab, pill): a station is a bundle's word,
 *  so drawing one would put the PHC in the renderer. A station is drawn with
 *  its own first letter instead.
 *
 *  Which icon an action gets is decided by its declared instrument. Nothing
 *  here is keyed to a view: iconForView is gone (Vernier's sidebar spec,
 *  "zero glyphs in navigation" -- two of its four nav icons resolved to the
 *  same #i-list glyph and a 13px label is a faster, unambiguous discriminator
 *  anyway), and #i-flask went with it, unused everywhere else.
 */
import type { Operation } from "./types";

export type IconName =
  "sliders" | "mark" | "mark-lg" | "search" | "home" | "moon" | "sun" | "vitals" | "mic" | "box" | "clip" | "eye" | "plus" | "folder" | "chat" | "spark" | "check" | "alert" | "lock" | "send" | "user" | "users" | "list" | "cog" | "refer" | "chev" | "id" | "doc" |
  "handle" | "out" | "clock" | "bell" | "sidebar" | "ticket";

export function Icon({ name, size, className }: {
  name: IconName; size?: "sm" | "lg"; className?: string;
}) {
  return (
    <svg className={className ?? `i${size ? ` ${size}` : ""}`} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

/** One sheet, mounted once at the root. `<use>` needs the symbols in the
 *  document, not in a component that unmounts. */
export function IconSheet() {
  return (
    <svg style={{ display: "none" }} aria-hidden="true" dangerouslySetInnerHTML={{ __html: SHEET }} />
  );
}

/** An instrument names how a value is captured, so it is what the pill should
 *  say. `device` and `constrained-voice` borrow the form icon: they are all a
 *  field being filled in, and only the scribe is a different act. The name
 *  must be a catalogue/vocab.py INSTRUMENTS entry, which is what
 *  scripts/check_instruments.py asserts: this read `"voice"` for a while, a
 *  value no operation can declare, so the branch could never be taken. */
export function iconFor(op: Operation): IconName {
  if (op.irreversibility === "irreversible") return "lock";
  if (op.instrument === "scribe") return "mic";
  if (op.instrument === "constrained-voice" || op.instrument === "device") return "vitals";
  return "clip";
}

const SHEET = `
  <style>
    #i-mark path, #i-mark circle, #i-mark-lg path, #i-mark-lg circle {
      fill: none; stroke: currentColor; vector-effect: non-scaling-stroke;
    }
  </style>
  <symbol id="i-mark" viewBox="0 0 24 24"><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(0 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(60 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(120 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(180 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(240 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(300 12 12)"/><circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="1.9" opacity=".5"/></symbol>
  <symbol id="i-mark-lg" viewBox="0 0 24 24"><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(0 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(60 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(120 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(180 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(240 12 12)"/><path d="M12 8.3C10.3 7.6 9.6 5.7 9.6 4C9.6 2.3 10.7 1.2 12 1.1C13.3 1.2 14.4 2.3 14.4 4C14.4 5.7 13.7 7.6 12 8.3Z" transform="rotate(300 12 12)"/><circle cx="12" cy="12" r="3.5"/><circle cx="12" cy="12" r="2.2" opacity=".6"/><circle cx="12" cy="12" r="0.9" opacity=".4"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
  <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5h4v5"/></symbol>
  <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></symbol>
  <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></symbol>
  <symbol id="i-vitals" viewBox="0 0 24 24"><path d="M2.5 12h4l2-5 3.5 10 2.5-7 1.5 2h5.5"/></symbol>
  <symbol id="i-sliders" viewBox="0 0 24 24"><path d="M4 7h7M15 7h5M4 17h3M11 17h9"/><circle cx="13" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></symbol>
  <symbol id="i-mic" viewBox="0 0 24 24"><rect x="9" y="2.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5M9 21.5h6"/></symbol>
  <symbol id="i-box" viewBox="0 0 24 24"><path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/></symbol>
  <symbol id="i-clip" viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4.5a3 3 0 0 1 6 0"/><path d="M9 11h6M9 15h4"/></symbol>
  <symbol id="i-eye" viewBox="0 0 24 24"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
  <symbol id="i-folder" viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></symbol>
  <symbol id="i-chat" viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-8 8H8l-5 2 1.5-4.2A8 8 0 1 1 21 12z"/></symbol>
  <symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3.5 13.8 9l5.7 1.8-5.7 1.8L12 18.2l-1.8-5.6-5.7-1.8L10.2 9z"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="m4 12.5 5 5L20 6.5"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M12 3.5 22 20H2z"/><path d="M12 10v4M12 17h.01"/></symbol>
  <symbol id="i-lock" viewBox="0 0 24 24"><rect x="4.5" y="10" width="15" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></symbol>
  <symbol id="i-send" viewBox="0 0 24 24"><path d="M12 19.5V5M5.5 11.5 12 5l6.5 6.5"/></symbol>
  <symbol id="i-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.6"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/></symbol>
  <symbol id="i-users" viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 5.5a3.2 3.2 0 0 1 0 6M17.5 14.5a6 6 0 0 1 4 5.5"/></symbol>
  <symbol id="i-list" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></symbol>
  <symbol id="i-cog" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.9 19.4l-.1.1A2 2 0 1 1 5 16.7l.1-.1A1.6 1.6 0 0 0 3.9 14H3.8a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7L5 7.2A2 2 0 1 1 7.8 4.4l.1.1A1.6 1.6 0 0 0 10.6 3.4V3.3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1A2 2 0 1 1 20.2 7.2l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.1a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/></symbol>
  <symbol id="i-refer" viewBox="0 0 24 24"><path d="M4 12h13M12 6l6 6-6 6"/></symbol>
  <symbol id="i-chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
  <symbol id="i-id" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><circle cx="8.5" cy="11" r="2.2"/><path d="M5.2 16.2c.8-1.4 2-2 3.3-2s2.5.6 3.3 2M15 10h4M15 14h3"/></symbol>
  <symbol id="i-doc" viewBox="0 0 24 24"><circle cx="12" cy="7" r="3.4"/><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2"/><path d="M12 15.5v3M10.5 17h3"/></symbol>
  <!-- The card-reorder handle's glyph (spec: "two 12px horizontal rules 4px
       apart -- the plate's own seam repeated, not a stock six-dot grip"). -->
  <symbol id="i-handle" viewBox="0 0 24 24"><path d="M4 9h16M4 15h16"/></symbol>
  <!-- The way out: a door left open and an arrow leaving through it. Drawn
       rather than borrowed so its stroke matches the sheet. -->
  <symbol id="i-out" viewBox="0 0 24 24"><path d="M15 4.5h3.5a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H15"/><path d="M10 8l-4 4 4 4M6 12h9"/></symbol>
  <!-- A panel beside the page, shown as the page with one edge filled. The
       control that opens and closes a column should look like the column,
       not like an arrow: an arrow says "go", and this goes nowhere. -->
  <!-- The token: an admission ticket, outlined, with a notch cut into each end and a dotted perforation. -->
  <symbol id="i-ticket" viewBox="0 0 24 24"><path d="M4 6h16a2 2 0 0 1 2 2v2.1a1.9 1.9 0 0 0 0 3.8V16a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-2.1a1.9 1.9 0 0 0 0-3.8V8a2 2 0 0 1 2-2z"/><path d="M9 7.5v9" stroke-dasharray="1.4 2.1"/></symbol>
  <symbol id="i-sidebar" viewBox="0 0 24 24"><rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M15 4.5v15"/></symbol>
  <!-- What is waiting for somebody, in the one place a person already looks
       for that. Drawn rather than borrowed so its stroke matches the sheet:
       a plain bell, no clapper swing and no notification dot baked in -- the
       count is a separate element, because a glyph that always looks urgent
       stops meaning urgent. -->
  <symbol id="i-bell" viewBox="0 0 24 24"><path d="M18 9a6 6 0 0 0-12 0c0 5-2 6.5-2 6.5h16S18 14 18 9z"/><path d="M13.7 19a2 2 0 0 1-3.4 0"/></symbol>
  <!-- A clock face. The hero says the time and nothing else, so the glyph
       has to read at a glance for somebody who does not read the numerals. -->
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></symbol>
`;
