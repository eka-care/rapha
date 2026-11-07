/** Who is at this station, and the way out.
 *
 *  SIGNING OUT IS HONEST ABOUT WHAT IT CAN DO. The session is a cookie on
 *  `.eka.care`, set by login.eka.care, and a page on another origin cannot
 *  delete it -- it is not ours, and it is not readable from script. So this
 *  does the two things it CAN do and says so: it forgets the session here,
 *  which brings the way-in screen back, and it offers Eka, which is where a
 *  session actually ends. A button that claimed to sign somebody out of Eka
 *  and left the cookie sitting there would be the worst of the three.
 *
 *  The role is the other half. It is what the kernel is told on every
 *  request, and until an administrator sets it this is where it is chosen.
 */
import { useEffect, useRef, useState } from "react";
import { currentRole, setRole } from "../api";
import { Icon, type IconName } from "../icons";
import type { Facility } from "../types";
import { roleGlyph, title } from "../words";
import { LOGIN_URL } from "./session";

export function Profile({ facility, onSignOut }: {
  facility?: Facility;
  onSignOut: () => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Click away, or Escape. A menu that only closes by its own button is a
  // menu somebody leaves open.
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  const role = currentRole();
  const roles = facility?.roles ?? [];

  return (
    <div className="prof" ref={box}>
      <button
        className="prof-btn"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="prof-av">
          <Icon name="user" className="i" />
        </span>
        <span className="prof-r">{title(role)}</span>
        <Icon name="chev" className="i sm" />
      </button>

      {open && (
        <div className="prof-menu" role="menu">
          <div className="prof-h">
            <span className="prof-h-av">
              <Icon name={roleGlyph(role) as IconName} className="i sm" />
            </span>
            <div className="prof-hb">
              <div className="prof-n">{title(role)}</div>
              <div className="prof-s">
                {facility?.user.capabilities.length ?? 0} capabilities
                {facility?.bundle.title ? ` · ${facility.bundle.title}` : ""}
              </div>
            </div>
          </div>

          {roles.length > 1 && (
            <div className="prof-sec">
              {/* Until an administrator assigns it, this is where the role is
                  chosen, and it is the one the kernel is told on every
                  request. Each row carries its own glyph: ten role names in
                  one typeface is a list that has to be read word by word. */}
              {roles.map((r) => (
                <button
                  key={r}
                  className={`prof-role${r === role ? " on" : ""}`}
                  role="menuitemradio"
                  aria-checked={r === role}
                  onClick={() => { setRole(r); location.reload(); }}
                >
                  <Icon name={roleGlyph(r) as IconName} className="i sm prof-role-i" />
                  {title(r)}
                  {r === role && <Icon name="check" className="i sm ml-auto" />}
                </button>
              ))}
            </div>
          )}

          <div className="prof-sec">
            <button className="prof-out" role="menuitem" onClick={onSignOut}>
              <Icon name="out" className="i sm" />
              Sign out of {facility?.bundle.title ?? "this centre"}
            </button>
            <a className="prof-eka" href={LOGIN_URL} target="_blank" rel="noreferrer">
              End the Eka session
              <Icon name="chev" className="i sm" />
            </a>
            <p className="prof-note">
              The session is a cookie on eka.care. Signing out here forgets it on
              this device; ending it everywhere is Eka's own page.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
