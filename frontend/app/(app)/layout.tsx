"use client";

import { usePathname, useRouter } from "next/navigation";
import { Suspense, useEffect } from "react";

import { DashboardSwitcher } from "@/components/DashboardSwitcher";
import { RoleNav } from "@/components/RoleNav";
import { useAuth } from "@/lib/auth/AuthProvider";
import { isSignedIn, loginRedirect } from "@/lib/auth/guards";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isSignedIn(user)) {
      router.replace(loginRedirect(pathname, window.location.search));
    }
  }, [isLoading, user, pathname, router]);

  if (isLoading) {
    return (
      <main className="container flex min-h-screen items-center justify-center py-16">
        <p role="status" className="text-sm text-muted-foreground">
          Loading your workspace…
        </p>
      </main>
    );
  }

  if (!isSignedIn(user)) {
    return (
      <main className="container flex min-h-screen items-center justify-center py-16">
        <p role="status" className="text-sm text-muted-foreground">
          Redirecting to sign in…
        </p>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-20">
        <RoleNav />
        <div
          id="dashboard-switcher"
          data-dashboard-switcher
          className="border-b border-border bg-card px-6 py-2 empty:hidden"
        >
          <Suspense fallback={null}>
            <DashboardSwitcher />
          </Suspense>
        </div>
      </header>
      <main className="container flex-1 py-8">{children}</main>
    </div>
  );
}
