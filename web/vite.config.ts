/** Two ways to run this app, and the second one exists only so the Eka
 *  session can be tested.
 *
 *  `npm run dev` is the ordinary one: http on localhost, where the session
 *  gate is off because a cookie for `.eka.care` is never sent to localhost
 *  and a gate nobody can satisfy only locks a developer out.
 *
 *  `EKA_HOST=<you>.eka.care npm run dev:eka` is the other, and it is
 *  nectar's own setup (apps/abdm-parent/README.md): https, on a subdomain of
 *  eka.care that /etc/hosts points at this machine, on port 443. All three
 *  matter. The cookie belongs to `.eka.care`, so the page has to be served
 *  from one; it is Secure, so the page has to be https; and the port has to
 *  be the default one because that is the origin nectar's own clients use.
 *
 *  THE PROXY IS WHY THE REST OF THE APP STILL WORKS. A page on
 *  `https://x.eka.care` cannot call `http://localhost:8000`: the browser
 *  blocks it as mixed content, and it would be a cross origin call besides.
 *  So in that mode `/api` is proxied to the kernel and the app is told to
 *  use its own origin, which makes every kernel call same origin and plain.
 */
import basicSsl from "@vitejs/plugin-basic-ssl";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const EKA_HOST = process.env.EKA_HOST;
const KERNEL = process.env.VITE_KERNEL ?? "http://localhost:8000";

export default defineConfig({
  plugins: EKA_HOST ? [react(), basicSsl()] : [react()],
  server: EKA_HOST
    ? {
        host: EKA_HOST,
        port: 443,
        strictPort: true,
        // Same origin to the browser, this machine's kernel underneath.
        proxy: { "/api": { target: KERNEL, changeOrigin: true } },
      }
    : undefined,
});
