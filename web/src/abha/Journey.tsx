/** The real ABHA journey, mounted. One component, one journey in the product.
 *
 *  This replaces a hand built form that had a "Journey" dropdown, a bare ABHA
 *  number field and a consent checkbox, and that could not create an ABHA at
 *  all. Eka ships the journey; imitating it was the bug.
 *
 *  The safety rule is the instrument rule and it is unchanged. This component
 *  has no client, calls no commit and no confirm, and cannot write. What it
 *  produces is values, which land in the panel's ordinary editable fields and
 *  are committed by the panel's own tap, behind the irreversible confirm. Same
 *  shape as web/src/scribe/Recorder.tsx, for the same reason.
 *
 *  Which SDK is loaded is the server's answer (GET /abha/config), so the
 *  environment is a setting and no client id is baked into this bundle. It is
 *  on screen as a chip, and it defaults to staging: a production ABHA journey
 *  sends a real one time password to a real phone and creates a permanent
 *  national health account, which is the one line that stays a sentence.
 */
import { useEffect, useId, useRef, useState } from "react";
import { API_BASE } from "../api";
import {
  environmentLine, identifierFrom, loadFailure,
  type AbhaConfig, type AbhaOutcome,
} from "./sdk";
import "./abha.css";

declare global {
  interface Window {
    initAbhaApp?: (options: Record<string, unknown>) => () => void;
    closeAbhaApp?: () => void;
  }
}

/** One script and one stylesheet per page, however many panels open. Keyed by
 *  url, so switching ABHA_ENV on the server and reloading gets the other one.
 */
const loading = new Map<string, Promise<void>>();

function load(config: AbhaConfig): Promise<void> {
  const held = loading.get(config.script);
  if (held) return held;
  const started = new Promise<void>((resolve, reject) => {
    if (!document.querySelector(`link[href="${config.css}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = config.css;
      document.head.appendChild(link);        // a missing stylesheet is ugly, not fatal
    }
    if (typeof window.initAbhaApp === "function") return resolve();
    const script = document.createElement("script");
    script.src = config.script;
    script.async = true;
    script.onload = () =>
      typeof window.initAbhaApp === "function"
        ? resolve()
        : reject(new Error("the script loaded and defined no initAbhaApp"));
    script.onerror = () => reject(new Error("the browser could not fetch it"));
    document.head.appendChild(script);
  });
  // A failed load is not cached: the next panel should try again rather than
  // inherit somebody else's dead network.
  started.catch(() => loading.delete(config.script));
  loading.set(config.script, started);
  return started;
}

export function Journey({
  onOutcome, onSkipPath, mobile,
}: {
  /** Every outcome, including the ones that are not a link. The panel decides
   *  what to do with each; this component never writes. */
  onOutcome: (outcome: AbhaOutcome) => void;
  /** "Register without an ABHA", one tap, from any outcome that is not a link.
   *  It has to be exactly as easy as finishing the journey. */
  onSkipPath?: () => void;
  /** A mobile number the clerk has already typed, from the search that missed.
   *  Handing it over saves typing it a second time at the counter. */
  mobile?: string;
}) {
  const [config, setConfig] = useState<AbhaConfig | null>(null);
  const [failure, setFailure] = useState("");
  const [outcome, setOutcome] = useState<AbhaOutcome | null>(null);
  const [mounted, setMounted] = useState(false);
  // React's useId contains colons. getElementById takes an id and not a
  // selector so it would work, but the SDK also writes CSS against it, so this
  // stays boring.
  const container = `abha-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  /** The SDK fires onAbhaClose after a success and again after a skip, and it
   *  fired it TWICE on one skip in a browser. First outcome wins; the rest are
   *  dropped. Without this a completed link is followed by "closed before it
   *  finished" and the person believes the second sentence. */
  const settled = useRef(false);
  const unmount = useRef<(() => void) | null>(null);

  const settle = (next: AbhaOutcome) => {
    if (settled.current) return;
    settled.current = true;
    setOutcome(next);
    setMounted(false);
    onOutcome(next);
  };
  const latest = useRef(settle);
  latest.current = settle;

  useEffect(() => {
    let live = true;
    settled.current = false;

    (async () => {
      let got: AbhaConfig;
      try {
        const res = await fetch(`${API_BASE}/api/v1/phc/abha/config`);
        if (!res.ok) throw new Error(`the kernel answered ${res.status}`);
        got = (await res.json()) as AbhaConfig;
      } catch (e) {
        console.warn("abha config", e);
        if (live) setFailure(loadFailure(null));
        return;
      }
      if (!live) return;
      setConfig(got);

      try {
        await load(got);
      } catch (e) {
        console.warn("abha sdk", e);
        if (live) setFailure(loadFailure(got));
        return;
      }
      if (!live || typeof window.initAbhaApp !== "function") return;

      unmount.current = window.initAbhaApp({
        clientId: got.client_id,
        containerId: container,
        method: "login_or_create_abha",
        ...(got.theme ? { theme: got.theme } : {}),
        data: {
          // The SDK's own skip, which is the whole of "register now, link
          // later". Without this the journey has no way out but a failure.
          skipABHAEnable: true,
          // What the clerk already typed into the palette. `mobile` seeds the
          // store's identifier value and `identifier`/`identifier_type` go to
          // the SDK's own handleIdentifier, which is the one that selects the
          // mobile journey; the bundle reads all three off `data`.
          ...(mobile ? { mobile, identifier: mobile, identifier_type: "mobile" } : {}),
          ...(got.hip_id ? { hipId: got.hip_id } : {}),
        },
        // The bundle reads the caller's `onSuccess` and calls it internally as
        // onAbhaSuccess. There is no onAbhaFailure prop; `onError` is it.
        onSuccess: (raw: unknown) => {
          latest.current({ kind: "linked", raw, ...identifierFrom(raw) });
        },
        onError: (e: { error?: string } | string) => {
          const reason = typeof e === "string" ? e : e?.error || "The journey reported an error.";
          latest.current({ kind: "failed", reason });
        },
        onSkipAbha: (s: { identifier?: string; identifier_type?: string }) =>
          latest.current({
            kind: "skipped",
            identifier: s?.identifier ?? "",
            identifier_type: s?.identifier_type ?? "",
          }),
        onAbhaClose: () => latest.current({ kind: "closed" }),
      });
      if (live) setMounted(true);
    })();

    return () => {
      live = false;
      // The SDK unmounts itself on every terminal outcome, so unmounting again
      // here would be a second unmount of a root React has already dropped.
      if (!settled.current) {
        try {
          unmount.current?.();
        } catch {
          /* already gone */
        }
      }
      unmount.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const env = config ? environmentLine(config) : null;

  return (
    <div className="abha">
      {/* A chip, and no heading over it: the panel title above already says
          this is the ABHA journey. The package name is the chip's tooltip. */}
      {env && (
        <div className="abha-bar" title={config?.package}>
          <span className={env.danger ? "abha-env danger" : "abha-env"}>{env.text}</span>
        </div>
      )}

      {failure ? (
        <div className="abha-note bad">
          <div>{failure}</div>
          {onSkipPath && (
            <button className="cq" onClick={onSkipPath}>Register without an ABHA</button>
          )}
        </div>
      ) : (
        <>
          {!mounted && !outcome && <div className="abha-note">Loading</div>}
          {outcome?.kind === "failed" && <div className="abha-note bad">{outcome.reason}</div>}
          {/* Kept in the tree whatever happens: the SDK holds a React root on
              this node and removing it from under React is how a blank modal
              happens. It is emptied by the SDK itself on a terminal outcome. */}
          <div id={container} className={mounted ? "abha-mount live" : "abha-mount"} />
          {outcome && outcome.kind !== "linked" && onSkipPath && (
            <button className="cq" onClick={onSkipPath}>Register without an ABHA</button>
          )}
        </>
      )}
    </div>
  );
}
