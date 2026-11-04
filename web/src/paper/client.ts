/** The medical records SDK, set up the way this product needs it.
 *
 *  `@eka-care/medical-records-ts-sdk` is the same SDK the claims portal
 *  uses, doing the same job: it asks the service for an upload
 *  authorisation and sends the photograph straight to the presigned bucket
 *  that comes back. So a ten megabyte picture goes browser to bucket and
 *  never through this product's kernel.
 *
 *  TWO THINGS ARE SET DIFFERENTLY FROM THE CLAIMS PORTAL, and both are
 *  because of what a health centre workstation is.
 *
 *  `baseUrl` points at our own kernel rather than at the service. The
 *  claims portal's users are Eka account holders with sessions of their
 *  own; a health centre is one shared machine signed in as a facility, and
 *  the credential it would otherwise have to carry in the browser is the
 *  facility's. The kernel proxies and attaches it (api/vault.py), so the
 *  SDK behaves exactly as it does there and no token is ever in this
 *  browser. The presigned upload is unaffected: that URL is the bucket's,
 *  not the service's, and the SDK sends it directly.
 *
 *  `cache` is OFF. The SDK's offline store is one of the best things about
 *  it and it is wrong here: it keeps records and smart reports in IndexedDB
 *  on the device, and this device is a counter shared by a queue of people.
 *  One patient's laboratory report sitting on disk while the next patient is
 *  served is not a feature. It is one flag the day this runs on a clinician's
 *  own tablet.
 */
import { MedicalRecordsClient } from "@eka-care/medical-records-ts-sdk";
import { API_BASE, ApiError, currentRole } from "../api";

/** The tenant the SDK scopes its own local bookkeeping by. It never leaves
 *  the device -- the service scopes by the patient's oid and the facility's
 *  token, and `bid` appears in no request -- so this is the facility's name
 *  for itself and not a credential. */
const BID = "phc";

let held: MedicalRecordsClient | null = null;

export function records(): MedicalRecordsClient {
  if (!held) {
    held = new MedicalRecordsClient({
      baseUrl: API_BASE,
      cache: false,
      defaultHeaders: { "X-PHC-Role": currentRole() },
    });
  }
  return held;
}

/** Upload one photograph against one patient, and answer the document id.
 *
 *  `patientId` is the patient's own Eka oid, which the patient directory
 *  put on their row when this centre published them. It is what the service
 *  files the document under, and it is why the paper follows the patient
 *  rather than living on this visit alone.
 */
export async function filePaper(patientId: string, file: File): Promise<string> {
  const answer = await records().addDocument({
    bid: BID,
    patientId,
    batchRequests: [{
      // "lr" is the service's code for a laboratory report, which is what
      // the parser reads best and what a patient most often carries. A
      // discharge summary read as one yields its date and whatever table it
      // holds, which is more than nothing and never presented as more.
      documentType: "lr",
      files: [{ contentType: (file.type || "application/pdf") as "application/pdf",
                file_size: file.size }],
    }],
    files: [[file]],
    filenames: [[file.name]],
  });
  const id = answer?.batch_response?.[0]?.document_id;
  if (!id) {
    throw new ApiError("The records service accepted the picture and gave "
                       + "nothing back to read it by.",
                       "Type what the paper says.");
  }
  return id;
}

/** What the service read off a document, as a draft for the form.
 *
 *  The reading is the kernel's, not this file's, and that is on purpose:
 *  which question each part of the paper lands in is the instrument
 *  declaration's `fills`, which the kernel lints against the questionnaire.
 *  A copy of that mapping in a browser would be a copy to keep in step.
 */
export async function readPaper(operation: string, documentId: string,
                                patient: string) {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/paper`, {
      method: "POST",
      body: JSON.stringify({ operation, document_id: documentId, patient }),
      headers: { "Content-Type": "application/json", "X-PHC-Role": currentRole() },
    });
  } catch {
    throw new ApiError(
      `Cannot reach the kernel at ${API_BASE}, so the paper cannot be read.`,
      "The paper is saved on the patient's record. Type what it says.");
  }
  const body = await res.text();
  if (!res.ok) {
    let detail = body.slice(0, 400);
    try { detail = JSON.parse(body).detail ?? detail; } catch { /* the text is the detail */ }
    throw new ApiError(detail || `The kernel answered ${res.status}.`,
                       "Type what the paper says.", res.status);
  }
  return JSON.parse(body);
}
