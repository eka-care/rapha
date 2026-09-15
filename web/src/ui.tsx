/** The three states every screen owes the person, and nothing else. */
import type { ApiError } from "./api";

export function Loading({ what }: { what: string }) {
  return <div className="state">Loading {what}...</div>;
}

/** Never a blank screen and never "something went wrong": what failed, and
 *  the one thing to do about it. */
export function Failed({
  error, onRetry, what = "Not loaded",
}: { error: ApiError; onRetry?: () => void; what?: string }) {
  return (
    <div className="card state bad">
      <div className="eyebrow">{what}</div>
      <div className="state-t">{error.message}</div>
      <p className="state-p">{error.next}</p>
      <div className="state-actions">
        {onRetry && <button className="cq" onClick={onRetry}>Try again</button>}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card state">{children}</div>;
}

/** Every badge rank collapses to the one neutral .badge: none of them is a
 *  per-shift clinical escalation, so none may hold a signal colour (the
 *  colour law's one genuine exception, .b-crit[data-act], is a hand-written
 *  span in Form.tsx, never this component). `style` used to select a
 *  b-warn/b-crit/b-ok/b-mute/b-blue suffix class, but four of those five had
 *  no rule in any stylesheet and the fifth (.b-crit) never carried the
 *  [data-act] attribute that would have let it render as anything but
 *  neutral either -- so the lookup changed nothing on any screen it ever
 *  ran on. `style` stays in the type so a caller passing a declared flag's
 *  own colour word still type-checks; it is simply not read. */
export function Badge({ children }: { style?: string; children: React.ReactNode }) {
  return <span className="badge">{children}</span>;
}

export { human, title } from "./words";

/** A render that throws must not leave a white page. React unmounts the whole
 *  tree on an uncaught error, so this is the only place that can promise
 *  "never blank": it catches, names the screen, and offers the way back.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

export class Boundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };

  static getDerivedStateFromError(err: Error) {
    return { err };
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    console.error("renderer crashed", err, info.componentStack);
  }

  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="card state bad">
        <div className="eyebrow">This screen stopped</div>
        <div className="state-t">The renderer could not draw what the API sent.</div>
        <pre className="state-p" style={{ whiteSpace: "pre-wrap", fontSize: 11 }}>
          {this.state.err.message}
        </pre>
        <div className="state-actions">
          <button className="cq rose" onClick={() => location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}
