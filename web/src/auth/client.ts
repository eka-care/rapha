/** Which surface is asking, and when a session is worth refreshing.
 *
 *  Both rules are nectar's, from apps/abdm-parent/src/main.ts and
 *  apps/abdm/src/features/api/baseApi.ts, carried here so the claims product
 *  and this one behave the same way in front of the same session. Pure, so
 *  `client.check.ts` runs them with no browser and no network.
 */

/** The four surfaces Eka knows. The iPad is a Macintosh that reports touch,
 *  which is the only way a browser distinguishes it from a laptop; nectar
 *  tests it in exactly this order and so does this. */
export function clientIdFor(userAgent: string, hasTouch: boolean): string {
  if (/Macintosh/.test(userAgent) && hasTouch) return "doctor-ipad-ios";
  if (/iPhone/i.test(userAgent)) return "doctor-app-ios";
  if (/Android/i.test(userAgent)) return "androiddoc";
  return "doc-web";
}

/** Is this answer worth one refresh and one retry?
 *
 *  401 and 403 are the token; "FETCH_ERROR" is nectar's own name for a fetch
 *  that threw, which on a cross origin call is what an expired session looks
 *  like -- the browser reports a CORS failure rather than the 401 underneath
 *  it, so the two are indistinguishable from here and both are tried.
 */
export function worthRefreshing(status: number | "FETCH_ERROR"): boolean {
  return status === 401 || status === 403 || status === "FETCH_ERROR";
}

/** Where Eka is. `VITE_APP_ENV=PROD` is nectar's switch, spelled the same. */
export function apiBase(env: string | undefined): string {
  return env === "PROD" ? "https://api.eka.care" : "https://api.dev.eka.care";
}

/** Where a person signs in, when there is no session to refresh. */
export function loginBase(env: string | undefined): string {
  return env === "PROD" ? "https://login.eka.care" : "https://login.dev.eka.care";
}


/** Does the Eka session gate apply on this origin?
 *
 *  THE COOKIE IS THE WHOLE MECHANISM, and a cookie for `.eka.care` is never
 *  sent to localhost. So on localhost the gate cannot be satisfied by
 *  anybody, ever, and turning it on there does not protect a developer's
 *  machine -- it locks them out of their own screen with no way in. Any real
 *  deployment is not localhost, so the gate is on everywhere else, including
 *  an origin somebody has pointed at a laptop: that is how nectar is
 *  developed, on an `.eka.care` subdomain over https, and the session works
 *  there exactly as it does in production.
 *
 *  Said as one rule in one place so that it is visible, rather than being an
 *  `if` somebody finds later in a component.
 */
export function gateApplies(hostname: string): boolean {
  return !(hostname === "localhost" || hostname === "127.0.0.1"
           || hostname === "[::1]" || hostname === "::1"
           || hostname.endsWith(".localhost"));
}
