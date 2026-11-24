"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBadge } from "@/components/StageBadge";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useTatMetrics, useUpdateStageSla } from "@/lib/features/dashboard/queries";
import type { TatMetrics } from "@/lib/features/dashboard/queries";
import { formatDateTime, formatDurationHours } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import { STAGES } from "@/lib/workflow/stages";

interface StageRow {
  position: number;
  slug: string;
  name: string;
  stageId: string | null;
  slaDays: number | null;
  measured: number;
  breached: number;
  averageHours: number | null;
}

function buildStageRows(metrics: TatMetrics): StageRow[] {
  const allStageMetrics = metrics.samples.flatMap((sample) => sample.stages);

  return STAGES.map((stage) => {
    const metricsForStage = allStageMetrics.filter((metric) => metric.position === stage.position);
    const measured = metricsForStage.filter((metric) => metric.duration_hours != null);
    const totalHours = measured.reduce((sum, metric) => sum + (metric.duration_hours ?? 0), 0);

    return {
      ...stage,
      stageId: metricsForStage.find((metric) => metric.stage_id)?.stage_id ?? null,
      slaDays: metricsForStage.find((metric) => metric.sla_days != null)?.sla_days ?? null,
      measured: measured.length,
      breached: metricsForStage.filter((metric) => metric.breached).length,
      averageHours: measured.length > 0 ? totalHours / measured.length : null,
    };
  });
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function SlaEditor({
  stageId,
  stageName,
  slaDays,
}: {
  stageId: string;
  stageName: string;
  slaDays: number | null;
}) {
  const update = useUpdateStageSla();
  const [value, setValue] = useState(slaDays?.toString() ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSaved(false);

    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1) {
      setError("Enter a whole number of days (1 or more).");
      return;
    }

    update.mutate(
      { stageId, slaDays: parsed },
      {
        onSuccess: () => setSaved(true),
        onError: (mutationError) => {
          setError(
            mutationError instanceof ApiError
              ? mutationError.detail
              : "Could not update the stage SLA. Please try again.",
          );
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          min={1}
          step={1}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setSaved(false);
          }}
          aria-label={`SLA days for ${sentenceCase(stageName)}`}
          className="w-16 rounded-md border border-input bg-background px-2 py-1 text-sm tabular-nums"
        />
        <SubmitButton
          type="submit"
          pending={update.isPending}
          pendingLabel="Saving…"
          variant="outline"
          className="px-2 py-1 text-xs"
        >
          Save
        </SubmitButton>
      </div>
      {saved ? <span className="text-xs text-success">Saved</span> : null}
      <GateError detail={error} className="px-2 py-1 text-xs" />
    </form>
  );
}

export default function MetricsPage() {
  const { can } = useAuth();
  const isAdmin = can("admin");
  const metricsQuery = useTatMetrics({ enabled: isAdmin });

  if (!isAdmin) {
    return (
      <EmptyState
        title="Turnaround metrics are admin-only"
        description="Ask an administrator for access to per-stage durations and breaches."
      />
    );
  }

  if (metricsQuery.isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading turnaround metrics…
      </p>
    );
  }

  if (metricsQuery.isError || !metricsQuery.data) {
    return (
      <GateError
        detail={
          metricsQuery.error instanceof ApiError
            ? metricsQuery.error.detail
            : "Could not load turnaround metrics. Please try again."
        }
      />
    );
  }

  const metrics = metricsQuery.data;
  const stageRows = buildStageRows(metrics);
  const pastTarget = metrics.samples.filter((sample) => sample.target_breached);
  const breachedStageCount = stageRows.reduce((sum, row) => sum + row.breached, 0);

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Turnaround metrics</h1>
        <p className="text-sm text-muted-foreground">
          Per-stage durations and breaches, the 18-day internal target, and external-vendor
          turnaround. Generated {formatDateTime(metrics.generated_at)}.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Internal target" value={`${metrics.target_days} days`} />
        <StatCard label="Baseline" value={`${metrics.baseline_working_days} working days`} />
        <StatCard label="Past target" value={`${pastTarget.length} / ${metrics.samples.length}`} />
        <StatCard label="Stage breaches" value={breachedStageCount} />
      </div>

      <section aria-labelledby="stage-metrics-heading" className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="stage-metrics-heading" className="text-lg font-semibold tracking-tight">
            Per-stage targets and breaches
          </h2>
          <p className="text-sm text-muted-foreground">
            Editing a stage SLA changes future measurement only; recorded durations are never
            rewritten.
          </p>
        </div>

        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Per-stage turnaround metrics</caption>
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Stage
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Measured
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Average
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Breaches
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  SLA (days)
                </th>
              </tr>
            </thead>
            <tbody>
              {stageRows.map((row) => (
                <tr key={row.slug} className="border-b border-border last:border-0">
                  <td className="px-4 py-3">
                    <StageBadge stage={row} />
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.measured}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {formatDurationHours(row.averageHours)}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.breached}</td>
                  <td className="px-4 py-3">
                    {row.stageId ? (
                      <SlaEditor
                        key={`${row.stageId}-${row.slaDays ?? "none"}`}
                        stageId={row.stageId}
                        stageName={row.name}
                        slaDays={row.slaDays}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground">No data yet</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="vendor-metrics-heading" className="flex flex-col gap-3">
        <h2 id="vendor-metrics-heading" className="text-lg font-semibold tracking-tight">
          External vendors
        </h2>
        {metrics.vendors.length === 0 ? (
          <p className="text-sm text-muted-foreground">No vendors configured.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">External-vendor turnaround</caption>
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Vendor
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    TAT (days)
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Anchor
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Assigned
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Breached
                  </th>
                </tr>
              </thead>
              <tbody>
                {metrics.vendors.map((vendor) => (
                  <tr key={vendor.vendor_id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium">{vendor.name}</td>
                    <td className="px-4 py-3 tabular-nums">{vendor.tat_days}</td>
                    <td className="px-4 py-3">{sentenceCase(vendor.tat_anchor)}</td>
                    <td className="px-4 py-3 tabular-nums">{vendor.assigned_samples}</td>
                    <td className="px-4 py-3 tabular-nums">{vendor.breached_samples}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section aria-labelledby="breached-samples-heading" className="flex flex-col gap-3">
        <h2 id="breached-samples-heading" className="text-lg font-semibold tracking-tight">
          Past the 18-day target
        </h2>
        {pastTarget.length === 0 ? (
          <p className="text-sm text-muted-foreground">No samples are past the internal target.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Samples past the internal target</caption>
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Case
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Stage
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Calendar days
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Working days
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Vendor
                  </th>
                </tr>
              </thead>
              <tbody>
                {pastTarget.map((sample) => (
                  <tr key={sample.sample_id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium">{sample.case_id}</td>
                    <td className="px-4 py-3">
                      <StageBadge stage={sample.current_stage} />
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {sample.elapsed_calendar_days.toFixed(1)}
                    </td>
                    <td className="px-4 py-3 tabular-nums">{sample.elapsed_working_days}</td>
                    <td className="px-4 py-3">{sample.vendor?.name ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
