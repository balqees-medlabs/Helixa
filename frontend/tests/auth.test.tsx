import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppLayout from "@/app/(app)/layout";
import LoginPage from "@/app/(auth)/login/page";
import { resetSessionExpiredState } from "@/lib/api/client";

import { TEST_PASSWORD, TEST_USERS, resetTestSession, signInAs } from "./msw/handlers";
import { server } from "./msw/server";
import { renderWithAuth } from "./render";

const nav = vi.hoisted(() => ({
  pathname: "/dashboard",
  search: "",
  replace: vi.fn(),
  push: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: nav.replace,
    push: nav.push,
    refresh: nav.refresh,
    prefetch: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
}));

describe("sign in and session handling (US1)", () => {
  beforeEach(() => {
    resetSessionExpiredState();
    resetTestSession();
    nav.pathname = "/dashboard";
    nav.search = "";
    window.history.replaceState({}, "", "/dashboard");
  });

  it("signs in and lands on the most privileged dashboard", async () => {
    const user = userEvent.setup();
    nav.pathname = "/login";
    window.history.replaceState({}, "", "/login");
    renderWithAuth(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), TEST_USERS.genomics.email ?? "");
    await user.type(screen.getByLabelText("Password"), TEST_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard?view=genomics"));
  });

  it("returns the user to the requested route after signing in", async () => {
    const user = userEvent.setup();
    nav.pathname = "/login";
    nav.search = "?next=%2Fsamples%3Fstage%3D2";
    window.history.replaceState({}, "", "/login");
    renderWithAuth(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), TEST_USERS.genomics.email ?? "");
    await user.type(screen.getByLabelText("Password"), TEST_PASSWORD);
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/samples?stage=2"));
  });

  it("shows one non-revealing error for wrong credentials", async () => {
    const user = userEvent.setup();
    nav.pathname = "/login";
    window.history.replaceState({}, "", "/login");
    renderWithAuth(<LoginPage />);

    await user.type(screen.getByLabelText("Email"), TEST_USERS.genomics.email ?? "");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const alerts = await screen.findAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent("Invalid email or password");
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("presents the signed-in identity and roles", async () => {
    signInAs("bioinformatics");
    renderWithAuth(
      <AppLayout>
        <p>Protected workspace</p>
      </AppLayout>,
    );

    expect(await screen.findByText(TEST_USERS.bioinformatics.display_name)).toBeInTheDocument();
    expect(screen.getByText("Bioinformatics")).toBeInTheDocument();
    expect(screen.getByText("Protected workspace")).toBeInTheDocument();
  });

  it("redirects an unauthenticated visitor to sign in and preserves the target", async () => {
    nav.pathname = "/samples";
    window.history.replaceState({}, "", "/samples");

    renderWithAuth(
      <AppLayout>
        <p>Protected workspace</p>
      </AppLayout>,
    );

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login?next=%2Fsamples"));
    expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
  });

  it("silently refreshes an expired session and retries", async () => {
    signInAs("genomics");
    let meCalls = 0;

    server.use(
      http.get("/api/auth/me", () => {
        meCalls += 1;
        return meCalls === 1
          ? HttpResponse.json({ detail: "expired" }, { status: 401 })
          : HttpResponse.json(TEST_USERS.genomics);
      }),
    );

    renderWithAuth(
      <AppLayout>
        <p>Protected workspace</p>
      </AppLayout>,
    );

    expect(await screen.findByText(TEST_USERS.genomics.display_name)).toBeInTheDocument();
    expect(meCalls).toBe(2);
    expect(nav.replace).not.toHaveBeenCalled();
  });

  it("returns to sign in when the refresh fails", async () => {
    nav.pathname = "/samples/42";
    window.history.replaceState({}, "", "/samples/42");

    server.use(
      http.get("/api/auth/me", () => HttpResponse.json({ detail: "expired" }, { status: 401 })),
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ detail: "expired" }, { status: 401 }),
      ),
    );

    renderWithAuth(
      <AppLayout>
        <p>Protected workspace</p>
      </AppLayout>,
    );

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login?next=%2Fsamples%2F42"));
  });

  it("signs out and makes protected screens unreachable", async () => {
    signInAs("genomics");
    const user = userEvent.setup();

    renderWithAuth(
      <AppLayout>
        <p>Protected workspace</p>
      </AppLayout>,
    );

    await screen.findByText(TEST_USERS.genomics.display_name);
    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login"));
    expect(await screen.findByText("Redirecting to sign in…")).toBeInTheDocument();
    expect(screen.queryByText("Protected workspace")).not.toBeInTheDocument();
  });
});
