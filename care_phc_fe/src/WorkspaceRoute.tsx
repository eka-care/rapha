import { useEffect, useState } from "react";

import Workspace from "./Workspace";
import type { Facility } from "./data";

/** The care_fe route. Fetches the facility once and hands it to the shell.
 *
 *  The cadre is not switchable here: it is whichever bundles the signed-in user
 *  holds, and the backend already filters actions by them. */
export default function WorkspaceRoute() {
  const [facility, setFacility] = useState<Facility | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bundle, setBundle] = useState("mo");

  useEffect(() => {
    let live = true;
    fetch("/api/v1/phc/facility/")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((f) => {
        if (!live) return;
        setFacility(f);
        if (f.bundle) setBundle(f.bundle);
      })
      .catch((e) => live && setError(String(e.message ?? e)));
    return () => {
      live = false;
    };
  }, []);

  if (error) {
    return (
      <div className="phc" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
        Could not reach the facility ({error}).
        <div style={{ marginTop: 6, fontSize: 12 }}>
          Every station still works from its own forms. Try again, or record on paper and
          enter it when this comes back.
        </div>
      </div>
    );
  }
  if (!facility) return <div className="phc" style={{ padding: 40 }}>Loading…</div>;
  return <Workspace facility={facility} bundle={bundle} />;
}
