import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The questionnaires live one directory up, in questionnaires/. They are
// declarations, not app code, so the dev server has to be allowed to read
// outside its root. When the kernel API serves questionnaires, delete this
// and the glob in src/declarations.ts.
export default defineConfig({
  plugins: [react()],
  server: { port: Number(process.env.PORT) || 5173, fs: { allow: [".."] } },
});
