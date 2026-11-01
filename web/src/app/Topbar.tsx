/** §52: where you are, one way to search from anywhere, and the theme.
 *
 *  THE TITLE IS THE PAGE'S h1. There was no h1 on any screen but the home
 *  one, so the heading outline began at the h3 the role editor draws and said
 *  nothing about which screen a person was on. The one piece of text that
 *  already answers "where am I", on every route, is this one, and it comes
 *  from a declaration.
 *
 *  WHAT WAS UNDER IT, AND WHY IT IS GONE. The facility's own name, on every
 *  screen, four hundred times a day. A person standing in the building knows
 *  which building it is. The word is not lost: App puts it in the document
 *  title, where it tells a person with six tabs open which tab this is --
 *  which is the one place it was actually doing work.
 */
import { Icon } from "../icons";

export function Topbar({ title, theme, onSearch, onTheme, onMenu }: {
  title: string;
  theme: "light" | "dark";
  onSearch: () => void;
  onTheme: () => void;
  onMenu: () => void;
}) {
  return (
    <header className="topbar">
      <button className="icon-btn topbar__menu" onClick={onMenu} aria-label="Open navigation">
        <Icon name="list" className="i sm" />
      </button>
      <div style={{ minWidth: 0 }}>
        <h1 className="tb-title" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </h1>
      </div>
      <button className="pill ml-auto" onClick={onSearch}>
        <Icon name="search" className="i sm" />
        Search or ask
        <span className="kbd">⌘K</span>
      </button>
      <button
        className="icon-btn"
        onClick={onTheme}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} className="i sm" />
      </button>
    </header>
  );
}
