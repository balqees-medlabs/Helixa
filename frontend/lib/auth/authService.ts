import { ApiError, apiFetch } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type SessionUser = components["schemas"]["UserOut"];

/** One non-revealing message for every rejected sign-in (FR-005). */
export const INVALID_CREDENTIALS = "Invalid email or password";

export async function login(email: string, password: string): Promise<SessionUser> {
  return apiFetch("/auth/login", { method: "post", body: { email, password } });
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "post" });
}

/** Session truth is `GET /auth/me`; a 401 simply means signed out (research D3). */
export async function me(): Promise<SessionUser | null> {
  try {
    return await apiFetch("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export { landingDashboardFor as landingPathForRoles } from "./roles";
