"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBadge } from "@/components/StageBadge";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useBoardSamples, useUserCount, useVendors } from "@/lib/features/dashboard/queries";
import { resolveDashboardView } from "@/lib/features/dashboard/views";
import type { Sample } from "@/lib/features/samples/queries";
import { formatDateTime } from "@/lib/format";
import { isPastTarget } from "@/lib/workflow/stages";

function QueueTable({ samples }: { samples: readonly Sample[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-card">
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">Samples awaiting this role</caption>
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" className="px-4 py-2 text-start font-medium">
              Case
            </th>
            <th scope="col" className="px-4 py-2 text-start font-medium">
              Stage
            </th>
            <th scope="col" className="px-4 py-2 text-start font-medium">
              Received
            </th>
            <th scope="col" className="px-4 py-2 text-start font-medium">
              Target
            </th>
          </tr>
        </thead>
        <tbody>
          {samples.map((sample) => {
            const overdue = isPastTarget(sample.received_at);
            return (
              <tr key={sample.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">
                  <Link
                    href={`/samples/${sample.id}`}
                    className="font-medium text-brand hover:underline"
                  >
                    {sample.case_id}
                  </Link>
                </td>
                <td className="px-4 py-3">
                  <StageBadge stage={sample.current_stage} />
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {formatDateTime(sample.received_at)}
                </td>
                <td className="px-4 py-3">
                  {overdue ? (
                    <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
                      Past target
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">Within target</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function DashboardContent() {
  const { roles } = useAuth();
  const searchParams = useSearchParams();
  const view = resolveDashboardView(roles, searchParams.get("view"));

  const samplesQuery = useBoardSamples();
  const usersQuery = useUserCount({ enabled: view.adminSummary });
  const vendorsQuery = useVendors({ enabled: view.adminSummary });

  const samples = samplesQuery.data?.items ?? [];
  const queue = samples.filter(
    (sample) =>
      sample.status === "active" && view.stagePositions.includes(sample.current_stage.position),
  );
  const pastTarget = queue.filter((sample) => isPastTarget(sample.received_at)).length;
  const activeVendors = (vendorsQuery.data ?? []).filter((vendor) => vendor.is_active).length;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{view.title}</h1>
        <p className="text-sm text-muted-foreground">{view.description}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Awaiting this role" value={queue.length} />
        <StatCard label="Past target" value={pastTarget} />
        {view.adminSummary ? (
          <>
            <StatCard label="Users" value={usersQuery.data?.total ?? "—"} />
            <StatCard label="Active vendors" value={vendorsQuery.data ? activeVendors : "—"} />
          </>
        ) : null}
      </div>

      {samplesQuery.isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading your work queue…
        </p>
      ) : samplesQuery.isError ? (
        <GateError
          detail={
            samplesQuery.error instanceof ApiError
              ? samplesQuery.error.detail
              : "Could not load your work queue. Please try again."
          }
        />
      ) : queue.length === 0 ? (
        <EmptyState
          title="Nothing in your queue"
          description="Samples awaiting this role will appear here."
        />
      ) : (
        <QueueTable samples={queue} />
      )}

      {view.adminSummary && usersQuery.isError ? (
        <GateError
          detail={
            usersQuery.error instanceof ApiError
              ? usersQuery.error.detail
              : "Could not load the user count."
          }
        />
      ) : null}
    </section>
  );
}

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <p role="status" className="text-sm text-muted-foreground">
          Loading dashboard…
        </p>
      }
    >
      <DashboardContent />
    </Suspense>
  );
}
