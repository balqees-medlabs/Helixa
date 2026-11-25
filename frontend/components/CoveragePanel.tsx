"use client";

import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import type { Coverage } from "@/lib/features/pipeline/queries";

interface Props {
  latest: Coverage | null;
  history: Coverage[];
  gateReason: string;
}

export function coverageGateReason(options: {
  latest: Coverage | null;
  hasConversion: boolean;
}): string {
  const latest = options.latest;
  if (!latest) {
    return "No coverage recorded yet.";
  }
  if (latest.verdict === "pass") {
    return options.hasConversion
      ? "Stage 7 satisfied — the sample can advance once at Stage 6."
      : "Stage 7 waiting for FASTQ conversion.";
  }
  return `Stage 7 blocked — coverage below target (${latest.depth_x.toFixed(1)} < ${latest.target_x}).`;
}

function VerdictBadge({ verdict }: { verdict: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        verdict === "pass"
          ? "bg-success/10 text-success"
          : "bg-destructive/10 text-destructive"
      }`}
    >
      {sentenceCase(verdict)}
    </span>
  );
}

export function CoveragePanel({ latest, history, gateReason }: Props) {
  return (
    <section
      aria-labelledby="coverage-heading"
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
    >
      <h2 id="coverage-heading" className="text-lg font-semibold tracking-tight">
        Coverage (QC)
      </h2>

      {latest ? (
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Depth
            </dt>
            <dd className="font-medium">
              {latest.depth_x}x <span className="text-muted-foreground">target {latest.target_x}×</span>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Verdict
            </dt>
            <dd>
              <VerdictBadge verdict={latest.verdict} />
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Read pairs
            </dt>
            <dd className="tabular-nums">{latest.read_pairs}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Yield
            </dt>
            <dd className="tabular-nums">{latest.yield_gb} GB</dd>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-muted-foreground">No coverage recorded yet.</p>
      )}

      <p role="status" className="text-sm text-muted-foreground">
        Gate: {gateReason}
      </p>

      {history.length > 0 ? (
        <ol className="flex flex-col gap-2">
          {history.slice(0, 10).map((row) => (
            <li key={row.id} className="flex items-center gap-3 text-sm">
              <VerdictBadge verdict={row.verdict} />
              <span className="text-xs text-muted-foreground">
                Depth {row.depth_x}x · {row.read_pairs} read pairs · {formatDateTime(row.reported_at)}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
