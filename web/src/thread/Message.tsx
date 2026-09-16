/** §9.1, §9.2: an open message block. No bubble, no tail, no alignment games.
 *  Actor, time, content -- and mentions picked out so a person can see at a
 *  glance that they were named.
 */
import { Icon } from "../icons";

/** §13. A mention is rendered from the text itself; there is no people
 *  directory to resolve it against yet, so it is highlighted, not linked.
 *  Linking it would promise a profile that does not exist. */
function withMentions(text: string) {
  return text.split(/(@[\w.-]+)/g).map((part, i) =>
    part.startsWith("@")
      ? <span className="mention" key={i}>{part}</span>
      : <span key={i}>{part}</span>,
  );
}

export function Message({ who, actor, at, text }: {
  who: "user" | "agent";
  actor: string;
  at: string;
  text: string;
}) {
  return (
    <div className="message">
      <div className="avatar" data-who={who} aria-hidden="true">
        {who === "agent" ? <Icon name="spark" /> : initials(actor)}
      </div>
      <div className="message__content">
        <div className="message__meta">
          <strong style={{ color: "var(--color-text-secondary)" }}>{actor}</strong>
          <span aria-hidden="true">·</span>
          <time>{at}</time>
        </div>
        <div className="message__body">{withMentions(text)}</div>
      </div>
    </div>
  );
}

const initials = (name: string) =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("") || "?";
