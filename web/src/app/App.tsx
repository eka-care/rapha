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
import { keep, type Filter, type Recent } from "../loops";
import { header, mentionsOf, queueViewFor, type Ctx, type Said } from "../messages";
import { say } from "../announce";
import { Announcer, Boundary, Failed, Loading, PageTitle } from "../parts";
import { Encounter } from "../screens/Encounter";
import { useLiveScribe } from "../scribe/live";
import { Desk } from "../screens/Desk";
import { ListScreen } from "../screens/ListScreen";
import { Patient } from "../screens/Patient";
import { Patients } from "../screens/Patients";
import { seenTour, Tour } from "./Tour";
import { cameBackFromLogin, gateApplies, rememberSignedOut, signedOutHere } from "../auth/client";
import { SignIn } from "../auth/SignIn";
import { signedIn } from "../auth/session";
import { Control } from "../screens/Control";
import { Today } from "../screens/Today";
import type { Facility, QueueRow, TaskRow, ViewDecl, ViewResult, Workflow } from "../types";
import { IconSheet } from "../icons";
import { Khoj } from "./Khoj";
import { Bell } from "./Bell";
import { Grip } from "./Grip";
import { clampWidth, readWidth, saveWidth } from "./width";
import { Sidebar, panelFor } from "./Sidebar";
import { Garland } from "../auth/Bloom";
import { Rail } from "./Rail";
import { PARTS } from "../screens/Control";
import { NAME } from "../brand";
import { AskAi } from "../assistant/AskAi";
import type { Question } from "../assistant/Lazy";
import { Topbar } from "./Topbar";
import { Profile } from "../auth/Profile";
import { fields } from "../view/View";

type Route =
  | { kind: "today" }
  | { kind: "view"; id: string }
  | { kind: "thread"; id: string }
  | { kind: "patient"; id: string }
  | { kind: "patients" }
  | { kind: "desk"; q: string }
  | { kind: "settings"; part: string }
  | { kind: "notfound"; id: string };

function parse(hash: string): Route {
  // THE QUERY IS NOT PART OF THE PATH, and forgetting that is what broke the
  // one control in the line column: calling token 1 goes to `#/desk?q=1`, the
  // whole of which was read as a first segment, matched nothing, and fell
  // through to the last line of this function as a view id -- so the kernel
  // was asked for `/views/desk?q=1/` and rightly said it had no such view.
  const bare = hash.replace(/^#\/?/, "");
  const cut = bare.indexOf("?");
  const path = cut === -1 ? bare : bare.slice(0, cut);
  const args = new URLSearchParams(cut === -1 ? "" : bare.slice(cut + 1));
  const [head, id] = path.split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  if (head === "patients" && id) return { kind: "patient", id };
  // The register itself, which is the top of the patients hierarchy.
  if (head === "patients") return { kind: "patients" };
  if (head === "settings") return { kind: "settings", part: id ?? "" };
  if (head === "desk") return { kind: "desk", q: args.get("q") ?? "" };
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

  // The control panel sets the three-way preference; the topbar button only
  // flips what is on screen. Both are here so there is one source of it.
  return [dark ? "dark" : "light", () => setTheme(dark ? "light" : "dark"),
          theme, setTheme] as const;
}

export function App() {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  const liveScribe = useLiveScribe();
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);

  const [theme, flipTheme, themePref, setThemePref] = useTheme();

  /** The Eka session, nectar's way: there is no login form here, only the
   *  question of whether one was done on Eka. `null` is "still asking".
   *
   *  It gates this SCREEN. The kernel is its own service and cannot check an
   *  Eka cookie, so it still takes a caller's word -- web/src/auth/session.ts
   *  says so at length, and so does `caller()` in api/main.py. */
  const [session, setSession] = useState<boolean | null>(
    () => (signedOutHere() ? false
         : gateApplies(location.hostname) ? null : true));
  // Asking is also how somebody comes BACK, so it is the one place the
  // signed-out mark is cleared. Clearing it anywhere else would undo the
  // button on the next reload, which is the bug this replaced.
  const askSession = useCallback(() => {
    rememberSignedOut(false);
    // WHERE THE GATE DOES NOT APPLY, THERE IS NOTHING TO ASK. On localhost
    // the `.eka.care` cookie is never sent, so the probe can only ever say
    // no -- and asking it here would mean a developer who pressed Sign out
    // could never get back in. That is precisely the lockout `gateApplies`
    // exists to prevent, so coming back is just forgetting the mark.
    if (!gateApplies(location.hostname)) { setSession(true); return; }
    setSession(null);
    void signedIn().then(setSession);
  }, []);
  const leave = useCallback(() => {
    rememberSignedOut(true);
    setSession(false);
  }, []);
  useEffect(() => {
    if (!signedOutHere() && gateApplies(location.hostname)) askSession();
  }, [askSession]);
  /** The tour runs once, on a person's first load, and only once the screen
   *  has something to point at. Nothing reopens it: a tour that comes back
   *  is an interruption, and the control panel is where it starts again. */
  const [tour, setTour] = useState(() => !seenTour());
  const [khojOpen, setKhojOpen] = useState(false);
  // The medical assistant, outside a visit. `assistSeen` keeps it mounted
  // after the first opening so closing it does not end the conversation.
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistSeen, setAssistSeen] = useState(false);
  const [assistQuestion, setAssistQuestion] = useState<Question | null>(null);
  // ONE SHAPE NOW. It used to come forward in the middle of the page when
  // asked from the command bar and dock at the side when asked about a
  // patient, which was two layouts to keep right for one assistant. The Ask
  // AI widget has one, the docked one, which is the shape that lets a
  // clinician keep the visit in view and does no harm anywhere else. The
  // callers still say where they are asking from; nothing reads it, and the
  // argument stays so this is one decision to reverse rather than thirty
  // call sites.
  const askAssistant = (text: string, _where: "side" | "centre", context?: Question["context"]) => {
    setAssistQuestion({ text, n: Date.now(), context });
    setAssistSeen(true);
    setAssistOpen(true);
  };
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

  const allViews = useMemo<ViewDecl[]>(() => facility.data?.views ?? [], [facility.data]);
  // A summary view belongs to a thread, not to the nav -- the rule
  // `summariesFor` in messages.ts is built on. This is where it was being
  // broken: every declared view was loaded on arrival and offered in the
  // palette, so the one that reads a single visit was asked for with no
  // visit, and the kernel rightly answered 400 on every page load. The
  // filter reads the declared kind, never an id this file may not know.
  //
  // AND NOT A PLACE THIS SEAT MAY NOT GO. Every view declares the capability
  // it takes to open, and the kernel refuses one the caller does not hold --
  // but the rail was offering all of them anyway, so a clerk had a row for
  // this centre's numbers that answered 403 when pressed. A nav row that
  // fails is worse than one that is absent: it teaches a person the product
  // is broken rather than that the door is not theirs.
  //
  // Both halves of the comparison were handed to this file by `/facility`:
  // the view's own `capability` and the caller's own list. It names neither,
  // so a bundle that moves a view behind a different capability needs no
  // edit here. A view that declares none is open to everybody.
  const held = useMemo(
    () => new Set(facility.data?.user.capabilities ?? []), [facility.data]);
  const navViews = useMemo<ViewDecl[]>(
    () => allViews.filter((v) => v.kind !== "summary"
                              && (!v.capability || held.has(v.capability))),
    [allViews, held]);

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
    say(n === 1 ? "1 patient is here." : `${n} patients are here.`);
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


  /** HOW TODAY'S LINE IS NARROWED, held once for the whole shell.
   *
   *  It lives here and not in either panel because both of them draw the
   *  same people: the second panel is the line and the list screen is the
   *  line, and a narrowing applied to one of those and not the other is two
   *  answers to one question on one screen. The control that sets it is in
   *  the second panel, beside the people; the list obeys it.
   *
   *  Null means everybody, which is the state a person has to be able to get
   *  back to from anywhere.
   */
  const [narrow, setNarrow] = useState<Filter>(null);

  /** WHAT IS WAITING FOR SOMEBODY, out of the rows already loaded. The
   *  declared tasklist used to be a nav row of its own; it is the bell in
   *  the top right now, because nobody navigates to "things that need me".
   *  The kind is the view's own, so this file names no view. */
  const [bellOpen, setBellOpen] = useState(false);
  /** How wide the second panel is, which is the person's choice and not
   *  ours. A centre that works off the line all day wants it wide; one
   *  reading long consultation notes wants it out of the way. The rule and
   *  its limits are in width.ts, checked under plain node. */
  const [panelW, setPanelW] = useState(readWidth);
  /** Whether the line beside a visit is tucked away. The person's own choice, remembered. */
  const [lineFolded, setLineFolded] = useState(() => {
    try { return localStorage.getItem("rapha.line.folded") === "1"; } catch { return false; }
  });
  const foldLine = (v: boolean) => {
    setLineFolded(v);
    try { localStorage.setItem("rapha.line.folded", v ? "1" : "0"); } catch { /* private window */ }
  };
  const tasks = useMemo<TaskRow[]>(
    () => loaded.filter((l) => l.decl.kind === "tasklist")
      .flatMap((l) => (l.result.rows ?? []) as TaskRow[]),
    [loaded],
  );

  const remember = useCallback((r: Recent) => {
    setRecents((was) => {
      const next = [r, ...was.filter((x) => x.id !== r.id)].slice(0, 8);
      save(RECENT_KEY, next);
      return next;
    });
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  // The main panel is a card standing on the rail's colour. When the place
  // changes it comes out of the rail: a short slide and fade from the left,
  // so what moved is the thing you chose. Skipped for anyone who has asked for
  // less motion.
  const mainRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = mainRef.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    el.animate(
      [{ opacity: 0, transform: "translateX(-16px) scale(0.985)" }, { opacity: 1, transform: "none" }],
      { duration: 240, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
    );
  }, [route.kind]);

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
    const to = mentionsOf(text);
    const mine: Said = { id: `u-${at}`, at, who: "user", text, actor: "You",
                         ...(to.length ? { to } : {}) };
    setSaid((was) => {
      const next = { ...was, [thread]: [...(was[thread] ?? []), mine] };
      save(SAID_KEY, next);
      return next;
    });
    // AN @ MAKES IT A MESSAGE TO A PERSON, NOT A QUESTION FOR THE AGENT. It
    // goes on the thread as what the user said, addressed to whoever they
    // named, and nothing answers it -- the agent used to, in the third
    // person, about a colleague who had been spoken to directly. Owner,
    // 2026-11-04: "it should just treat it as part of the message from the
    // user to the other user".
    if (to.length) return;
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

  // Eka has just sent the browser back, INSIDE the sign in frame. Drawing
  // the app here would put the whole workspace in a box on its own sign in
  // screen. One line, and the page around the frame notices the cookie and
  // takes it from here.
  if (cameBackFromLogin(location.search, window.top !== window.self)) {
    return <div className="came-back">Signed in. One moment…</div>;
  }

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

  const here = location.hash.replace(/^#\/?/, "");
  const panel = panelFor(here, navViews);

  // The way back from a visit: the line's own title, and the patient's name
  // read the same way the line reads it.
  const lineHead = line[0]?.decl;
  const visit = route.kind === "thread" ? line.find(({ row }) => row.thread === route.id) : undefined;
  const crumb = lineHead && visit
    ? { back: lineHead.title ?? title, onBack: () => go(`#/views/${lineHead.id}`), here: fields(visit.decl, visit.row).name }
    : undefined;

  return (
    <div className="app" data-panel={panel ?? "none"}
         /* THE RIGHT RAIL STANDS DOWN WHILE THE ASSISTANT IS AT THE SIDE.
            Both live at the right edge, so with the assistant open a visit
            had two columns of its own beside it and the conversation was
            squeezed into what was left. Which of the two a person wants is
            not a question: they just opened the assistant. The rail comes
            back the moment they close it, and nothing about it is lost. */
         data-assist={assistSeen && assistOpen ? "side" : undefined}
         style={{ "--panel-w": `${panelW}px` } as React.CSSProperties}>
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
      <Rail
        route={here}
        views={navViews}
        theme={theme}
        onGo={go}
        onTheme={flipTheme}
        scribe={liveScribe}
        bell={
              <Bell
                rows={tasks}
                open={bellOpen}
                onOpen={setBellOpen}
                cat={catalogue}
                onGo={(thread) => { setBellOpen(false); go(`#/threads/${thread}`); }}
              />
        }
      />
      {panel && !(lineFolded && panel === "line") && (
        <Sidebar
          onFold={panel === "line" ? () => foldLine(true) : undefined}
          facility={facility.data}
          route={here}
          panel={panel}
          sections={PARTS}
          line={line}
          narrow={narrow}
          onNarrow={setNarrow}
          open={drawer}
          onGo={go}
          onCall={(token) => { setKhojOpen(false); go(`#/desk?q=${encodeURIComponent(token)}`); }}
          onCloseDrawer={() => setDrawer(false)}
        />
      )}
      {panel && !(lineFolded && panel === "line") && (
        <Grip
          width={panelW}
          label="Width of this panel"
          onWidth={(px) => setPanelW(clampWidth(px))}
          onDone={(px) => saveWidth(px)}
        />
      )}
      {tour && <Tour onClose={() => setTour(false)} />}
      {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}
      <div className={`main${route.kind === "thread" ? " main--flat" : ""}`} ref={mainRef}>
        {/* The screens with no second panel carry the spray instead, so the
            flowers are not only on the screens a person moves between
            people from. Home is busy enough with its own day; the desk and
            the settings are forms. */}
        {!panel && (route.kind === "view" || route.kind === "patients" || route.kind === "patient")
          && <Garland kind="spray" />}
        {/* A BAR INSIDE A VISIT, WITH A WAY BACK. It used to be left out: it carried
            one word, "Encounter", above a card already headed with the patient's
            name, and its controls went elsewhere. The word is now the way back
            and where you are (Lines > Lakshmi Devi), which is the one thing a
            person on a visit cannot otherwise see. The visit's own h1 stays the
            patient's name (screens/Encounter.tsx); the breadcrumb is a nav
            landmark, not a second heading. Register and Ask stay because the
            desk and the command bar are one press away from any screen. */}
        {(
          <Topbar
            title={title}
            crumb={crumb}
            onShowLine={panel === "line" && lineFolded ? () => foldLine(false) : undefined}
            profile={<Profile facility={facility.data} onSignOut={leave} />}
            deskLabel={createLabel(catalogue, facility.data?.bundle.workflow)}
            onSearch={() => setKhojOpen(true)}
            onMenu={() => setDrawer((d) => !d)}
            onDesk={() => go("#/desk")}
          />
        )}
        <main id="workspace" tabIndex={-1} className={route.kind === "thread" ? "view" : "view scroll"}>
          <div className="wrap">
          <Boundary>
            {/* THE SCRIBED VISIT STAYS MOUNTED while somebody is elsewhere:
                unmounting its screen would stop the microphone. Same key,
                same instance, so coming back finds the recording running. */}
            {[...new Set([route.kind === "thread" ? route.id : "", liveScribe?.thread ?? ""].filter(Boolean))].map((tid) => (
              <div key={tid} style={{ display: route.kind === "thread" && route.id === tid ? "contents" : "none" }}>
                <ThreadScreen
                  id={tid} cat={catalogue} ctx={ctx} nonce={nonce}
                  said={said[tid] ?? []} asking={asking}
                  onSay={(t) => onSay(tid, t)}
                  onChanged={reload}
                  onOpenSubject={(sid) => go(`#/patients/${sid}`)}
                  onAskRapha={(q, c) => askAssistant(q, "side", c)}
                  onRemember={remember}
                  catchment={facility.data?.catchment}
                />
              </div>
            ))}
            {route.kind !== "thread" && (
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
                    q={route.q}
                    onOpenThread={(t) => { reload(); go(`#/threads/${t}`); }}
                  />
                )}
                {route.kind === "settings" && (
                  <Control
                    client={api} cat={catalogue}
                    roleIds={facility.data?.roles ?? []}
                    facility={{
                      withheld: facility.data?.withheld ?? {},
                      without: facility.data?.without ?? {},
                    }}
                    theme={themePref} onTheme={setThemePref}
                    part={route.part}
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

      {/* THE ASSISTANT IS EKA'S OWN ASK AI WIDGET. It docks to the right
          edge and brings its own panel, so there is no overlay of this
          app's around it; assistant/AskAi.tsx says why it replaced the
          hand-built one. `side` is gone with it: the widget has one shape
          and it is the docked one, which is what a clinician wants in a
          visit and does no harm anywhere else. */}
      {assistSeen && (
        <AskAi open={assistOpen} question={assistQuestion}
               onClose={() => setAssistOpen(false)} />
      )}

      {khojOpen && (
        <Khoj
          queues={loaded.filter((l) => l.decl.kind === "queue")}
          nav={navViews}
          cat={catalogue}
          workflow={facility.data?.bundle.workflow}
          onClose={() => setKhojOpen(false)}
          onOpenThread={(t) => go(`#/threads/${t}`)}
          onGoView={(v) => go(v ? `#/views/${v}` : "#/")}
          onAsk={(question) => askAssistant(question, "centre")}
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
  if (route.kind === "today") return NAME.toUpperCase();
  if (route.kind === "settings") return "Control panel";
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

function ThreadScreen({ id, cat, ctx, said, asking, nonce, catchment, onSay, onChanged, onRemember, onOpenSubject, onAskRapha }: {
  id: string; cat: ReturnType<typeof Object>; ctx: Ctx; said: Said[];
  asking: boolean; nonce: number;
  catchment?: Facility["catchment"];
  onSay: (t: string) => void; onChanged: () => void; onRemember: (r: Recent) => void;
  onOpenSubject: (subjectId: string) => void;
  onAskRapha: (question: string, context: { title: string; text: string }) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.thread(id), [id, nonce]);
  // header() already answers "what is this thread called", using the queue
  // declaration's own column order. Picking the first string off the subject
  // instead -- which is what this did -- returns the encounter id, because
  // that is the first key the adapter puts in the subject dict.
  const name = data ? header(data, queueViewFor(cat as never, data.workflow), displayFor).name : id;
  useEffect(() => { if (data) onRemember({ id, name }); }, [data, id, name, onRemember]);

  // Only the FIRST read draws a skeleton. A reload after a commit keeps
  // the visit mounted, so the tab the person was reading is still the tab
  // they are on when the new data lands.
  if (loading && !data) return <Loading what="this encounter" shape="messages" rows={3} />;
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
      onAskRapha={onAskRapha}
    />
  );
}
