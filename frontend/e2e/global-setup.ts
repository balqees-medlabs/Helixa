import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { request } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";

import { AUTH_DIR, ROLES, SEED_FILE, accountFor, authFile, type E2ERole } from "./fixtures";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const frontendDir = process.cwd();
const backendDir = path.resolve(frontendDir, "../backend");
const pythonBin = fs.existsSync(path.join(backendDir, ".venv", "bin", "python"))
  ? path.join(backendDir, ".venv", "bin", "python")
  : "python3";

interface ApiUser {
  id: string;
  email: string | null;
  display_name: string;
  roles: string[];
  is_active: boolean;
}

interface ApiSample {
  id: string;
  case_id: string;
  current_stage: { position: number; slug: string; name: string };
}

function ensureAdmin(): void {
  const admin = accountFor("admin");
  const result = spawnSync(
    pythonBin,
    [
      "-m",
      "app.cli",
      "create-admin",
      "--email",
      admin.email,
      "--name",
      "E2E Admin",
      "--password",
      admin.password,
    ],
    { cwd: backendDir, env: process.env, encoding: "utf8" },
  );

  if (result.status !== 0) {
    const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
    if (!/already exists/i.test(output)) {
      throw new Error(`Could not provision the E2E admin:\n${output.trim()}`);
    }
  }
}

async function signIn(api: APIRequestContext, role: E2ERole): Promise<void> {
  const account = accountFor(role);
  const response = await api.post("/api/auth/login", { data: account });
  if (!response.ok()) {
    throw new Error(`E2E login failed for ${role}: ${response.status()} ${await response.text()}`);
  }
}

async function createRoleUsers(admin: APIRequestContext): Promise<void> {
  for (const role of ROLES) {
    if (role === "admin") {
      continue;
    }
    const account = accountFor(role);
    const response = await admin.post("/api/users", {
      data: {
        email: account.email,
        display_name: `${role} E2E`,
        password: account.password,
        roles: [role],
      },
    });
    if (!response.ok() && response.status() !== 409) {
      throw new Error(
        `Could not provision the ${role} E2E user: ${response.status()} ${await response.text()}`,
      );
    }
  }
}

async function advance(
  api: APIRequestContext,
  sampleId: string,
  fromStage: number,
  role: E2ERole,
): Promise<void> {
  const response = await api.post(`/api/samples/${sampleId}/advance`, {
    data: { from_stage: fromStage },
  });
  if (!response.ok()) {
    throw new Error(
      `Seed advance ${fromStage}->${fromStage + 1} failed for ${role}: ${response.status()} ${await response.text()}`,
    );
  }
}

async function seedQcPassedSample(apis: Record<E2ERole, APIRequestContext>): Promise<void> {
  const caseId = `E2E-${Date.now()}`;
  const register = await apis.genomics.post("/api/samples", { data: { case_id: caseId } });
  if (!register.ok()) {
    throw new Error(`Could not seed a sample: ${register.status()} ${await register.text()}`);
  }
  const sample = (await register.json()) as ApiSample;

  const consent = await apis.genomics.post(`/api/samples/${sample.id}/consent`, {
    data: {
      items: [
        { item: "signed_consent", complete: true, required: true },
        { item: "id_verified", complete: true, required: true },
        { item: "requisition_received", complete: true, required: true },
      ],
    },
  });
  if (!consent.ok()) {
    throw new Error(`Could not seed consent: ${consent.status()} ${await consent.text()}`);
  }

  await advance(apis.genomics, sample.id, 1, "genomics");
  await advance(apis.genomics, sample.id, 2, "genomics");
  await advance(apis.molecular, sample.id, 3, "molecular");
  await advance(apis.bioinformatics, sample.id, 4, "bioinformatics");
  await advance(apis.trf, sample.id, 5, "trf");
  await advance(apis.trf, sample.id, 6, "trf");

  const qc = await apis.bioinformatics.post(`/api/samples/${sample.id}/qc`, {
    data: { kind: "qc", passed: true, detail: { source: "e2e-seed" } },
  });
  if (!qc.ok()) {
    throw new Error(`Could not seed QC: ${qc.status()} ${await qc.text()}`);
  }

  await advance(apis.bioinformatics, sample.id, 7, "bioinformatics");

  fs.writeFileSync(
    SEED_FILE,
    `${JSON.stringify({ sampleId: sample.id, caseId } satisfies Record<string, string>, null, 2)}\n`,
  );
}

export default async function globalSetup(): Promise<void> {
  fs.mkdirSync(AUTH_DIR, { recursive: true });
  ensureAdmin();

  const admin = await request.newContext({ baseURL });
  try {
    await signIn(admin, "admin");
    await admin.storageState({ path: authFile("admin") });
    await createRoleUsers(admin);
  } finally {
    await admin.dispose();
  }

  const apis = {} as Record<E2ERole, APIRequestContext>;
  try {
    for (const role of ROLES) {
      const api = await request.newContext({ baseURL });
      await signIn(api, role);
      await api.storageState({ path: authFile(role) });
      apis[role] = api;
    }

    await seedQcPassedSample(apis);
    const seed = JSON.parse(fs.readFileSync(SEED_FILE, "utf8")) as { caseId: string };
    console.log(`E2E fixtures ready: QC-passed sample ${seed.caseId}`);
  } finally {
    await Promise.all(Object.values(apis).map((api) => api.dispose()));
  }
}
