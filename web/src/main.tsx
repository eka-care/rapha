/** The shell: which declared view is on screen, which thread is open, and
 *  what happens when a person taps something.
 *
 *  There is no screen in this app that was written for a particular bundle.
 *  The navigation is the views the catalogue declares, the forms are the
 *  questionnaires the operations name, the steps are the workflow's, and the
 *  roles are the ones /facility returns. Point it at the laboratory kernel on
 *  another port and the same code draws the laboratory.
 *
 *  Every write in this file goes through OperationPanel, in a modal, and needs
 *  a tap in it. Nothing on this page commits; it opens the screen that can.
 */
import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { API_BASE, DEMO_ROLE, api, currentRole, setRole, useAsync } from "./api";
import { ask, NO_AGENT } from "./ask";
import { questionnaire } from "./declarations";
import { Home } from "./Home";
import { Icon, IconSheet } from "./icons";
import { clock, header, queueViewFor, type Ctx, type Said } from "./messages";
import { mockApi } from "./mock";
import { OperationPanel, proposalOperation } from "./OperationPanel";
import { Palette } from "./Palette";
import { firstOperation } from "./search";
import {
  navViews, Overlay, recents, remember, Sheet, Sidebar, toast, Toast, useTheme, type Recent,
} from "./Shell";
import { Thread } from "./Thread";
import type { Catalogue, MetricValue, Operation, Proposal, ThreadView, ViewDecl, ViewResult } from "./types";
import { Boundary, Failed, Loading, human, title } from "./ui";
import { ViewRenderer } from "./ViewRenderer";
import "./theme.css";
import "./renderer.css";

type Route = { kind: "home" | "view" | "thread" | "ask"; id: string };

function parse(hash: string): Route {
  const [head, id] = hash.replace(/^#\/?/, "").split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  if (head === "ask") return { kind: "ask", id: "" };
  if (head && head !== "home") return { kind: "view", id: head };
  return { kind: "home", id: "" };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return route;
}

const go = (hash: string) => {
  location.hash = hash.replace(/^#/, "");
};

/** Questions a person typed. The kernel stores none of them, so they live
 *  here, per thread, per browser, and the empty state says so. */
const SAID = "phc.said";
const loadSaid = (): Record<string, Said[]> => {
  try {
    return JSON.parse(localStorage.getItem(SAID) || "{}");
  } catch {
    return {};
  }
};

type Loaded = { decl: ViewDecl; result: ViewResult };

function App() {
  const [demo, setDemo] = useState(false);
  const client = demo ? mockApi : api;
  const [role, setRoleState] = useState(currentRole());
  const [theme, toggleTheme] = useTheme();
  const route = useRoute();

  const cat = useAsync<Catalogue>(() => client.catalogue(), [demo, role]);
  const fac = useAsync(() => client.facility(), [demo, role]);

  // One read per non-summary view, shared by the nav counts, Home and the
  // palette. A view the role may not open answers 403; that is an answer, not
  // a crash, so it drops out of the list.
  const nav = useMemo(() => navViews(cat.data), [cat.data]);
  const loaded = useAsync<Loaded[]>(
    () =>
      Promise.all(
        nav.map((decl) =>
          client.view(decl.id).then(
            (result) => ({ decl, result }),
            () => null,
          ),
        ),
      ).then((all) => all.filter((x): x is Loaded => x !== null)),
    [nav, demo, role],
  );
  const queues = (loaded.data ?? []).filter((x) => x.decl.kind === "queue");
  const dashboards = (loaded.data ?? []).filter((x) => x.decl.kind === "dashboard");

  const thread = useAsync(
    () => (route.kind === "thread" ? client.thread(route.id) : Promise.resolve(null)),
    [route.kind, route.id, demo, role],
  );

  const [recent, setRecent] = useState<Recent[]>(recents);
  const [palette, setPalette] = useState(false);
  const [modal, setModal] = useState<{ op: Operation; thread: string; proposal?: Proposal } | null>(null);
  const [sheet, setSheet] = useState<{ view: ViewDecl; thread: string } | null>(null);
  const [said, setSaid] = useState<Record<string, Said[]>>(loadSaid);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    if (!thread.data) return;
    const q = queueViewFor(cat.data, thread.data.workflow);
    remember({ id: thread.data.id, name: header(thread.data, q).name });
    setRecent(recents());
  }, [thread.data, cat.data]);

  // A role is one kernel's word. This browser remembers the last one chosen,
  // and pointing it at a different bundle (the laboratory on another port)
  // means every request is 400 "no such role" until it is forgotten. Falling
  // back to the kernel's own default is better than a workspace that will not
  // draw, and the toast says what happened.
  useEffect(() => {
    // /catalogue takes no caller, so it is /facility that answers 400 here.
    if ((fac.error?.status ?? cat.error?.status) === 400 && role !== DEMO_ROLE) {
      setRole(DEMO_ROLE);
      setRoleState(DEMO_ROLE);
      toast(`This kernel has no role "${role}", so this is the demo account again.`);
    }
  }, [fac.error, cat.error, role]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
    };
    addEventListener("keydown", key);
    return () => removeEventListener("keydown", key);
  }, []);

  const ctx: Ctx = useMemo(
    () => ({
      operations: cat.data?.operations ?? {},
      schema: questionnaire,
      badges: queueViewFor(cat.data, thread.data?.workflow)?.badges ?? {},
    }),
    [cat.data, thread.data?.workflow],
  );

  const pushSaid = useCallback((key: string, m: Said) => {
    setSaid((was) => {
      const next = { ...was, [key]: [...(was[key] ?? []), m].slice(-40) };
      try {
        localStorage.setItem(SAID, JSON.stringify(next));
      } catch {
        /* this session still has them */
      }
      return next;
    });
  }, []);

  /** Sending a sentence. This is the one path on the page that talks to
   *  something other than the kernel, and all it can do is make the agent
   *  propose. It never calls commit or confirm; the proposals come back as
   *  cards in the thread. */
  const say = useCallback(
    async (key: string, text: string, threadId?: string) => {
      const at = new Date().toISOString();
      pushSaid(key, { id: `u${Date.now()}`, at, who: "user", text, actor: role === "demo" ? "you" : human(role) });
      setAsking(true);
      const answer = await ask({ utterance: text, thread: threadId, role });
      setAsking(false);
      pushSaid(key, { id: `a${Date.now()}`, at: new Date().toISOString(), who: "agent", text: answer.said, actor: "agent" });
      if (answer.proposed) thread.reload();
    },
    [pushSaid, role, thread],
  );

  const openThread = (id: string) => {
    setPalette(false);
    go(`#/threads/${id}`);
  };

  /** Create on miss: open an empty thread, which writes an encounter row and
   *  no clinical fact, then open the first operation of the workflow's first
   *  step. Whichever operation that is, is the bundle's answer. */
  const register = async () => {
    if (!cat.data) return;
    try {
      const opened = await client.openThread({});
      setPalette(false);
      go(`#/threads/${opened.id}`);
      const id = firstOperation(cat.data, opened.workflow);
      const op = id ? cat.data.operations?.[id] : undefined;
      if (op) setModal({ op, thread: opened.id });
      toast(`Opened ${opened.id}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not open a thread");
    }
  };

  const heading = topbar(route, cat.data, thread.data ?? null);

  return (
    <div className="phc app">
      <IconSheet />
      <Sidebar
        cat={cat.data}
        facility={fac.data}
        queues={queues.map((q) => q.result)}
        route={route}
        role={role}
        recent={recent}
        onGo={go}
        onNewChat={() => go("#/ask")}
        onSearch={() => setPalette(true)}
        onRole={(r) => {
          setRole(r);
          setRoleState(r);
          toast(`Role: ${r === "demo" ? "every capability (demo)" : human(r)}`);
        }}
      />

      <div className="main">
        <div className="topbar">
          <div>
            <div className="tb-title">{heading[0]}</div>
            <div className="tb-sub">{heading[1]}</div>
          </div>
          <div className="ml-auto" />
          <div className="srcline">
            <span className={`dot ${demo ? "demo" : cat.error ? "down" : "up"}`} />
            {demo ? "Demo data, nothing is real" : API_BASE}
          </div>
          <button className="pill" onClick={() => setDemo(!demo)}>
            {demo ? "Use the API" : "Use demo data"}
          </button>
          <button className="pill" onClick={() => setPalette(true)}>
            <Icon name="search" size="sm" />Search or ask<span className="kbd">⌘K</span>
          </button>
          <button className="icon-btn" onClick={toggleTheme} title="Light or dark">
            <Icon name={theme === "light" ? "moon" : "sun"} />
          </button>
        </div>

        <div className={`view${route.kind === "thread" || route.kind === "ask" ? "" : " scroll"}`}>
          <div className="wrap">
            <Boundary key={`${route.kind}-${route.id}-${demo}-${role}`}>
              {cat.loading && <Loading what="the catalogue" />}
              {cat.error && (
                <Failed error={cat.error} onRetry={cat.reload} onDemo={demo ? undefined : () => setDemo(true)} />
              )}
              {cat.data && route.kind === "home" && (
                <>
                  {loaded.loading && <Loading what="today" />}
                  <Home
                    cat={cat.data}
                    role={role}
                    queues={queues}
                    dashboards={dashboards}
                    recent={recent}
                    onOpenThread={openThread}
                    onGo={go}
                    onSearch={() => setPalette(true)}
                    onAsk={(q) => {
                      go("#/ask");
                      say("workspace", q);
                    }}
                  />
                </>
              )}

              {cat.data && route.kind === "ask" && (
                <Workspace
                  cat={cat.data}
                  loaded={loaded.data ?? []}
                  said={said.workspace ?? []}
                  asking={asking}
                  onSay={(t) => say("workspace", t)}
                  onGo={go}
                />
              )}

              {cat.data && route.kind === "view" && (
                <ViewScreen id={route.id} cat={cat.data} client={client} onOpenThread={openThread} />
              )}

              {cat.data && route.kind === "thread" && (
                <>
                  {thread.loading && <Loading what="this thread" />}
                  {thread.error && <Failed error={thread.error} onRetry={thread.reload} />}
                  {thread.data && (
                    <Thread
                      thread={thread.data}
                      cat={cat.data}
                      ctx={ctx}
                      role={role === DEMO_ROLE ? "the demo account" : human(role)}
                      said={said[thread.data.id] ?? []}
                      asking={asking}
                      onSay={(t) => say(route.id, t, route.id)}
                      onAction={(op) => setModal({ op, thread: route.id })}
                      onReview={(p) =>
                        setModal({ op: proposalOperation(p, cat.data?.operations ?? {}), thread: route.id, proposal: p })
                      }
                      onReject={async (p) => {
                        try {
                          await client.reject(p.id, {});
                          toast("Proposal rejected. Nothing was written.");
                          thread.reload();
                        } catch (e) {
                          toast(e instanceof Error ? e.message : "Could not reject");
                        }
                      }}
                      onSummary={(v) => setSheet({ view: v, thread: route.id })}
                      onMore={() => setPalette(true)}
                    />
                  )}
                </>
              )}
            </Boundary>
          </div>
        </div>
      </div>

      {palette && cat.data && (
        <Overlay onClose={() => setPalette(false)}>
          <Palette
            cat={cat.data}
            client={client}
            queues={queues}
            nav={nav}
            role={role}
            onClose={() => setPalette(false)}
            onOpenThread={openThread}
            onGo={(h: string) => {
              setPalette(false);
              go(h);
            }}
            onAsk={(q: string) => {
              setPalette(false);
              go("#/ask");
              say("workspace", q);
            }}
            onRegister={register}
            onAction={(t: string, op: Operation) => {
              setPalette(false);
              go(`#/threads/${t}`);
              setModal({ op, thread: t });
            }}
          />
        </Overlay>
      )}

      {modal && cat.data && (
        <Overlay onClose={() => setModal(null)}>
          <OperationPanel
            op={modal.op}
            thread={modal.thread}
            client={client}
            proposal={modal.proposal}
            instruments={cat.data.instruments}
            flags={thread.data?.flags ?? []}
            onCancel={() => setModal(null)}
            onDone={() => {
              toast(`${modal.op.title} committed`);
              setModal(null);
              thread.reload();
              loaded.reload();
            }}
          />
        </Overlay>
      )}

      {sheet && cat.data && (
        <SummarySheet
          view={sheet.view}
          thread={sheet.thread}
          client={client}
          cat={cat.data}
          onClose={() => setSheet(null)}
          onAction={(op) => {
            setSheet(null);
            setModal({ op, thread: sheet.thread });
          }}
          onReview={(p) => {
            setSheet(null);
            setModal({ op: proposalOperation(p, cat.data?.operations ?? {}), thread: sheet.thread, proposal: p });
          }}
        />
      )}

      <Toast />
    </div>
  );
}

/** The topbar's two lines. On a thread the second is where the baton stands
 *  and what the last done step was called, both in the workflow's own
 *  words. */
function topbar(
  route: Route,
  cat: Catalogue | undefined,
  thread: ThreadView | null,
): [string, string] {
  if (route.kind === "home") return ["Today", "Your shift at a glance"];
  if (route.kind === "ask") return ["Workspace chat", "Not scoped to one thread"];
  if (route.kind === "view") {
    const v = cat?.views?.[route.id];
    return [v?.title ?? title(route.id), v?.summary ?? ""];
  }
  if (!thread) return [title(route.id), ""];
  const done = [...thread.line].reverse().find((s) => s.status === "done");
  const name = header(thread, queueViewFor(cat, thread.workflow)).name;
  return [
    name,
    `${thread.station ? title(thread.station) : "Complete"}${done ? ` · ${title(done.label)}` : ""}`,
  ];
}

function ViewScreen({
  id, cat, client, onOpenThread,
}: {
  id: string; cat: Catalogue; client: typeof api; onOpenThread: (t: string) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => client.view(id), [id, client]);
  return (
    <>
      {loading && <Loading what={title(id)} />}
      {error && <Failed error={error} onRetry={reload} />}
      {data && <ViewRenderer result={data} titles={titlesOf(cat)} onOpenThread={onOpenThread} />}
    </>
  );
}

function SummarySheet({
  view, thread, client, cat, onClose, onAction, onReview,
}: {
  view: ViewDecl; thread: string; client: typeof api; cat: Catalogue;
  onClose: () => void; onAction: (op: Operation) => void; onReview: (p: Proposal) => void;
}) {
  const { data, error, loading, reload } = useAsync(() => client.view(view.id, thread), [view.id, thread, client]);
  return (
    <Sheet title={view.title ?? title(view.id)} sub={view.summary} onClose={onClose}>
      {loading && <Loading what="the summary" />}
      {error && <Failed error={error} onRetry={reload} />}
      {data && (
        <ViewRenderer result={data} titles={titlesOf(cat)} onAction={onAction} onReview={onReview} />
      )}
    </Sheet>
  );
}

/** The workspace chat. It is not scoped to a thread, and the only thing it can
 *  answer without an agent is a question that names a declared view, which it
 *  answers by drawing the read it already has. Everything else goes to the
 *  agent wrapper, and says so plainly when there is not one. */
function Workspace({
  cat, loaded, said, asking, onSay, onGo,
}: {
  cat: Catalogue;
  loaded: Loaded[];
  said: Said[];
  asking?: boolean;
  onSay: (t: string) => void;
  onGo: (h: string) => void;
}) {
  const [text, setText] = useState("");
  const send = () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    onSay(t);
  };
  // A question that names a view is answered from the read this page already
  // did. The match is on the view's own title and id words, so a bundle that
  // declares a different view gets a different answer with no change here.
  const answerFor = (q: string): Loaded | undefined => {
    const lo = q.toLowerCase();
    return loaded.find(
      (l) =>
        lo.includes((l.decl.title ?? "").toLowerCase()) ||
        l.decl.id.split(/[.\-_]/).filter((w) => w.length > 3).some((w) => lo.includes(w)),
    );
  };

  return (
    <div className="chatgrid" style={{ gridTemplateColumns: "1fr" }}>
      <div className="card chatcard">
        <div className="pt-head">
          <div className="avatar"><Icon name="spark" /></div>
          <div style={{ flex: 1 }}>
            <div className="pt-name">Workspace chat</div>
            <div className="pt-meta">
              Not scoped to one thread. {cat.manifest?.title ?? "This bundle"} ·{" "}
              {cat.manifest?.version ?? ""}
            </div>
          </div>
        </div>
        <div className="thread">
          {said.length === 0 && (
            <div className="empty">
              Ask about a declared view and it is answered from the read this page already did.
              Anything else needs the agent.
              <br />
              <br />
              Nothing typed here is part of the record: the kernel has no route for a sentence and
              stores none.
            </div>
          )}
          {said.map((m) => {
            if (m.who === "user") {
              return (
                <div className="msg right" key={m.id}>
                  <div className="m-av"><Icon name="user" size="sm" /></div>
                  <div className="m-b">
                    <div className="m-meta" style={{ justifyContent: "flex-end" }}>{m.actor} · {clock(m.at)}</div>
                    <div className="bubble">{m.text}</div>
                  </div>
                </div>
              );
            }
            const asked = [...said].reverse().find((x) => x.who === "user" && x.at <= m.at);
            const hit = asked ? answerFor(asked.text) : undefined;
            return (
              <div className="msg" style={{ maxWidth: "97%" }} key={m.id}>
                <div className="m-av agent"><Icon name="spark" size="sm" /></div>
                <div className="m-b" style={{ flex: 1 }}>
                  <div className="m-meta">Agent · {clock(m.at)}</div>
                  <div className="bubble">
                    {hit ? (
                      <>
                        <div className="t">{hit.decl.title ?? title(hit.decl.id)}</div>
                        A read across this facility. No write was performed.
                        <Counts l={hit} cat={cat} />
                        <div className="props">
                          <button className="prop" onClick={() => onGo(`#/views/${hit.decl.id}`)}>
                            <Icon name="list" />
                            <span style={{ flex: 1 }}>
                              <span className="p-l">Open {hit.decl.title ?? title(hit.decl.id)}</span>
                              <div className="p-s">The same read, on its own screen.</div>
                            </span>
                          </button>
                        </div>
                      </>
                    ) : (
                      m.text || NO_AGENT
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="composer">
          <div className="cbar">
            {loaded.map((l) => (
              <button key={l.decl.id} className="cq" onClick={() => onSay(`Show ${l.decl.title ?? title(l.decl.id)}`)}>
                <Icon name={l.decl.kind === "dashboard" ? "vitals" : "list"} size="sm" />
                {l.decl.title ?? title(l.decl.id)}
              </button>
            ))}
          </div>
          <div className="crow">
            <input
              value={text}
              placeholder="Ask about the facility"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
            />
            <button className="btn btn-b send" onClick={send} title={asking ? "Thinking" : "Send"}>
              <Icon name={asking ? "spark" : "send"} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Counts({ l, cat }: { l: Loaded; cat: Catalogue }) {
  const rows: [string, string][] =
    l.decl.kind === "dashboard"
      ? (l.result.rows as MetricValue[]).map((m) => [
          m.title ?? cat.metrics?.[m.metric]?.title ?? human(m.metric),
          String(m.unit === "percent" ? `${(m.value ?? 0).toFixed(1)}%` : m.value),
        ])
      : (l.result.groups ?? []).map((g) => [
          g.key === null ? "Complete" : title(String(g.key)),
          String(g.count),
        ]);
  if (!rows.length) return null;
  return (
    <div className="kvbox">
      {rows.map(([k, v]) => (
        <div className="kv" key={k}><span>{k}</span><b>{v}</b></div>
      ))}
    </div>
  );
}

/** Every declaration the catalogue carries, by id, so a result that names a
 *  metric or a view by id can be labelled with the words its author wrote. */
function titlesOf(cat: Catalogue): Record<string, string> {
  const out: Record<string, string> = {};
  for (const group of [cat.views, cat.metrics, cat.operations, cat.workflows]) {
    for (const [id, d] of Object.entries(group ?? {})) {
      if (d && typeof d === "object" && "title" in d) out[id] = String((d as { title: string }).title);
    }
  }
  return out;
}

// Keep the root on the element so a hot reload re-renders instead of mounting
// a second React root onto the same node.
const el = document.getElementById("root")! as HTMLElement & { _root?: ReturnType<typeof createRoot> };
(el._root ??= createRoot(el)).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
