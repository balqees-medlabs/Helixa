import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SampleDetailPage from "@/app/(app)/samples/[id]/page";

import { resetSamples, seedSample, signInAs } from "./msw/handlers";
import { server } from "./msw/server";
import { renderWithAuth } from "./render";

const nav = vi.hoisted(() => ({
  pathname: "/samples/s1",
  search: "",
  params: { id: "s1" },
  replace: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: nav.replace,
    push: nav.push,
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
  useParams: () => nav.params,
}));

function renderDetail(sampleId = "s1") {
  nav.pathname = `/samples/${sampleId}`;
  nav.params = { id: sampleId };
  window.history.replaceState({}, "", `/samples/${sampleId}`);
  return renderWithAuth(<SampleDetailPage />);
}

const COVERAGE_PASS = {
  id: "cov1",
  pipeline_sample_id: "s1",
  read_pairs: 12_345,
  yield_gb: 18.5,
  depth_x: 31.2,
  target_x: 30,
  verdict: "pass",
  reported_by: "00000000-0000-4000-8000-000000000005",
  reported_at: "2026-11-20T10:00:00Z",
  idempotency_key: "ck-1",
};

const COVERAGE_BELOW = {
  ...COVERAGE_PASS,
  id: "cov2",
  depth_x: 24.0,
  verdict: "below",
  reported_at: "2026-11-21T10:00:00Z",
  idempotency_key: "ck-2",
};

describe("pipeline visibility (US2)", () => {
  beforeEach(() => {
    resetSamples();
    nav.pathname = "/samples/s1";
    nav.params = { id: "s1" };
    window.history.replaceState({}, "", "/samples/s1");
    server.resetHandlers();
  });

  it("renders the latest coverage verdict and gate reason", async () => {
    signInAs("bioinformatics");
    seedSample({ id: "s1", caseId: "CASE-PIPE-1", stage: 3 });
    server.use(
      http.get("/api/samples/s1/coverage", () => HttpResponse.json([COVERAGE_PASS])),
      http.get("/api/samples/s1/pipeline-results", () => HttpResponse.json([])),
    );

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-PIPE-1" });

    expect(await screen.findByText("31.2x")).toBeInTheDocument();
    expect((await screen.findAllByText("Pass")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Stage 7 waiting for FASTQ conversion/)).toBeInTheDocument();
  });

  it("shows the BELOW flag and the blocked gate reason", async () => {
    signInAs("bioinformatics");
    seedSample({ id: "s1", caseId: "CASE-PIPE-2", stage: 3 });
    server.use(
      http.get("/api/samples/s1/coverage", () => HttpResponse.json([COVERAGE_BELOW])),
      http.get("/api/samples/s1/pipeline-results", () => HttpResponse.json([])),
    );

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-PIPE-2" });

    expect((await screen.findAllByText("Below")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Stage 7 blocked/)).toBeInTheDocument();
    expect(screen.getByText(/24\.0 < 30/)).toBeInTheDocument();
  });

  it("renders the pipeline timeline results", async () => {
    signInAs("molecular");
    seedSample({ id: "s1", caseId: "CASE-PIPE-3", stage: 4 });
    server.use(
      http.get("/api/samples/s1/coverage", () => HttpResponse.json([])),
      http.get("/api/samples/s1/pipeline-results", () =>
        HttpResponse.json([
          {
            id: "pr1",
            pipeline_sample_id: "s1",
            kind: "ingest",
            status: "ok",
            read_length: null,
            q30: null,
            reads_assigned_pct: null,
            source_run_ids: null,
            integrity_ok: null,
            plan_match: null,
            detail: {},
            reported_by: "00000000-0000-4000-8000-000000000004",
            reported_at: "2026-11-18T09:00:00Z",
            idempotency_key: "ik-1",
          },
        ]),
      ),
    );

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-PIPE-3" });

    expect(await screen.findByText("Ingest")).toBeInTheDocument();
    expect(screen.getByText("Pipeline timeline")).toBeInTheDocument();
  });
});
