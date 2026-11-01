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

/** Where Eka sends the browser once the cookie is set: back here.
 *
 *  `next` is required -- the login answers 400 without one -- and it has to
 *  be an address that RESOLVES, which is what went wrong before. Eka's own
 *  default for dev is `https://docapp.eka.care`, read off the redirect
 *  login.dev.eka.care issues for itself, and that name has no DNS record at
 *  all: signing in worked and then dropped the frame on "server IP address
 *  could not be found". Production's default, `https://dr.eka.care`, is a
 *  real host but it is somebody else's dashboard.
 *
 *  So it comes back here. This origin certainly resolves -- the browser is
 *  already on it -- and the login accepts it: it answers 200 for a `next`
 *  of this app's own address.
 */
export function returnTo(origin: string, path: string): string {
  return origin + path;
}

/** Did this page load because the login sent the browser back to it?
 *
 *  Eka appends `mode=login` to the return address, which is visible in the
 *  `next_url` its own page computes. Inside the frame, that pair -- framed,
 *  and carrying Eka's marker -- is the whole app being asked to load itself
 *  inside its own sign in screen, which it must not do. It draws one line
 *  instead, and the page around the frame notices the cookie and moves on.
 *
 *  BOTH HALVES MATTER. Framed alone is not enough: this app could one day
 *  be embedded somewhere on purpose. The marker alone is not enough either:
 *  it is on the address bar of the real page too once the login has been
 *  through it.
 */
export function cameBackFromLogin(search: string, framed: boolean): boolean {
  return framed && new URLSearchParams(search).get("mode") === "login";
}

/** Where the login goes.
 *
 *  `audience` is the surface asking, the same id every request carries, and
 *  `next` is where Eka sends the browser afterwards. See `returnTo`.
 */
export function loginUrl(env: string | undefined, clientId: string, back: string): string {
  const next = encodeURIComponent(back);
  return `${loginBase(env)}/auth/login?audience=${encodeURIComponent(clientId)}&next=${next}`;
}
