import type { Action, Patient, Thread } from "./types";

/** A patient row as the queue and directory need it. */
export type PatientRow = Patient & {
  init: string; phone: string; cat: string; token: number | null;
  patientId?: string; facilityId?: string;
  dx: string; last: string; today: boolean; abha: string | null;
  flags: string[]; station: string | null;
  team: [string, string, string][];
  audit: [string, string, string][];
  agent: string;
  nudges: Record<string, string>;
  actions: Record<string, Action[]>;
};

export type Facility = {
  bundles: Record<string, string[]>;
  capabilities: string[];
  patients: PatientRow[];
};

export const BUNDLE_LABELS: Record<string, string> = {
  frontdesk: "Front desk", nurse: "Nurse", mo: "Medical officer",
  lab: "Lab technician", lab_incharge: "Lab in-charge", pharmacist: "Pharmacist",
  asha: "ASHA", anm: "ANM", cho: "CHO",
};

export const BUNDLE_SUBS: Record<string, string> = {
  frontdesk: "Registration and ABHA", nurse: "Vitals and triage",
  mo: "Consultation and prescribing", lab: "Result entry",
  lab_incharge: "Result entry and release", pharmacist: "Dispense and stock",
  asha: "Household visits", anm: "Household visits and vitals",
  cho: "Community clinical care",
};

export const STATION_LABELS: Record<string, string> = {
  reception: "Reception", nurse: "Vitals", doctor: "Doctor",
  lab: "Lab", pharmacy: "Pharmacy",
};

/** What the backend's thread endpoint would return for this patient and cadre. */
export function threadFor(p: PatientRow, bundle: string, f: Facility): Thread {
  return {
    patient: { name: p.name, age: p.age, sex: p.sex, village: p.village, note: p.note },
    flags: p.flags,
    station: p.station,
    actions: p.actions[bundle] ?? [],
    team: p.team ?? [],
    audit: p.audit ?? [],
    agent: p.agent,
    nudge: p.nudges[bundle] ?? "",
    capabilities: f.capabilities,
    held: f.bundles[bundle] ?? [],
  };
}

export function stateLabel(p: PatientRow): string {
  const f = new Set(p.flags);
  if (f.has("dispensed.complete")) return "Closed";
  if (f.has("dispensed.partial")) return "Part dispensed";
  if (f.has("lab.resulted")) return "Result ready";
  if (f.has("lab.ordered")) return "Lab ordered";
  if (f.has("rx.confirmed")) return "Rx confirmed";
  if (f.has("consult.documented")) return "Consult done";
  if (f.has("vitals.flagged")) return "Vitals abnormal";
  if (f.has("vitals.recorded")) return "Vitals recorded";
  return "Registered";
}
