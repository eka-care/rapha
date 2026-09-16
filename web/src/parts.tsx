/** The small shared pieces: the three states every screen can be in, and the
 *  boundary that keeps one broken screen from blanking the app.
 *
 *  §72 empty, §73 loading, §75 error. The rule those three sections share is
 *  that a screen is never blank and never says "something went wrong":
 *  ApiError already carries a `next` sentence saying what to do, so the error
 *  state's job is to show it, not to invent one.
 */
import { Component, type ReactNode } from "react";
import { ApiError } from "./api";

/** §73: skeletons, never a full-page spinner. */
export function Loading({ what, rows = 3 }: { what: string; rows?: number }) {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="u-sr">Loading {what}</span>
      <div style={{ display: "grid", gap: "var(--space-2)" }}>
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="skeleton" style={{ height: 58, opacity: 1 - i * 0.18 }} />
        ))}
      </div>
    </div>
  );
}

/** §75: what failed, whether the record changed, what to do next. The middle
 *  one is the part products usually drop. A read that failed changed nothing
 *  and should say so, because the alternative is a person re-entering data
 *  they already committed. */
export function Failed({
  error, what, onRetry,
}: { error: ApiError; what?: string; onRetry?: () => void }) {
  return (
    <div className="notice" role="alert">
      <div className="t-strong">{what ? `Unable to ${what}.` : "That did not go through."}</div>
      <div className="t-body">{error.message}</div>
      <div className="t-meta u-mute">Nothing was written.</div>
      <div className="t-body">{error.next}</div>
      {onRetry && <button className="btn" onClick={onRetry}>Retry</button>}
    </div>
  );
}

/** §72: an empty screen is an invitation to act, so it carries the action. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="t-strong">{title}</div>
      {children && <div className="t-body u-mute">{children}</div>}
    </div>
  );
}

export class Boundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="workspace-scroll">
        <div className="notice" role="alert">
          <div className="t-strong">This screen stopped drawing.</div>
          <div className="t-body">{this.state.err.message}</div>
          <div className="t-meta u-mute">Nothing was written. This is a bug in the renderer, not in your data.</div>
          <button className="btn" onClick={() => location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}
