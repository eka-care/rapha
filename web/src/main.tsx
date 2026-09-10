/** The shell: which declared view is on screen, and which thread is open.
 *
 *  There is no screen in this app that was written for a particular bundle.
 *  The navigation is the views the catalogue declares, the forms are the
 *  questionnaires the operations name, and the steps are the workflow's.
 */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { API_BASE, api, useAsync } from "./api";
import { mockApi } from "./mock";
import { OperationPanel, proposalOperation } from "./OperationPanel";
import { Thread } from "./Thread";
import { ViewRenderer } from "./ViewRenderer";
import type { Catalogue, Operation, Proposal, ViewDecl } from "./types";
import { Boundary, Failed, Loading, human } from "./ui";
import "./theme.css";
import "./renderer.css";

type Route = { kind: "view"; id: string } | { kind: "thread"; id: string };

function parse(hash: string): Route | null {
  const [head, id] = hash.replace(/^#\/?/, "").split("/");
  if (head === "threads" && id) return { kind: "thread", id };
  if (head === "views" && id) return { kind: "view", id };
  return head ? { kind: "view", id: head } : null;
}

function useRoute() {
  const [route, setRoute] = useState<Route | null>(() => parse(location.hash));
  useEffect(() => {
    const on = () => setRoute(parse(location.hash));
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return route;
}

const go = (path: string) => {
  location.hash = path;
};

function App() {
  const [demo, setDemo] = useState(false);
  const client = demo ? mockApi : api;
  const route = useRoute();
  const cat = useAsync<Catalogue>(() => client.catalogue(), [demo]);

  const views: ViewDecl[] = Object.values(cat.data?.views ?? {});
  const nav = views.filter((v) => v.kind !== "summary");
  const current =
    route?.kind === "view" ? route.id : nav.length ? nav[0].id : null;

  return (
    <div className="phc app">
      <header className="topbar">
        <div className="brand">{cat.data?.manifest?.title ?? "Renderer"}</div>
        <nav className="navtabs">
          {nav.map((v) => (
            <button key={v.id} className={`qtab${route?.kind === "view" && current === v.id ? " on" : ""}`}
                    onClick={() => go(`/views/${v.id}`)}>
              {v.title ?? human(v.id)}
            </button>
          ))}
        </nav>
        <div className="ml-auto srcline">
          <span className={`dot ${demo ? "demo" : cat.error ? "down" : "up"}`} />
          {demo ? "Demo data, nothing is real" : API_BASE}
          <button className="cq" onClick={() => setDemo(!demo)}>{demo ? "Use the API" : "Use demo data"}</button>
        </div>
      </header>

      <main className="main">
        <Boundary key={`${route?.kind}-${route?.kind === "view" || route?.kind === "thread" ? route.id : ""}-${demo}`}>
        {cat.loading && <Loading what="the catalogue" />}
        {cat.error && <Failed error={cat.error} onRetry={cat.reload} onDemo={demo ? undefined : () => setDemo(true)} />}
        {cat.data &&
          (route?.kind === "thread" ? (
            <ThreadScreen key={`${route.id}-${demo}`} id={route.id} cat={cat.data} demo={demo} />
          ) : current ? (
            <ViewScreen key={`${current}-${demo}`} id={current} demo={demo} cat={cat.data} />
          ) : (
            <Failed
              error={{
                name: "", message: "The catalogue declares no views.",
                next: "Add a view declaration to the bundle and rebuild catalogue.json. Until then there is nothing to draw.",
              } as never}
            />
          ))}
        </Boundary>
      </main>
    </div>
  );
}

function ViewScreen({ id, cat, demo }: { id: string; cat: Catalogue; demo: boolean }) {
  const client = demo ? mockApi : api;
  const { data, error, loading, reload } = useAsync(() => client.view(id), [id, demo]);
  const decl = cat.views?.[id];
  return (
    <>
      <h1 className="h1">{decl?.title ?? data?.title ?? human(id)}</h1>
      {decl?.summary && <p className="f-hint sub">{decl.summary}</p>}
      {loading && <Loading what={human(id)} />}
      {error && <Failed error={error} onRetry={reload} />}
      {data && <ViewRenderer result={data} titles={titlesOf(cat)} onOpenThread={(t) => go(`/threads/${t}`)} />}
    </>
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

function ThreadScreen({ id, cat, demo }: { id: string; cat: Catalogue; demo: boolean }) {
  const client = demo ? mockApi : api;
  const [open, setOpen] = useState<{ op: Operation; proposal?: Proposal } | null>(null);
  const [tab, setTab] = useState<"thread" | string>("thread");
  const thread = useAsync(() => client.thread(id), [id, demo]);
  const summaries = Object.values(cat.views ?? {}).filter((v) => v.kind === "summary");
  const summary = useAsync(
    () => (tab === "thread" ? Promise.resolve(null) : client.view(tab, id)),
    [tab, id, demo],
  );

  return (
    <>
      <div className="crumbs">
        <button className="link" onClick={() => history.back()}>Back</button>
        <span>/</span>
        <span>{human(id)}</span>
      </div>

      <div className="qtabs">
        <button className={`qtab${tab === "thread" ? " on" : ""}`} onClick={() => setTab("thread")}>Thread</button>
        {summaries.map((v) => (
          <button key={v.id} className={`qtab${tab === v.id ? " on" : ""}`} onClick={() => setTab(v.id)}>
            {v.title ?? human(v.id)}
          </button>
        ))}
      </div>

      {open && (
        <OperationPanel
          op={open.op}
          thread={id}
          client={client}
          proposal={open.proposal}
          instruments={cat.instruments}
          flags={thread.data?.flags ?? []}
          onCancel={() => setOpen(null)}
          onDone={() => {
            setOpen(null);
            thread.reload();
            summary.reload();
          }}
        />
      )}

      {thread.loading && <Loading what="this thread" />}
      {thread.error && <Failed error={thread.error} onRetry={thread.reload} />}

      {tab === "thread"
        ? thread.data && (
            <Thread
              thread={thread.data}
              onAction={(op) => setOpen({ op })}
              onReview={(p) => setOpen({ op: proposalOperation(p, cat.operations ?? {}), proposal: p })}
            />
          )
        : (
          <>
            {summary.loading && <Loading what="the summary" />}
            {summary.error && <Failed error={summary.error} onRetry={summary.reload} />}
            {summary.data && (
              <ViewRenderer
                result={summary.data}
                titles={titlesOf(cat)}
                onAction={(op) => setOpen({ op })}
                onReview={(p) => setOpen({ op: proposalOperation(p, cat.operations ?? {}), proposal: p })}
              />
            )}
          </>
        )}
    </>
  );
}

// Keep the root on the element so a hot reload re-renders instead of mounting
// a second React root onto the same node.
const el = document.getElementById("root")! as HTMLElement & { _root?: ReturnType<typeof createRoot> };
(el._root ??= createRoot(el)).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
