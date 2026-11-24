import { execFileSync } from "node:child_process";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

const frontendDir = process.cwd();
const script = path.join(frontendDir, "scripts", "check-contract.mjs");
const backendContract = path.resolve(frontendDir, "../backend", "openapi.json");
const committedClient = path.join(frontendDir, "lib", "api", "schema.d.ts");

interface RunResult {
  ok: boolean;
  status: number | undefined;
  output: string;
}

function runCheck(cwd: string): RunResult {
  try {
    const stdout = execFileSync(process.execPath, [script], { cwd, encoding: "utf8" });
    return { ok: true, status: 0, output: stdout };
  } catch (error) {
    const failure = error as { status?: number; stdout?: string; stderr?: string };
    return {
      ok: false,
      status: failure.status,
      output: `${failure.stdout ?? ""}${failure.stderr ?? ""}`,
    };
  }
}

/**
 * Builds an isolated checkout-shaped fixture: `<base>/frontend` (cwd) with its
 * own backend contract and generated client, sharing this repo's
 * node_modules/.bin/openapi-typescript.
 */
function fixtureWith(clientContent: string): string {
  const base = mkdtempSync(path.join(tmpdir(), "helixa-contract-"));
  const cwd = path.join(base, "frontend");
  mkdirSync(path.join(cwd, "lib", "api"), { recursive: true });
  mkdirSync(path.join(base, "backend"), { recursive: true });
  cpSync(backendContract, path.join(base, "backend", "openapi.json"));
  writeFileSync(path.join(cwd, "lib", "api", "schema.d.ts"), clientContent);
  symlinkSync(path.join(frontendDir, "node_modules"), path.join(cwd, "node_modules"), "dir");
  return base;
}

describe("contract drift guard (SC-008 / FR-021)", () => {
  it("accepts the committed client against the real backend contract", () => {
    const result = runCheck(frontendDir);

    expect(result.ok, result.output).toBe(true);
    expect(result.output).toContain("Contract in sync");
  });

  it("fails when the backend contract changes without regenerating the client", () => {
    const staleClient = readFileSync(committedClient, "utf8") + "\nexport type StaleMarker = 1;\n";
    const base = fixtureWith(staleClient);
    try {
      const result = runCheck(path.join(base, "frontend"));

      expect(result.ok, "drift must fail the check").toBe(false);
      expect(result.status).toBe(1);
      expect(result.output).toContain("Contract drift");
      expect(result.output).toContain("npm run gen:client");
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  });

  it("regenerates an identical client from the contract (positive fixture)", () => {
    const base = fixtureWith(readFileSync(committedClient, "utf8"));
    try {
      const result = runCheck(path.join(base, "frontend"));

      expect(result.ok, result.output).toBe(true);
      expect(result.output).toContain("Contract in sync");
      // The temporary regeneration artifact must not be left behind.
      expect(() =>
        readFileSync(path.join(base, "frontend", "lib", "api", ".schema.tmp.d.ts")),
      ).toThrow();
    } finally {
      rmSync(base, { recursive: true, force: true });
    }
  });
});
