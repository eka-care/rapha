/** The root: routing, the four loads, and the state that outlives a screen.
 *
 *  Everything drawn below comes from a declaration. This file knows there are
 *  views, threads and operations; it does not know what any of them are called.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, currentRole, useAsync } from "../api";
import { ask } from "../ask";
import { createLabel, firstOperation } from "../search";
import { displayFor, load as loadDeclarations, questionnaire } from "../declarations";
import { deskTitle } from "../desk";
import { keep, type Recent } from "../loops";
import { header, queueViewFor, type Ctx, type Said } from "../messages";
import { say } from "../announce";
import { Announcer, Boundary, Failed, Loading, PageTitle } from "../parts";
import { Encounter } from "../screens/Encounter";
import { Desk } from "../screens/Desk";
import { ListScreen } from "../screens/ListScreen";
import { Patient } from "../screens/Patient";
import { Patients } from "../screens/Patients";
import { seenTour, Tour } from "./Tour";
import { gateApplies } from "../auth/client";
import { SignIn } from "../auth/SignIn";
import { signedIn } from "../auth/session";
import { Roles } from "../screens/Settings";
import { Today } from "../screens/Today";
import type { Facility, QueueRow, ViewDecl, ViewResult, Workflow } from "../types";
import { IconSheet } from "../icons";
import { Khoj } from "./Khoj";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type Route =
  | { kind: "today" }
  | { kind: "view"; id: string }
  | { kind: "thread"; id: string }
  | { kind: "patient"; id: string }
  | { kind: "patients" }
  | { kind: "desk" }
  | { kind: "settings" }
  | { kind: "notfound"; id: string };

function parse(hash: string): Route {
  const [head, id] = hash.replace(/^#\/?/, "").split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  if (head === "patients" && id) return { kind: "patient", id };
  // The register itself, which is the top of the patients hierarchy.
  if (head === "patients") return { kind: "patients" };
  if (head === "settings") return { kind: "settings" };
  if (head === "desk") return { kind: "desk" };
  if (!head || head === "today") return { kind: "today" };
  // A second segment under an unrecognised first one is a malformed route,
  // not a bare view id. Guessing is how an empty thread id once reached the
  // API as `views/thread/`.
  if (id) return { kind: "notfound", id: hash };
  return { kind: "view", id: head };
}

const go = (hash: string) => { location.hash = hash.replace(/^#/, ""); };

// ---- things that outlive a screen -----------------------------------------

const SAID_KEY = "phc.said";
const RECENT_KEY = "phc.recents";
const THEME_KEY = "phc.theme";

const read = <T,>(key: string, fallback: T): T => {
  try { return JSON.parse(localStorage.getItem(key) || "") as T; } catch { return fallback; }
};
const save = (key: string, v: unknown) => {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* private window */ }
};

/** Light, dark, or whatever the device is set to -- and the device is the
 *  default, which it was not.
 *
 *  `data-theme` was written on every load, pinned to light, so a phone or a
 *  laptop in dark mode got the light palette and the whole dark half of
 *  tokens.css only ever appeared if somebody found the moon button. The
 *  token contract has three states for this reason: no attribute means
 *  follow `prefers-color-scheme`, and the attribute is an override a person
 *  asked for. So nothing is written until they ask.
 */
type Theme = "system" | "light" | "dark";

const systemDark = () =>
  typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;

function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => read<Theme>(THEME_KEY, "system"));
  // What is actually on screen, which is what the button has to flip. Kept in
  // state so that a device changing its own setting redraws the icon.
  const [dark, setDark] = useState(() => (theme === "system" ? systemDark() : theme === "dark"));

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    save(THEME_KEY, theme);
    setDark(theme === "system" ? systemDark() : theme === "dark");
  }, [theme]);

  useEffect(() => {
    if (theme !== "system" || typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [theme]);

  return [dark ? "dark" : "light", () => setTheme(dark ? "light" : "dark")] as const;
}

export function App() {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);

  const [theme, flipTheme] = useTheme();

  /** The Eka session, nectar's way: there is no login form here, only the
   *  question of whether one was done on Eka. `null` is "still asking".
   *
   *  It gates this SCREEN. The kernel is its own service and cannot check an
   *  Eka cookie, so it still takes a caller's word -- web/src/auth/session.ts
   *  says so at length, and so does `caller()` in api/main.py. */
  const [session, setSession] = useState<boolean | null>(
    () => (gateApplies(location.hostname) ? null : true));
  const askSession = useCallback(() => {
    setSession(null);
    void signedIn().then(setSession);
  }, []);
  useEffect(() => {
    if (gateApplies(location.hostname)) askSession();
  }, [askSession]);
  /** The tour runs once, on a person's first load, and only once the screen
   *  has something to point at. Nothing reopens it: a tour that comes back
   *  is an interruption, and the control panel is where it starts again. */
  const [tour, setTour] = useState(() => !seenTour());
  const [khojOpen, setKhojOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [said, setSaid] = useState<Record<string, Said[]>>(() => read(SAID_KEY, {}));
  const [recents, setRecents] = useState<Recent[]>(() => read(RECENT_KEY, []));
  const [asking, setAsking] = useState(false);
  const [nonce, setNonce] = useState(0);

  const facility = useAsync(() => api.facility(), []);
  const cat = useAsync(() => api.catalogue(), []);
  // The forms, before the first screen draws. They used to be compiled into
  // the browser bundle from questionnaires/*.json, which meant the one part
  // of a screen the kernel did not serve was what it asked a clinician.
  const decls = useAsync(() => loadDeclarations(api), []);

  // §35: ⌘K from anywhere.
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setKhojOpen(true);
      }
    };
    addEventListener("keydown", on);
    return () => removeEventListener("keydown", on);
  }, []);

  const navViews = useMemo<ViewDecl[]>(() => facility.data?.views ?? [], [facility.data]);

  // Every declared view, loaded once, because the sidebar's counts, Today and
  // the command bar all read the same rows and loading them three times would
  // show three different numbers.
  const [loaded, setLoaded] = useState<{ decl: ViewDecl; result: ViewResult }[]>([]);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  // Whether that load is still running. Without it the home screen draws
  // itself out of an empty array -- nobody in the facility, every station
  // clear, "you're clear" -- which is a lie told confidently and is
  // indistinguishable from a kernel that is down.
  const [loadingViews, setLoadingViews] = useState(true);
  useEffect(() => {
    if (!navViews.length) return;
    let live = true;
    setLoadingViews(true);
    Promise.all(navViews.map((decl) =>
      api.view(decl.id).then(
        (result) => ({ decl, result }),
        () => null,
      )))
      .then((all) => {
        if (!live) return;
        const good = all.filter(Boolean) as { decl: ViewDecl; result: ViewResult }[];
        setLoaded(good);
        setLoadingViews(false);
        setLoadError(good.length ? null : new ApiError("No view answered.", "Check the kernel is running."));
      });
    return () => { live = false; };
  }, [navViews, nonce]);

  // SC 4.1.3: a write anywhere re-reads every list, and the number in the
  // rail changes under a person who is looking at something else. The first
  // read is not announced -- arriving on a screen and being told what is on
  // it is the screen's job, not a status message's.
  const announced = useRef(false);
  useEffect(() => {
    if (loadingViews) return;
    if (!announced.current) { announced.current = true; return; }
    const n = loaded.filter((l) => l.decl.kind === "queue")
      .reduce((t, l) => t + ((l.result.rows ?? []) as unknown[]).length, 0);
    say(n === 1 ? "1 in the workspace." : `${n} in the workspace.`);
  }, [loaded, loadingViews]);

  const liveThreads = useMemo(
    () => loaded.filter((l) => l.decl.kind === "queue")
      .flatMap((l) => ((l.result.rows ?? []) as QueueRow[]).map((r) => r.thread)),
    [loaded],
  );
  const shownRecents = useMemo(() => keep(recents, liveThreads), [recents, liveThreads]);

  /** The line, out of the rows already loaded for the counts. One fetch, one
   *  order, one set of rows: the rail and the view behind it cannot disagree
   *  about who is waiting. */
  const line = useMemo(
    // The CATALOGUE's declaration, not the short form `/facility` sends. The
    // short one carries a title and a kind; `columns` and `labels` -- which
    // say what a row is called and which of its values earn a filter chip --
    // come with the full one, and without them the rail could draw a row but
    // not narrow the line.
    () => loaded.filter((l) => l.decl.kind === "queue")
      .flatMap((l) => {
        const decl = cat.data?.views?.[l.decl.id] ?? l.decl;
        return ((l.result.rows ?? []) as QueueRow[]).map((row) => ({ decl, row }));
      }),
    [loaded, cat.data],
  );


  const remember = useCallback((r: Recent) => {
    setRecents((was) => {
      const next = [r, ...was.filter((x) => x.id !== r.id)].slice(0, 8);
      save(RECENT_KEY, next);
      return next;
    });
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  if (facility.loading || cat.loading || decls.loading) {
    return <main className="view scroll"><div className="wrap"><Loading what="the workspace" shape="blocks" rows={3} /></div></main>;
  }
  if (facility.error || cat.error || decls.error) {
    return (
      <main className="view scroll"><div className="wrap">
        <Failed error={(facility.error ?? cat.error ?? decls.error)!} what="reach the kernel" onRetry={() => location.reload()} />
      </div></main>
    );
  }

  const catalogue = cat.data!;
  const ctx: Ctx = {
    operations: catalogue.operations ?? {},
    schema: questionnaire,
    display: displayFor,
    badges: queueViewFor(catalogue, facility.data?.bundle.workflow)?.badges ?? {},
  };

  const onSay = async (thread: string, text: string) => {
    const at = new Date().toISOString();
    const mine: Said = { id: `u-${at}`, at, who: "user", text, actor: "You" };
    setSaid((was) => {
      const next = { ...was, [thread]: [...(was[thread] ?? []), mine] };
      save(SAID_KEY, next);
      return next;
    });
    setAsking(true);
    try {
      const answer = await ask({ utterance: text, thread, role: currentRole() });
      const back: Said = {
        id: `a-${Date.now()}`, at: new Date().toISOString(),
        who: "agent", text: answer.said, actor: "Agent",
      };
      setSaid((was) => {
        const next = { ...was, [thread]: [...(was[thread] ?? []), back] };
        save(SAID_KEY, next);
        return next;
      });
      // SC 4.1.3: the answer appears at the bottom of a thread nobody's focus
      // is in. It is the agent's own sentence, not a word invented here.
      say(answer.said);
      // A turn that proposed something changed the thread, so re-read it.
      if (answer.proposed > 0) reload();
    } finally {
      setAsking(false);
    }
  };

  // The desk is titled by the STATION a patient reaches first, which is the
  // workflow's first step and is what that screen is. It used to wear the
  // declared title of the operation its panel commits through -- "Register a
  // new patient" -- so the screen was called by the name of one of the two
  // things it does, and called that while a clerk was searching for somebody
  // who is already registered. See desk.deskTitle. The operation's title has
  // not moved: it is still the name of the panel. Every other route is
  // titled the way it always was.
  const deskOp = catalogue.operations?.[firstOperation(catalogue, facility.data?.bundle.workflow) ?? ""];
  const title = route.kind === "desk"
    ? (deskTitle(catalogue, facility.data?.bundle.workflow)
       || deskOp?.title || createLabel(catalogue, facility.data?.bundle.workflow))
    : titleFor(route, navViews);

  // The queue this desk is the front of, read once with every other view so
  // the rail, the home screen and the desk cannot show three numbers.
  const deskQueue = queueViewFor(catalogue, facility.data?.bundle.workflow);
  const deskRows = (loaded.find((l) => l.decl.id === deskQueue?.id)?.result.rows ?? []) as QueueRow[];

  // No Eka session: the one screen there is to show. In front of everything,
  // because a sign-in behind a half drawn workspace is not a sign-in.
  if (session !== true) {
    return (
      <div className="app">
        <IconSheet />
        <SignIn checking={session === null} onRetry={askSession} />
      </div>
    );
  }

  return (
    <div className="app">
      <IconSheet />
      {/* SC 2.4.2: every screen was called "Workspace", so a person with the
          queue and a patient open in two tabs could not tell them apart. Both
          halves of this are declarations: the screen's own name, and the
          facility's -- which is where that word earns its place, rather than
          under the title on every screen. */}
      <PageTitle title={facility.data?.bundle.title ? `${title} · ${facility.data.bundle.title}` : title} />
      <Announcer />
      {/* SC 2.4.1: the rail repeats on every screen, and until now the only
          way past it was to tab through all of it. A link and not an anchor,
          because the address bar is this app's router and #workspace would
          be read as a route. */}
      <button
        className="skiplink"
        onClick={() => document.getElementById("workspace")?.focus()}
      >
        Skip to the workspace
      </button>
      <Sidebar
        facility={facility.data}
        route={location.hash.replace(/^#\/?/, "")}
        line={line}
        open={drawer}
        onGo={go}
        onCall={(token) => { setKhojOpen(false); go(`#/desk?q=${encodeURIComponent(token)}`); }}
        onCloseDrawer={() => setDrawer(false)}
      />
      {tour && <Tour onClose={() => setTour(false)} />}
      {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}
      <div className="main">
        <Topbar
          title={title}
          theme={theme}
          views={navViews}
          route={location.hash.replace(/^#\/?/, "")}
          deskLabel={createLabel(catalogue, facility.data?.bundle.workflow)}
          onSearch={() => setKhojOpen(true)}
          onTheme={flipTheme}
          onMenu={() => setDrawer((d) => !d)}
          onGo={go}
          onDesk={() => go("#/desk")}
          onSettings={() => go("#/settings")}
        />
        <main id="workspace" tabIndex={-1} className={route.kind === "thread" ? "view" : "view scroll"}>
          <div className="wrap">
          <Boundary>
            {route.kind === "thread" ? (
              <ThreadScreen
                id={route.id} cat={catalogue} ctx={ctx} nonce={nonce}
                said={said[route.id] ?? []} asking={asking}
                onSay={(t) => onSay(route.id, t)}
                onChanged={reload}
                onOpenSubject={(sid) => go(`#/patients/${sid}`)}
                onRemember={remember}
                catchment={facility.data?.catchment}
              />
            ) : (
              <div>
                {route.kind === "today" && (
                  <Today
                    loaded={loaded} loading={loadingViews} recents={shownRecents}
                    cat={catalogue}
                    onOpenThread={(t) => go(`#/threads/${t}`)}
                    onGoView={(v) => go(`#/views/${v}`)}
                    onAsk={(q) => {
                      // An empty question is the hero's ask box being tapped:
                      // that opens the command bar rather than asking nothing.
                      if (!q) { setKhojOpen(true); return; }
                      const first = shownRecents[0]?.id ?? liveThreads[0];
                      if (first) { go(`#/threads/${first}`); onSay(first, q); }
                    }}
                  />
                )}
                {route.kind === "view" && (
                  <ViewScreen
                    id={route.id} nonce={nonce}
                    decl={catalogue.views?.[route.id]}
                    workflow={catalogue.workflows?.[catalogue.views?.[route.id]?.workflow ?? ""]}
                  />
                )}
                {route.kind === "patient" && (
                  <Patient id={route.id} cat={catalogue} onOpenThread={(t) => go(`#/threads/${t}`)} />
                )}
                {route.kind === "patients" && (
                  <Patients
                    cat={catalogue}
                    onOpenThread={(t) => go(`#/threads/${t}`)}
                    onOpenSubject={(sid) => go(`#/patients/${sid}`)}
                  />
                )}
                {route.kind === "desk" && (
                  <Desk
                    cat={catalogue}
                    decl={deskQueue}
                    workflow={facility.data?.bundle.workflow}
                    client={api}
                    queue={deskRows}
                    loadingQueue={loadingViews}
                    onOpenThread={(t) => { reload(); go(`#/threads/${t}`); }}
                  />
                )}
                {route.kind === "settings" && (
                  <Roles
                    client={api} cat={catalogue}
                    roleIds={facility.data?.roles ?? []}
                    facility={{
                      withheld: facility.data?.withheld ?? {},
                      without: facility.data?.without ?? {},
                    }}
                    onClose={() => go("#/")}
                  />
                )}
                {route.kind === "notfound" && (
                  <div className="notice" role="alert">
                    <div className="t-strong">Nothing at {route.id}.</div>
                    <div className="t-body">Check the address, or pick something from the list on the left.</div>
                  </div>
                )}
                {loadError && route.kind === "today" && (
                  <Failed error={loadError} what="load your lists" onRetry={reload} />
                )}
              </div>
            )}
          </Boundary>
          </div>
        </main>
      </div>

      {khojOpen && (
        <Khoj
          queues={loaded.filter((l) => l.decl.kind === "queue")}
          nav={navViews}
          cat={catalogue}
          workflow={facility.data?.bundle.workflow}
          onClose={() => setKhojOpen(false)}
          onOpenThread={(t) => go(`#/threads/${t}`)}
          onGoView={(v) => go(v ? `#/views/${v}` : "#/")}
          onAnswer={async (question) => {
            // The visit a question is about, as far as this box can tell:
            // the one somebody had open, else the first on today's line. The
            // answer names it, so a wrong guess is visible rather than
            // silent.
            const thread = shownRecents[0]?.id ?? liveThreads[0];
            if (!thread) return null;
            const got = await ask({ utterance: question, thread, role: currentRole() });
            return { said: got.said, thread };
          }}
          /* A search miss goes to the desk, not straight to an empty visit.
             The palette searches today's line; the desk searches the whole
             register and the patient directory, so "no matching patient" in
             here is not yet an answer about whether this person exists. */
          onCreate={() => go("#/desk")}
        />
      )}
    </div>
  );
}

function titleFor(route: Route, views: ViewDecl[]): string {
  if (route.kind === "today") return "Today";
  if (route.kind === "settings") return "Settings";
  if (route.kind === "view") return views.find((v) => v.id === route.id)?.title ?? "List";
  if (route.kind === "thread") return "Encounter";
  if (route.kind === "patients") return "Patients";
  if (route.kind === "patient") return "Patient";
  return "Not found";
}

function ViewScreen({ id, decl, workflow, nonce }: {
  id: string; decl?: ViewDecl; workflow?: Workflow; nonce: number;
}) {
  const { data, error, loading, reload } = useAsync(() => api.view(id), [id, nonce]);
  if (loading) return <Loading what="this list" shape="rows" rows={5} />;
  if (error) return <Failed error={error} what="load this list" onRetry={reload} />;
  return (
    <ListScreen
      result={data!} decl={decl} workflow={workflow}
      onOpenThread={(t) => go(`#/threads/${t}`)}
    />
  );
}

function ThreadScreen({ id, cat, ctx, said, asking, nonce, catchment, onSay, onChanged, onRemember, onOpenSubject }: {
  id: string; cat: ReturnType<typeof Object>; ctx: Ctx; said: Said[];
  asking: boolean; nonce: number;
  catchment?: Facility["catchment"];
  onSay: (t: string) => void; onChanged: () => void; onRemember: (r: Recent) => void;
  onOpenSubject: (subjectId: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.thread(id), [id, nonce]);
  // header() already answers "what is this thread called", using the queue
  // declaration's own column order. Picking the first string off the subject
  // instead -- which is what this did -- returns the encounter id, because
  // that is the first key the adapter puts in the subject dict.
  const name = data ? header(data, queueViewFor(cat as never, data.workflow), displayFor).name : id;
  useEffect(() => { if (data) onRemember({ id, name }); }, [data, id, name, onRemember]);

  if (loading) return <Loading what="this encounter" shape="messages" rows={3} />;
  if (error) return <Failed error={error} what="open this encounter" onRetry={reload} />;
  return (
    <Encounter
      thread={data!}
      cat={cat as never}
      ctx={ctx}
      client={api}
      said={said}
      asking={asking}
      catchment={catchment}
      onSay={onSay}
      onChanged={() => { reload(); onChanged(); }}
      onOpenSubject={onOpenSubject}
    />
  );
}
