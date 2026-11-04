/** The first panel: the whole product's destinations, as icons.
 *
 *  WHAT THIS REPLACES. Every destination used to be a word in the top bar --
 *  Home, Patients, Facility today, Lines, Needs you -- next to a Register
 *  button, a search pill, a theme toggle, a cog and an account chip. Nine
 *  things in one horizontal strip, in two visual languages, with the
 *  screen's own title competing for the same row. Nothing told you which of
 *  the nine was a place and which was an action, so finding a place meant
 *  reading all nine.
 *
 *  Places are here and nowhere else. Actions stay in the top bar. That is
 *  the whole rule, and it is why this is a column of equals rather than a
 *  row of leftovers.
 *
 *  ON GLYPHS IN NAVIGATION. icons.tsx records the decision that took them
 *  out: two of four nav icons resolved to the same list glyph, so the icon
 *  discriminated nothing and a 13px label did the work. That reasoning held
 *  for icons used INSTEAD of words. Every row here carries both, so the
 *  glyph is the thing found at a glance and the word is what settles it --
 *  and a view whose icon collides with another's is still unambiguous.
 *
 *  This file names no view. A view's icon comes from its declared `kind`,
 *  which is the same property that decides how the kernel evaluates it.
 */
import { Icon, type IconName } from "../icons";
import type { Facility, ViewDecl } from "../types";
import { Profile } from "../auth/Profile";

/** A view's glyph, from the kind it declares. Four kinds, four glyphs: a
 *  queue is a line of people, a dashboard is a reading, a tasklist is work
 *  outstanding. A kind this renderer has not met gets the neutral one
 *  rather than nothing, because a nav row with no mark is a broken row. */
const KIND_GLYPH: Record<string, IconName> = {
  queue: "users", dashboard: "vitals", tasklist: "alert", summary: "clip",
};

export type Place = { id: string; label: string; icon: IconName; hash: string };

/** Everywhere a person can go, in the order a shift uses them: the day, the
 *  people in it, the register behind them, and the settings underneath. */
export function places(views: ViewDecl[]): Place[] {
  return [
    { id: "home", label: "Home", icon: "home", hash: "#/" },
    // A TASKLIST IS NOT A PLACE, it is an interruption, and it had a nav row
    // of its own that sat there all day saying the same number. What is
    // waiting for somebody belongs where a person already looks for that --
    // the bell, top right -- and the rail goes back to being the places you
    // can stand. The word `tasklist` is the view's own declared kind, which
    // is the same property this file already reads to pick a glyph.
    ...views.filter((v) => v.kind !== "tasklist").map((v) => ({
      id: `views/${v.id}`,
      label: v.title,
      icon: KIND_GLYPH[v.kind] ?? "list",
      hash: `#/views/${v.id}`,
    })),
    // NOT A FOLDER. The register is people, not filing: a folder glyph says
    // "documents are in here" above a screen that lists human beings, and it
    // was the one row in this rail whose mark argued with its own label. A
    // record card with a person on it is what a patient register is.
    { id: "patients", label: "Patients", icon: "id", hash: "#/patients" },
  ];
}

export function Rail({
  route, views, facility, theme, onGo, onTheme, onSignOut,
}: {
  route: string;
  views: ViewDecl[];
  facility?: Facility;
  theme: "light" | "dark";
  onGo: (hash: string) => void;
  onTheme: () => void;
  onSignOut: () => void;
}) {
  const here = (id: string) =>
    id === "home" ? route === "" || route === "today" : route.startsWith(id);

  return (
    <nav className="rail" aria-label="Places">
      <span className="rail-mark"><Icon name="mark" /></span>

      <div className="rail-list">
        {places(views).map((p) => (
          <button
            key={p.id}
            type="button"
            className={`rail-i${here(p.id) ? " on" : ""}`}
            aria-current={here(p.id) ? "page" : undefined}
            onClick={() => onGo(p.hash)}
          >
            <Icon name={p.icon} className="i" />
            {/* The label is not a tooltip. A tooltip is invisible on a
                touchscreen and late on a mouse, and this is the word that
                tells two similar glyphs apart. */}
            <span className="rail-l">{p.label}</span>
          </button>
        ))}
      </div>

      <div className="rail-foot">
        <button
          type="button"
          className={`rail-i${route === "settings" ? " on" : ""}`}
          aria-current={route === "settings" ? "page" : undefined}
          onClick={() => onGo("#/settings")}
        >
          <Icon name="cog" className="i" />
          <span className="rail-l">Settings</span>
        </button>
        <button
          type="button"
          className="rail-i"
          onClick={onTheme}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} className="i" />
          <span className="rail-l">{theme === "dark" ? "Light" : "Dark"}</span>
        </button>
        <Profile facility={facility} onSignOut={onSignOut} />
      </div>
    </nav>
  );
}
