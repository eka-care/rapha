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

export function Topbar({ title, theme, views, route, deskLabel, onSearch, onTheme, onMenu,
                        onGo, onDesk, onSettings }: {
  title: string;
  theme: "light" | "dark";
  /** The declared views. They were a permanent list down the rail, under the
   *  people waiting; the artifact gives that column to the line alone and
   *  carries everything else up here. */
  views: { id: string; title: string }[];
  route: string;
  deskLabel: string;
  onSearch: () => void;
  onTheme: () => void;
  onMenu: () => void;
  onGo: (hash: string) => void;
  onDesk: () => void;
  onSettings: () => void;
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
      <nav className="tb-nav" aria-label="Views">
        <button className={`tb-nv${route === "" || route === "today" ? " on" : ""}`}
                onClick={() => onGo("#/")}>Home</button>
        {views.map((v) => (
          <button key={v.id}
                  className={`tb-nv${route === `views/${v.id}` ? " on" : ""}`}
                  onClick={() => onGo(`#/views/${v.id}`)}>{v.title}</button>
        ))}
      </nav>
      <button className="pill ml-auto" onClick={onDesk}>
        <Icon name="plus" className="i sm" />
        {deskLabel}
      </button>
      <button className="pill" onClick={onSearch}>
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
      <button className="icon-btn" onClick={onSettings} aria-label="Control panel">
        <Icon name="cog" className="i sm" />
      </button>
    </header>
  );
}
