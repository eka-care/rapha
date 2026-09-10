import { lazy } from "react";

const ThreadTab = lazy(() => import("./ThreadTab"));

/** care_fe reads this after loading remoteEntry.js.
 *
 *  encounterTabs is a supported manifest field, so the thread rides on the
 *  encounter page rather than needing a new extension point in care_fe. */
const manifest = {
  plugin: "care-phc-fe",
  encounterTabs: { phc: ThreadTab },
} as const;

export default manifest;
