import { lazy } from "react";

const ThreadTab = lazy(() => import("./ThreadTab"));
const QueueRoute = lazy(() => import("./QueueRoute"));

/** care_fe reads this after loading remoteEntry.js.
 *
 *  We add to CARE's pages rather than replacing them. CARE already ships the
 *  patient directory (PatientIndex, search first with create only on a miss),
 *  the encounters overview and a command palette, so we ship none of those.
 *
 *  What is left is the part CARE has no concept of: a patient's position in
 *  the outpatient line. That is the encounter tab, and a queue grouped by
 *  station rather than by encounter class.
 *
 *  The route draws no chrome. care_fe merges plugin routes into its own and
 *  renders them inside its sidebar, so a route here is an ordinary CARE page. */
const manifest = {
  plugin: "care-phc-fe",
  encounterTabs: { phc: ThreadTab },
  routes: {
    "/phc/queue": () => <QueueRoute />,
  },
  navItems: [{ name: "Station queue", url: "/phc/queue" }],
} as const;

export default manifest;
