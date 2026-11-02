/** What happens after somebody picks the thing they are about to do.
 *
 *  THE ORDER IS THE POINT. A visit does not open on a microphone: it opens on
 *  the thread, and a person chooses "Record vitals" or "Document a
 *  consultation" first, because that is the decision they are actually
 *  making. Only then does this appear, and from here speaking is the way in
 *  and the form is the way round.
 *
 *  SPEAKING IS THE PRODUCT. The forms are not: they are where what was heard
 *  lands, and a person checks it before it is kept. So the microphone is the
 *  big control and typing is a line of text beneath it, which is the reverse
 *  of how this screen used to read.
 *
 *  THE NUDGES ARE EXAMPLES AND NOT A FORM, which is why they are worded as
 *  somebody speaking rather than as field labels. A consultation with a
 *  fourth reading, a finding nobody listed, or three medicines instead of one
 *  is recorded exactly the same way; nothing here narrows what the microphone
 *  accepts. They are on screen because a person who has just pressed record
 *  and does not know what to say will say nothing, and a blank screen is what
 *  sends a clinic back to paper.
 *
 *  They are DECLARED, in bundle.yaml under `scribe.<station>.nudges`, and
 *  this file types none of them. A centre whose doctors speak differently
 *  edits them and this screen follows, which is the rule every other word on
 *  every other screen already follows.
 */
import { Icon } from "../icons";

export type Nudge = { field: string; say: string };

export function ScribeStart({ title, nudges, reason, onStart, onType, onCancel }: {
  /** The operation's own title. The person just tapped it, and the screen
   *  that follows has to be obviously the same thing. */
  title: string;
  nudges: Nudge[];
  /** Why recording is unavailable, if it is. A control that does nothing and
   *  says nothing is worse than one that is not there. */
  reason?: string;
  onStart: () => void;
  onType: () => void;
  onCancel: () => void;
}) {
  // Grouped by the part of the record each fills, in the order declared. A
  // field with two examples is one group with two lines, not two groups.
  const groups: { field: string; says: string[] }[] = [];
  for (const n of nudges) {
    const last = groups[groups.length - 1];
    if (last && last.field === n.field) last.says.push(n.say);
    else groups.push({ field: n.field, says: [n.say] });
  }

  return (
    <section className="sc-start" aria-label={title}>
      <header className="sc-head">
        <h2 className="sc-head-t">{title}</h2>
        <button type="button" className="sc-x" onClick={onCancel} aria-label="Back to the visit">
          <Icon name="chev" className="i sm" />
        </button>
      </header>

      <button type="button" className="sc-go" onClick={onStart} disabled={!!reason}
              title={reason} aria-label={reason || "Start speaking"}>
        <span className="sc-go-ring" aria-hidden="true">
          <Icon name="mic" className="i" />
        </span>
        <span className="sc-go-t">Start speaking</span>
        <span className="sc-go-s">{reason || "Say it in your own words. Check it after."}</span>
      </button>

      {groups.length > 0 && (
        <div className="sc-nudges">
          <p className="sc-nudges-h">Things you can say</p>
          <ul className="sc-list">
            {groups.map((g) => (
              <li className="sc-n" key={g.field}>
                <span className="sc-n-f">{g.field}</span>
                <span className="sc-n-s">
                  {g.says.map((s) => <span className="sc-n-q" key={s}>{s}</span>)}
                </span>
              </li>
            ))}
          </ul>
          <p className="sc-foot">Not a list to stick to. Say whatever the visit needs.</p>
        </div>
      )}

      <button type="button" className="sc-type" onClick={onType}>
        <Icon name="doc" className="i sm" />
        Fill it in by hand instead
      </button>
    </section>
  );
}
