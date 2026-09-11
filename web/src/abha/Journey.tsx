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
 *  environment is a setting, no client id is baked into this bundle, and the
 *  environment is on screen in words. It defaults to staging: a production
 *  ABHA journey sends a real one time password to a real phone and creates a
 *  permanent national health account.
 */
import { useEffect, useId, useRef, useState } from "react";
import { API_BASE } from "../api";
import {
  environmentLine, identifierFrom, loadFailure, sentence,
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
  onOutcome, onSkipPath,
}: {
  /** Every outcome, including the ones that are not a link. The panel decides
   *  what to do with each; this component never writes. */
  onOutcome: (outcome: AbhaOutcome) => void;
  /** "Register without an ABHA", one tap, from any outcome that is not a link.
   *  It has to be exactly as easy as finishing the journey. */
  onSkipPath?: () => void;
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
        if (live) setFailure(loadFailure(null, e instanceof Error ? e.message : String(e)));
        return;
      }
      if (!live) return;
      setConfig(got);

      try {
        await load(got);
      } catch (e) {
        if (live) setFailure(loadFailure(got, e instanceof Error ? e.message : String(e)));
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
          // `data.mobile` would prefill the number the patient gave at
          // registration and save them typing it again. Not passed: the panel
          // does not carry the subject, and the SDK asks for it anyway. Worth
          // adding the day somebody times the counter.
          ...(got.hip_id ? { hipId: got.hip_id } : {}),
        },
        // The bundle reads the caller's `onSuccess` and calls it internally as
        // onAbhaSuccess. There is no onAbhaFailure prop; `onError` is it.
        onSuccess: (raw: unknown) => {
          latest.current({ kind: "linked", ...identifierFrom(raw) });
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
      <div className="abha-bar">
        <span className="abha-what">ABHA journey</span>
        {env && (
          <span className={env.danger ? "abha-env danger" : "abha-env"}>{env.text}</span>
        )}
        {config && <span className="abha-pkg">{config.package}</span>}
      </div>

      {failure ? (
        <div className="abha-note bad">
          <div>{failure}</div>
          {onSkipPath && (
            <button className="cq" onClick={onSkipPath}>Register without an ABHA</button>
          )}
        </div>
      ) : (
        <>
          <div className="abha-note">
            {sentence(
              outcome,
              mounted
                ? "Eka's own journey is below and this screen is not driving it. Finish it and the " +
                  "identifier lands in the form here; skip it and the patient is registered, " +
                  "tokened and seen with ABHA pending. Nothing is recorded either way until the " +
                  "tap at the foot of this panel."
                : config
                  ? "Loading the journey."
                  : "Asking the kernel which SDK to load.",
            )}
          </div>
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
