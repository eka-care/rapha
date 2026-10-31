import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Nothing outside this root is read any more. The questionnaires and the
// value sets arrive from the kernel (GET /questionnaires/, GET
// /valuesets/{slug}), so the `fs.allow` escape that let the dev server read
// one directory up is gone with the globs that needed it.
export default defineConfig({
  plugins: [react()],
  server: { port: Number(process.env.PORT) || 5173 },
});
