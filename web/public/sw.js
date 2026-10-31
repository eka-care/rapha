/* The service worker, and the one line it will not cross.
 *
 * WHAT IT CACHES. The application itself, and the DECLARATIONS: the compiled
 * catalogue, the questionnaires and the value sets. Those are compiled
 * artifacts with a version on them, identical for every caller, and the whole
 * architecture rests on them being the same document everywhere.
 *
 * WHAT IT NEVER CACHES. Anything about a patient. A queue, a thread, a
 * subject, a search, a proposal, an audit row. Not once, not briefly, not
 * "just the last one".
 *
 * That is not caution, it is the only line that survives contact with a
 * clinic. A stale queue is worse than no queue: it shows a patient still
 * waiting who has been seen, or hides one who is. A stale vital sign is worse
 * still. Offline, this application must say it cannot see the facility rather
 * than show yesterday's facility, and the screens are built to say so.
 *
 * WHAT IT DOES NOT DO. It does not sync in the background. A service worker
 * is not running when the application is closed, Background Sync is not
 * dependable, and claiming otherwise in a village with no signal is how a
 * health worker loses a morning's visits. Work goes out when she next opens
 * this with a signal, and the interface shows her what has not gone.
 *
 * WRITES ARE NOT HELD HERE EITHER. A POST that fails offline is the
 * application's problem, not this file's: it is held in the application's own
 * store, where it can be shown, counted and retried under the guard's rules.
 * A service worker replaying a clinical write that the user can no longer see
 * is exactly the "reported as sent when it was not" failure the outbox was
 * built to prevent.
 */

const VERSION = "v1";
const SHELL = `shell-${VERSION}`;      // the application: HTML, JS, CSS, icons
const DECL = `declarations-${VERSION}`; // catalogue, questionnaires, value sets

/** The declaration reads, by path. Everything else under the API prefix is
 *  about a person and goes straight to the network. Anchored, so a path that
 *  merely CONTAINS one of these words is not matched: `/threads/valuesets` is
 *  not a value set. */
const DECLARATION = [
  /\/api\/v1\/phc\/catalogue\/?$/,
  /\/api\/v1\/phc\/questionnaires\/?$/,
  /\/api\/v1\/phc\/questionnaires\/[^/]+\/?$/,
  /\/api\/v1\/phc\/valuesets\/[^/]+\/?$/,
];

self.addEventListener("install", (e) => {
  // The shell is cached as it is fetched rather than from a list written here.
  // A hand-maintained precache list and a bundler that hashes its filenames
  // disagree on the first build nobody re-checked, and the symptom is a blank
  // screen offline. The one thing worth seeding is the entry document, because
  // a navigation offline has nothing else to fall back to.
  e.waitUntil(caches.open(SHELL).then((c) => c.add("/")).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  const keep = new Set([SHELL, DECL]);
  e.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((n) => !keep.has(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

/** Network first, falling back to what we have. Used for declarations, which
 *  change when a bundle is recompiled: a stale questionnaire would ask a
 *  question the kernel no longer accepts, so the network wins whenever there
 *  is one. */
async function declaration(request) {
  try {
    const fresh = await fetch(request);
    if (fresh.ok) (await caches.open(DECL)).put(request, fresh.clone());
    return fresh;
  } catch (err) {
    const hit = await caches.match(request);
    if (hit) return hit;
    throw err;
  }
}

/** Cache first for the application's own files. They are content-hashed by the
 *  build, so a changed file is a changed URL and this can never serve a stale
 *  one. */
async function shell(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const fresh = await fetch(request);
  if (fresh.ok && fresh.type === "basic") {
    (await caches.open(SHELL)).put(request, fresh.clone());
  }
  return fresh;
}

self.addEventListener("fetch", (e) => {
  const { request } = e;
  if (request.method !== "GET") return;          // every write goes to the network

  const url = new URL(request.url);

  // A single-page application's routes are not files. A navigation that the
  // network cannot answer falls back to the entry document, which then renders
  // the route itself and says what it cannot reach.
  if (request.mode === "navigate") {
    e.respondWith(fetch(request).catch(() => caches.match("/")));
    return;
  }

  if (DECLARATION.some((re) => re.test(url.pathname))) {
    e.respondWith(declaration(request));
    return;
  }

  // Everything else on the API's origin is about a person. Untouched.
  if (url.pathname.startsWith("/api/")) return;

  if (url.origin === self.location.origin) {
    e.respondWith(shell(request));
  }
});
