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
import { useState } from "react";
import { Icon } from "../icons";
import { months, type Scale } from "./arc-scale";
import type { Contact, Episode } from "../types";
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

export function Arc({ episodes, onAct, scale: first = "day" }: {
  episodes: Episode[];
  /** Which layout opens first. The patient screen asks for "year", because
   *  the reason to open it is the shape of the whole arc. */
  scale?: Scale;
  /** Open the operation that would close a contact. Absent where this
   *  screen cannot act, which is every screen that is not a visit. */
  onAct?: (operation: string) => void;
}) {
  if (!episodes.length) return null;
  return (
    <>
      {episodes.map((e) => <OneArc key={e.id} episode={e} onAct={onAct} first={first} />)}
    </>
  );
}

function OneArc({ episode, onAct, first }: { episode: Episode; onAct?: (op: string) => void; first: Scale }) {
  const [scale, setScale] = useState<Scale>(first);
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
          Dated {episode.anchor_date}
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
        <>
        <div className="arc-scale" role="tablist" aria-label="Scale">
          {(["day", "month", "year"] as Scale[]).map((k) => (
            <button key={k} type="button" role="tab" aria-selected={scale === k}
              className={scale === k ? "on" : ""} onClick={() => setScale(k)}>
              {title(k)}
            </button>
          ))}
        </div>
        {scale !== "day" && <Months episode={episode} dense={scale === "year"} />}
        {scale === "day" && (
        <ol className="arc-list">
          {episode.contacts.map((c) => (
            <Step key={c.contact} contact={c} onAct={onAct} />
          ))}
        </ol>
        )}
        </>
      )}
    </section>
  );
}

function Step({ contact, onAct }: { contact: Contact; onAct?: (op: string) => void }) {
  const c = contact;
  return (
    <li className={`arc-step s-${c.state}`}>
      <span className="arc-dot" aria-hidden="true">
        <Icon name={(MARK[c.state] ?? "clock") as never} className="i sm" />
      </span>
      <span className="arc-b">
        <span className="arc-t">
          {c.title}
          <span className={`badge ${TONE[c.state] ?? "b-mute"}`}>{title(c.state)}</span>
          {/* What the programme calls this, when it calls it anything. A
              centre doing more contacts than it reports still has to know
              which line each one fills in. */}
          {c.reports_as && <span className="badge b-mute">{c.reports_as}</span>}
        </span>
        <span className="arc-when">
          {c.state === "done" && c.done_at
            ? <>Recorded {c.done_at}</>
            : <>Due {c.due} · open {c.opens} to {c.closes}</>}
          {c.state !== "done" && <> · {human(c.owner)}</>}
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

const monthName = (key: string) =>
  new Date(`${key}-01T00:00:00Z`).toLocaleString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });

/** The arc as months, every month between the first contact and the last
 *  drawn even when nothing falls in it: the empty stretch is the point. */
function Months({ episode, dense }: { episode: Episode; dense: boolean }) {
  const ms = months(episode);
  return (
    <div className={`arc-months${dense ? " dense" : ""}`}>
      {ms.map((m) => (
        <div key={m.month} className="arc-month">
          <div className="arc-mn">{monthName(m.month)}</div>
          <div className="arc-days">
            {!m.days.some((d) => d.state) && <span className="arc-none">Nothing booked</span>}
            {m.days.map((d) => (
              <span key={d.day} title={d.state ? `${d.event}, ${d.state}, ${d.day}` : d.day}
                className={`arc-d${d.state ? ` s-${d.state}` : ""}`}>
                {!dense && Number(d.day.slice(8))}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
