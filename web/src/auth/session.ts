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
import { apiBase, clientIdFor, loginBase, whoIsThereUrl, worthRefreshing } from "./client";

export const ENV = import.meta.env.VITE_APP_ENV as string | undefined;
export const API_BASE = apiBase(ENV);
export const LOGIN_URL = loginBase(ENV);
export const CLIENT_ID = clientIdFor(
  navigator.userAgent,
  "ontouchend" in document,
);

const REFRESH_URL = `${API_BASE}/connect-auth/v1/account/refresh-token`;

/** nectar's own hub account, overridable the way it is there. */
const HUB_ACCOUNT = (import.meta.env.VITE_HUB_ACCOUNT_ID as string) ?? "5";
const HUB_URL = whoIsThereUrl(ENV, HUB_ACCOUNT);

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

/** Renew the token. A RETRY, not a question.
 *
 *  This is what refresh-token is for everywhere in nectar, and the only
 *  thing it is for. Asking it whether somebody is signed in is what kept a
 *  signed in person on the sign in screen.
 */
async function renew(): Promise<boolean> {
  try {
    // An empty object, and it has to be there. With a real session Eka
    // answered 400 and said so in as many words:
    //     {"error":{"code":"INVALID_REQUEST","message":"EOF"}}
    // "EOF" is a JSON decoder reaching the end of a body that was never
    // sent. nectar sends none, and nectar only ever calls this as a retry,
    // so nobody there would have seen it.
    const res = await fetch(REFRESH_URL, {
      method: "POST",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Is there a session? Asked by using one, which is nectar's own answer.
 *
 *  The hub read is the question; a refusal worth one retry gets one, and the
 *  renewal above is that retry. Exactly `fetchConfig` in
 *  apps/abdm-parent/src/main.ts, and for the same reason: a session is
 *  proved by a call that needed it succeeding.
 *
 *  The body is never read. With no cookie the hub answers 302 to Eka's own
 *  login and that redirect carries no CORS header, so the browser refuses to
 *  follow it and the fetch throws -- which is why "no answer" here means
 *  turned away at the gate rather than Eka being down.
 */
async function askTheHub(): Promise<Answer> {
  try {
    const res = await fetch(HUB_URL, {
      credentials: "include",
      headers: { "client-id": CLIENT_ID },
    });
    return { ok: res.ok, said: res.status };
  } catch {
    return { ok: false, said: "no answer" };
  }
}

/** A session, or not, and what Eka said. The app first, then the cookie. */
export async function probe(): Promise<Answer> {
  if (await throughTheApp()) return { ok: true, said: "the app" };

  const first = await askTheHub();
  if (first.ok) return first;

  // A cross origin refusal and a cross origin block arrive the same way, so
  // "no answer" is nectar's FETCH_ERROR under another name.
  const why = typeof first.said === "number" ? first.said : ("FETCH_ERROR" as const);
  if (worthRefreshing(why) && await renew()) return askTheHub();
  return first;
}

/** A session, or false. */
export async function refresh(): Promise<boolean> {
  return (await probe()).ok;
}

/** Is somebody signed in?
 *
 *  Asked by reading something that needs a session, because that is the only
 *  honest way to ask: a read that succeeds proves the cookie is good. This
 *  used to ask the refresh route instead, which proved nothing and answered
 *  400 to everybody.
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
 * So the rule lives in client.ts as `worthRefreshing`, and `probe` above is
 * now its one caller: the hub read is a call to Eka's API, so a refusal
 * there IS worth a renewal and a second try. Nothing wraps the kernel's own
 * calls, and nothing should.
 */
