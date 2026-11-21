/**
 * Route helpers shared by the authenticated shell and per-area pages. The UI
 * only reflects coarse area access; the backend remains the authority on every
 * action (Art. I.3 / III.2).
 */
export function requireRoles(roles: readonly string[], allowed: readonly string[]): boolean {
  if (roles.includes("admin")) {
    return true;
  }
  return allowed.some((slug) => roles.includes(slug));
}

export function isSignedIn(user: unknown): boolean {
  return Boolean(user);
}

/** Accept only same-origin relative targets so `?next=` can't leave the app. */
export function safeNextPath(next: string | null | undefined): string | null {
  if (!next) {
    return null;
  }

  const trimmed = next.trim();
  if (!trimmed.startsWith("/") || trimmed.startsWith("//") || trimmed.startsWith("/\\")) {
    return null;
  }
  if (trimmed === "/login" || trimmed.startsWith("/login?")) {
    return null;
  }
  return trimmed;
}

/** Build the sign-in URL that returns the visitor to the attempted route. */
export function loginRedirect(pathname: string, search = ""): string {
  return `/login?next=${encodeURIComponent(`${pathname}${search}`)}`;
}
