/** §9.1: an open message block. The prototype's shape: a small square avatar,
 *  a meta line, and a bubble. A person's own message sits right and tinted. */
import { Icon } from "../icons";
import { initialsOf } from "../agent";

/** §13. Mentions are picked out of the text; there is no people directory to
 *  link them to yet, so they are highlighted rather than linked. */
export function withMentions(text: string) {
  return text.split(/(@[\w.-]+)/g).map((part, i) =>
    part.startsWith("@")
      ? <span className="mention" key={i}>{part}</span>
      : <span key={i}>{part}</span>);
}

export function Message({ who, actor, at, text }: {
  who: "user" | "agent"; actor: string; at: string; text: string;
}) {
  return <Turn who={who} actor={actor} at={at} texts={[text]} />;
}

/** ONE PERSON TALKING IS ONE BLOCK. Three lines typed in a row drew three
 *  avatars, three names and three clocks, which is three times the furniture
 *  for one thing somebody said. The header belongs to the turn; which line
 *  it was is not information anybody needs. Who speaks and when is decided
 *  in fold.ts, not here. */
export function Turn({ who, actor, at, texts }: {
  who: "user" | "agent"; actor: string; at: string; texts: string[];
}) {
  const mine = who === "user";
  return (
    <div className={`msg${mine ? " right" : ""}`}>
      <div className={`m-av${who === "agent" ? " agent" : ""}`} aria-hidden="true">
        {who === "agent" ? <Icon name="spark" className="i sm" /> : initialsOf(actor)}
      </div>
      <div className="m-b">
        <div className="m-meta">{actor} · {at}</div>
        {texts.map((text, i) => (
          <div className="bubble" key={i}>{withMentions(text)}</div>
        ))}
      </div>
    </div>
  );
}
