"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { SubmitButton } from "@/components/SubmitButton";
import { useAuth } from "@/lib/auth/AuthProvider";
import { requireRoles } from "@/lib/auth/guards";
import { dashboardViewsForRoles } from "@/lib/auth/roles";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  roles?: readonly string[];
  exact?: boolean;
}

/**
 * Role→area map from contracts/routes.md. Empty `roles` means every signed-in
 * role may see the area; `admin` passes every entry via `requireRoles`.
 */
const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/board", label: "TAT board" },
  { href: "/samples", label: "Samples" },
  { href: "/samples/register", label: "Register sample", roles: ["genomics"] },
  { href: "/batches", label: "Batches", roles: ["genomics", "bioinformatics"] },
  { href: "/qc", label: "QC", roles: ["bioinformatics"] },
  { href: "/vendors", label: "Vendors" },
  { href: "/reports", label: "Reports", roles: ["genomics", "bioinformatics"] },
  { href: "/metrics", label: "Metrics", roles: ["admin"] },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.href === "/samples" && pathname.startsWith("/samples/register")) {
    return false;
  }
  return pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`));
}

function DashboardSwitcher({ roles }: { roles: readonly string[] }) {
  const pathname = usePathname();
  const views = dashboardViewsForRoles(roles);

  if (views.length < 2) {
    return null;
  }

  return (
    <nav
      aria-label="Dashboards"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"
    >
      <span className="font-medium uppercase tracking-wide">Dashboards</span>
      {views.map((view) => (
        <Link
          key={view.slug}
          href={view.href}
          className={cn(
            "rounded-sm px-1 py-0.5 transition-colors hover:text-brand",
            pathname === "/dashboard" ? "text-foreground" : "text-muted-foreground",
          )}
        >
          {view.label}
        </Link>
      ))}
    </nav>
  );
}

export function RoleNav() {
  const { user, roles, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [pending, setPending] = useState(false);

  const items = NAV_ITEMS.filter((item) => !item.roles || requireRoles(roles, item.roles));

  async function handleSignOut() {
    setPending(true);
    try {
      await logout();
      router.replace("/login");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex w-full flex-col gap-4 border-b border-border bg-card px-6 py-4 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline gap-3">
          <Link href="/dashboard" className="text-lg font-semibold tracking-tight text-brand">
            Helixa
          </Link>
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            Medlabs Genomics
          </span>
        </div>
        <nav aria-label="Main" className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {items.map((item) => {
            const active = isActive(pathname, item);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-sm px-1 py-0.5 transition-colors hover:text-brand",
                  active
                    ? "font-medium text-brand underline underline-offset-4"
                    : "text-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <DashboardSwitcher roles={roles} />
      </div>

      <div className="flex items-center gap-4 text-sm">
        <div className="text-end">
          <p className="font-medium">{user?.display_name}</p>
          <p className="text-xs text-muted-foreground">
            {roles.length ? roles.map((role) => sentenceCase(role)).join(", ") : "No role"}
          </p>
        </div>
        <SubmitButton
          type="button"
          pending={pending}
          pendingLabel="Signing out…"
          variant="outline"
          onClick={handleSignOut}
        >
          Sign out
        </SubmitButton>
      </div>
    </div>
  );
}
