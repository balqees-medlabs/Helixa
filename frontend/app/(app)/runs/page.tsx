"use client";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { RunIntakeForm } from "@/components/RunIntakeForm";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useRuns } from "@/lib/features/runs/queries";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

export default function RunsPage() {
  const { can, isLoading } = useAuth();
  const isMolecular = can("molecular");
  const runsQuery = useRuns();
  const runs = runsQuery.data ?? [];

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="text-sm text-muted-foreground">
          Sequencing runs recorded in Helixa and the samples they will produce. Molecular records
          runs here; the spreadsheet is no longer needed.
        </p>
      </div>

      {runsQuery.isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading runs…
        </p>
      ) : runsQuery.isError ? (
        <GateError
          detail={
            runsQuery.error instanceof ApiError
              ? runsQuery.error.detail
              : "Could not load runs. Please try again."
          }
        />
      ) : runs.length === 0 ? (
        <EmptyState
          title="No runs yet"
          description={
            isMolecular
              ? "Record the first sequencing run with its samples."
              : "The Molecular team records runs from the sequencing host."
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-card">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Sequencing runs</caption>
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Run folder
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Instrument
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Readiness
                </th>
                <th scope="col" className="px-4 py-2 text-start font-medium">
                  Cycles
                </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id} className="border-b border-border last:border-0">
                  <td className="px-4 py-3 font-medium">{run.run_folder}</td>
                  <td className="px-4 py-3">{run.instrument}</td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        run.readiness === "ready"
                          ? "bg-success/10 text-success"
                          : run.readiness === "received"
                            ? "bg-secondary text-secondary-foreground"
                            : "bg-destructive/10 text-destructive",
                      )}
                    >
                      {sentenceCase(run.readiness)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {[run.cycle_r1, run.cycle_r2, run.cycle_i1, run.cycle_i2]
                      .filter((value) => value != null)
                      .join(" / ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {isMolecular ? <RunIntakeForm /> : null}
    </section>
  );
}
