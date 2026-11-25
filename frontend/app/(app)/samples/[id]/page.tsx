"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { AdvanceAction } from "@/components/AdvanceAction";
import { ConsentChecklist } from "@/components/ConsentChecklist";
import { CoveragePanel, coverageGateReason } from "@/components/CoveragePanel";
import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { PipelineTimeline } from "@/components/PipelineTimeline";
import { StageBadge } from "@/components/StageBadge";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useSample, useSampleEvents } from "@/lib/features/samples/queries";
import { useSampleCoverage, useSamplePipelineResults } from "@/lib/features/pipeline/queries";
import { formatDateTime, formatDurationHours } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";

export default function SampleDetailPage() {
  const params = useParams<{ id: string }>();
  const sampleId = params?.id ?? "";
  const { can } = useAuth();

  const sampleQuery = useSample(sampleId);
  const eventsQuery = useSampleEvents(sampleId);

  const sample = sampleQuery.data;
  const coverageQuery = useSampleCoverage(sample?.id ?? "");
  const resultsQuery = useSamplePipelineResults(sample?.id ?? "");

  const results = resultsQuery.data ?? [];
  const hasConversion = results.some((result) => result.kind === "conversion" && result.status === "ok");

  if (sampleQuery.isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading sample…
      </p>
    );
  }

  if (sampleQuery.isError) {
    const notFound = sampleQuery.error instanceof ApiError && sampleQuery.error.status === 404;
    if (notFound) {
      return (
        <EmptyState
          title="Sample not found"
          description="It may have been removed or you may not have access to it."
          action={
            <Link href="/samples" className="text-sm text-brand hover:underline">
              Back to samples
            </Link>
          }
        />
      );
    }
    return (
      <GateError
        detail={
          sampleQuery.error instanceof ApiError
            ? sampleQuery.error.detail
            : "Could not load the sample. Please try again."
        }
      />
    );
  }

  if (!sample) {
    return null;
  }

  const events = eventsQuery.data ?? [];

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Link href="/samples" className="text-sm text-brand hover:underline">
          Samples
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{sample.case_id}</h1>
          <StageBadge stage={sample.current_stage} />
          <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground">
            {sentenceCase(sample.status)}
          </span>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Received</dt>
            <dd>{formatDateTime(sample.received_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              External reference
            </dt>
            <dd>{sample.external_ref || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Current stage</dt>
            <dd>{sentenceCase(sample.current_stage.name)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Status</dt>
            <dd>{sentenceCase(sample.status)}</dd>
          </div>
        </dl>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section
          aria-labelledby="history-heading"
          className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <h2 id="history-heading" className="text-lg font-semibold tracking-tight">
            Stage history
          </h2>

          {eventsQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading history…</p>
          ) : eventsQuery.isError ? (
            <GateError
              detail={
                eventsQuery.error instanceof ApiError
                  ? eventsQuery.error.detail
                  : "Could not load the stage history."
              }
            />
          ) : events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No stage history recorded.</p>
          ) : (
            <ol className="flex flex-col gap-4">
              {events.map((event, index) => {
                const isCurrent =
                  index === events.length - 1 &&
                  event.stage.position === sample.current_stage.position;
                return (
                  <li key={event.id} className="flex flex-col gap-1 border-s-2 border-border ps-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <StageBadge stage={event.stage} />
                      {isCurrent ? (
                        <span className="text-xs font-medium text-brand">Current stage</span>
                      ) : null}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Entered {formatDateTime(event.entered_at)} · Time in stage{" "}
                      {formatDurationHours(event.duration_hours)}
                    </p>
                    {event.note ? <p className="text-sm">{event.note}</p> : null}
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        <div className="flex flex-col gap-4">
          <section
            aria-labelledby="advance-heading"
            className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
          >
            <h2 id="advance-heading" className="text-lg font-semibold tracking-tight">
              Advance
            </h2>
          <AdvanceAction
            sampleId={sample.id}
            fromStage={sample.current_stage.position}
            status={sample.status}
          />
        </section>

        <CoveragePanel
          latest={coverageQuery.data?.[0] ?? null}
          history={coverageQuery.data ?? []}
          gateReason={coverageGateReason({
            latest: coverageQuery.data?.[0] ?? null,
            hasConversion,
          })}
        />

        <PipelineTimeline results={results} />

        <ConsentChecklist sampleId={sample.id} canEdit={can("genomics")} />
        </div>
      </div>
    </section>
  );
}
