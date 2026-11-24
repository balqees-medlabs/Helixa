import { dashboardViewsForRoles } from "@/lib/auth/roles";
import type { RoleSlug } from "@/lib/auth/roles";

export interface DashboardDefinition {
  slug: RoleSlug;
  label: string;
  title: string;
  description: string;
  stagePositions: readonly number[];
  adminSummary: boolean;
}

/**
 * The four dashboards from the constitution (VII.4), in privilege order so a
 * multi-role user defaults to the most privileged one (research D4). Each queue
 * is the set of stages whose work belongs to that role.
 */
export const DASHBOARD_DEFINITIONS: readonly DashboardDefinition[] = [
  {
    slug: "admin",
    label: "Admin",
    title: "Administration",
    description: "Every stage, plus account and vendor oversight.",
    stagePositions: [1, 2, 3, 4, 5, 6, 7, 8],
    adminSummary: true,
  },
  {
    slug: "bioinformatics",
    label: "Bioinformatics",
    title: "Bioinformatics work queue",
    description: "Data generation, conversion/QC and reporting.",
    stagePositions: [4, 7, 8],
    adminSummary: false,
  },
  {
    slug: "genomics",
    label: "Genomics",
    title: "Genomics work queue",
    description: "Sample intake and the consent/documentation gate.",
    stagePositions: [1, 2],
    adminSummary: false,
  },
  {
    slug: "molecular",
    label: "Molecular biology",
    title: "Molecular biology work queue",
    description: "Molecular processing awaiting completion.",
    stagePositions: [3],
    adminSummary: false,
  },
];

/**
 * `trf` has no dedicated dashboard in the constitution; its samples still need
 * an at-a-glance view, so a shared TRF queue is used only when no dashboard
 * role applies.
 */
export const TRF_DASHBOARD: DashboardDefinition = {
  slug: "trf",
  label: "TRF",
  title: "TRF work queue",
  description: "TRF preparation and confirmation awaiting completion.",
  stagePositions: [5, 6],
  adminSummary: false,
};

/** The dashboards a user may open, in privilege order. */
export function availableDashboardViews(roles: readonly string[]): DashboardDefinition[] {
  const granted = new Set(dashboardViewsForRoles(roles).map((view) => view.slug));
  const views = DASHBOARD_DEFINITIONS.filter((definition) => granted.has(definition.slug));
  return views.length > 0 ? views : [TRF_DASHBOARD];
}

/** The requested dashboard when permitted, otherwise the most privileged one. */
export function resolveDashboardView(
  roles: readonly string[],
  requested: string | null | undefined,
): DashboardDefinition {
  const views = availableDashboardViews(roles);
  return views.find((view) => view.slug === requested) ?? views[0];
}
