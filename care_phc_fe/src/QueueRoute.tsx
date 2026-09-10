import { useEffect, useState } from "react";

import Queue from "./components/Queue";
import type { PatientRow } from "./data";
import "./theme.css";

/** A plugin route, which care_fe renders as an ordinary page inside its own
 *  sidebar and chrome. We draw no chrome of our own.
 *
 *  This exists because CARE's encounters overview tabs by encounter class,
 *  while a primary health centre's question is which station the patient is
 *  standing at. That is the baton, and CARE has no concept of it. Everything
 *  else on this route's page is CARE's. */
export default function QueueRoute() {
  const [patients, setPatients] = useState<PatientRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("all");

  useEffect(() => {
    let live = true;
    fetch("/api/v1/phc/queue/")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => live && setPatients(d.patients))
      .catch((e) => live && setError(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, []);

  if (error) {
    return (
      <div className="phc" style={{ padding: 32, color: "var(--ink-3)", fontSize: 12.5 }}>
        Could not load the queue ({error}).
        <div style={{ marginTop: 6 }}>
          Every station still works from its own forms. Try again, or work from the
          patient list and record it when this comes back.
        </div>
      </div>
    );
  }
  if (!patients) return <div className="phc" style={{ padding: 32 }}>Loading the queue…</div>;

  return (
    <div className="phc" style={{ padding: 24 }}>
      <Queue
        patients={patients}
        tab={tab}
        onTab={setTab}
        onOpen={(p) => {
          window.location.href = `/facility/${p.facilityId}/patient/${p.patientId}`;
        }}
      />
    </div>
  );
}
