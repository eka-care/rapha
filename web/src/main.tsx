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
import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ABHA_OP, ABHA_PENDING, mobileHint } from "./abha/sdk";
import { ApiError, API_BASE, DEMO_ROLE, api, currentRole, setRole, useAsync } from "./api";
import { ask, NO_AGENT } from "./ask";
import { CloseCard } from "./CloseCard";
import { questionnaire } from "./declarations";
import { Home } from "./Home";
import { Icon, IconSheet } from "./icons";
import { Khoj } from "./Khoj";
import { cue, keep, offered, opensOnArrival, weigh, type Cue } from "./loops";
import { clock, header, queueViewFor, summariesFor, type Ctx, type Said } from "./messages";
import { OperationPanel, proposalOperation } from "./OperationPanel";
import { Roles } from "./Roles";
import { firstOperation } from "./search";
import {
  navViews, Overlay, recents, remember, Sheet, Sidebar, toast, Toast, useTheme, type Recent,
} from "./Shell";
import { Thread } from "./Thread";
import type {
  Catalogue, Facility, MetricValue, Operation, Payload, Proposal, QueueRow, SectionResult, ThreadView, ViewDecl,
  ViewResult,
} from "./types";
import { Boundary, Failed, Loading, human, title } from "./ui";
import { ViewRenderer } from "./ViewRenderer";
import "./theme.css";
import "./renderer.css";

type Route = { kind: "home" | "view" | "thread" | "ask" | "notfound"; id: string };

function parse(hash: string): Route {
  const [head, id] = hash.replace(/^#\/?/, "").split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  if (head === "ask") return { kind: "ask", id: "" };
  if (!head || head === "home") return { kind: "home", id: "" };
  // A second segment under an unrecognised first one (`#/thread/enc-1`,
  // singular, is the one that actually happened) is a malformed route, not a
  // bare view id: guessing `head` as a view id here is how an empty thread id
  // used to reach the API as `views/thread/`. Say so instead of guessing.
  if (id) return { kind: "notfound", id: hash };
  return { kind: "view", id: head };
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
const SAID = "phc.said." + API_BASE;
const loadSaid = (): Record<string, Said[]> => {
  try {
    return JSON.parse(localStorage.getItem(SAID) || "{}");
  } catch {
    return {};
  }
};

type Loaded = { decl: ViewDecl; result: ViewResult };

/** Every thread id any loaded queue still lists. keep() filters recents
 *  against this, not against a single queue, because a recent can belong to
 *  any workflow this role's nav carries. */
function liveThreadIds(loaded: Loaded[] | undefined): string[] {
  return (loaded ?? [])
    .filter((l) => l.decl.kind === "queue")
    .flatMap((l) => (l.result.rows as QueueRow[] | undefined) ?? [])
    .map((r) => r.thread);
}

function App() {
  const client = api;
  const [role, setRoleState] = useState(currentRole());
  const [theme, toggleTheme] = useTheme();
  const route = useRoute();

  const cat = useAsync<Catalogue>(() => client.catalogue(), [role]);
  const fac = useAsync(() => client.facility(), [role]);

  // One read per view the caller may open, shared by the nav counts, Home and
  // Khoj. navViews has already dropped the ones whose capability this
  // role does not hold, so this normally asks for nothing it cannot have; a
  // 403 that gets through anyway is an answer, not a crash, and drops out.
  const nav = useMemo(() => navViews(cat.data, fac.data?.user?.capabilities), [cat.data, fac.data]);
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
    [nav, role],
  );
  const queues = (loaded.data ?? []).filter((x) => x.decl.kind === "queue");
  const dashboards = (loaded.data ?? []).filter((x) => x.decl.kind === "dashboard");
  const tasklists = (loaded.data ?? []).filter((x) => x.decl.kind === "tasklist");

  const thread = useAsync(
    () => (route.kind === "thread" ? client.thread(route.id) : Promise.resolve(null)),
    [route.kind, route.id, role],
  );

  // The rail's Records panel is the summary view's own sections, read for
  // this thread. There is one summary view per workflow (never picked by
  // id: it is the ViewDecl the catalogue itself marks kind "summary").
  const summaryView = cat.data && thread.data ? summariesFor(cat.data, thread.data.workflow)[0] : undefined;
  const summary = useAsync(
    () => (summaryView ? client.view(summaryView.id, route.id) : Promise.resolve(null)),
    [summaryView?.id, route.id, role],
  );

  const [recent, setRecent] = useState<Recent[]>(recents);
  const [khoj, setKhoj] = useState(false);
  const [modal, setModal] = useState<{
    op: Operation; thread: string; proposal?: Proposal;
    /** A mobile number the clerk typed in Khoj, for the journey. */
    mobile?: string;
    /** Answers already obtained by a journey on the previous panel. */
    seed?: Payload;
  } | null>(null);
  const [sheet, setSheet] = useState<{ view: ViewDecl; thread: string } | null>(null);
  const [rolesOpen, setRolesOpen] = useState(false);
  const [said, setSaid] = useState<Record<string, Said[]>>(loadSaid);
  const [asking, setAsking] = useState(false);
  const [closed, setClosed] = useState<{ what: string; cue: Cue } | null>(null);

  // A close card is about the thread that just closed, not whichever one is
  // on screen next. Without this, leaving and returning to a station shows a
  // stale card for a loop that already moved on.
  useEffect(() => { setClosed(null); }, [route.id]);

  // The instrument is the screen, not a thing a button offers to fetch. Once
  // per thread PER ROLE: thread.data refetches on role, and a role switch on
  // the same thread can carry a different primary action, so the guard has
  // to key on both. Reopening after a person closes it is a trap, not a
  // default, but a role that has never seen this thread's panel is not that.
  const openedFor = useRef<string | null>(null);
  useEffect(() => {
    if (route.kind !== "thread" || !thread.data || modal || closed) return;
    const key = `${role}:${route.id}`;
    if (openedFor.current === key) return;
    const { primary } = weigh(thread.data.actions, thread.data.closes);
    if (!opensOnArrival(primary)) return;
    openedFor.current = key;
    setModal({ op: primary!, thread: route.id });
  }, [route.kind, route.id, thread.data, modal, closed, role]);

  useEffect(() => {
    if (!thread.data) return;
    const q = queueViewFor(cat.data, thread.data.workflow);
    remember({ id: thread.data.id, name: header(thread.data, q).name });
    setRecent(keep(recents(), liveThreadIds(loaded.data)));
  }, [thread.data, cat.data, loaded.data]);

  // A reseed changes every thread id, and the recents list survives it in
  // localStorage: without this, the sidebar fills with tokens that 404 on
  // click. This runs whenever the queue reloads, not only when a thread is
  // opened, so a reseed clears them even if nobody happens to open a thread.
  useEffect(() => {
    if (!loaded.data) return;
    setRecent(keep(recents(), liveThreadIds(loaded.data)));
  }, [loaded.data]);

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
        setKhoj(true);
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
    setKhoj(false);
    go(`#/threads/${id}`);
  };

  /** Open an operation on a thread already in progress, never by id alone.
   *
   *  Six denials landed on an already-registered patient because a surface
   *  opened `phc.op.patient-register` by id, and `thread.actions` had
   *  already, correctly, stopped offering it. A copy of `actions` held from
   *  an earlier moment (a Khoj preview, a summary sheet opened minutes
   *  ago) can be just as stale as a hard-coded id, so this reads the thread
   *  fresh and checks with `offered()` — the guard's own membership test —
   *  right before opening. Not present: this says what the kernel said (its
   *  nudge), never nothing, because a button that does nothing is how the
   *  six denials went unnoticed.
   *
   *  Not for register(): that path opens a brand-new thread and its
   *  workflow's first operation, which has no `actions` yet to check against
   *  and is the bundle's own definition of what registers somebody. */
  const openIfOffered = async (
    threadId: string, op: Operation,
    extra?: { proposal?: Proposal; mobile?: string; seed?: Payload },
  ) => {
    try {
      const panel = await client.thread(threadId);
      const op2 = offered(op.id, panel.actions);
      if (op2) {
        setModal({ op: op2, thread: threadId, ...extra });
      } else {
        toast(panel.nudge || `${op.title} is no longer being offered on this thread.`);
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not open that action");
    }
  };

  /** Read `closes` before reloading, because the reload is what changes it. */
  const finish = (op: Operation) => {
    const wasClosing = thread.data?.closes === op.id;
    thread.reload();
    loaded.reload();
    if (!wasClosing || !cat.data) return;
    setClosed({
      what: op.title,
      cue: cue({
        station: thread.data?.station ?? null,
        opener: openerFor(cat.data, thread.data?.workflow, fac.data),
        // ponytail: first queue only, correct while a bundle has one queue per
        // station. A second queue at this station would leave the cue empty
        // with a full line sitting behind it; upgrade to merge queues[*].result.rows.
        queue: (queues[0]?.result.rows ?? []) as QueueRow[],
        closed: route.id,
      }),
    });
  };

  /** After a write, the journey the kernel now says is available here.
   *
   *  This is what makes the real ABHA journey the default path out of
   *  registration rather than something a clerk has to remember. It is not a
   *  hard coded "after register, do ABHA": it asks the kernel for this
   *  thread's actions again and opens the ABHA one only if the guard is
   *  offering it, which it does when the patient is registered, not yet
   *  linked, still at the station that declares the operation, and this role
   *  holds the capability. Anything else and nothing opens.
   *
   *  Opening a chat never runs this. The product spec's rule is about a new
   *  conversation, where auto-initiating the journey would make create the
   *  default and search the exception, which manufactures duplicate patients
   *  and duplicate ABHAs. Registration is downstream of a search that already
   *  missed, so the same rule points the other way here. */
  const offerJourney = async (
    id: string, justCommitted: string, workflow?: string,
    carried?: Payload, alreadyAsked?: boolean,
  ) => {
    // Only out of registration. The kernel offers phc.op.abha-link on a thread
    // for as long as the patient is unlinked, which is right for the action
    // list and would be wrong here: opening a national identity journey over
    // the screen after every vitals entry is how a clerk learns to dismiss it.
    // "The first operation of the workflow's first step" is the bundle's own
    // answer to "what registers somebody", the same one register() uses.
    if (!cat.data || justCommitted !== firstOperation(cat.data, workflow)) return;
    // The journey already ran, on the registration panel, and the clerk left
    // it without an identifier. Reopening it two seconds later is how a person
    // learns to dismiss it; the patient is ABHA pending and on the worklist,
    // which is what that path is for.
    if (alreadyAsked && !carried) return;
    try {
      const panel = await client.thread(id);
      const op = offered(ABHA_OP, panel.actions);
      // `seed` rather than a second journey: the identifier is already known,
      // and the consent and the method on that form are still a person's to
      // answer, behind its own un-prefilled confirm.
      if (op) setModal({ op, thread: id, seed: carried });
    } catch {
      /* the thread reload below is what tells the person where this stands */
    }
  };

  /** Create on miss: open an empty thread, which writes an encounter row and
   *  no clinical fact, then open the first operation of the workflow's first
   *  step. Whichever operation that is, is the bundle's answer. */
  const register = async (typed?: string) => {
    if (!cat.data) return;
    try {
      const opened = await client.openThread({});
      setKhoj(false);
      go(`#/threads/${opened.id}`);
      const id = firstOperation(cat.data, opened.workflow);
      const op = id ? cat.data.operations?.[id] : undefined;
      // The panel decides whether this operation opens the journey first; all
      // this screen adds is what the clerk already typed, when that was a
      // mobile number, so nobody types the same ten digits twice.
      if (op) setModal({ op, thread: opened.id, mobile: mobileHint(typed) });
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
        queues={queues}
        route={route}
        role={role}
        recent={recent}
        onGo={go}
        onAddRecent={() => setKhoj(true)}
        onRole={(r) => {
          setRole(r);
          setRoleState(r);
          toast(`Role: ${r === "demo" ? "every capability (demo)" : human(r)}`);
        }}
        onManageRoles={() => setRolesOpen(true)}
      />

      <div className="main">
        <div className="topbar">
          <div className="tb-info">
            <div className="tb-title">{heading[0]}</div>
            <div className="tb-sub">{heading[1]}</div>
          </div>
          {/* Khoj takes the centre of the header bar: the middle column of a
              three-column grid, not a side-aligned button pushed inward by a
              margin. The two side columns are equal (`1fr` each), so this
              stays centred on the bar itself, not on whatever the title or
              the theme toggle happen to measure. */}
          <button className="khoj-trigger" onClick={() => setKhoj(true)} aria-label="Search or ask Khoj">
            <span className="khoj-trigger-label"><Icon name="search" size="sm" />Search or ask</span>
            <span className="kbd">⌘K</span>
          </button>
          <div className="tb-actions">
            <span className={`dot${cat.error ? " down" : ""}`} title={cat.error ? "Kernel unreachable" : "Kernel reachable"} />
            <button className="icon-btn" onClick={toggleTheme} title="Light or dark">
              <Icon name={theme === "light" ? "moon" : "sun"} />
            </button>
          </div>
        </div>

        <div className={`view${route.kind === "thread" || route.kind === "ask" ? "" : " scroll"}`}>
          <div className="wrap">
            <Boundary key={`${route.kind}-${route.id}-${role}`}>
              {cat.loading && <Loading what="the catalogue" />}
              {cat.error && (
                <Failed error={cat.error} onRetry={cat.reload} />
              )}
              {cat.data && route.kind === "home" && (
                <>
                  {loaded.loading && <Loading what="today" />}
                  <Home
                    cat={cat.data}
                    queues={queues}
                    dashboards={dashboards}
                    tasklists={tasklists}
                    recent={recent}
                    onOpenThread={openThread}
                    onGo={go}
                    titles={titlesOf(cat.data)}
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

              {cat.data && route.kind === "notfound" && (
                <Failed
                  error={new ApiError(
                    `Nothing at ${route.id}.`,
                    "Check the address, or go back to Home.",
                    404,
                  )}
                  onRetry={() => go("#/home")}
                />
              )}

              {cat.data && route.kind === "view" && (
                <ViewScreen id={route.id} cat={cat.data} client={client} onOpenThread={openThread} />
              )}

              {cat.data && route.kind === "thread" && (
                <>
                  {thread.loading && <Loading what="this thread" />}
                  {thread.error && <Failed error={thread.error} onRetry={thread.reload} />}
                  {closed && (
                    <CloseCard
                      what={closed.what}
                      wentTo={thread.data?.station ?? null}
                      cue={closed.cue}
                      onCue={() => {
                        const c = closed.cue;
                        setClosed(null);
                        if (c.kind === "open") void register();
                        else if (c.kind === "next") openThread(c.thread);
                      }}
                    />
                  )}
                  {thread.data && (
                    <Thread
                      thread={thread.data}
                      cat={cat.data}
                      ctx={ctx}
                      said={said[thread.data.id] ?? []}
                      sections={(summary.data?.rows as SectionResult[] | undefined) ?? []}
                      asking={asking}
                      onSay={(t) => say(route.id, t, route.id)}
                      onAction={(op) => void openIfOffered(route.id, op)}
                      renderProposal={(p) => (
                        <OperationPanel
                          inline
                          op={proposalOperation(p, cat.data?.operations ?? {})}
                          thread={route.id}
                          client={client}
                          proposal={p}
                          instruments={cat.data?.instruments}
                          flags={thread.data?.flags ?? []}
                          onDone={(carried) => {
                            finish(proposalOperation(p, cat.data?.operations ?? {}));
                            void offerJourney(route.id, p.operation, thread.data?.workflow, carried);
                          }}
                        />
                      )}
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
                      onMore={() => setKhoj(true)}
                    />
                  )}
                </>
              )}
            </Boundary>
          </div>
        </div>
      </div>

      {khoj && cat.data && (
        <Overlay onClose={() => setKhoj(false)}>
          <Khoj
            cat={cat.data}
            client={client}
            queues={queues}
            nav={nav}
            onClose={() => setKhoj(false)}
            onOpenThread={openThread}
            onGo={(h: string) => {
              setKhoj(false);
              go(h);
            }}
            onAsk={(q: string) => {
              setKhoj(false);
              go("#/ask");
              say("workspace", q);
            }}
            onRegister={(typed: string) => void register(typed)}
            onAction={(t: string, op: Operation) => {
              setKhoj(false);
              go(`#/threads/${t}`);
              void openIfOffered(t, op);
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
            mobile={modal.mobile}
            seed={modal.seed}
            onCancel={() => setModal(null)}
            onDone={(carried) => {
              setModal(null);
              finish(modal.op);
              void offerJourney(
                modal.thread, modal.op.id, thread.data?.workflow, carried,
                // Whether that panel mounted the journey itself, which is the
                // same declaration the panel reads. A proposal keeps the plain
                // form, so a registration confirmed from a card is still
                // offered the journey here.
                !modal.proposal && !!modal.op.emits?.includes(ABHA_PENDING),
              );
            }}
          />
        </Overlay>
      )}

      {rolesOpen && cat.data && fac.data && (
        <Overlay onClose={() => setRolesOpen(false)}>
          <Roles
            cat={cat.data}
            roleIds={fac.data.roles}
            client={client}
            onClose={() => setRolesOpen(false)}
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
            void openIfOffered(sheet.thread, op);
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

/** The workflow's opener, but only for someone who may actually perform it.
 *  A nurse who cannot register must be cued to their queue, not to a button
 *  the guard will refuse. */
function openerFor(cat: Catalogue, workflow: string | undefined, facility?: Facility) {
  const id = firstOperation(cat, workflow);
  const op = id ? cat.operations?.[id] : undefined;
  if (!op) return null;
  return facility?.user?.capabilities?.includes(op.capability) ? op : null;
}

/** The topbar's two lines. On a thread the second is where the baton stands
 *  and what the last done step was called, both in the workflow's own
 *  words. */
function topbar(
  route: Route,
  cat: Catalogue | undefined,
  thread: ThreadView | null,
): [string, string] {
  if (route.kind === "home") return ["Today", ""];
  if (route.kind === "ask") return ["Workspace chat", ""];
  if (route.kind === "notfound") return ["Not found", ""];
  if (route.kind === "view") {
    const v = cat?.views?.[route.id];
    return [v?.title ?? title(route.id), ""];
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
      {data && <ViewRenderer result={data} decl={cat.views?.[id]} titles={titlesOf(cat)} onOpenThread={onOpenThread} />}
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
    <Sheet title={view.title ?? title(view.id)} onClose={onClose}>
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
              {cat.manifest?.title ?? "This bundle"} · {cat.manifest?.version ?? ""}
            </div>
          </div>
        </div>
        <div className="thread">
          {said.length === 0 && (
            <div className="empty">Nothing asked yet.</div>
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
                        <Counts l={hit} cat={cat} />
                        <div className="props">
                          <button className="prop" onClick={() => onGo(`#/views/${hit.decl.id}`)}>
                            <Icon name="list" />
                            <span style={{ flex: 1 }}>
                              <span className="p-l">Open {hit.decl.title ?? title(hit.decl.id)}</span>
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
export function titlesOf(cat: Catalogue): Record<string, string> {
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
