/** §52: where you are, one way to search from anywhere, and the theme. */
import { Icon } from "../icons";

export function Topbar({ title, sub, theme, onSearch, onTheme, onMenu }: {
  title: string;
  sub?: string;
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
        <div className="tb-title" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </div>
        {sub && <div className="tb-sub">{sub}</div>}
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
