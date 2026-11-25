"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useRun } from "@/lib/features/runs/queries";
import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";

  const runQuery = useRun(runId);

  if (runQuery.isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading run…
      </p>
    );
  }

  if (runQuery.isError) {
    const notFound = runQuery.error instanceof ApiError && runQuery.error.status === 404;
    if (notFound) {
      return (
        <EmptyState
          title="Run not found"
          description="The run may have been removed or you may not have access to it."
          action={
            <Link href="/runs" className="text-sm text-brand hover:underline">
              Back to runs
            </Link>
          }
        />
      );
    }
    return (
      <GateError
        detail={
          runQuery.error instanceof ApiError
            ? runQuery.error.detail
            : "Could not load the run. Please try again."
        }
      />
    );
  }

  const run = runQuery.data;
  if (!run) {
    return null;
  }

  const cycleValues = [run.cycle_r1, run.cycle_r2, run.cycle_i1, run.cycle_i2].filter(
    (value) => value != null,
  );

  return (
    <section className="flex flex-col gap-6">
      <Link href="/runs" className="text-sm text-brand hover:underline">
        Runs
      </Link>
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight break-words">{run.run_folder}</h1>
        <p className="text-sm text-muted-foreground">
          Sequencing run recorded in Helixa. See the run&apos;s samples on the workflow Sample
          screens once intake adds them.
        </p>
      </div>

      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Instrument
          </dt>
          <dd className="mt-1 font-medium">{run.instrument}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Project
          </dt>
          <dd className="mt-1 font-medium">{run.project ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Run side
          </dt>
          <dd className="mt-1">{run.run_side ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Run date
          </dt>
          <dd className="mt-1">{run.run_date ? formatDateTime(run.run_date) : "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Storage location
          </dt>
          <dd className="mt-1 break-all">{run.storage_location ?? "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Readiness
          </dt>
          <dd className="mt-1">
            <span
              className={cn(
                "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                run.readiness === "ready"
                  ? "bg-success/10 text-success"
                  : run.readiness === "received"
                    ? "bg-secondary text-secondary-foreground"
                    : "bg-destructive/10 text-destructive",
              )}
            >
              {sentenceCase(run.readiness)}
            </span>
          </dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Cycle counts (R1, R2, I1, I2)
          </dt>
          <dd className="mt-1">{cycleValues.length ? cycleValues.join(" / ") : "—"}</dd>
        </div>
        <div className="rounded-lg border border-border bg-card p-4">
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Recorded at
          </dt>
          <dd className="mt-1">{formatDateTime(run.created_at)}</dd>
        </div>
      </dl>
    </section>
  );
}
