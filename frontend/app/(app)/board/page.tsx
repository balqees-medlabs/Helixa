"use client";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBoard } from "@/components/StageBoard";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useBoardSamples, useTatMetrics } from "@/lib/features/dashboard/queries";
import { POLL_MS } from "@/lib/query/client";

export default function BoardPage() {
  const { can } = useAuth();
  const canSeeMetrics = can("admin");

  const samplesQuery = useBoardSamples({ refetchInterval: POLL_MS });
  const metricsQuery = useTatMetrics({
    enabled: canSeeMetrics,
    refetchInterval: POLL_MS,
  });

  const samples = samplesQuery.data?.items ?? [];

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">TAT board</h1>
        <p className="text-sm text-muted-foreground">
          Every sample across the 8 stages. Cards refresh automatically, and advance is gated by the
          backend just like the sample detail view.
        </p>
      </div>

      {samplesQuery.isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading the board…
        </p>
      ) : samplesQuery.isError ? (
        <GateError
          detail={
            samplesQuery.error instanceof ApiError
              ? samplesQuery.error.detail
              : "Could not load the board. Please try again."
          }
        />
      ) : samples.length === 0 ? (
        <EmptyState
          title="No samples on the board"
          description="Register a sample to see it move across the stages."
        />
      ) : (
        <>
          {canSeeMetrics && metricsQuery.isError ? (
            <GateError
              detail={
                metricsQuery.error instanceof ApiError
                  ? metricsQuery.error.detail
                  : "Stage timings are temporarily unavailable; showing the board without them."
              }
            />
          ) : null}
          {!canSeeMetrics ? (
            <p className="rounded-md border border-border bg-card px-3 py-2 text-xs text-muted-foreground">
              Stage-level time and per-stage breach detail are available to administrators. Cards
              show overall time open and the 18-day target here.
            </p>
          ) : null}
          <StageBoard
            samples={samples}
            metrics={canSeeMetrics ? metricsQuery.data : undefined}
            stageTimingsVisible={canSeeMetrics && Boolean(metricsQuery.data)}
          />
        </>
      )}
    </section>
  );
}
