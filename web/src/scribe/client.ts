/** The three calls, and only the three. Split from session.ts because that
 *  file is pure and runs under plain node in scribe.check.ts; this one needs
 *  `import.meta.env` and a fetch, and a check that had to stub both would be
 *  checking the stub.
 *
 *  The Eka credentials are not here and cannot be: this posts a blob to the
 *  kernel, which holds them. What comes back is api/scribe.py:public(), which
 *  carries no transaction id, because that is the handle on somebody's
 *  consultation audio and it is not the browser's.
 */
import { ApiError, API_BASE, currentRole } from "../api";
import type { ScribeSession } from "./session";

const ROUTE = "/api/v1/phc/scribe/sessions";

async function ask(path: string, init: RequestInit): Promise<ScribeSession> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "X-PHC-Role": currentRole(), ...(init.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the kernel at ${API_BASE}, so the recording went nowhere.`,
      "Nothing was uploaded or kept. Type the note.",
    );
  }
  const body = await res.text();
  if (!res.ok) {
    let detail = body.slice(0, 400);
    try {
      detail = JSON.parse(body).detail ?? detail;
    } catch { /* not json, the text is the detail */ }
    throw new ApiError(detail || `The kernel answered ${res.status}.`,
                       "Type the note.", res.status);
  }
  return JSON.parse(body) as ScribeSession;
}

export type Templates = {
  default: string | null;
  choose: { operation: string; title: string }[];
  /** The Eka library template this station is written up in unless the person
   *  turns it off, by the title the bundle declares. Null when the station
   *  declares none or the library has no such template. */
  note?: { id: string; title: string } | null;
};

/** What this station may be recorded into, ahead of the microphone being
 *  pressed at all. No language comes back: nothing picks one. */
export async function templates(station: string): Promise<Templates> {
  const res = await fetch(`${API_BASE}${ROUTE.replace("/sessions", "/templates")}?station=${encodeURIComponent(station)}`,
                          { headers: { "X-PHC-Role": currentRole() } });
  if (!res.ok) throw new ApiError(`The kernel answered ${res.status}.`, "Type the note.", res.status);
  return res.json();
}

/** Hand one recording to the kernel. The blob is the body: no multipart, no
 *  base64, and no field around it that could carry a patient's name. */
/** NO LANGUAGE ARGUMENT. Every recording goes up as every language this
 *  facility supports and the service decides what it heard. A consultation
 *  in a primary health centre is not in one language, and asking somebody
 *  to predict their own before they speak cost them the transcript when
 *  they guessed wrong. api/scribe.LANGUAGES says the same at length. */
export const startSession = (thread: string, audio: Blob, operations: string[], library: string[] = []) =>
  ask(`${ROUTE}?thread=${encodeURIComponent(thread)}&operations=${encodeURIComponent(operations.join(","))}` +
      (library.length ? `&library=${encodeURIComponent(library.join(","))}` : ``),
      { method: "POST", body: audio, headers: { "Content-Type": audio.type || "audio/webm" } });

export const pollSession = (id: string) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}`, { method: "GET" });

/** Fill more operations from a session already transcribed, without
 *  re-recording: the transcript stands, only the questionnaire is new. */
export const refill = (id: string, operations: string[]) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}/extract`,
      { method: "POST", body: JSON.stringify({ operations }), headers: { "Content-Type": "application/json" } });

/** Withdrawal, and also the doctor giving up on it. Same call, because the
 *  effect is the one thing E.3 asks for: nothing further is fetched and any
 *  draft held is dropped. */
export const dropSession = (id: string) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}`, { method: "DELETE" });


/** One of Eka's own note templates, as the workspace lists it. */
export type LibraryItem = { id: string; title: string; desc: string; default: boolean; favorite: boolean };

/** The workspace's template library, ahead of any recording. Read only. */
export async function library(): Promise<LibraryItem[]> {
  const res = await fetch(`${API_BASE}${ROUTE.replace("/sessions", "/library")}`,
                          { headers: { "X-PHC-Role": currentRole() } });
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail ?? ""; } catch { /* not json */ }
    throw new ApiError(detail || `The kernel answered ${res.status}.`, "Type the note.", res.status);
  }
  return (await res.json()).items;
}

/** Have a recording already transcribed written up in one library template.
 *  No audio moves: the service shapes the transcript it holds. */
export const writeNote = (id: string, template: string) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}/note?template=${encodeURIComponent(template)}`, { method: "POST" });


/** One template's note for a visit: a section per recording, oldest first,
 *  each under the name of whoever made it. */
export type ThreadNote = {
  template: string;
  title: string;
  sections: { id: string; actor: string; at: string; text: string }[];
};

/** The notes this visit has had written, whoever wrote them. */
export async function threadNotes(thread: string): Promise<ThreadNote[]> {
  const res = await fetch(`${API_BASE}${ROUTE.replace("/sessions", "/notes")}?thread=${encodeURIComponent(thread)}`,
                          { headers: { "X-PHC-Role": currentRole() } });
  if (!res.ok) throw new ApiError(`The kernel answered ${res.status}.`, "", res.status);
  return (await res.json()).notes;
}
