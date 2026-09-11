/** The prototype's icon sheet, and the one helper that draws from it.
 *
 *  Copied verbatim from the <symbol> block of agentic-emr-prototype.html, less
 *  the station glyphs (desk, nurse, lab, pill): a station is a bundle's word,
 *  so drawing one would put the PHC in the renderer. A station is drawn with
 *  its own first letter instead.
 *
 *  Which icon an action gets is decided by its declared instrument, and which
 *  icon a nav entry gets by its declared view kind. Nothing here is keyed to
 *  an id.
 */
import type { Operation, ViewDecl } from "./types";

export type IconName =
  "mark" | "mark-lg" | "search" | "home" | "moon" | "sun" | "vitals" | "mic" | "flask" | "box" | "clip" | "eye" | "plus" | "folder" | "chat" | "spark" | "check" | "alert" | "lock" | "send" | "user" | "users" | "list" | "cog" | "refer" | "chev" | "id" | "doc";

export function Icon({ name, size }: { name: IconName; size?: "sm" | "lg" }) {
  return (
    <svg className={`i${size ? ` ${size}` : ""}`} aria-hidden="true">
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
 *  say. `device` and `voice` borrow the form icon: they are all a field being
 *  filled in, and only the scribe is a different act. */
export function iconFor(op: Operation): IconName {
  if (op.irreversibility === "irreversible") return "lock";
  if (op.instrument === "scribe") return "mic";
  if (op.instrument === "voice" || op.instrument === "device") return "vitals";
  return "clip";
}

export function iconForView(v: ViewDecl): IconName {
  return v.kind === "dashboard" ? "vitals" : v.kind === "summary" ? "eye" : "list";
}

const SHEET = `
  <style>
    #i-mark path, #i-mark circle, #i-mark-lg path, #i-mark-lg circle {
      fill: none; stroke: currentColor; vector-effect: non-scaling-stroke;
    }
  </style>
  <symbol id="i-mark" viewBox="0 0 24 24"><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(0 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(45 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(90 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(135 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(180 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(225 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(270 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(315 12 12)"/><circle cx="12" cy="12" r="1.7"/>  <circle cx="12" cy="12" r="6.2" opacity=".35"/>  <circle cx="3.1" cy="3.1" r=".7"/><circle cx="20.9" cy="3.1" r=".7"/>  <circle cx="3.1" cy="20.9" r=".7"/><circle cx="20.9" cy="20.9" r=".7"/></symbol>
  <symbol id="i-mark-lg" viewBox="0 0 24 24"><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(0 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(45 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(90 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(135 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(180 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(225 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(270 12 12)"/><path d="M12 12C12 8.6 9.6 6.9 12 3.4C14.4 6.9 12 8.6 12 12Z" transform="rotate(315 12 12)"/><circle cx="12" cy="12" r="1.7"/>  <circle cx="12" cy="12" r="6.2" opacity=".3"/><circle cx="12" cy="12" r="9.4" opacity=".16"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></symbol>
  <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 10.5 12 3l9 7.5"/><path d="M5.5 9.5V20h13V9.5"/><path d="M10 20v-5h4v5"/></symbol>
  <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/></symbol>
  <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></symbol>
  <symbol id="i-vitals" viewBox="0 0 24 24"><path d="M2.5 12h4l2-5 3.5 10 2.5-7 1.5 2h5.5"/></symbol>
  <symbol id="i-mic" viewBox="0 0 24 24"><rect x="9" y="2.5" width="6" height="11" rx="3"/><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5M9 21.5h6"/></symbol>
  <symbol id="i-flask" viewBox="0 0 24 24"><path d="M10 3v6l-5 9a1.8 1.8 0 0 0 1.6 2.7h10.8A1.8 1.8 0 0 0 19 18l-5-9V3"/><path d="M9 3h6"/></symbol>
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
  <symbol id="i-send" viewBox="0 0 24 24"><path d="M21 3 10.5 13.5M21 3l-6.8 18-3.7-7.5L3 9.8z"/></symbol>
  <symbol id="i-user" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.6"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/></symbol>
  <symbol id="i-users" viewBox="0 0 24 24"><circle cx="9" cy="8" r="3.2"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 5.5a3.2 3.2 0 0 1 0 6M17.5 14.5a6 6 0 0 1 4 5.5"/></symbol>
  <symbol id="i-list" viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></symbol>
  <symbol id="i-cog" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 7.9 19.4l-.1.1A2 2 0 1 1 5 16.7l.1-.1A1.6 1.6 0 0 0 3.9 14H3.8a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.7L5 7.2A2 2 0 1 1 7.8 4.4l.1.1A1.6 1.6 0 0 0 10.6 3.4V3.3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1A2 2 0 1 1 20.2 7.2l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.1a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/></symbol>
  <symbol id="i-refer" viewBox="0 0 24 24"><path d="M4 12h13M12 6l6 6-6 6"/></symbol>
  <symbol id="i-chev" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></symbol>
  <symbol id="i-id" viewBox="0 0 24 24"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><circle cx="8.5" cy="11" r="2.2"/><path d="M5.2 16.2c.8-1.4 2-2 3.3-2s2.5.6 3.3 2M15 10h4M15 14h3"/></symbol>
  <symbol id="i-doc" viewBox="0 0 24 24"><circle cx="12" cy="7" r="3.4"/><path d="M5 21v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2"/><path d="M12 15.5v3M10.5 17h3"/></symbol>
`;
