/** The control panel: a page, with sections, and not a dialog.
 *
 *  IT WAS A MODAL and it should not have been. Everything here is a change
 *  to how a centre works rather than to one visit: who may do what, what the
 *  recording screen suggests, what the rail beside a visit shows. Those are
 *  settled once, read back later, and argued about by more than one person,
 *  and a box floating over a half drawn workspace is the wrong shape for all
 *  three. It also had nowhere to grow: the roles editor filled it, and the
 *  next thing a centre wants to set had no room.
 *
 *  Sections, down the side, because they have different audiences: an
 *  administrator sets the roles, a doctor sets their own rail, and neither
 *  wants to scroll past the other's.
 *
 *  NOTHING HERE NAMES A STATION, A CAPABILITY OR AN OPERATION. The sections
 *  read them off the catalogue, the same rule every other screen follows.
 */
import type { Client } from "../api";
import { Icon, type IconName } from "../icons";
import type { Catalogue } from "../types";
import type { Withheld } from "../grants";
import { Roles } from "./Settings";
import { Nudges } from "./Nudges";
import { RailPrefs } from "./RailPrefs";
import { human, title } from "../words";

type Theme = "system" | "light" | "dark";

type Part = { id: string; title: string; icon: IconName; blurb: string };

/** The sections, and the order they are offered in. Exported because the
 *  second panel of the shell draws them now: a page's sections are
 *  navigation, and this product keeps navigation in one column rather than
 *  giving every page its own private one. */
export const PARTS: Part[] = [
  { id: "look", title: "Appearance", icon: "sun",
    blurb: "How this workspace looks on this device." },
  { id: "recording", title: "Recording", icon: "mic",
    blurb: "What the screen suggests somebody can say, station by station." },
  { id: "rail", title: "Beside a visit", icon: "list",
    blurb: "Which panels sit beside an open visit on this device." },
  { id: "roles", title: "Roles", icon: "users",
    blurb: "What a person in each role may do at this centre." },
];

export function Control({
  cat, client, roleIds, facility, theme, onTheme, part,
}: {
  cat: Catalogue;
  client: Client;
  roleIds: string[];
  facility: Withheld;
  theme: Theme;
  onTheme: (t: Theme) => void;
  /** Which section the address bar is on. It used to be state held inside
   *  this component, which meant the section a person was reading could not
   *  be linked to, did not survive a reload, and had to be found again
   *  after every change they made. */
  part: string;
}) {
  const here = PARTS.find((p) => p.id === part) ?? PARTS[0];

  return (
    <div className="cp">
      <section className="cp-pane" aria-label={here.title}>
        <header className="cp-head">
          {/* h2, not h1: the top bar already carries this page's heading, and
              two of them on one page is the thing ui.check.ts refuses. */}
          <h2 className="cp-t">{here.title}</h2>
          <p className="cp-s">{here.blurb}</p>
        </header>

        {here.id === "look" && <Look theme={theme} onTheme={onTheme} />}
        {here.id === "recording" && <Nudges cat={cat} client={client} />}
        {here.id === "rail" && <RailPrefs />}
        {here.id === "roles" && (
          <Roles client={client} cat={cat} roleIds={roleIds} facility={facility} />
        )}
      </section>
    </div>
  );
}

/** Three states, and the device is one of them. A two way switch could not
 *  say "follow this phone", which is what most people want and what the
 *  token contract is built for. */
function Look({ theme, onTheme }: { theme: Theme; onTheme: (t: Theme) => void }) {
  const choices: { id: Theme; label: string; icon: IconName; say: string }[] = [
    { id: "system", label: "Follow the device", icon: "cog",
      say: "Light by day and dark by night, if this phone or laptop is set that way." },
    { id: "light", label: "Always light", icon: "sun", say: "For a bright room." },
    { id: "dark", label: "Always dark", icon: "moon", say: "For a dim one." },
  ];
  return (
    <div className="cp-choices" role="radiogroup" aria-label="Theme">
      {choices.map((c) => (
        <button key={c.id} type="button" role="radio" aria-checked={theme === c.id}
                className={`cp-choice${theme === c.id ? " on" : ""}`}
                onClick={() => onTheme(c.id)}>
          <span className="cp-choice-i"><Icon name={c.icon} className="i sm" /></span>
          <span className="cp-choice-b">
            <span className="cp-choice-t">{c.label}</span>
            <span className="cp-choice-s">{c.say}</span>
          </span>
          {theme === c.id && <Icon name="check" className="i sm cp-choice-on" />}
        </button>
      ))}
    </div>
  );
}

/** Shared by the two sections that are a list of stations. The word is the
 *  bundle's own, cased for reading. */
export const stationName = (id: string) => title(human(id));
