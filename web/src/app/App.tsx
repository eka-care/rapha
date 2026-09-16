/** The root: routing, the four loads, and the state that outlives a screen.
 *
 *  Everything drawn below comes from a declaration. This file knows there are
 *  views, threads and operations; it does not know what any of them are called.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError, currentRole, useAsync } from "../api";
import { ask } from "../ask";
import { questionnaire } from "../declarations";
import { keep, type Recent } from "../loops";
import { header, queueViewFor, type Ctx, type Said } from "../messages";
import { Boundary, Failed, Loading } from "../parts";
import { Encounter } from "../screens/Encounter";
import { ListScreen } from "../screens/ListScreen";
import { Patient } from "../screens/Patient";
import { Roles } from "../screens/Settings";
import { Today } from "../screens/Today";
import type { QueueRow, ViewDecl, ViewResult } from "../types";
import { IconSheet } from "../icons";
import { Khoj } from "./Khoj";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type Route =
  | { kind: "today" }
  | { kind: "view"; id: string }
  | { kind: "thread"; id: string }
  | { kind: "patient"; id: string }
  | { kind: "settings" }
  | { kind: "notfound"; id: string };

function parse(hash: string): Route {
  const [head, id] = hash.replace(/^#\/?/, "").split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  if (head === "patients" && id) return { kind: "patient", id };
  if (head === "settings") return { kind: "settings" };
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

function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() => read<"light" | "dark">(THEME_KEY, "light"));
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    save(THEME_KEY, theme);
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))] as const;
}

export function App() {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);

  const [theme, flipTheme] = useTheme();
  const [khojOpen, setKhojOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [said, setSaid] = useState<Record<string, Said[]>>(() => read(SAID_KEY, {}));
  const [recents, setRecents] = useState<Recent[]>(() => read(RECENT_KEY, []));
  const [asking, setAsking] = useState(false);
  const [nonce, setNonce] = useState(0);

  const facility = useAsync(() => api.facility(), []);
  const cat = useAsync(() => api.catalogue(), []);

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
  useEffect(() => {
    if (!navViews.length) return;
    let live = true;
    Promise.all(navViews.map((decl) =>
      api.view(decl.id).then(
        (result) => ({ decl, result }),
        () => null,
      )))
      .then((all) => {
        if (!live) return;
        const good = all.filter(Boolean) as { decl: ViewDecl; result: ViewResult }[];
        setLoaded(good);
        setLoadError(good.length ? null : new ApiError("No view answered.", "Check the kernel is running."));
      });
    return () => { live = false; };
  }, [navViews, nonce]);

  const liveThreads = useMemo(
    () => loaded.filter((l) => l.decl.kind === "queue")
      .flatMap((l) => ((l.result.rows ?? []) as QueueRow[]).map((r) => r.thread)),
    [loaded],
  );
  const shownRecents = useMemo(() => keep(recents, liveThreads), [recents, liveThreads]);

  const counts = useMemo(() => Object.fromEntries(
    loaded.map((l) => [l.decl.id, ((l.result.rows ?? []) as unknown[]).length]),
  ), [loaded]);

  const remember = useCallback((r: Recent) => {
    setRecents((was) => {
      const next = [r, ...was.filter((x) => x.id !== r.id)].slice(0, 8);
      save(RECENT_KEY, next);
      return next;
    });
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  if (facility.loading || cat.loading) {
    return <div className="workspace-scroll"><Loading what="the workspace" /></div>;
  }
  if (facility.error || cat.error) {
    return (
      <div className="workspace-scroll">
        <Failed error={(facility.error ?? cat.error)!} what="reach the kernel" onRetry={() => location.reload()} />
      </div>
    );
  }

  const catalogue = cat.data!;
  const ctx: Ctx = {
    operations: catalogue.operations ?? {},
    schema: questionnaire,
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
      // A turn that proposed something changed the thread, so re-read it.
      if (answer.proposed > 0) reload();
    } finally {
      setAsking(false);
    }
  };

  const title = titleFor(route, navViews);

  return (
    <div className="app-shell">
      <IconSheet />
      <Sidebar
        facility={facility.data}
        views={navViews}
        route={location.hash.replace(/^#\/?/, "")}
        recents={shownRecents}
        counts={counts}
        open={drawer}
        onGo={go}
        onNew={() => setKhojOpen(true)}
        onSettings={() => go("#/settings")}
        onCloseDrawer={() => setDrawer(false)}
      />
      {drawer && <div className="drawer-scrim" onClick={() => setDrawer(false)} />}
      <div className="main">
        <Topbar
          title={title}
          sub={facility.data?.bundle.title}
          theme={theme}
          onSearch={() => setKhojOpen(true)}
          onTheme={flipTheme}
          onMenu={() => setDrawer((d) => !d)}
        />
        <div className="workspace">
          <Boundary>
            {route.kind === "thread" ? (
              <ThreadScreen
                id={route.id} cat={catalogue} ctx={ctx} nonce={nonce}
                said={said[route.id] ?? []} asking={asking}
                onSay={(t) => onSay(route.id, t)}
                onChanged={reload}
                onOpenSubject={(sid) => go(`#/patients/${sid}`)}
                onRemember={remember}
              />
            ) : (
              <div className="workspace-scroll">
                {route.kind === "today" && (
                  <Today
                    loaded={loaded} recents={shownRecents}
                    onOpenThread={(t) => go(`#/threads/${t}`)}
                    onGoView={(v) => go(`#/views/${v}`)}
                  />
                )}
                {route.kind === "view" && (
                  <ViewScreen id={route.id} nonce={nonce} decl={catalogue.views?.[route.id]} />
                )}
                {route.kind === "patient" && (
                  <Patient id={route.id} onOpenThread={(t) => go(`#/threads/${t}`)} />
                )}
                {route.kind === "settings" && (
                  <Roles client={api} cat={catalogue} roleIds={facility.data?.roles ?? []} onClose={() => go("#/")} />
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
          onAsk={(q) => {
            const first = shownRecents[0]?.id ?? liveThreads[0];
            if (first) { go(`#/threads/${first}`); onSay(first, q); }
          }}
          onCreate={async () => {
            const t = await api.openThread({});
            reload();
            go(`#/threads/${t.id}`);
          }}
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
  if (route.kind === "patient") return "Patient";
  return "Not found";
}

function ViewScreen({ id, decl, nonce }: { id: string; decl?: ViewDecl; nonce: number }) {
  const { data, error, loading, reload } = useAsync(() => api.view(id), [id, nonce]);
  if (loading) return <Loading what="this list" />;
  if (error) return <Failed error={error} what="load this list" onRetry={reload} />;
  return <ListScreen result={data!} decl={decl} onOpenThread={(t) => go(`#/threads/${t}`)} />;
}

function ThreadScreen({ id, cat, ctx, said, asking, nonce, onSay, onChanged, onRemember, onOpenSubject }: {
  id: string; cat: ReturnType<typeof Object>; ctx: Ctx; said: Said[];
  asking: boolean; nonce: number;
  onSay: (t: string) => void; onChanged: () => void; onRemember: (r: Recent) => void;
  onOpenSubject: (subjectId: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => api.thread(id), [id, nonce]);
  // header() already answers "what is this thread called", using the queue
  // declaration's own column order. Picking the first string off the subject
  // instead -- which is what this did -- returns the encounter id, because
  // that is the first key the adapter puts in the subject dict.
  const name = data ? header(data, queueViewFor(cat as never, data.workflow)).name : id;
  useEffect(() => { if (data) onRemember({ id, name }); }, [data, id, name, onRemember]);

  if (loading) return <div className="workspace-scroll"><Loading what="this encounter" /></div>;
  if (error) return <div className="workspace-scroll"><Failed error={error} what="open this encounter" onRetry={reload} /></div>;
  return (
    <Encounter
      thread={data!}
      cat={cat as never}
      ctx={ctx}
      client={api}
      said={said}
      asking={asking}
      onSay={onSay}
      onChanged={() => { reload(); onChanged(); }}
      onOpenSubject={onOpenSubject}
    />
  );
}
