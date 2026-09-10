export type Action = {
  id: string; tool: string; short: string; title: string; summary: string; station: string;
  capability: string;
  instrument: "form" | "device" | "constrained-voice" | "scribe" | "palette";
  irreversibility: "reversible" | "correctable" | "irreversible";
  verified: "verified" | "unverified" | "stale";
  preconditions: string[];
  kind: "read" | "write";
};

export type Patient = { name: string; age: number; sex: string; village: string; note: string };

/** Exactly what the backend returns for a thread. The frontend decides none of
 *  it: visibility and ordering are the guard's, so there is one implementation
 *  of the rules and it is the one that enforces them. */
export type Thread = {
  patient: Patient;
  flags: string[];
  station: string | null;
  actions: Action[];
  /** [initials, name, role on this episode] */
  team: [string, string, string][];
  /** [time, operation id, actor] */
  audit: [string, string, string][];
  agent: string;
  nudge: string;
  /** Every capability, and the ones this person holds. Shown, not hidden:
   *  permissions are the product, so they belong on the patient screen. */
  capabilities: string[];
  held: string[];
};
