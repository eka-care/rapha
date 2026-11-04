/** Handing one photograph to the kernel, and taking back a draft.
 *
 *  The picture is the body: no multipart, no base64, and no field around it
 *  that could carry a patient's name. The only thing beside it is the name
 *  of the operation whose form is open, which the kernel needs to know which
 *  declaration governs the read.
 *
 *  The file's own name goes up in a header rather than the body, because the
 *  service's extension check wants it and because a header is the one place
 *  it cannot be mistaken for content. It is a filename off this clerk's
 *  device; it is not logged by the kernel and it is not stored.
 */
import { API_BASE, ApiError, currentRole } from "../api";
import type { ScribeDraft } from "../scribe/session";

const ROUTE = "/api/paper";

export async function readPaper(operation: string, file: File): Promise<ScribeDraft> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${ROUTE}?operation=${encodeURIComponent(operation)}`, {
      method: "POST",
      body: file,
      headers: {
        "Content-Type": file.type || "application/octet-stream",
        "X-Filename": file.name.replace(/[^\w.\-]/g, "_").slice(0, 120),
        "X-PHC-Role": currentRole(),
      },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the kernel at ${API_BASE}, so the paper cannot be read.`,
      "Type what the paper says.");
  }
  const body = await res.text();
  if (!res.ok) {
    let detail = body.slice(0, 400);
    try { detail = JSON.parse(body).detail ?? detail; } catch { /* the text is the detail */ }
    throw new ApiError(detail || `The kernel answered ${res.status}.`,
                       "Type what the paper says.", res.status);
  }
  return JSON.parse(body) as ScribeDraft;
}
