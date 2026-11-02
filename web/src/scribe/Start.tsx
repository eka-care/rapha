/** The way a visit is recorded, and the thing this screen is for.
 *
 *  SPEAKING IS THE PRODUCT. The forms are not: they are where what was heard
 *  lands, and a person checks it before it is kept. So the microphone is not
 *  an icon at the end of a text box any more. It is the centre of the page,
 *  and everything else on the page is smaller than it.
 *
 *  THE NUDGES ARE EXAMPLES AND NOT A FORM, which is the whole reason they are
 *  worded as somebody speaking rather than as field labels. A consultation
 *  with a fourth reading, a finding nobody listed, or three medicines instead
 *  of one is recorded exactly the same way; nothing here narrows what the
 *  microphone accepts. They are on screen because a person who has just
 *  pressed record and does not know what to say will say nothing, and a
 *  blank screen is what makes somebody go back to paper.
 *
 *  They are DECLARED, in bundle.yaml under `scribe.<station>.nudges`, and
 *  this file types none of them. A centre whose doctors speak differently
 *  edits them and this screen follows, which is the same rule every other
 *  word on every other screen already follows.
 */
import { Icon } from "../icons";

export type Nudge = { field: string; say: string };

export function ScribeStart({ nudges, reason, onStart }: {
  nudges: Nudge[];
  /** Why recording is unavailable, if it is. A control that does nothing and
   *  says nothing is worse than one that is not there. */
  reason?: string;
  onStart: () => void;
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
    <div className="sc-start">
      <button type="button" className="sc-go" onClick={onStart} disabled={!!reason}
              title={reason} aria-label={reason || "Start session"}>
        <span className="sc-go-ring" aria-hidden="true">
          <Icon name="mic" className="i" />
        </span>
        <span className="sc-go-t">Start session</span>
        <span className="sc-go-s">{reason || "Speak normally. Check it after."}</span>
      </button>

      {groups.length > 0 && (
        <div className="sc-nudges">
          <p className="sc-nudges-h">You can say things like</p>
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
    </div>
  );
}
