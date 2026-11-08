/** §9.1: an open message block. The prototype's shape: a small square avatar,
 *  a meta line, and a bubble. A person's own message sits right and tinted. */

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
/** The colour a person's name is drawn in. The same name is always the same hue,
 *  so who posted is told apart by name and colour, never by an initials tile (the
 *  tile is how a patient is identified). */
export function roleVar(name: string): string {
  let h = 0;
  for (const c of name.toLowerCase()) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return `var(--role-${(h % 6) + 1})`;
}

export function Turn({ who, actor, at, to, texts }: {
  who: "user" | "agent"; actor: string; at: string; texts: string[];
  to?: string[];
}) {
  const agent = who === "agent";
  return (
    <div className="lg2">
      <div className="lg2-who" style={{ color: agent ? "var(--color-agent)" : roleVar(actor) }}>
        {agent ? "Agent" : actor}
        <time>{at}</time>
      </div>
      <div className="lg2-body">
        {to?.length ? <div className="lg2-to">to {to.map((n) => `@${n}`).join(" ")}</div> : null}
        {texts.map((text, i) => (
          <p className="lg2-txt" key={i}>{withMentions(text)}</p>
        ))}
      </div>
    </div>
  );
}
