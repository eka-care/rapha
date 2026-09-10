import federation from "@originjs/vite-plugin-federation";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Mirrors care_eka_scribe_fe's shape so care_fe loads this the same way:
// register { url: "http://localhost:10123/assets/remoteEntry.js",
//            name: "care_phc_fe" } in care_fe's admin.
export default defineConfig({
  envPrefix: "REACT_",
  plugins: [
    federation({
      name: "care_phc_fe",
      filename: "remoteEntry.js",
      exposes: { "./manifest": "./src/manifest.tsx" },
      shared: ["react", "react-dom"],
    }),
    react(),
  ],
  build: { target: "esnext", minify: false, cssCodeSplit: false },
  server: { port: 10123 },
  preview: { port: 10123, cors: { origin: "*" } },
});
