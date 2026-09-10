/** The kernel API, and the truth about whether it is there.
 *
 *  Every failure comes back as an ApiError carrying a `next`: one plain
 *  sentence saying what the person should do. A screen that renders an
 *  ApiError is never blank and never says "something went wrong".
 */
import { useCallback, useEffect, useState } from "react";
import type { Catalogue, ThreadView, ViewResult } from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";
const PREFIX = "/api/v1/phc";

export class ApiError extends Error {
  next: string;
  status?: number;
  constructor(message: string, next: string, status?: number) {
    super(message);
    this.next = next;
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${PREFIX}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // fetch only rejects for network, DNS, TLS and CORS. All four look the
    // same from here, so say all four.
    throw new ApiError(
      `Cannot reach the kernel API at ${API_BASE}.`,
      "Start it and reload. If it is running, it is refusing this origin: it needs to allow " +
        `${location.origin} in CORS. Meanwhile, "Use demo data" draws these screens from a fixture.`,
    );
  }
  if (res.status === 404) {
    // A 404 is two different sentences: the record is gone, or the route was
    // never built. The person cannot tell which, so say both.
    throw new ApiError(
      `Nothing at ${path}.`,
      "Either that record does not exist any more, or the kernel does not serve this route yet. " +
        "Check the id in the address bar first, then kernel/contracts.py ROUTES for the name it expects.",
      404,
    );
  }
  if (!res.ok) {
    const body = await res.text();
    let detail = body.slice(0, 400);
    try {
      const parsed = JSON.parse(body);
      detail = parsed.reason ?? parsed.detail ?? parsed.error ?? detail;
    } catch {
      /* not json, the text is the detail */
    }
    throw new ApiError(
      detail || `The API answered ${res.status}.`,
      res.status === 403
        ? "You do not hold the capability this needs. Someone with it has to do this step."
        : res.status >= 500
          ? "This is the API's error, not yours. Its log will say more."
          : "Correct what it names above and try again.",
      res.status,
    );
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const post = <T,>(path: string, body: unknown) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  catalogue: () => req<Catalogue>("/catalogue/"),
  view: (id: string, thread?: string) =>
    req<ViewResult>(`/views/${id}/${thread ? `?thread=${encodeURIComponent(thread)}` : ""}`),
  thread: (id: string) => req<ThreadView>(`/threads/${id}/`),
  /** The rendered surface's write. `confirmed` is only ever true because a
   *  person ticked an empty box on this screen. */
  commit: (op: string, body: { thread: string; payload: unknown; confirmed: boolean }) =>
    post<unknown>(`/operations/${op}/commit/`, body),
  confirm: (proposal: string, body: { payload: unknown; confirmed: boolean }) =>
    post<unknown>(`/proposals/${proposal}/confirm/`, body),
  reject: (proposal: string, body: { reason?: string }) =>
    post<unknown>(`/proposals/${proposal}/reject/`, body),
};

/** What a screen needs to talk to a kernel. The demo client in mock.ts
 *  satisfies the same shape, so a screen never learns which one it has. */
export type Client = typeof api;

/** Load once, reload on demand, and never leave the caller without one of the
 *  three states. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({ loading: true });
  const [nonce, setNonce] = useState(0);
  const run = useCallback(fn, deps); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let live = true;
    setState({ loading: true });
    run().then(
      (data) => live && setState({ data, loading: false }),
      (e) =>
        live &&
        setState({
          loading: false,
          error: e instanceof ApiError ? e : new ApiError(String(e?.message ?? e), "This is a bug in the renderer, not in your data."),
        }),
    );
    return () => {
      live = false;
    };
  }, [run, nonce]);

  return { ...state, reload: () => setNonce((n) => n + 1) };
}
