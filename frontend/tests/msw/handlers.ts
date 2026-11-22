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

export const STAGE_IDS: Record<number, string> = {
  1: "00000000-0000-4000-9000-000000000001",
  2: "00000000-0000-4000-9000-000000000002",
  3: "00000000-0000-4000-9000-000000000003",
  4: "00000000-0000-4000-9000-000000000004",
  5: "00000000-0000-4000-9000-000000000005",
  6: "00000000-0000-4000-9000-000000000006",
  7: "00000000-0000-4000-9000-000000000007",
  8: "00000000-0000-4000-9000-000000000008",
};

const DEFAULT_STAGE_SLA: Record<number, number> = {
  1: 2,
  2: 3,
  3: 5,
  4: 5,
  5: 3,
  6: 3,
  7: 5,
  8: 3,
};

export interface TestVendor {
  id: string;
  name: string;
  tat_days: number;
  tat_anchor: string;
  is_active: boolean;
}

export interface TestBatch {
  id: string;
  name: string;
  created_by: string;
  member_ids: string[];
}

const REQUIRED_CONSENT_ITEMS = ["signed_consent", "id_verified", "requisition_received"];

function stageAt(position: number) {
  return TEST_STAGES.find((stage) => stage.position === position) ?? TEST_STAGES[0];
}

let sampleStore: TestSample[] = [];
let eventStore: Record<string, TestSampleEvent[]> = {};
let consentStore: Record<string, TestConsentItem[]> = {};
let qcPassed = new Set<string>();
let vendorStore: TestVendor[] = [];
let batchStore: TestBatch[] = [];
let reportStore: components["schemas"]["ReportOut"][] = [];
let pushStore: components["schemas"]["PortalPushOut"][] = [];
let stageSlaStore: Record<number, number> = { ...DEFAULT_STAGE_SLA };

export function resetSamples(): void {
  sampleStore = [];
  eventStore = {};
  consentStore = {};
  qcPassed = new Set<string>();
  vendorStore = [];
  batchStore = [];
  reportStore = [];
  pushStore = [];
  stageSlaStore = { ...DEFAULT_STAGE_SLA };
}

export interface SeedVendorOptions {
  id?: string;
  name?: string;
  tatDays?: number;
  tatAnchor?: string;
  isActive?: boolean;
}

export function seedVendor(options: SeedVendorOptions = {}): TestVendor {
  const id = options.id ?? crypto.randomUUID();
  const vendor: TestVendor = {
    id,
    name: options.name ?? `Vendor ${id.slice(0, 4)}`,
    tat_days: options.tatDays ?? 21,
    tat_anchor: options.tatAnchor ?? "receipt",
    is_active: options.isActive ?? true,
  };
  vendorStore.push(vendor);
  return vendor;
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

function buildEvents(
  sampleId: string,
  stagePosition: number,
  receivedAt: string,
): TestSampleEvent[] {
  const base = Date.parse(receivedAt);
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
  receivedAt?: string;
  vendorId?: string | null;
}

export function seedSample(options: SeedSampleOptions = {}): TestSample {
  const id = options.id ?? crypto.randomUUID();
  const stage = stageAt(options.stage ?? 1);
  const receivedAt = options.receivedAt ?? "2026-11-01T09:00:00Z";

  const sample: TestSample = {
    id,
    case_id: options.caseId ?? `CASE-${id.slice(0, 8)}`,
    external_ref: options.externalRef ?? null,
    vendor_id: options.vendorId ?? null,
    received_at: receivedAt,
    status: options.status ?? "active",
    current_stage: stage,
  };

  sampleStore.unshift(sample);
  eventStore[id] = buildEvents(id, stage.position, receivedAt);
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

const forbidden = (detail: string) => HttpResponse.json({ detail }, { status: 403 });

export interface SeedReportOptions {
  sampleId?: string;
  pushStatus?: string;
  attempts?: number;
  lastError?: string | null;
  sizeBytes?: number;
}

export function seedReport(options: SeedReportOptions = {}): {
  report: components["schemas"]["ReportOut"];
  push: components["schemas"]["PortalPushOut"];
} {
  const sample = options.sampleId
    ? findSample(options.sampleId)
    : sampleStore[sampleStore.length - 1];
  const sampleId = options.sampleId ?? sample?.id ?? crypto.randomUUID();
  const status = options.pushStatus ?? "queued";
  const reportId = crypto.randomUUID();
  const pushId = crypto.randomUUID();
  const now = new Date().toISOString();

  const report: components["schemas"]["ReportOut"] = {
    id: reportId,
    sample_id: sampleId,
    path: `/data/reports/${sampleId}/${reportId}.pdf`,
    content_type: "application/pdf",
    size_bytes: options.sizeBytes ?? 2048,
    sha256: "a".repeat(64),
    uploaded_by: TEST_USERS.bioinformatics.id,
    uploaded_at: now,
    push_id: pushId,
    push_status: status,
  };
  const push: components["schemas"]["PortalPushOut"] = {
    id: pushId,
    report_id: reportId,
    status,
    attempts: options.attempts ?? (status === "failed" ? 1 : 0),
    last_error: options.lastError ?? (status === "failed" ? "Portal unavailable" : null),
    next_attempt_at: now,
    delivered_at: status === "success" ? now : null,
  };

  reportStore.push(report);
  pushStore.push(push);
  return { report, push };
}

const REPORT_MAX_BYTES = 52_428_800;
const ALLOWED_REPORT_TYPES = new Set(["application/pdf"]);

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function buildTatMetrics(): components["schemas"]["TatMetrics"] {
  const now = Date.now();

  const samples = sampleStore.map((sample) => {
    const events = eventStore[sample.id] ?? [];
    const stages = events.map((event, index) => {
      const following = events[index + 1];
      const hours = following
        ? (Date.parse(following.entered_at) - Date.parse(event.entered_at)) / 3_600_000
        : (now - Date.parse(event.entered_at)) / 3_600_000;
      const slaDays = stageSlaStore[event.stage.position] ?? null;

      return {
        stage_id: STAGE_IDS[event.stage.position],
        position: event.stage.position,
        slug: event.stage.slug,
        name: event.stage.name,
        sla_days: slaDays,
        duration_hours: round2(hours),
        breached: slaDays != null ? hours > slaDays * 24 : null,
      };
    });

    const elapsedDays = Math.max(0, (now - Date.parse(sample.received_at)) / 86_400_000);
    const workingDays = Math.floor((elapsedDays * 5) / 7);
    const vendor = vendorStore.find((entry) => entry.id === sample.vendor_id);

    let vendorMetric: components["schemas"]["VendorSampleMetric"] | null = null;
    if (vendor) {
      const anchorAt =
        vendor.tat_anchor === "receipt"
          ? sample.received_at
          : (events.find((event) => event.stage.position === 4)?.entered_at ?? null);
      const elapsedVendorDays =
        anchorAt != null ? round2((now - Date.parse(anchorAt)) / 86_400_000) : null;
      vendorMetric = {
        id: vendor.id,
        name: vendor.name,
        tat_days: vendor.tat_days,
        tat_anchor: vendor.tat_anchor,
        anchor_at: anchorAt,
        elapsed_days: elapsedVendorDays,
        breached: elapsedVendorDays != null ? elapsedVendorDays > vendor.tat_days : null,
      };
    }

    return {
      sample_id: sample.id,
      case_id: sample.case_id,
      status: sample.status,
      current_stage: sample.current_stage,
      received_at: sample.received_at,
      elapsed_calendar_days: round2(elapsedDays),
      elapsed_working_days: workingDays,
      target_days: 18,
      target_breached: elapsedDays > 18,
      baseline_working_days: 45,
      baseline_breached: workingDays > 45,
      stages,
      vendor: vendorMetric,
    };
  });

  return {
    generated_at: new Date(now).toISOString(),
    target_days: 18,
    baseline_working_days: 45,
    samples,
    vendors: vendorStore.map((vendor) => {
      const assigned = samples.filter((sample) => sample.vendor?.id === vendor.id);
      return {
        vendor_id: vendor.id,
        name: vendor.name,
        tat_days: vendor.tat_days,
        tat_anchor: vendor.tat_anchor,
        assigned_samples: assigned.length,
        breached_samples: assigned.filter((sample) => sample.vendor?.breached).length,
      };
    }),
  };
}

type AdvanceBody = components["schemas"]["AdvanceRequest"];

type AdvanceOutcome =
  | { status: "advanced"; sample: TestSample }
  | { status: "conflict" | "gate_failed" | "forbidden" | "not_found"; detail: string };

function hasRole(...roles: string[]): boolean {
  if (!currentUser) {
    return false;
  }
  return (
    currentUser.roles.includes("admin") || roles.some((role) => currentUser!.roles.includes(role))
  );
}

function attemptAdvance(sampleId: string, body: AdvanceBody): AdvanceOutcome {
  const sample = findSample(sampleId);
  if (!sample) {
    return { status: "not_found", detail: "Sample not found" };
  }
  const user = currentUser;
  if (!user) {
    return { status: "forbidden", detail: "Not authenticated" };
  }

  if (sample.status !== "active") {
    return {
      status: "conflict",
      detail: `Sample is ${sample.status}; only active samples can advance`,
    };
  }

  if (sample.current_stage.position !== body.from_stage) {
    return {
      status: "conflict",
      detail: `Sample has already advanced to stage ${sample.current_stage.position}; refresh and retry`,
    };
  }

  const targetPosition = body.from_stage + 1;
  if (body.to_stage != null && body.to_stage !== targetPosition) {
    return {
      status: "conflict",
      detail: `Cannot skip stages: ${body.from_stage} -> ${body.to_stage}; expected ${targetPosition}`,
    };
  }
  if (targetPosition > 8) {
    return { status: "conflict", detail: "Sample is already at the final stage" };
  }

  const allowed = STAGE_ROLES[targetPosition] ?? [];
  if (!user.roles.includes("admin") && !allowed.some((role) => user.roles.includes(role))) {
    return {
      status: "forbidden",
      detail: `Advancing to stage ${targetPosition} requires: ${allowed.join(", ") || "admin"}`,
    };
  }

  if (targetPosition === 3 && !requiredComplete(sample.id)) {
    return {
      status: "gate_failed",
      detail: "Consent checklist incomplete: every required item must be complete",
    };
  }
  if (targetPosition === 8 && !qcPassed.has(sample.id)) {
    return {
      status: "gate_failed",
      detail: "Quality control must be passed before report/archive",
    };
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
    actor_id: user.id,
    note: body.note ?? null,
  });
  eventStore[sample.id] = events;

  return { status: "advanced", sample: updated };
}

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
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }

    const body = (await request.json()) as components["schemas"]["AdvanceRequest"];
    const outcome = attemptAdvance(String(params.sampleId), body);

    switch (outcome.status) {
      case "advanced":
        return HttpResponse.json(outcome.sample);
      case "not_found":
        return notFound();
      case "forbidden":
        return forbidden(outcome.detail);
      default:
        return HttpResponse.json({ detail: outcome.detail }, { status: 409 });
    }
  }),

  http.post("/api/samples/:sampleId/qc", async ({ params, request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    const user = currentUser;
    if (!hasRole("bioinformatics")) {
      return forbidden("Insufficient role");
    }
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }

    const body = (await request.json()) as components["schemas"]["QcCreate"];
    if (body.kind === "qc") {
      setQcPassed(sample.id, body.passed);
    }

    return HttpResponse.json({
      id: crypto.randomUUID(),
      sample_id: sample.id,
      kind: body.kind,
      passed: body.passed,
      detail: body.detail ?? {},
      recorded_by: user.id,
      recorded_at: new Date().toISOString(),
    });
  }),

  http.get("/api/metrics/tat", () => {
    if (!currentUser?.roles.includes("admin")) {
      return forbidden("Only administrators may view turnaround metrics");
    }
    return HttpResponse.json(buildTatMetrics());
  }),

  http.patch("/api/stages/:stageId/sla", async ({ params, request }) => {
    if (!currentUser?.roles.includes("admin")) {
      return forbidden("Only administrators may update stage SLAs");
    }

    const position = Number(Object.entries(STAGE_IDS).find(([, id]) => id === params.stageId)?.[0]);
    if (!position) {
      return HttpResponse.json({ detail: "Stage not found" }, { status: 404 });
    }

    const body = (await request.json()) as components["schemas"]["SlaUpdate"];
    stageSlaStore[position] = body.sla_days;
    const stage = stageAt(position);

    return HttpResponse.json({
      stage_id: STAGE_IDS[position],
      position: stage.position,
      slug: stage.slug,
      name: stage.name,
      sla_days: body.sla_days,
      updated_at: new Date().toISOString(),
    });
  }),

  http.get("/api/users", ({ request }) => {
    if (!currentUser?.roles.includes("admin")) {
      return forbidden("Only administrators may list users");
    }

    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const users = Object.values(TEST_USERS);

    return HttpResponse.json({
      items: users.slice(offset, offset + limit),
      total: users.length,
      limit,
      offset,
    });
  }),

  http.post("/api/batches", async ({ request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    const user = currentUser;
    if (!hasRole("genomics", "bioinformatics")) {
      return forbidden("Insufficient role");
    }

    const body = (await request.json()) as components["schemas"]["BatchCreate"];
    const batch: TestBatch = {
      id: crypto.randomUUID(),
      name: body.name,
      created_by: user.id,
      member_ids: [],
    };
    batchStore.push(batch);
    return HttpResponse.json(batch, { status: 201 });
  }),

  http.post("/api/batches/:batchId/members", async ({ params, request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("genomics", "bioinformatics")) {
      return forbidden("Insufficient role");
    }
    const batch = batchStore.find((entry) => entry.id === params.batchId);
    if (!batch) {
      return HttpResponse.json({ detail: "Batch not found" }, { status: 404 });
    }

    const body = (await request.json()) as components["schemas"]["BatchMembers"];
    for (const sampleId of body.sample_ids) {
      if (!findSample(sampleId)) {
        return notFound();
      }
      if (!batch.member_ids.includes(sampleId)) {
        batch.member_ids.push(sampleId);
      }
    }
    return HttpResponse.json(batch);
  }),

  http.post("/api/batches/:batchId/advance", async ({ params, request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    const batch = batchStore.find((entry) => entry.id === params.batchId);
    if (!batch) {
      return HttpResponse.json({ detail: "Batch not found" }, { status: 404 });
    }

    const body = (await request.json()) as components["schemas"]["BatchAdvanceRequest"];
    const results = batch.member_ids.map((sampleId) => {
      const sample = findSample(sampleId);
      const fromStage = body.from_stage ?? sample?.current_stage.position ?? 1;
      const outcome = attemptAdvance(sampleId, { ...body, from_stage: fromStage });
      if (outcome.status === "advanced") {
        return {
          sample_id: sampleId,
          status: "advanced",
          detail: null,
          from_stage: fromStage,
          to_stage: outcome.sample.current_stage.position,
        };
      }
      return {
        sample_id: sampleId,
        status: outcome.status,
        detail: outcome.detail,
        from_stage: fromStage,
        to_stage: null,
      };
    });

    return HttpResponse.json(results);
  }),

  http.get("/api/vendors", () => HttpResponse.json(vendorStore)),

  http.post("/api/vendors", async ({ request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin")) {
      return forbidden("Insufficient role");
    }

    const body = (await request.json()) as components["schemas"]["VendorCreate"];
    if (vendorStore.some((vendor) => vendor.name === body.name)) {
      return HttpResponse.json({ detail: `Vendor ${body.name} already exists` }, { status: 409 });
    }

    const vendor = seedVendor({
      name: body.name,
      tatDays: body.tat_days,
      tatAnchor: body.tat_anchor,
      isActive: body.is_active,
    });
    return HttpResponse.json(vendor, { status: 201 });
  }),

  http.patch("/api/vendors/:vendorId", async ({ params, request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin")) {
      return forbidden("Insufficient role");
    }

    const vendor = vendorStore.find((entry) => entry.id === params.vendorId);
    if (!vendor) {
      return HttpResponse.json({ detail: "Vendor not found" }, { status: 404 });
    }

    const body = (await request.json()) as components["schemas"]["VendorUpdate"];
    if (
      body.name &&
      vendorStore.some((entry) => entry.id !== vendor.id && entry.name === body.name)
    ) {
      return HttpResponse.json({ detail: `Vendor ${body.name} already exists` }, { status: 409 });
    }

    if (body.name != null) {
      vendor.name = body.name;
    }
    if (body.tat_days != null) {
      vendor.tat_days = body.tat_days;
    }
    if (body.tat_anchor != null) {
      vendor.tat_anchor = body.tat_anchor;
    }
    if (body.is_active != null) {
      vendor.is_active = body.is_active;
    }

    return HttpResponse.json(vendor);
  }),

  http.post("/api/samples/:sampleId/report", async ({ params, request }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("bioinformatics")) {
      return forbidden("Insufficient role");
    }
    const sample = findSample(params.sampleId);
    if (!sample) {
      return notFound();
    }
    if (!qcPassed.has(sample.id)) {
      return HttpResponse.json(
        { detail: "Quality control must be passed before report upload" },
        { status: 409 },
      );
    }

    const form = await request.formData();
    const file = form.get("file");
    if (!file || typeof file === "string") {
      return HttpResponse.json({ detail: "Report file is required" }, { status: 422 });
    }

    const mediaType = (file.type || "").split(";")[0].trim().toLowerCase();
    if (!ALLOWED_REPORT_TYPES.has(mediaType)) {
      return HttpResponse.json(
        {
          detail: `Unsupported content type ${mediaType || "unknown"}; allowed: application/pdf`,
        },
        { status: 415 },
      );
    }
    if (file.size === 0) {
      return HttpResponse.json({ detail: "Report file is empty" }, { status: 422 });
    }
    if (file.size > REPORT_MAX_BYTES) {
      return HttpResponse.json(
        { detail: `Report exceeds the ${REPORT_MAX_BYTES}-byte limit` },
        { status: 413 },
      );
    }

    const { report } = seedReport({ sampleId: sample.id, sizeBytes: file.size });
    return HttpResponse.json(report, { status: 201 });
  }),

  http.get("/api/reports/:reportId/file", ({ params }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin", "bioinformatics", "genomics")) {
      return forbidden("Insufficient role");
    }
    const report = reportStore.find((entry) => entry.id === params.reportId);
    if (!report) {
      return HttpResponse.json({ detail: "Report not found" }, { status: 404 });
    }
    return new HttpResponse("%PDF-1.4 test", {
      headers: { "Content-Type": "application/pdf" },
    });
  }),

  http.get("/api/reports/:reportId", ({ params }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin", "bioinformatics", "genomics")) {
      return forbidden("Insufficient role");
    }
    const report = reportStore.find((entry) => entry.id === params.reportId);
    return report
      ? HttpResponse.json(report)
      : HttpResponse.json({ detail: "Report not found" }, { status: 404 });
  }),

  http.get("/api/portal-pushes/:pushId", ({ params }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin")) {
      return forbidden("Insufficient role");
    }
    const push = pushStore.find((entry) => entry.id === params.pushId);
    return push
      ? HttpResponse.json(push)
      : HttpResponse.json({ detail: "Portal push not found" }, { status: 404 });
  }),

  http.post("/api/portal-pushes/:pushId/retry", ({ params }) => {
    if (!currentUser) {
      return HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
    }
    if (!hasRole("admin")) {
      return forbidden("Insufficient role");
    }
    const push = pushStore.find((entry) => entry.id === params.pushId);
    if (!push) {
      return HttpResponse.json({ detail: "Portal push not found" }, { status: 404 });
    }
    if (push.status === "success" || push.delivered_at) {
      return HttpResponse.json({ detail: "Push has already been delivered" }, { status: 409 });
    }
    if (push.attempts >= 5) {
      return HttpResponse.json(
        { detail: "Push has exhausted its retry attempts" },
        { status: 409 },
      );
    }

    push.status = "queued";
    push.last_error = null;
    push.next_attempt_at = new Date().toISOString();
    const report = reportStore.find((entry) => entry.id === push.report_id);
    if (report) {
      report.push_status = "queued";
    }
    return HttpResponse.json(push);
  }),
];
