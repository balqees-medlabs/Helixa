/**
 * `npm run dev`: the reverse proxy on :3000 plus Next on :3001, so local
 * requests are same-origin exactly like the Caddy deployment.
 */

import { spawn } from "node:child_process";
import process from "node:process";

import "./proxy.mjs";

const next = spawn(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["next", "dev", "-p", "3001"],
  {
    stdio: "inherit",
    env: process.env,
  },
);

const shutdown = (signal) => {
  next.kill(signal);
  process.exit(0);
};

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

next.on("exit", (code) => {
  process.exit(code ?? 0);
});
