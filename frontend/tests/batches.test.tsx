import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BatchesPage from "@/app/(app)/batches/page";
import { resetSessionExpiredState } from "@/lib/api/client";

import { resetSamples, resetTestSession, seedSample, signInAs } from "./msw/handlers";
import { server } from "./msw/server";
import { renderWithAuth } from "./render";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/batches",
  useSearchParams: () => new URLSearchParams(),
}));

describe("batches (US4, FR-015)", () => {
  beforeEach(() => {
    resetSessionExpiredState();
    resetTestSession();
    resetSamples();
  });

  it("renders every member's advance outcome with its reason", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ id: "s1", caseId: "CASE-ADVANCED", stage: 3 });
    seedSample({ id: "s2", caseId: "CASE-CONFLICT", stage: 4 });
    seedSample({ id: "s3", caseId: "CASE-GATE", stage: 2 });
    seedSample({ id: "s4", caseId: "CASE-FORBIDDEN", stage: 3 });

    server.use(
      http.post("/api/batches/:batchId/advance", () =>
        HttpResponse.json([
          {
            sample_id: "s1",
            status: "advanced",
            detail: null,
            from_stage: 3,
            to_stage: 4,
          },
          {
            sample_id: "s2",
            status: "conflict",
            detail: "Sample has already advanced to stage 5; refresh and retry",
            from_stage: 4,
            to_stage: null,
          },
          {
            sample_id: "s3",
            status: "gate_failed",
            detail: "Consent checklist incomplete: every required item must be complete",
            from_stage: 2,
            to_stage: null,
          },
          {
            sample_id: "s4",
            status: "forbidden",
            detail: "Advancing to stage 4 requires: bioinformatics",
            from_stage: 3,
            to_stage: null,
          },
        ]),
      ),
    );

    renderWithAuth(<BatchesPage />);

    await user.type(await screen.findByLabelText("Batch name"), "Batch Alpha");
    await user.click(screen.getByRole("button", { name: "Create batch" }));

    for (const caseId of ["CASE-ADVANCED", "CASE-CONFLICT", "CASE-GATE", "CASE-FORBIDDEN"]) {
      await user.click(await screen.findByRole("checkbox", { name: caseId }));
    }
    await user.click(screen.getByRole("button", { name: "Add members" }));

    expect(await screen.findByText("Members (4)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Advance batch" }));

    const results = await screen.findByRole("region", { name: "Batch advance results" });
    const rows = within(results).getAllByRole("listitem");
    expect(rows).toHaveLength(4);

    expect(within(results).getByText("CASE-ADVANCED")).toBeInTheDocument();
    expect(within(results).getByText("Advanced")).toBeInTheDocument();

    expect(within(results).getByText("CASE-CONFLICT")).toBeInTheDocument();
    expect(within(results).getByText("Conflict")).toBeInTheDocument();
    expect(
      within(results).getByText("Sample has already advanced to stage 5; refresh and retry"),
    ).toBeInTheDocument();

    expect(within(results).getByText("CASE-GATE")).toBeInTheDocument();
    expect(within(results).getByText("Gate failed")).toBeInTheDocument();
    expect(
      within(results).getByText(
        "Consent checklist incomplete: every required item must be complete",
      ),
    ).toBeInTheDocument();

    expect(within(results).getByText("CASE-FORBIDDEN")).toBeInTheDocument();
    expect(within(results).getByText("Forbidden")).toBeInTheDocument();
    expect(
      within(results).getByText("Advancing to stage 4 requires: bioinformatics"),
    ).toBeInTheDocument();
  });

  it("does not offer batch tools to roles outside the batch area", async () => {
    signInAs("molecular");

    renderWithAuth(<BatchesPage />);

    expect(await screen.findByText("Batches are not available to your role")).toBeInTheDocument();
    expect(screen.queryByLabelText("Batch name")).not.toBeInTheDocument();
  });
});
