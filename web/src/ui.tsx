/** The three states every screen owes the person, and nothing else. */
import type { ApiError } from "./api";

export function Loading({ what }: { what: string }) {
  return <div className="state">Loading {what}...</div>;
}

/** Never a blank screen and never "something went wrong": what failed, and
 *  the one thing to do about it. */
export function Failed({
  error, onRetry, onDemo, what = "Not loaded",
}: { error: ApiError; onRetry?: () => void; onDemo?: () => void; what?: string }) {
  return (
    <div className="card state bad">
      <div className="eyebrow">{what}</div>
      <div className="state-t">{error.message}</div>
      <p className="state-p">{error.next}</p>
      <div className="state-actions">
        {onRetry && <button className="cq" onClick={onRetry}>Try again</button>}
        {onDemo && <button className="cq rose" onClick={onDemo}>Use demo data</button>}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="card state">{children}</div>;
}

const STYLE: Record<string, string> = { warn: "b-warn", crit: "b-crit", ok: "b-ok", mute: "b-mute", blue: "b-blue" };

export function Badge({ style = "mute", children }: { style?: string; children: React.ReactNode }) {
  return <span className={`badge ${STYLE[style] ?? "b-mute"}`}>{children}</span>;
}

/** Declaration ids are machine names. Nothing but the declaration knows a
 *  human label, so when one is missing this is the least-worst fallback. */
export const human = (id: string | null | undefined) =>
  (id ?? "").replace(/^[a-z0-9]+\.(op|view|wf|inst|metric)\./, "").replace(/[-_.]/g, " ");

/** Same, for somewhere a label starts a line. */
export const title = (id: string | null | undefined) => {
  const s = human(id);
  return s.charAt(0).toUpperCase() + s.slice(1);
};

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
        <p className="state-p">
          Nothing was written and nothing was lost. Reload; if it happens again, this data has a
          shape the renderer does not handle, and the message below says where.
        </p>
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
