/** §52: where you are, and the two things you can do from anywhere.
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
 *
 *  THE PLACES ARE NOT HERE ANY MORE. Five nav words, a theme toggle, a cog
 *  and an account chip used to share this row with the screen's own title,
 *  so the bar answered "where am I" and "where could I go" in the same
 *  breath and in the same type. Places live in the icon rail; what is left
 *  here is the title and the two things that are not places -- starting
 *  somebody off, and asking.
 */
import { NAME } from "../brand";
import { Icon } from "../icons";

export function Topbar({ title, deskLabel, bell, onSearch, onMenu, onDesk }: {
  title: string;
  deskLabel: string;
  /** What is waiting for somebody, drawn last in this row. It is not a
   *  place, so it is not in the rail; it is not an action a person chose,
   *  so it does not wear a pill. */
  bell?: React.ReactNode;
  onSearch: () => void;
  onMenu: () => void;
  onDesk: () => void;
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
      <button className="pill ml-auto" onClick={onDesk}>
        <Icon name="plus" className="i sm" />
        {deskLabel}
      </button>
      <button className="pill" onClick={onSearch}>
        <Icon name="search" className="i sm" />
        Ask {NAME}
        <span className="kbd">⌘K</span>
      </button>
      {bell}
    </header>
  );
}
