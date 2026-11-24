import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BoardPage from "@/app/(app)/board/page";

import { resetTestSession, seedSample, signInAs } from "./msw/handlers";
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
  usePathname: () => "/board",
  useSearchParams: () => new URLSearchParams(),
}));

const DAY_MS = 86_400_000;

describe("shared TAT board (SC-005)", () => {
  beforeEach(() => {
    resetTestSession();
  });

  it("places samples in their stage column and flags past-target samples", async () => {
    const old = new Date(Date.now() - 20 * DAY_MS).toISOString();
    seedSample({ caseId: "CASE-OLD", stage: 3, receivedAt: old });
    seedSample({ caseId: "CASE-FRESH", stage: 1, receivedAt: new Date().toISOString() });
    signInAs("admin");

    renderWithAuth(<BoardPage />);

    expect(await screen.findByText("CASE-OLD")).toBeInTheDocument();

    const molecular = screen.getByRole("region", { name: "Molecular processing column" });
    const received = screen.getByRole("region", { name: "Sample received column" });

    expect(within(molecular).getByText("CASE-OLD")).toBeInTheDocument();
    expect(within(received).getByText("CASE-FRESH")).toBeInTheDocument();

    const oldCard = screen.getByRole("article", { name: "CASE-OLD card" });
    const freshCard = screen.getByRole("article", { name: "CASE-FRESH card" });
    expect(within(oldCard).getByText("Past target")).toBeInTheDocument();
    expect(within(freshCard).queryByText("Past target")).not.toBeInTheDocument();
  });

  it("moves a card to its new stage after an advance and refetch", async () => {
    seedSample({ caseId: "CASE-MOVE", stage: 3, receivedAt: new Date().toISOString() });
    signInAs("admin");

    renderWithAuth(<BoardPage />);

    const card = await screen.findByRole("article", { name: "CASE-MOVE card" });
    await userEvent.click(within(card).getByRole("button", { name: "Advance" }));

    const dataGeneration = screen.getByRole("region", { name: "Data generation column" });
    await waitFor(() => {
      expect(within(dataGeneration).getByText("CASE-MOVE")).toBeInTheDocument();
    });

    const molecular = screen.getByRole("region", { name: "Molecular processing column" });
    expect(within(molecular).queryByText("CASE-MOVE")).not.toBeInTheDocument();
  });

  it("shows overall open time instead of admin-only stage timings to non-admins", async () => {
    seedSample({ caseId: "CASE-OPEN", stage: 3, receivedAt: new Date().toISOString() });
    signInAs("molecular");

    renderWithAuth(<BoardPage />);

    expect(await screen.findByText("CASE-OPEN")).toBeInTheDocument();
    expect(
      screen.getByText(
        /Stage-level time and per-stage breach detail are available to administrators/,
      ),
    ).toBeInTheDocument();
    const card = screen.getByRole("article", { name: "CASE-OPEN card" });
    expect(within(card).getByText(/Open \d+\.\d d/)).toBeInTheDocument();
  });
});
