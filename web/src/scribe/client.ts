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

/** Hand one recording to the kernel. The blob is the body: no multipart, no
 *  base64, and no field around it that could carry a patient's name. */
export const startSession = (thread: string, audio: Blob) =>
  ask(`${ROUTE}?thread=${encodeURIComponent(thread)}`,
      { method: "POST", body: audio, headers: { "Content-Type": audio.type || "audio/webm" } });

export const pollSession = (id: string) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}`, { method: "GET" });

/** Withdrawal, and also the doctor giving up on it. Same call, because the
 *  effect is the one thing E.3 asks for: nothing further is fetched and any
 *  draft held is dropped. */
export const dropSession = (id: string) =>
  ask(`${ROUTE}/${encodeURIComponent(id)}`, { method: "DELETE" });
