import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import { DashboardSwitcher } from "@/components/DashboardSwitcher";

import {
  TEST_USERS,
  resetTestSession,
  seedSample,
  seedVendor,
  setCurrentUser,
  signInAs,
  type RoleSlug,
} from "./msw/handlers";
import { renderWithAuth } from "./render";

const navState = vi.hoisted(() => ({ search: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => "/dashboard",
  useSearchParams: () => navState.search,
}));

const now = new Date().toISOString();

function seedWorkQueues() {
  seedSample({ caseId: "CASE-GEN", stage: 1, receivedAt: now });
  seedSample({ caseId: "CASE-MOL", stage: 3, receivedAt: now });
  seedSample({ caseId: "CASE-BIO", stage: 4, receivedAt: now });
  seedSample({ caseId: "CASE-TRF", stage: 5, receivedAt: now });
  seedSample({ caseId: "CASE-REP", stage: 8, receivedAt: now });
}

const QUEUES: Record<RoleSlug, { title: string; visible: string[]; hidden: string[] }> = {
  admin: {
    title: "Administration",
    visible: ["CASE-GEN", "CASE-MOL", "CASE-BIO", "CASE-TRF", "CASE-REP"],
    hidden: [],
  },
  genomics: {
    title: "Genomics work queue",
    visible: ["CASE-GEN"],
    hidden: ["CASE-MOL", "CASE-BIO"],
  },
  molecular: {
    title: "Molecular biology work queue",
    visible: ["CASE-MOL"],
    hidden: ["CASE-GEN", "CASE-BIO"],
  },
  bioinformatics: {
    title: "Bioinformatics work queue",
    visible: ["CASE-BIO", "CASE-REP"],
    hidden: ["CASE-GEN", "CASE-MOL"],
  },
  trf: { title: "TRF work queue", visible: ["CASE-TRF"], hidden: ["CASE-GEN", "CASE-MOL"] },
};

describe("role dashboards (SC-002)", () => {
  beforeEach(() => {
    resetTestSession();
    navState.search = new URLSearchParams();
  });

  for (const role of Object.keys(QUEUES) as RoleSlug[]) {
    it(`shows ${role}'s work queue`, async () => {
      seedWorkQueues();
      signInAs(role);

      renderWithAuth(<DashboardPage />);

      expect(await screen.findByRole("heading", { name: QUEUES[role].title })).toBeInTheDocument();
      for (const caseId of QUEUES[role].visible) {
        expect(await screen.findByText(caseId)).toBeInTheDocument();
      }
      for (const caseId of QUEUES[role].hidden) {
        expect(screen.queryByText(caseId)).not.toBeInTheDocument();
      }
    });
  }

  it("shows account and vendor counts on the admin dashboard", async () => {
    seedSample({ caseId: "CASE-ADMIN", stage: 2, receivedAt: now });
    seedVendor({ name: "Genome Lab", isActive: true });
    signInAs("admin");

    renderWithAuth(<DashboardPage />);

    expect(await screen.findByText("Users")).toBeInTheDocument();
    const vendorStat = screen.getByText("Active vendors").parentElement;
    const userStat = screen.getByText("Users").parentElement;
    expect(vendorStat).not.toBeNull();
    expect(userStat).not.toBeNull();
    await waitFor(() => {
      expect(within(vendorStat as HTMLElement).getByText("1")).toBeInTheDocument();
      expect(
        within(userStat as HTMLElement).getByText(String(Object.keys(TEST_USERS).length)),
      ).toBeInTheDocument();
    });
  });

  it("lands a multi-role user on the most privileged dashboard with a switcher", async () => {
    setCurrentUser({
      ...TEST_USERS.genomics,
      id: "00000000-0000-4000-8000-000000000099",
      email: "multi@helixa.test",
      display_name: "Multi Role",
      roles: ["genomics", "bioinformatics"],
    });
    seedWorkQueues();

    renderWithAuth(
      <>
        <DashboardPage />
        <DashboardSwitcher />
      </>,
    );

    expect(
      await screen.findByRole("heading", { name: "Bioinformatics work queue" }),
    ).toBeInTheDocument();

    const switcher = screen.getByRole("navigation", { name: "Dashboards" });
    expect(within(switcher).getByRole("link", { name: "Genomics" })).toHaveAttribute(
      "href",
      "/dashboard?view=genomics",
    );
    expect(within(switcher).getByRole("link", { name: "Bioinformatics" })).toHaveAttribute(
      "href",
      "/dashboard?view=bioinformatics",
    );
  });

  it("switches to a requested dashboard the user's roles grant", async () => {
    setCurrentUser({
      ...TEST_USERS.genomics,
      id: "00000000-0000-4000-8000-000000000098",
      email: "multi2@helixa.test",
      display_name: "Multi Two",
      roles: ["genomics", "bioinformatics"],
    });
    navState.search = new URLSearchParams("view=genomics");
    seedWorkQueues();

    renderWithAuth(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "Genomics work queue" })).toBeInTheDocument();
    expect(screen.getByText("CASE-GEN")).toBeInTheDocument();
  });

  it("ignores a dashboard the user's roles do not grant", async () => {
    signInAs("genomics");
    navState.search = new URLSearchParams("view=admin");
    seedWorkQueues();

    renderWithAuth(<DashboardPage />);

    expect(await screen.findByRole("heading", { name: "Genomics work queue" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Administration" })).not.toBeInTheDocument();
  });
});
