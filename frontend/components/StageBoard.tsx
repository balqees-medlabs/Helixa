"use client";

import Link from "next/link";

import { AdvanceAction } from "@/components/AdvanceAction";
import type { SampleTat, TatMetrics } from "@/lib/features/dashboard/queries";
import type { Sample } from "@/lib/features/samples/queries";
import { formatDateTime, formatDurationHours } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import { STAGES, elapsedCalendarDays, isPastTarget } from "@/lib/workflow/stages";
import { cn } from "@/lib/utils";

interface StageBoardProps {
  samples: readonly Sample[];
  metrics?: TatMetrics;
  stageTimingsVisible: boolean;
}

function BoardCard({
  sample,
  tat,
  stageTimingsVisible,
}: {
  sample: Sample;
  tat?: SampleTat;
  stageTimingsVisible: boolean;
}) {
  const currentStage = tat?.stages[tat.stages.length - 1];
  const openDays = tat?.elapsed_calendar_days ?? elapsedCalendarDays(sample.received_at);
  const breached = tat ? tat.target_breached : isPastTarget(sample.received_at);

  return (
    <article
      aria-label={`${sample.case_id} card`}
      className={cn(
        "flex flex-col gap-2 rounded-md border bg-background p-3 text-sm shadow-sm",
        breached ? "border-destructive/40" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link href={`/samples/${sample.id}`} className="font-medium text-brand hover:underline">
          {sample.case_id}
        </Link>
        {breached ? (
          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">
            Past target
          </span>
        ) : null}
      </div>

      <p className="text-xs text-muted-foreground">
        {stageTimingsVisible ? (
          <>In stage {formatDurationHours(currentStage?.duration_hours ?? null)}</>
        ) : (
          <>Open {openDays.toFixed(1)} d</>
        )}
        {" · "}
        Received {formatDateTime(sample.received_at)}
      </p>

      {sample.status !== "active" ? (
        <span className="w-fit rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
          {sentenceCase(sample.status)}
        </span>
      ) : (
        <AdvanceAction
          sampleId={sample.id}
          fromStage={sample.current_stage.position}
          status={sample.status}
          compact
        />
      )}
    </article>
  );
}

export function StageBoard({ samples, metrics, stageTimingsVisible }: StageBoardProps) {
  const tatBySample = new Map((metrics?.samples ?? []).map((tat) => [tat.sample_id, tat]));

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {STAGES.map((stage) => {
        const cards = samples.filter((sample) => sample.current_stage.position === stage.position);
        const label = sentenceCase(stage.name);

        return (
          <section
            key={stage.slug}
            aria-label={`${label} column`}
            className="flex w-64 shrink-0 flex-col gap-3 rounded-lg border border-border bg-card p-3"
          >
            <header className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold tracking-tight">{label}</h2>
              <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium tabular-nums text-secondary-foreground">
                {cards.length}
              </span>
            </header>

            {cards.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-2 py-4 text-center text-xs text-muted-foreground">
                No samples
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {cards.map((sample) => (
                  <BoardCard
                    key={sample.id}
                    sample={sample}
                    tat={tatBySample.get(sample.id)}
                    stageTimingsVisible={stageTimingsVisible}
                  />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
