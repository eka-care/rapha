/** §52. The title of where you are, the way to search from anywhere, and the
 *  theme switch. Nothing else earns a place in a 56px strip. */
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
      <button className="icon-btn" onClick={onMenu} aria-label="Menu" style={{ display: "none" }} data-drawer>
        <Icon name="list" />
      </button>
      <div className="topbar__title">
        <div className="t-strong" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {title}
        </div>
        {sub && <div className="t-meta u-faint">{sub}</div>}
      </div>
      <div className="topbar__spacer" />
      <button className="btn" data-variant="ghost" onClick={onSearch} aria-label="Search">
        <Icon name="search" />
        <span className="kbd">⌘K</span>
      </button>
      <button
        className="icon-btn"
        onClick={onTheme}
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      >
        <Icon name={theme === "dark" ? "sun" : "moon"} />
      </button>
    </header>
  );
}
