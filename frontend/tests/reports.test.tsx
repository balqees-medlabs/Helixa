import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ReportsPage from "@/app/(app)/reports/page";
import { resetSessionExpiredState } from "@/lib/api/client";

import {
  resetSamples,
  resetTestSession,
  seedReport,
  seedSample,
  setQcPassed,
  signInAs,
} from "./msw/handlers";
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
  usePathname: () => "/reports",
  useSearchParams: () => new URLSearchParams(),
}));

const PDF = () => new File(["%PDF-1.4"], "report.pdf", { type: "application/pdf" });

describe("reports and portal delivery (US5)", () => {
  beforeEach(() => {
    resetSessionExpiredState();
    resetTestSession();
    resetSamples();
  });

  it("surfaces an unsupported-type reason on upload", async () => {
    const user = userEvent.setup();
    signInAs("bioinformatics");
    const sample = seedSample({ id: "s1", caseId: "CASE-415" });
    setQcPassed(sample.id, true);

    server.use(
      http.post("/api/samples/:sampleId/report", () =>
        HttpResponse.json(
          { detail: "Unsupported content type text/plain; allowed: application/pdf" },
          { status: 415 },
        ),
      ),
    );

    renderWithAuth(<ReportsPage />);

    await screen.findByRole("option", { name: /CASE-415/ });
    await user.selectOptions(screen.getByLabelText("Sample"), "s1");
    await user.upload(
      screen.getByLabelText("Report file (PDF)"),
      new File(["hello"], "report.txt", { type: "text/plain" }),
    );
    await user.click(screen.getByRole("button", { name: "Upload report" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Unsupported content type text/plain; allowed: application/pdf",
    );
  });

  it("surfaces the QC-required reason on upload", async () => {
    const user = userEvent.setup();
    signInAs("bioinformatics");
    seedSample({ id: "s1", caseId: "CASE-NO-QC" });

    renderWithAuth(<ReportsPage />);

    await screen.findByRole("option", { name: /CASE-NO-QC/ });
    await user.selectOptions(screen.getByLabelText("Sample"), "s1");
    await user.upload(screen.getByLabelText("Report file (PDF)"), PDF());
    await user.click(screen.getByRole("button", { name: "Upload report" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Quality control must be passed before report upload",
    );
  });

  it("surfaces the oversize reason on upload", async () => {
    const user = userEvent.setup();
    signInAs("bioinformatics");
    const sample = seedSample({ id: "s1", caseId: "CASE-413" });
    setQcPassed(sample.id, true);

    server.use(
      http.post("/api/samples/:sampleId/report", () =>
        HttpResponse.json({ detail: "Report exceeds the 52428800-byte limit" }, { status: 413 }),
      ),
    );

    renderWithAuth(<ReportsPage />);

    await screen.findByRole("option", { name: /CASE-413/ });
    await user.selectOptions(screen.getByLabelText("Sample"), "s1");
    await user.upload(screen.getByLabelText("Report file (PDF)"), PDF());
    await user.click(screen.getByRole("button", { name: "Upload report" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Report exceeds the 52428800-byte limit",
    );
  });

  it("does not offer report retrieval to roles the backend forbids", async () => {
    signInAs("molecular");

    renderWithAuth(<ReportsPage />);

    expect(await screen.findByText("Reports are not available to your role")).toBeInTheDocument();
    expect(screen.queryByLabelText("Report ID")).not.toBeInTheDocument();
  });

  it("lets a permitted role retrieve a stored report", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ id: "s1", caseId: "CASE-STORED" });
    const { report } = seedReport({ sampleId: "s1", pushStatus: "success" });

    renderWithAuth(<ReportsPage />);

    await user.type(await screen.findByLabelText("Report ID"), report.id);
    await user.click(screen.getByRole("button", { name: "Load report" }));

    expect(
      await screen.findByRole("heading", { name: `Report ${report.id.slice(0, 8)}` }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download file" })).toBeInTheDocument();
    expect(await screen.findByText("CASE-STORED")).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Portal delivery status" }),
    ).not.toBeInTheDocument();
  });

  it("shows the portal status and lets an admin retry a failed push", async () => {
    const user = userEvent.setup();
    signInAs("admin");
    seedSample({ id: "s1", caseId: "CASE-PORTAL" });
    const { report } = seedReport({
      sampleId: "s1",
      pushStatus: "failed",
      attempts: 1,
      lastError: "Portal unavailable",
    });

    renderWithAuth(<ReportsPage />);

    await user.type(await screen.findByLabelText("Report ID"), report.id);
    await user.click(screen.getByRole("button", { name: "Load report" }));

    const portal = await screen.findByRole("region", { name: "Portal delivery status" });
    expect(within(portal).getByText("Failed")).toBeInTheDocument();
    expect(within(portal).getByText(/Portal unavailable/)).toBeInTheDocument();

    await user.click(within(portal).getByRole("button", { name: "Retry push" }));

    await waitFor(() => {
      expect(
        within(screen.getByRole("region", { name: "Portal delivery status" })).getByText("Queued"),
      ).toBeInTheDocument();
    });
  });
});
