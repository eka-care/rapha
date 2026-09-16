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
      {/* Below 768px the rail is a drawer and this is the only way to it.
          It was inline-styled display:none with no rule to bring it back,
          which left a phone with no navigation at all. shell.css shows it. */}
      <button className="icon-btn topbar__menu" onClick={onMenu} aria-label="Open navigation">
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
