import fs from "node:fs";
import path from "node:path";

import { expect, test as base } from "@playwright/test";
import type { Page } from "@playwright/test";

export const ROLES = ["admin", "genomics", "trf", "molecular", "bioinformatics"] as const;
export type E2ERole = (typeof ROLES)[number];

export const E2E_PASSWORD = process.env.E2E_PASSWORD ?? "e2e-password-123";

export function accountFor(role: E2ERole): { email: string; password: string } {
  return {
    email: `${role}@e2e.helixa.test`,
    password: E2E_PASSWORD,
  };
}

export const AUTH_DIR = path.resolve(process.cwd(), "e2e", ".auth");
export const SEED_FILE = path.join(AUTH_DIR, "seed.json");

export function authFile(role: E2ERole): string {
  return path.join(AUTH_DIR, `${role}.json`);
}

export interface E2ESeed {
  sampleId: string;
  caseId: string;
}

export function readSeed(): E2ESeed {
  return JSON.parse(fs.readFileSync(SEED_FILE, "utf8")) as E2ESeed;
}

export const test = base.extend<{ role: E2ERole; authenticatedPage: Page }>({
  role: ["admin", { option: true }],
  authenticatedPage: async ({ browser, baseURL, role }, use) => {
    const context = await browser.newContext({
      baseURL,
      storageState: authFile(role),
    });
    const page = await context.newPage();
    await use(page);
    await context.close();
  },
});

export { expect };
