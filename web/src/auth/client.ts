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


/** May this origin put the Eka login inside a frame?
 *
 *  MEASURED, not assumed. login.dev.eka.care answers with
 *  `frame-ancestors 'self' https://eka.care https://*.dev.eka.care
 *  https://*.eka.care`, so a page on an eka.care subdomain MAY frame it and
 *  everywhere else is refused by the browser with a blank box and a console
 *  line nobody reads. nectar's own eka-relay guessed the other way -- "it
 *  almost certainly blocks framing" -- and opened a popup instead; the
 *  header says otherwise, and the header is what the browser obeys.
 *
 *  The same origins that may frame it are the ones that receive the cookie,
 *  which is not a coincidence: both are `.eka.care` and both are the reason
 *  the dev server is run from a subdomain of it.
 */
export function canFrameLogin(hostname: string): boolean {
  return hostname === "eka.care" || hostname.endsWith(".eka.care");
}

/** Where Eka sends a browser once the cookie is set, by environment.
 *
 *  MEASURED, from the redirect login.eka.care issues for itself:
 *    GET https://login.dev.eka.care/  ->  /auth/login?audience=doc-web&next=https://docapp.eka.care
 *    GET https://login.eka.care/      ->  /auth/login?audience=doc-web&next=https://dr.eka.care
 *  so these two are the return addresses Eka hands out, which means they are
 *  the two it is certain to accept.
 */
export function landingAfterLogin(env: string | undefined): string {
  return env === "PROD" ? "https://dr.eka.care" : "https://docapp.eka.care";
}

/** Where the login goes, for the card on this screen.
 *
 *  `audience` is the surface asking, the same id every request carries, and
 *  `next` is required -- the page answers 400 without one.
 *
 *  WHY `next` IS NOT THIS APP. It used to be, and that was wrong twice.
 *  Once because a login that completed then loaded the whole app INSIDE the
 *  card, an app in a box in the app. And once because `next` is a return
 *  address Eka recognises or does not: login.dev.eka.care answers a path it
 *  does not serve with `{"message":"Forbidden"}`, which is exactly what the
 *  card was showing, and an origin somebody has pointed at their own laptop
 *  is not an address Eka has ever been told about.
 *
 *  So it uses the address Eka itself names, and nothing waits on the
 *  redirect: the cookie is the whole result, and the card is already asking
 *  every couple of seconds whether it has arrived.
 */
export function loginUrl(env: string | undefined, clientId: string): string {
  const next = encodeURIComponent(landingAfterLogin(env));
  return `${loginBase(env)}/auth/login?audience=${encodeURIComponent(clientId)}&next=${next}`;
}
