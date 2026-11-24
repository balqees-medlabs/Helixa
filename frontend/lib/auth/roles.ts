export const ROLE_SLUGS = ["admin", "genomics", "trf", "molecular", "bioinformatics"] as const;

export type RoleSlug = (typeof ROLE_SLUGS)[number];

export interface DashboardView {
  slug: RoleSlug;
  label: string;
  href: string;
}

/**
 * Privilege order for the default landing (research D4): admin first, then the
 * operational dashboards. Only the four dashboards in the constitution (VII.4)
 * are listed; `trf` has no dedicated dashboard and lands on the shared view.
 */
const DASHBOARD_ORDER: readonly RoleSlug[] = ["admin", "bioinformatics", "genomics", "molecular"];

const DASHBOARD_LABELS: Partial<Record<RoleSlug, string>> = {
  admin: "Admin",
  genomics: "Genomics",
  molecular: "Molecular biology",
  bioinformatics: "Bioinformatics",
};

export function dashboardHref(slug: RoleSlug): string {
  return `/dashboard?view=${slug}`;
}

/**
 * The dashboards a user may open: all four for an administrator, otherwise the
 * ones matching the roles they hold, most privileged first.
 */
export function dashboardViewsForRoles(roles: readonly string[]): DashboardView[] {
  const isAdmin = roles.includes("admin");

  return DASHBOARD_ORDER.filter((slug) => isAdmin || roles.includes(slug)).map((slug) => ({
    slug,
    label: DASHBOARD_LABELS[slug] ?? slug,
    href: dashboardHref(slug),
  }));
}

/** The most privileged dashboard path for the landing view. */
export function landingDashboardFor(roles: readonly string[]): string {
  return dashboardViewsForRoles(roles)[0]?.href ?? "/dashboard";
}
