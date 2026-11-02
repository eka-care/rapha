/** The kernel API, and the truth about whether it is there.
 *
 *  Every failure comes back as an ApiError carrying a `next`: one plain
 *  sentence saying what the person should do. A screen that renders an
 *  ApiError is never blank and never says "something went wrong".
 */
import { useCallback, useEffect, useState } from "react";
import type { Resolution } from "./desk";
import type { Catalogue, Facility, Questionnaire, Register, SubjectView, ThreadView, ViewResult } from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8000";
const PREFIX = "/api/v1/phc";

/** Who the kernel thinks is asking. There is no authentication on this
 *  kernel: api/main.caller() reads X-PHC-Role and falls back to a union role
 *  that holds every capability. Switching it here switches which actions come
 *  back on every thread, which is the whole point of the switcher in the
 *  sidebar foot. It is a demo affordance and not a security boundary, and the
 *  API says so itself.
 *
 *  DEMO_ROLE is the kernel's default and the one value that is not a person. */
export const DEMO_ROLE = "demo";
const ROLE_KEY = "phc.role";

let role: string = (() => {
  try {
    return localStorage.getItem(ROLE_KEY) || DEMO_ROLE;
  } catch {
    return DEMO_ROLE;                                  // private window, no storage
  }
})();

export const currentRole = () => role;

export function setRole(next: string) {
  role = next;
  try {
    localStorage.setItem(ROLE_KEY, next);
  } catch {
    /* the header still carries it for this session */
  }
}

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
      headers: { "Content-Type": "application/json", "X-PHC-Role": role, ...(init?.headers ?? {}) },
    });
  } catch {
    // fetch only rejects for network, DNS, TLS and CORS. All four look the
    // same from here, so say all four.
    throw new ApiError(
      `Cannot reach the kernel API at ${API_BASE}.`,
      "Start it and reload.",
    );
  }
  if (res.status === 404) {
    // A 404 is two different sentences: the record is gone, or the route was
    // never built. The person cannot tell which, so say both.
    throw new ApiError(
      `Nothing at ${path}.`,
      "Check the id in the address bar, or the kernel does not serve this route.",
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
        ? "Someone who holds this capability has to do this step."
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
  /** What every form asks. Served by the kernel, keyed by the slug an
   *  operation names in `input`. Until this existed the renderer read the
   *  files off disk at build time, which made a form the one thing on a
   *  screen that did not come from the kernel. */
  questionnaires: () => req<{ questionnaires: Record<string, Questionnaire> }>("/questionnaires/"),
  /** A bound choice's concepts, expanded by the kernel's own terminology.
   *  200 is the route's own hard ceiling (api/main.py clamps it), so this
   *  asks for every concept the kernel will give. See declarations.ts for
   *  what that ceiling costs the day a value set is bigger than it. */
  valueset: (slug: string, limit = 200) =>
    req<{ valueset: string; concepts: { value: string; display: string; system: string }[] }>(
      `/valuesets/${encodeURIComponent(slug)}/?limit=${limit}`),
  facility: () => req<Facility>("/facility/"),
  /** Who might this be: this centre's own register and the patient directory,
   *  asked together and answered together. Always 200, even with no directory
   *  and no socket: the body says whether the directory was reachable and the
   *  local half is always there. So the desk's one failure mode is "nobody
   *  matched", which is a sentence, and never a screen that says the search
   *  broke when half of it worked. */
  patients: (q: string, limit = 8) =>
    req<Resolution>(`/patients/search/?q=${encodeURIComponent(q)}&limit=${limit}`),
  view: (id: string, thread?: string) =>
    req<ViewResult>(`/views/${id}/${thread ? `?thread=${encodeURIComponent(thread)}` : ""}`),
  thread: (id: string) => req<ThreadView>(`/threads/${id}/`),
  /** The spine: one subject and every visit it has had. 404 when the bundle
   *  declares no spine, which is a real answer and not an error to hide. */
  subject: (id: string) => req<SubjectView>(`/subjects/${id}/`),
  /** This centre's own register, newest first. The top of the patients
   *  screen's hierarchy; a row's visits are fetched when it opens. */
  register: (limit = 200) => req<Register>(`/patients/?limit=${limit}`),
  /** The rendered surface's write. `confirmed` is only ever true because a
   *  person ticked an empty box on this screen. */
  commit: (op: string, body: { thread: string; payload: unknown; confirmed: boolean }) =>
    post<unknown>(`/operations/${op}/commit/`, body),
  /** A correction to something already recorded on a visit that is still
   *  open. Not a second commit: the kernel REPLACES the rows this operation
   *  wrote rather than adding a contradictory set. */
  amend: (op: string, body: { thread: string; payload: unknown; confirmed: boolean }) =>
    post<unknown>(`/operations/${op}/amend/`, body),
  confirm: (proposal: string, body: { payload: unknown; confirmed: boolean }) =>
    post<unknown>(`/proposals/${proposal}/confirm/`, body),
  reject: (proposal: string, body: { reason?: string }) =>
    post<unknown>(`/proposals/${proposal}/reject/`, body),
  /** Opens an empty visit. It writes an encounter row and no clinical fact,
   *  which is why the palette may call it on a miss: it asserts nothing about
   *  a person. Everything the person then types still goes through the
   *  guard. */
  openThread: (body: { token?: string } = {}) => post<ThreadView>("/threads/", body),
  /** The shipped presets (bundle.yaml's `roles:`), read only, plus whatever
   *  a facility has already saved on top. Both come back so the editor can
   *  seed from a deviation rather than showing the preset as if the save
   *  never happened. */
  roles: () =>
    req<{ presets: Record<string, string[]>; overrides: Record<string, string[]>; current: string }>("/roles/"),
  /** A facility's own deviation from a preset. api/main.py stores it apart
   *  from the preset and requires facility.admin; a caller without it gets a
   *  403 back through the same ApiError every other write does. */
  setRole: (role: string, capabilities: string[]) =>
    req<{ role: string; capabilities: string[] }>(`/roles/${role}/`, {
      method: "PUT",
      body: JSON.stringify({ capabilities }),
    }),
};

/** What a screen needs to talk to a kernel. */
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
