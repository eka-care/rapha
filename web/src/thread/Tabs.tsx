/** The visit's tabs, in the shape a channel has them.
 *
 *  A thread is a conversation, and a conversation is a narrow column of short
 *  lines. Everything else got pushed into it anyway: the scribe's drafts sat
 *  at the foot of the card inside a 42vh scroller, which is a form in a
 *  letterbox, under the conversation it came from.
 *
 *  So the conversation is not the screen any more. It is the FIRST TAB of the
 *  screen, which is how a channel works everywhere a clinician has already
 *  used one: messages, files, and whatever else that channel keeps, in a row
 *  across the top, each taking the full width when you are in it. Owner, on
 *  a screenshot of exactly that row: "all of these should be tabs, records,
 *  scribe, etc".
 *
 *  IT DRAWS THE ROW AND NOTHING ELSE. The tabs it is given and the body under
 *  them both come from the screen above. That is not fastidiousness:
 *  `ui.check` forbids this renderer from naming a station, a flag or an
 *  operation, and the surest way to keep a surface clean of them is to give
 *  it nothing clinical to hold.
 */
import { Icon, type IconName } from "../icons";

/** Which tabs a visit can have. Each is a KIND OF THING THE VISIT KEEPS, not
 *  a feature of ours. The private conversation with the agent is the next
 *  one and is not here yet: it waits on a decision recorded in the design
 *  note, and a tab that opens on an apology is worse than a tab that is not
 *  there. "ask" is the medical assistant, which is general medicine and not
 *  this visit's own agent: it is given nothing about the patient.
 *
 *  "context" is paper from somewhere else -- a discharge summary, an outside
 *  result -- and it is a tab rather than a line in the conversation because
 *  somebody reads it BEFORE the visit starts, and because a two page letter
 *  in a chat bubble is not a readable letter. What belongs in it is not
 *  decided here: the screen picks it out by the `presents:` word the atom
 *  declares, so a bundle with no such operation simply has an empty tab. */
export type TabId = "messages" | "scribe" | "context" | "past" | "ask";

export type Tab = { id: TabId; title: string; icon: IconName; count?: number };

export function Tabs({ open, tabs, trailing, onPick }: {
  open: TabId;
  tabs: Tab[];
  /** Pinned to the right end of this row, outside the tablist.
   *
   *  The panel beside this visit used to carry its own Hide control, in a
   *  row of its own above its first card -- which pushed every card in that
   *  column 56px below the card they sat beside, and was the misalignment
   *  the owner saw. A control that opens and closes a column does not
   *  belong inside the column: it belongs in the row that spans the screen,
   *  at the end of it, which is where it is now and where Heidi keeps the
   *  same control. */
  trailing?: React.ReactNode;
  onPick: (id: TabId) => void;
}) {
  return (
    <div className="vtabs">
      <div className="vtabs-l" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={t.id === open}
          className={`vtab${t.id === open ? " on" : ""}`}
          onClick={() => onPick(t.id)}
        >
          <Icon name={t.icon} className="i sm" />
          {t.title}
          {/* A count only where there is something to count. A tab reading
              "Earlier visits 0" is a tab telling you not to open it, which
              is what the empty state inside it is for. */}
          {!!t.count && <span className="vtab-n">{t.count}</span>}
        </button>
      ))}
      </div>
      {trailing}
    </div>
  );
}
