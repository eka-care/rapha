/** The room the thread does not have.
 *
 *  A visit thread is a conversation, and a conversation is a narrow column of
 *  short lines. Everything else we needed to show got pushed into it anyway:
 *  the scribe's drafts went in at the foot of the card inside a 42vh scroller,
 *  which is a form in a letterbox, and an earlier visit was reduced to a
 *  sparkline in a 300px rail because that was the only space left.
 *
 *  This is the other half of the screen, in the Slack sense: the thread keeps
 *  the conversation, and anything you need to READ rather than say opens
 *  beside it with the width to be read. It takes the rail's column and more,
 *  and under 1100px it takes the page, because on a phone a second column is
 *  a worse answer than a second screen.
 *
 *  IT DRAWS CHROME AND NOTHING ELSE. The tabs it is given and the body inside
 *  it both come from the screen above. That is not fastidiousness: `ui.check`
 *  forbids this renderer from naming a station, a flag or an operation, and
 *  the surest way to keep a surface clean of them is to give it nothing
 *  clinical to hold.
 */
import { useEffect } from "react";
import { Icon, type IconName } from "../icons";

/** Which views may open here. Each is a KIND OF READING, not a clinical
 *  thing: what was just heard, and what happened before. Files and the
 *  private conversation with the agent are the next two and are not here
 *  yet -- both wait on a decision recorded in the design note. */
export type SideId = "past" | "scribe";

export type Tab = { id: SideId; title: string; icon: IconName };

export function Side({ open, tabs, onPick, onClose, children }: {
  open: SideId;
  tabs: Tab[];
  onPick: (id: SideId) => void;
  onClose: () => void;
  children: React.ReactNode;
}) {
  // Escape closes it, because this covers the rail and anything that covers
  // something needs a way back that is not a hunt for a small button.
  useEffect(() => {
    const off = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", off);
    return () => window.removeEventListener("keydown", off);
  }, [onClose]);

  const here = tabs.find((t) => t.id === open);
  return (
    <aside className="side" aria-label={here?.title ?? "Beside this visit"}>
      <div className="side-h">
        <div className="side-tabs" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={t.id === open}
              className={`side-tab${t.id === open ? " on" : ""}`}
              onClick={() => onPick(t.id)}
            >
              <Icon name={t.icon} className="i sm" />
              {t.title}
            </button>
          ))}
        </div>
        {/* The one glyph this set has for a cross, turned. A view that covers
            the rail must say how to uncover it. */}
        <button type="button" className="side-x" onClick={onClose}
                aria-label="Close this view">
          <Icon name="plus" className="i sm" />
        </button>
      </div>
      <div className="side-b" role="tabpanel">{children}</div>
    </aside>
  );
}
