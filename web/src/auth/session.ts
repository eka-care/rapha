/** The Eka session, replicated from nectar's claims product.
 *
 *  WHAT NECTAR ACTUALLY DOES, because it is not a login screen. The claims
 *  app (apps/nhcx) is a microfrontend: the host hands it a token on the URL,
 *  every request carries the `.eka.care` cookie and a `client-id` header, and
 *  on a 401 it calls refresh-token once and retries. Signing in happens on
 *  Eka's own login, elsewhere. apps/abdm-parent/src/main.ts is the same thing
 *  with the native bridges in front, and this file is that file's rules.
 *
 *  WHAT THIS GATES, SAID PLAINLY. The screen, and not the kernel. Nectar's
 *  API is Eka's, so Eka validates the cookie on every call; this kernel is
 *  its own service on its own port and cannot validate an Eka cookie, so it
 *  still takes a caller's word for who they are -- see `caller()` in
 *  api/main.py, which says so too. Anybody who can reach the port can still
 *  reach the data with curl. The owner chose this knowing it on 2026-11-01,
 *  and the honest thing is to write it here rather than let a sign-in screen
 *  imply otherwise.
 *
 *  Running it locally needs what nectar needs, and for the same reason: the
 *  cookie belongs to `.eka.care`, so the dev server has to be on a subdomain
 *  of it over https, and the browser has to have signed in to the Eka portal
 *  already. There is no debug mode and no hardcoded token here either.
 */
import { apiBase, clientIdFor, loginBase } from "./client";

export const ENV = import.meta.env.VITE_APP_ENV as string | undefined;
export const API_BASE = apiBase(ENV);
export const LOGIN_URL = loginBase(ENV);
export const CLIENT_ID = clientIdFor(
  navigator.userAgent,
  "ontouchend" in document,
);

const REFRESH_URL = `${API_BASE}/connect-auth/v1/account/refresh-token`;

/** The native bridges, tried before the cookie.
 *
 *  An app has the session, not the web view, so on Android and iOS the host
 *  is asked to renew it and answers through a callback on `window`. Carried
 *  from nectar unchanged, including that the message to the parent goes out
 *  before the bridge call. */
let waiting: Array<(ok: boolean) => void> = [];

function answered() {
  waiting.forEach((resolve) => resolve(true));
  waiting = [];
}

function throughTheApp(): Promise<boolean> {
  const w = window as unknown as Record<string, any>;

  if (typeof w.Eka?.updateToken === "function") {
    window.parent?.postMessage({ type: "REFRESH_TOKEN" }, "*");
    w.refreshCallback = w.refreshCallback ?? answered;
    return new Promise((resolve) => {
      waiting.push(resolve);
      w.Eka.updateToken("refreshCallback");
    });
  }

  if (typeof w.webkit?.messageHandlers?.statusCodeHandler?.postMessage === "function") {
    window.parent?.postMessage({ type: "REFRESH_TOKEN" }, "*");
    w.refreshCallback = w.refreshCallback ?? answered;
    return new Promise((resolve) => {
      waiting.push(resolve);
      w.webkit.messageHandlers.statusCodeHandler.postMessage(
        JSON.stringify({ status: 401 }),
      );
    });
  }

  return Promise.resolve(false);
}

/** What the last ask came back as, for a screen that has to say so.
 *
 *  A SIGN IN THAT DOES NOTHING IS THE WORST ANSWER THERE IS. The way in used
 *  to ask this question every couple of seconds and throw away everything
 *  but yes or no, so somebody who had signed in to Eka and was still looking
 *  at the sign in screen had nothing to go on and neither did anybody
 *  helping them. The number Eka gave is kept now, and shown.
 */
export interface Answer {
  /** A session, or not. */
  ok: boolean;
  /** Eka's own status, or "no answer" when the call never arrived. */
  said: number | "no answer" | "the app";
}

/** A new token, or not, and what Eka said. The app first, then the cookie. */
export async function probe(): Promise<Answer> {
  if (await throughTheApp()) return { ok: true, said: "the app" };
  try {
    const res = await fetch(REFRESH_URL, {
      method: "POST",
      credentials: "include",
      headers: { "client-id": CLIENT_ID },
    });
    return { ok: res.ok, said: res.status };
  } catch {
    // Cross origin, so a refused refresh and an unreachable Eka arrive the
    // same way. Neither is a session, and neither carries a status.
    return { ok: false, said: "no answer" };
  }
}

/** A new token, or false. */
export async function refresh(): Promise<boolean> {
  return (await probe()).ok;
}

/** Is somebody signed in?
 *
 *  Asked by refreshing, because there is no cheaper question: a refresh that
 *  succeeds proves the cookie is good, and one that fails is the same answer
 *  a 401 would give. nectar never asks separately either -- it calls the API
 *  it wants and refreshes when that is refused.
 */
export const signedIn = refresh;

/* NECTAR'S RETRY WRAPPER IS NOT HERE, and that is deliberate.
 *
 * `baseQueryWithReauth` in apps/abdm/src/features/api/baseApi.ts refreshes
 * and retries once on 401, 403 or a fetch that threw. It wraps calls to
 * EKA's API, which is the only API that app has. This app's data calls go to
 * its own kernel, and wrapping those would be wrong twice over: an Eka token
 * does not fix a kernel refusal, and a 403 there is the guard saying a
 * capability is missing -- replaying a refused write is the one thing a
 * retry must never do.
 *
 * So the rule lives in client.ts as `worthRefreshing`, checked, ready for
 * the first browser call to Eka that needs it, and nothing here pretends to
 * use it. An engine with no caller is an engine somebody calls by accident.
 */
