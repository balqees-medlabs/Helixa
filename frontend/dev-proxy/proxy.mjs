/**
 * Local development reverse proxy (research D1).
 *
 * Serves the Next dev server at `/` and the backend at `/api`, stripping the
 * prefix — the same shape Caddy provides in deployment. The refresh cookie is
 * issued by the backend with `Path=/auth`; it only reaches the proxied refresh
 * endpoint if the browser sees `/api/auth`, so rewrite that cookie path on
 * `/api/auth/*` responses. Pure infra: the backend is untouched.
 *
 * Run `npm run dev` (proxy + Next) or `npm run dev:proxy` (proxy only).
 */

import http from "node:http";
import process from "node:process";

const PORT = Number(process.env.PROXY_PORT ?? 3000);
const NEXT_URL = new URL(process.env.NEXT_URL ?? "http://127.0.0.1:3001");
const BACKEND_URL = new URL(process.env.BACKEND_URL ?? "http://127.0.0.1:8000");

function rewriteRefreshCookie(pathname, setCookie) {
  if (!setCookie || !pathname.startsWith("/api/auth/")) {
    return setCookie;
  }
  const cookies = Array.isArray(setCookie) ? setCookie : [setCookie];
  return cookies.map((cookie) => cookie.replace(/(;\s*path=)\/auth(?=;|$)/gi, "$1/api/auth"));
}

function forward(req, res) {
  const incoming = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const isApi = incoming.pathname === "/api" || incoming.pathname.startsWith("/api/");
  const target = isApi ? BACKEND_URL : NEXT_URL;
  const path = isApi ? incoming.pathname.slice("/api".length) || "/" : incoming.pathname;

  const upstream = http.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: `${path}${incoming.search}`,
      headers: { ...req.headers, host: target.host },
    },
    (response) => {
      const headers = { ...response.headers };
      if (isApi) {
        const rewritten = rewriteRefreshCookie(incoming.pathname, headers["set-cookie"]);
        if (rewritten) {
          headers["set-cookie"] = rewritten;
        }
      }
      res.writeHead(response.statusCode ?? 502, headers);
      response.pipe(res);
    },
  );

  upstream.on("error", (error) => {
    console.error(`[dev-proxy] ${req.method} ${incoming.pathname} failed: ${error.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "application/json" });
    }
    res.end(JSON.stringify({ detail: "Development proxy could not reach the upstream service" }));
  });

  req.pipe(upstream);
}

const server = http.createServer(forward);

server.listen(PORT, "127.0.0.1", () => {
  console.log(
    `[dev-proxy] http://127.0.0.1:${PORT} -> frontend ${NEXT_URL.origin}, backend ${BACKEND_URL.origin}/api`,
  );
});
