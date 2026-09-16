/** §56: the frame every structured thing in the thread is drawn in.
 *
 *  A header that names what it is, a body, and a footer carrying provenance.
 *  The header's word comes from the declaration that produced the row -- an
 *  operation's own title -- never from a table in this file, which is what
 *  keeps the frame usable by a bundle this renderer has never seen.
 */
import type { ReactNode } from "react";

export function ThreadObject({
  label, end, children, footer, className, tone,
}: {
  label: string;
  /** Right of the header: a time, a state. Not uppercased. */
  end?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  tone?: "critical" | "agent";
}) {
  return (
    <article className={`thread-object${className ? ` ${className}` : ""}`}>
      <header className="thread-object__header">
        <span>{label}</span>
        {end && <span className="thread-object__header-end">{end}</span>}
      </header>
      <div className="thread-object__body">{children}</div>
      {footer && <footer className="thread-object__footer">{footer}</footer>}
      {tone && <span className="u-sr">{tone === "critical" ? "Critical" : "From the agent"}</span>}
    </article>
  );
}

/** §44 rule 4: label left, value right, numbers aligned. A critical value is
 *  named in words as well as coloured (§95). */
export function Values({ rows }: { rows: { link_id: string; label: string; value: string; crit: boolean }[] }) {
  if (!rows.length) return null;
  return (
    <div className="kv">
      {rows.map((r) => (
        <div className="kv__row" key={r.link_id} data-critical={r.crit}>
          <span className="kv__label">{r.label}</span>
          <span className="kv__value">
            {r.value}
            {r.crit && <span className="status" data-tone="critical" style={{ marginLeft: 8 }}>Critical</span>}
          </span>
        </div>
      ))}
    </div>
  );
}
