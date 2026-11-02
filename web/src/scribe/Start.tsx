/** What happens after somebody picks the thing they are about to do.
 *
 *  THE ORDER IS THE POINT. A visit does not open on a microphone: it opens on
 *  the thread, and a person chooses "Record vitals" or "Document a
 *  consultation" first, because that is the decision they are actually
 *  making. Only then does this appear, and from here speaking is the way in
 *  and the form is the way round.
 *
 *  IT IS A VOICE, NOT A DEVICE. The control is the shape a voice makes, not a
 *  picture of the thing you speak into: a microphone glyph is the hardware,
 *  and the hardware is not what anybody is thinking about. The wave is at
 *  rest until the pointer is on it, and it is still on `prefers-reduced-
 *  motion`, because a thing that moves forever on a clinical screen is an
 *  interruption.
 *
 *  THE EXAMPLES ARE NUDGES AND STAY NUDGE SIZED. They were a two column
 *  table, then cards, and both were too much furniture for a hint: a card
 *  reads as a thing you must fill in, which is the one thing these must not
 *  be. Each is now one line somebody said, in quotation marks, with the part
 *  of the record it fills in front of it.
 *
 *  There is no sentence underneath explaining that the list is not binding.
 *  It was there and it was filler: nothing about a row of loose quoted
 *  phrases suggests a form, so saying "not a list to stick to" only told
 *  somebody to worry about something they were not worrying about.
 *
 *  They are DECLARED, in bundle.yaml under `scribe.<station>.nudges`, and
 *  this file types none of them. A centre whose doctors speak differently
 *  edits them and this screen follows, which is the rule every other word on
 *  every other screen already follows.
 */
import { Icon } from "../icons";

export type Nudge = { field: string; say: string };

/** The wave's own shape. Fixed, not random: a control that is a different
 *  object on every render is a control nobody learns the look of. Read as
 *  relative heights, loudest in the middle, the way a sentence is. */
const WAVE = [
  12, 20, 34, 26, 48, 62, 40, 72, 88, 64, 96, 78, 100, 84,
  100, 72, 92, 60, 80, 46, 66, 38, 52, 28, 36, 22, 16, 10,
];

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
        <span className="sc-wave" aria-hidden="true">
          {WAVE.map((h, i) => (
            <span className="sc-bar" key={i}
                  style={{ height: `${h}%`, animationDelay: `${i * 55}ms` }} />
          ))}
        </span>
        <span className="sc-go-t">Start speaking</span>
        <span className="sc-go-s">{reason || "Say it in your own words. Check it after."}</span>
      </button>

      {groups.length > 0 && (
        <div className="sc-nudges">
          <p className="sc-nudges-h">Things people say here</p>
          <ul className="sc-says">
            {groups.map((g) => g.says.map((say) => (
              <li className="sc-say" key={say}>
                <span className="sc-say-f">{g.field}</span>
                <span className="sc-say-q">{say}</span>
              </li>
            )))}
          </ul>
        </div>
      )}

      <button type="button" className="sc-type" onClick={onType}>
        <Icon name="doc" className="i sm" />
        Fill it in by hand instead
      </button>
    </section>
  );
}
