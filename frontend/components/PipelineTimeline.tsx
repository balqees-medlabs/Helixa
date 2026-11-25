"use client";

import { sentenceCase } from "@/lib/i18n/dir";
import { formatDateTime } from "@/lib/format";
import type { PipelineResult } from "@/lib/features/pipeline/queries";

interface Props {
  results: PipelineResult[];
}

function resultSummary(result: PipelineResult): string {
  if (result.kind === "conversion") {
    const parts: string[] = [];
    if (result.read_length != null) {
      parts.push(`read length ${result.read_length}`);
    }
    if (result.q30 != null) {
      parts.push(`Q30 ${result.q30}`);
    }
    if (result.reads_assigned_pct != null) {
      parts.push(`reads ${result.reads_assigned_pct}%`);
    }
    return parts.join(" · ");
  }
  if (result.kind === "augmentation") {
    const runs = result.source_run_ids?.length ?? 0;
    return runs ? `merged ${runs} run(s)` : "merge result recorded";
  }
  return "";
}

export function PipelineTimeline({ results }: Props) {
  return (
    <section
      aria-labelledby="timeline-heading"
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
    >
      <h2 id="timeline-heading" className="text-lg font-semibold tracking-tight">
        Pipeline timeline
      </h2>

      {results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No pipeline results recorded yet.</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {results.slice(0, 20).map((result) => (
            <li key={result.id} className="flex flex-col gap-1 border-s-2 border-border ps-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">{sentenceCase(result.kind)}</span>
                <span className="text-xs text-muted-foreground">
                  {sentenceCase(result.status)}
                </span>
              </div>
              {resultSummary(result) ? (
                <p className="text-xs text-muted-foreground">{resultSummary(result)}</p>
              ) : null}
              <p className="text-xs text-muted-foreground">
                Reported {formatDateTime(result.reported_at)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
