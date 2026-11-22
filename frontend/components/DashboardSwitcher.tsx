"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { useAuth } from "@/lib/auth/AuthProvider";
import { availableDashboardViews, resolveDashboardView } from "@/lib/features/dashboard/views";
import { cn } from "@/lib/utils";

/**
 * Switcher for multi-role users; a single-dashboard user sees nothing. The
 * active view follows `?view=`, falling back to the most privileged one.
 */
export function DashboardSwitcher() {
  const { roles } = useAuth();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const views = availableDashboardViews(roles);

  if (views.length < 2) {
    return null;
  }

  const active = resolveDashboardView(roles, searchParams.get("view"));
  const onDashboard = pathname === "/dashboard";

  return (
    <nav
      aria-label="Dashboards"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"
    >
      <span className="font-medium uppercase tracking-wide">Dashboards</span>
      {views.map((view) => {
        const isActive = onDashboard && view.slug === active.slug;
        return (
          <Link
            key={view.slug}
            href={`/dashboard?view=${view.slug}`}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "rounded-sm px-1 py-0.5 transition-colors hover:text-brand",
              isActive
                ? "font-medium text-brand underline underline-offset-4"
                : "text-muted-foreground",
            )}
          >
            {view.label}
          </Link>
        );
      })}
    </nav>
  );
}
