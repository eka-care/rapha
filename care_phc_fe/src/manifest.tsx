import { lazy } from "react";

const Workspace = lazy(() => import("./WorkspaceRoute"));
const ThreadTab = lazy(() => import("./ThreadTab"));

/** care_fe reads this after loading remoteEntry.js.
 *
 *  We take full-page routes rather than only an encounter tab, because the
 *  prototype is a workspace and a workspace needs its own sidebar, palette and
 *  queue. The encounter tab stays: someone already inside CARE's own encounter
 *  page should see the thread there rather than being sent elsewhere. */
const manifest = {
  plugin: "care-phc-fe",
  routes: {
    "/phc": () => <Workspace />,
  },
  navItems: [
    { name: "PHC workspace", url: "/phc" },
  ],
  encounterTabs: { phc: ThreadTab },
} as const;

export default manifest;
