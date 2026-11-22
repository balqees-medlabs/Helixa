import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardSwitcher } from "@/components/DashboardSwitcher";
import { RoleNav } from "@/components/RoleNav";

import {
  TEST_USERS,
  resetTestSession,
  setCurrentUser,
  signInAs,
  type RoleSlug,
} from "./msw/handlers";
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
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

const ALL_NAV = [
  "Dashboard",
  "TAT board",
  "Samples",
  "Register sample",
  "Batches",
  "QC",
  "Vendors",
  "Reports",
  "Metrics",
] as const;

const EXPECTED_NAV: Record<RoleSlug, string[]> = {
  admin: [...ALL_NAV],
  genomics: [
    "Dashboard",
    "TAT board",
    "Samples",
    "Register sample",
    "Batches",
    "Vendors",
    "Reports",
  ],
  trf: ["Dashboard", "TAT board", "Samples", "Vendors"],
  molecular: ["Dashboard", "TAT board", "Samples", "Vendors"],
  bioinformatics: ["Dashboard", "TAT board", "Samples", "Batches", "QC", "Vendors", "Reports"],
};

async function renderSignedIn(role: RoleSlug) {
  signInAs(role);
  renderWithAuth(
    <>
      <RoleNav />
      <DashboardSwitcher />
    </>,
  );
  await screen.findByText(TEST_USERS[role].display_name);
}

describe("role-bound navigation (SC-002)", () => {
  beforeEach(() => {
    resetTestSession();
  });

  for (const role of Object.keys(EXPECTED_NAV) as RoleSlug[]) {
    it(`offers only ${role}'s permitted areas`, async () => {
      await renderSignedIn(role);

      for (const label of ALL_NAV) {
        const link = screen.queryByRole("link", { name: label });
        if (EXPECTED_NAV[role].includes(label)) {
          expect(link, `${role} should see ${label}`).toBeInTheDocument();
        } else {
          expect(link, `${role} should not see ${label}`).not.toBeInTheDocument();
        }
      }

      expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    });
  }

  it("gives admin every area and every dashboard", async () => {
    await renderSignedIn("admin");

    expect(screen.getByRole("navigation", { name: "Dashboards" })).toBeInTheDocument();
    for (const label of ["Admin", "Genomics", "Molecular biology", "Bioinformatics"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("lets a multi-role user reach every area their roles grant", async () => {
    setCurrentUser({
      ...TEST_USERS.genomics,
      id: "00000000-0000-4000-8000-000000000099",
      email: "multi@helixa.test",
      display_name: "Multi Role",
      roles: ["genomics", "bioinformatics"],
    });

    renderWithAuth(
      <>
        <RoleNav />
        <DashboardSwitcher />
      </>,
    );
    await screen.findByText("Multi Role");

    for (const label of [
      "Dashboard",
      "TAT board",
      "Samples",
      "Register sample",
      "Batches",
      "QC",
      "Vendors",
      "Reports",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: "Metrics" })).not.toBeInTheDocument();

    expect(screen.getByRole("link", { name: "Genomics" })).toHaveAttribute(
      "href",
      "/dashboard?view=genomics",
    );
    expect(screen.getByRole("link", { name: "Bioinformatics" })).toHaveAttribute(
      "href",
      "/dashboard?view=bioinformatics",
    );
  });

  it("shows no dashboard switcher to a single-role user", async () => {
    await renderSignedIn("molecular");

    expect(screen.queryByRole("navigation", { name: "Dashboards" })).not.toBeInTheDocument();
  });
});
