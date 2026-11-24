import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SampleDetailPage from "@/app/(app)/samples/[id]/page";
import SamplesPage from "@/app/(app)/samples/page";
import RegisterSamplePage from "@/app/(app)/samples/register/page";
import { resetSessionExpiredState } from "@/lib/api/client";

import { resetSamples, resetTestSession, seedSample, setQcPassed, signInAs } from "./msw/handlers";
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

describe("sample workflow (US2)", () => {
  beforeEach(() => {
    resetSessionExpiredState();
    resetTestSession();
    resetSamples();
    nav.pathname = "/samples/s1";
    nav.params = { id: "s1" };
    window.history.replaceState({}, "", "/samples/s1");
  });

  it("surfaces the consent gate reason verbatim", async () => {
    const user = userEvent.setup();
    signInAs("molecular");
    seedSample({ id: "s1", caseId: "CASE-CONSENT", stage: 2, consentComplete: false });

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-CONSENT" });
    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Consent checklist incomplete: every required item must be complete",
    );
  });

  it("surfaces the QC gate reason verbatim", async () => {
    const user = userEvent.setup();
    signInAs("bioinformatics");
    seedSample({ id: "s1", caseId: "CASE-QC", stage: 7 });

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-QC" });
    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Quality control must be passed before report/archive",
    );
  });

  it("surfaces a stale-advance reason verbatim", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ id: "s1", caseId: "CASE-STALE", stage: 2 });

    server.use(
      http.post("/api/samples/:sampleId/advance", () =>
        HttpResponse.json(
          { detail: "Sample has already advanced to stage 3; refresh and retry" },
          { status: 409 },
        ),
      ),
    );

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-STALE" });
    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sample has already advanced to stage 3; refresh and retry",
    );
  });

  it("surfaces a stage-skip reason verbatim", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ id: "s1", caseId: "CASE-SKIP", stage: 1 });

    server.use(
      http.post("/api/samples/:sampleId/advance", () =>
        HttpResponse.json({ detail: "Cannot skip stages: 1 -> 3; expected 2" }, { status: 409 }),
      ),
    );

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-SKIP" });
    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cannot skip stages: 1 -> 3; expected 2",
    );
  });

  it("advances the sample and updates the detail view", async () => {
    const user = userEvent.setup();
    signInAs("molecular");
    seedSample({ id: "s1", caseId: "CASE-ADVANCE", stage: 2, consentComplete: true });

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-ADVANCE" });
    expect((await screen.findAllByText("Consent & documentation")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    await waitFor(async () => {
      expect((await screen.findAllByText("Molecular processing")).length).toBeGreaterThan(0);
    });
  });

  it("opens the molecular gate when the consent checklist is completed", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ id: "s1", caseId: "CASE-CONSENT-SAVE", stage: 2, consentComplete: false });

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-CONSENT-SAVE" });
    expect(await screen.findByText("Molecular gate closed")).toBeInTheDocument();

    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);
    for (const checkbox of checkboxes) {
      await user.click(checkbox);
    }
    await user.click(screen.getByRole("button", { name: "Save consent" }));

    expect(await screen.findByText("Molecular gate open")).toBeInTheDocument();
  });

  it("surfaces the duplicate case-id reason on registration", async () => {
    const user = userEvent.setup();
    signInAs("genomics");
    seedSample({ caseId: "CASE-DUP" });

    renderWithAuth(<RegisterSamplePage />);
    await user.type(await screen.findByLabelText("Case identifier"), "CASE-DUP");
    await user.click(screen.getByRole("button", { name: "Register sample" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A sample with case id CASE-DUP already exists",
    );
    expect(nav.push).not.toHaveBeenCalled();
  });

  it("registers a sample and opens its detail view", async () => {
    const user = userEvent.setup();
    signInAs("genomics");

    renderWithAuth(<RegisterSamplePage />);
    await user.type(await screen.findByLabelText("Case identifier"), "CASE-NEW");
    await user.click(screen.getByRole("button", { name: "Register sample" }));

    await waitFor(() =>
      expect(nav.push).toHaveBeenCalledWith(expect.stringMatching(/^\/samples\/[0-9a-f-]+$/)),
    );
  });

  it("lists samples and shows an empty state", async () => {
    signInAs("genomics");

    const { unmount } = renderWithAuth(<SamplesPage />);
    expect(await screen.findByText("No samples yet")).toBeInTheDocument();
    unmount();

    seedSample({ caseId: "CASE-LIST" });
    renderWithAuth(<SamplesPage />);

    expect(await screen.findByRole("link", { name: "CASE-LIST" })).toBeInTheDocument();
  });

  it("keeps the advance action available after a QC pass", async () => {
    const user = userEvent.setup();
    signInAs("bioinformatics");
    const sample = seedSample({ id: "s1", caseId: "CASE-QC-PASS", stage: 7 });
    setQcPassed(sample.id, true);

    renderDetail();
    await screen.findByRole("heading", { name: "CASE-QC-PASS" });
    await user.click(screen.getByRole("button", { name: "Advance sample" }));

    expect(
      (await screen.findAllByText("Report upload/archive/portal push")).length,
    ).toBeGreaterThan(0);
  });
});
