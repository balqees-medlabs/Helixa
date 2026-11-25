import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RunsPage from "@/app/(app)/runs/page";

import { resetTestSession, seedSample, signInAs } from "./msw/handlers";
import { server } from "./msw/server";
import { renderWithAuth } from "./render";

const nav = vi.hoisted(() => ({
  pathname: "/runs",
  search: "",
  params: {},
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

const RUN_OUT = {
  id: "run-1",
  run_folder: "RUN-TEST-1",
  instrument: "AV242301",
  project: "AMJ",
  run_side: null,
  run_date: null,
  storage_location: null,
  readiness: "received",
  cycle_r1: 150,
  cycle_r2: 150,
  cycle_i1: 50,
  cycle_i2: null,
  created_by: "00000000-0000-4000-8000-000000000004",
  created_at: "2026-11-25T00:00:00Z",
};

const PIPELINE_SAMPLE_OUT = {
  id: "psmp1",
  sample_id: "smp1",
  ngs_sample_id: "G-TEST-1",
  sample_type: "G",
  coverage_target_x: 30,
  vendor_id: null,
  pipeline_state: "intake",
  created_by: "00000000-0000-4000-8000-000000000004",
  created_at: "2026-11-25T00:00:00Z",
};

describe("runs intake (US1)", () => {
  let recordedSampleBody: Record<string, unknown> | undefined;

  beforeEach(() => {
    resetTestSession();
    recordedSampleBody = undefined;
    server.resetHandlers();
    server.use(
      http.get("/api/runs", () => HttpResponse.json([])),
      http.post("/api/runs", () => HttpResponse.json(RUN_OUT, { status: 201 })),
      http.post("/api/runs/run-1/samples", async ({ request }) => {
        recordedSampleBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(PIPELINE_SAMPLE_OUT, { status: 201 });
      }),
    );
  });

  it("records a run with a linked sample and defaults the G target to 30", async () => {
    const user = userEvent.setup();
    signInAs("molecular");
    seedSample({ id: "smp1", caseId: "CASE-RUN-1" });

    renderWithAuth(<RunsPage />);
    await screen.findByRole("heading", { name: "Runs" });

    await user.type(screen.getByLabelText("Run folder"), "RUN-TEST-1");
    await user.type(screen.getByLabelText("Instrument"), "AV242301");
    await user.selectOptions(screen.getByLabelText("Linked Sample"), "smp1");
    await user.type(screen.getByLabelText("NGS sample ID"), "G-TEST-1");
    await user.click(screen.getByRole("button", { name: "Record run" }));

    await waitFor(() => expect(recordedSampleBody).toBeDefined());
    // Omitted target → the backend default applies (30 for G, 15 for R — FR-003).
    expect(recordedSampleBody).not.toHaveProperty("coverage_target_x");
    expect(await screen.findByRole("status")).toHaveTextContent("Run RUN-TEST-1 recorded.");
  });

  it("shows the linkage refusal verbatim", async () => {
    const user = userEvent.setup();
    signInAs("molecular");
    seedSample({ id: "smp1", caseId: "CASE-RUN-2" });

    server.use(
      http.post("/api/runs/run-1/samples", () =>
        HttpResponse.json(
          {
            detail:
              "Sample 00000000-0000-0000-0000-000000000000 is not a registered workflow Sample; register it first.",
          },
          { status: 422 },
        ),
      ),
    );

    renderWithAuth(<RunsPage />);
    await screen.findByRole("heading", { name: "Runs" });

    await user.type(screen.getByLabelText("Run folder"), "RUN-TEST-2");
    await user.type(screen.getByLabelText("Instrument"), "AV242301");
    await user.selectOptions(screen.getByLabelText("Linked Sample"), "smp1");
    await user.type(screen.getByLabelText("NGS sample ID"), "G-TEST-2");
    await user.click(screen.getByRole("button", { name: "Record run" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "is not a registered workflow Sample; register it first.",
    );
  });
});
