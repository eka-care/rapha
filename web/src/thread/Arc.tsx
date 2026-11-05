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
import { Icon } from "../icons";
import type { Contact, Episode } from "../types";
import { dateWords, dayMonth } from "../view/day";
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

export const MARK: Record<string, string> = {
  done: "check",
  due: "clock",
  missed: "alert",
  upcoming: "clock",
};

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
          teaches people to ignore the whole tracker. */}
      {episode.anchor_date && (
        <p className="arc-basis">
          Dated {dateWords(episode.anchor_date)}
          {episode.anchor_basis && <> from {human(episode.anchor_basis).toLowerCase()}</>}
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
  return (
    <li className={`arc-step s-${c.state}`}>
      <span className="arc-dot" aria-hidden="true">
        <Icon name={(MARK[c.state] ?? "clock") as never} className="i sm" />
      </span>
      <span className="arc-b">
        <span className="arc-t" title={c.programme_title || undefined}>
          {c.title}
          <span className={`badge ${TONE[c.state] ?? "b-mute"}`}>{title(c.state)}</span>
          {/* What the programme calls this, when it calls it anything. A
              centre doing more contacts than it reports still has to know
              which line each one fills in. */}
          {c.reports_as && <span className="badge b-mute">{c.reports_as}</span>}
        </span>
        {/* A DATE A PERSON CAN READ, AND A ROLE IN WORDS. This line read
            "Due 2026-11-15 · open 2026-11-01 to 2026-11-29 · MO": an ISO
            date and a bare code, on the record a health worker with little
            English reads. The role's name is the bundle's own. */}
        <span className="arc-when">
          {c.state === "done" && c.done_at
            ? <>Recorded {dateWords(c.done_at)}</>
            : <>Due {dateWords(c.due)} · open {dayMonth(c.opens)} to {dayMonth(c.closes)}</>}
          {c.state !== "done" && <> · {roleName(c.owner)}</>}
        </span>
      </span>
      {onAct && c.state !== "done" && c.state !== "upcoming" && (
        <button type="button" className="cq" onClick={() => onAct(c.operation)}>
          Record
        </button>
      )}
    </li>
  );
}
