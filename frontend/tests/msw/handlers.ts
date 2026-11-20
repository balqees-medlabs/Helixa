import { HttpResponse, http } from "msw";

import type { components } from "@/lib/api/schema";

export type SessionUser = components["schemas"]["UserOut"];
export type RoleSlug = "admin" | "genomics" | "trf" | "molecular" | "bioinformatics";

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
];
