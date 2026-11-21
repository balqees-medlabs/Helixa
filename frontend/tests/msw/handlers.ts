import { HttpResponse, http } from "msw";

import type { components } from "@/lib/api/schema";

export type SessionUser = components["schemas"]["UserOut"];
export type RoleSlug = "admin" | "genomics" | "trf" | "molecular" | "bioinformatics";
export type TestSample = components["schemas"]["SampleOut"];
export type TestSampleEvent = components["schemas"]["SampleEventOut"];
export type TestConsentItem = components["schemas"]["ConsentItemOut"];

export const TEST_PASSWORD = "e2e-password-123";

export const TEST_USERS: Record<RoleSlug, SessionUser> = {
  admin: {
    id: "00000000-0000-4000-8000-000000000001",
    email: "admin@helixa.test",
    display_name: "Amina Admin",
    roles: ["admin"],
    is_active: true,
  },
  genomics: {
    id: "00000000-0000-4000-8000-000000000002",
    email: "genomics@helixa.test",
    display_name: "Gita Genomics",
    roles: ["genomics"],
    is_active: true,
  },
  trf: {
    id: "00000000-0000-4000-8000-000000000003",
    email: "trf@helixa.test",
    display_name: "Tariq TRF",
    roles: ["trf"],
    is_active: true,
  },
  molecular: {
    id: "00000000-0000-4000-8000-000000000004",
    email: "molecular@helixa.test",
    display_name: "Mona Molecular",
    roles: ["molecular"],
    is_active: true,
  },
  bioinformatics: {
    id: "00000000-0000-4000-8000-000000000005",
    email: "bioinformatics@helixa.test",
    display_name: "Bilal Bioinformatics",
    roles: ["bioinformatics"],
    is_active: true,
  },
};

let currentUser: SessionUser | null = null;

export function setCurrentUser(user: SessionUser | null): void {
  currentUser = user;
}

export function signInAs(role: RoleSlug): SessionUser {
  currentUser = TEST_USERS[role];
  return currentUser;
}

export function getCurrentUser(): SessionUser | null {
  return currentUser;
}

export function resetTestSession(): void {
  currentUser = null;
}

export const TEST_STAGES: ReadonlyArray<{ position: number; slug: string; name: string }> = [
  { position: 1, slug: "received", name: "sample received" },
  { position: 2, slug: "consent_documentation", name: "consent & documentation" },
  { position: 3, slug: "molecular_processing", name: "molecular processing" },
  { position: 4, slug: "data_generation", name: "data generation" },
  { position: 5, slug: "trf_preparation", name: "TRF preparation" },
  { position: 6, slug: "trf_confirmation", name: "TRF confirmation" },
  { position: 7, slug: "data_conversion_qc", name: "data conversion & QC" },
  { position: 8, slug: "report_upload_archive", name: "report upload/archive/portal push" },
];

const STAGE_ROLES: Record<number, string[]> = {
  2: ["genomics"],
  3: ["molecular"],
  4: ["bioinformatics"],
  5: ["trf"],
  6: ["trf"],
  7: ["bioinformatics"],
  8: ["bioinformatics"],
};

const REQUIRED_CONSENT_ITEMS = ["signed_consent", "id_verified", "requisition_received"];

function stageAt(position: number) {
  return TEST_STAGES.find((stage) => stage.position === position) ?? TEST_STAGES[0];
}

let sampleStore: TestSample[] = [];
let eventStore: Record<string, TestSampleEvent[]> = {};
let consentStore: Record<string, TestConsentItem[]> = {};
let qcPassed = new Set<string>();

export function resetSamples(): void {
  sampleStore = [];
  eventStore = {};
  consentStore = {};
  qcPassed = new Set<string>();
}

export function setQcPassed(sampleId: string, passed = true): void {
  if (passed) {
    qcPassed.add(sampleId);
  } else {
    qcPassed.delete(sampleId);
  }
}

function requiredComplete(sampleId: string): boolean {
  const items = consentStore[sampleId] ?? [];
  const required = items.filter((item) => item.required);
  return required.length > 0 && required.every((item) => item.complete);
}

function consentFor(sampleId: string): components["schemas"]["ConsentOut"] {
  return {
    sample_id: sampleId,
    items: consentStore[sampleId] ?? [],
    required_complete: requiredComplete(sampleId),
  };
}

function buildEvents(sampleId: string, stagePosition: number): TestSampleEvent[] {
  const base = Date.parse("2026-11-01T09:00:00Z");
  const events: TestSampleEvent[] = [];

  for (let position = 1; position <= stagePosition; position += 1) {
    const isCurrent = position === stagePosition;
    events.push({
      id: crypto.randomUUID(),
      stage: stageAt(position),
      entered_at: new Date(base + (position - 1) * 86_400_000).toISOString(),
      duration_hours: isCurrent ? null : 24,
      actor_id: TEST_USERS.genomics.id,
      note: null,
    });
  }

  return events;
}

export interface SeedSampleOptions {
  id?: string;
  caseId?: string;
  stage?: number;
  status?: string;
  externalRef?: string | null;
  consentComplete?: boolean;
}

export function seedSample(options: SeedSampleOptions = {}): TestSample {
  const id = options.id ?? crypto.randomUUID();
  const stage = stageAt(options.stage ?? 1);
  const receivedAt = "2026-11-01T09:00:00Z";

  const sample: TestSample = {
    id,
    case_id: options.caseId ?? `CASE-${id.slice(0, 8)}`,
    external_ref: options.externalRef ?? null,
    vendor_id: null,
    received_at: receivedAt,
    status: options.status ?? "active",
    current_stage: stage,
  };

  sampleStore.unshift(sample);
  eventStore[id] = buildEvents(id, stage.position);
  consentStore[id] = REQUIRED_CONSENT_ITEMS.map((item) => ({
    item,
    required: true,
    complete: options.consentComplete ?? false,
    completed_at: options.consentComplete ? receivedAt : null,
    completed_by: options.consentComplete ? TEST_USERS.genomics.id : null,
  }));

  return sample;
}

function findSample(sampleId: string | readonly string[] | undefined): TestSample | undefined {
  return sampleStore.find((sample) => sample.id === sampleId);
}

const notFound = () => HttpResponse.json({ detail: "Sample not found" }, { status: 404 });

export const handlers = [
  http.post("/api/auth/login", async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    const match = Object.values(TEST_USERS).find(
      (user) => user.email === body.email && body.password === TEST_PASSWORD,
    );

    if (!match) {
      return HttpResponse.json({ detail: "Invalid email or password" }, { status: 401 });
    }

    currentUser = match;
    return HttpResponse.json(match);
  }),

  http.get("/api/auth/me", () => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    return HttpResponse.json(currentUser);
  }),

  http.post("/api/auth/refresh", () => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    return HttpResponse.json(currentUser);
  }),

  http.post("/api/auth/logout", () => {
    currentUser = null;
    return new HttpResponse(null, { status: 204 });
  }),

  http.get("/api/health", () => HttpResponse.json({ status: "ok" })),

  http.get("/api/samples", ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    const offset = Number(url.searchParams.get("offset") ?? 0);

    return HttpResponse.json({
      items: sampleStore.slice(offset, offset + limit),
      total: sampleStore.length,
      limit,
      offset,
    });
  }),

  http.post("/api/samples", async ({ request }) => {
    const body = (await request.json()) as components["schemas"]["SampleCreate"];

    if (sampleStore.some((sample) => sample.case_id === body.case_id)) {
      return HttpResponse.json(
        { detail: `A sample with case id ${body.case_id} already exists` },
        { status: 409 },
      );
    }

    const sample = seedSample({
      caseId: body.case_id,
      externalRef: body.external_ref ?? null,
    });
    return HttpResponse.json(sample, { status: 201 });
  }),

  http.get("/api/samples/:sampleId", ({ params }) => {
    const sample = findSample(params.sampleId);
    return sample ? HttpResponse.json(sample) : notFound();
  }),

  http.get("/api/samples/:sampleId/events", ({ params }) => {
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }
    return HttpResponse.json(eventStore[sample.id] ?? []);
  }),

  http.get("/api/samples/:sampleId/consent", ({ params }) => {
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }
    return HttpResponse.json(consentFor(sample.id));
  }),

  http.post("/api/samples/:sampleId/consent", async ({ params, request }) => {
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }
    if (
      !currentUser ||
      (!currentUser.roles.includes("admin") && !currentUser.roles.includes("genomics"))
    ) {
      return HttpResponse.json(
        { detail: "Only genomics staff may update consent" },
        { status: 403 },
      );
    }

    const body = (await request.json()) as components["schemas"]["ConsentRequest"];
    consentStore[sample.id] = body.items.map((item) => ({
      item: item.item,
      required: item.required,
      complete: item.complete,
      completed_at: item.complete ? new Date().toISOString() : null,
      completed_by: item.complete ? (currentUser?.id ?? null) : null,
    }));

    return HttpResponse.json(consentFor(sample.id));
  }),

  http.post("/api/samples/:sampleId/advance", async ({ params, request }) => {
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const body = (await request.json()) as components["schemas"]["AdvanceRequest"];

    if (sample.status !== "active") {
      return HttpResponse.json(
        { detail: `Sample is ${sample.status}; only active samples can advance` },
        { status: 409 },
      );
    }

    if (sample.current_stage.position !== body.from_stage) {
      return HttpResponse.json(
        {
          detail: `Sample has already advanced to stage ${sample.current_stage.position}; refresh and retry`,
        },
        { status: 409 },
      );
    }

    const targetPosition = body.from_stage + 1;
    if (body.to_stage != null && body.to_stage !== targetPosition) {
      return HttpResponse.json(
        {
          detail: `Cannot skip stages: ${body.from_stage} -> ${body.to_stage}; expected ${targetPosition}`,
        },
        { status: 409 },
      );
    }
    if (targetPosition > 8) {
      return HttpResponse.json({ detail: "Sample is already at the final stage" }, { status: 409 });
    }

    const allowed = STAGE_ROLES[targetPosition] ?? [];
    if (
      !currentUser.roles.includes("admin") &&
      !allowed.some((role) => currentUser?.roles.includes(role))
    ) {
      return HttpResponse.json(
        {
          detail: `Advancing to stage ${targetPosition} requires: ${allowed.join(", ") || "admin"}`,
        },
        { status: 403 },
      );
    }

    if (targetPosition === 3 && !requiredComplete(sample.id)) {
      return HttpResponse.json(
        { detail: "Consent checklist incomplete: every required item must be complete" },
        { status: 409 },
      );
    }
    if (targetPosition === 8 && !qcPassed.has(sample.id)) {
      return HttpResponse.json(
        { detail: "Quality control must be passed before report/archive" },
        { status: 409 },
      );
    }

    const nextStage = stageAt(targetPosition);
    const updated: TestSample = { ...sample, current_stage: nextStage };
    sampleStore = sampleStore.map((entry) => (entry.id === sample.id ? updated : entry));

    const events = eventStore[sample.id] ?? [];
    if (events.length > 0) {
      const last = events[events.length - 1];
      events[events.length - 1] = { ...last, duration_hours: 24 };
    }
    events.push({
      id: crypto.randomUUID(),
      stage: nextStage,
      entered_at: new Date().toISOString(),
      duration_hours: null,
      actor_id: currentUser.id,
      note: body.note ?? null,
    });
    eventStore[sample.id] = events;

    return HttpResponse.json(updated);
  }),
];
