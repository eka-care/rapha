/** A course of care, as the sequence of contacts it owes.
 *
 *  THIS FILE COMPUTES NOTHING. Every date, every state and every owner on
 *  the screen below is in the answer the kernel sent, derived there from a
 *  schedule declaration and the episode's own date. That is not fastidious:
 *  the rule that makes this product safe is that an episode which has ended
 *  carries NO contacts at all, and a renderer that worked out its own dates
 *  could keep drawing an arc for a pregnancy that is over.
 *
 *  So there is no obstetrics here, no interval, no threshold and no word
 *  for any contact. A bundle that schedules something else entirely draws
 *  through this unchanged.
 */
import type { Contact, Episode } from "../types";
import { dateWords, dayMonth, dayOf } from "../view/day";
import { human, title } from "../words";

/** The four states a contact comes back in, and how each one is drawn.
 *
 *  `missed` is the only one that takes the critical tone, and it takes it
 *  because somebody has to go and find her. `due` is ordinary work and is
 *  deliberately NOT red: a screen that is red for everybody who is simply
 *  expected this fortnight is a screen nobody reads.
 */
export const TONE: Record<string, string> = {
  done: "b-ok",
  due: "b-ink",
  missed: "b-crit",
  upcoming: "b-mute",
};

/** How THIS card draws a state's chip. TONE above is shared -- the calendar and
 *  the grid key their bars on its values -- so the card's own choices live here
 *  and not there. Something owed is sage, "yours to do"; something finished is
 *  quiet history and takes no colour, so nothing done competes with what is
 *  still owed. Missed stays the one red. */
const CHIP: Record<string, string> = { ...TONE, due: "b-sage", done: "b-mute" };

export const MARK: Record<string, string> = {
  done: "check",
  due: "clock",
  missed: "alert",
  upcoming: "clock",
};

/** A DATE, DRAWN AS A DATE. The day is the large thing and the month sits
 *  under it, so a column of them reads as a calendar down the left of the
 *  card and the eye can find "which one is this month" without reading a
 *  sentence. It used to be a phrase in small grey type under the heading,
 *  which is where nobody looked.
 *
 *  It lays out the kernel's YYYY-MM-DD by position and works nothing out. A
 *  date in any other shape is shown whole in the same tile rather than
 *  guessed at, and the full date is always its accessible name. */
export function DateTile({ date, tone }: { date: string; tone?: string }) {
  const { day, month } = dayOf(date);
  return (
    <span className={`dtile${tone ? ` ${tone}` : ""}${day ? "" : " raw"}`}
          role="img" aria-label={dateWords(date)}>
      {day ? <><b>{day}</b><i>{month}</i></> : <i>{date || "—"}</i>}
    </span>
  );
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** What a role is CALLED is the bundle's to say, never this file's. Without
 *  one the raw id shows, which is plain, where a word we made up would be a
 *  word nobody declared. */
type RoleName = (role: string) => string;

export function Arc({ episodes, onAct, roleName = (r) => r }: {
  episodes: Episode[];
  /** Open the operation that would close a contact. Absent where this
   *  screen cannot act, which is every screen that is not a visit. */
  onAct?: (operation: string) => void;
  /** The declared title of a role, from the catalogue's own vocabulary. */
  roleName?: RoleName;
}) {
  if (!episodes.length) return null;
  return (
    <>
      {episodes.map((e) => <OneArc key={e.id} episode={e} onAct={onAct} roleName={roleName} />)}
    </>
  );
}

function OneArc({ episode, onAct, roleName }: { episode: Episode; onAct?: (op: string) => void; roleName: RoleName }) {
  const over = episode.status === "ended";
  return (
    <section className="card arc">
      <div className="card-h">
        <div className="card-t">{title(human(episode.type))}</div>
        {over ? (
          <span className="badge b-mute ml-auto">
            {episode.outcome ? title(human(episode.outcome)) : "Closed"}
          </span>
        ) : (
          <span className="badge b-ok ml-auto">Open</span>
        )}
      </div>

      {/* HOW THE DATES WERE ARRIVED AT, said on the screen rather than
          implied by it. A contact "due in nine days" computed from a half
          remembered period is a false precision, and a false precision
          teaches people to ignore the whole tracker. One short line: what it
          was counted from, and the date, in that order. */}
      {episode.anchor_date && (
        <p className="arc-basis">
          {episode.anchor_basis ? sentence(human(episode.anchor_basis)) : "Counted from"}
          {" · "}<b>{dateWords(episode.anchor_date)}</b>
        </p>
      )}

      {episode.contacts.length === 0 ? (
        <p className="rail-none">
          {episode.nothing_due
            ? `Nothing is due: ${episode.nothing_due}.`
            : "Nothing is due."}
        </p>
      ) : (
        <ol className="arc-list">
          {episode.contacts.map((c) => (
            <Step key={c.contact} contact={c} onAct={onAct} roleName={roleName} />
          ))}
        </ol>
      )}
    </section>
  );
}

function Step({ contact, onAct, roleName }: { contact: Contact; onAct?: (op: string) => void; roleName: RoleName }) {
  const c = contact;
  const done = c.state === "done";
  // The whole sentence stays reachable, for a pointer and for a screen reader,
  // and is off the screen: the tile says when, the chip says what state, and
  // the line says who. The window a visit may be done in is the detail.
  const full = done && c.done_at
    ? `Recorded ${dateWords(c.done_at)}`
    : `Due ${dateWords(c.due)} · open ${dayMonth(c.opens)} to ${dayMonth(c.closes)}`;
  return (
    <li className={`arc-step s-${c.state}`} title={full}>
      <DateTile date={done && c.done_at ? c.done_at : c.due} tone={`s-${c.state}`} />
      <span className="arc-b">
        <span className="arc-t" title={c.programme_title || undefined}>
          {c.title}
          <span className={`badge ${CHIP[c.state] ?? "b-mute"}`}>{title(c.state)}</span>
          {/* What the programme calls this, when it calls it anything. A
              centre doing more contacts than it reports still has to know
              which line each one fills in. */}
          {c.reports_as && <span className="badge b-mute">{c.reports_as}</span>}
        </span>
        {!done && <span className="arc-when">{roleName(c.owner)}</span>}
        <span className="u-sr">{full}</span>
      </span>
      {onAct && !done && c.state !== "upcoming" && (
        <button type="button" className="cq" onClick={() => onAct(c.operation)}>
          Record
        </button>
      )}
    </li>
  );
}
