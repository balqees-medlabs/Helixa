"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBadge } from "@/components/StageBadge";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import {
  useAddBatchMembers,
  useAdvanceBatch,
  useCreateBatch,
} from "@/lib/features/batches/queries";
import type { Batch, MemberAdvanceResult } from "@/lib/features/batches/queries";
import { useSamples } from "@/lib/features/samples/queries";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

const RESULT_LABELS: Record<string, string> = {
  advanced: "Advanced",
  conflict: "Conflict",
  gate_failed: "Gate failed",
  forbidden: "Forbidden",
  not_found: "Not found",
};

function errorDetail(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.detail : fallback;
}

function ResultBadge({ status }: { status: string }) {
  const advanced = status === "advanced";
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium",
        advanced ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive",
      )}
    >
      {RESULT_LABELS[status] ?? sentenceCase(status)}
    </span>
  );
}

export default function BatchesPage() {
  const { can, isLoading } = useAuth();
  const canBatch = can("genomics", "bioinformatics");

  const samplesQuery = useSamples(200, 0);
  const createBatch = useCreateBatch();
  const addMembers = useAddBatchMembers();
  const advanceBatch = useAdvanceBatch();

  const [batch, setBatch] = useState<Batch | null>(null);
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<MemberAdvanceResult[] | null>(null);

  const samples = samplesQuery.data?.items ?? [];
  const sampleById = new Map(samples.map((sample) => [sample.id, sample]));
  const members = (batch?.member_ids ?? [])
    .map((id) => sampleById.get(id))
    .filter((sample): sample is (typeof samples)[number] => Boolean(sample));
  const available = samples.filter(
    (sample) => sample.status === "active" && !batch?.member_ids.includes(sample.id),
  );

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  if (!canBatch) {
    return (
      <section className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Batches</h1>
        <EmptyState
          title="Batches are not available to your role"
          description="Batch grouping is limited to genomics, bioinformatics and administrators."
        />
      </section>
    );
  }

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Enter a batch name.");
      return;
    }

    createBatch.mutate(trimmed, {
      onSuccess: (created) => {
        setBatch(created);
        setName("");
        setResults(null);
      },
      onError: (mutationError) =>
        setError(errorDetail(mutationError, "Could not create the batch. Please try again.")),
    });
  }

  function toggleSample(sampleId: string, checked: boolean) {
    setSelected((current) =>
      checked ? [...new Set([...current, sampleId])] : current.filter((id) => id !== sampleId),
    );
  }

  function handleAddMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!batch) {
      return;
    }
    if (selected.length === 0) {
      setError("Select at least one sample to add.");
      return;
    }

    addMembers.mutate(
      { batchId: batch.id, sampleIds: selected },
      {
        onSuccess: (updated) => {
          setBatch(updated);
          setSelected([]);
        },
        onError: (mutationError) =>
          setError(errorDetail(mutationError, "Could not add the members. Please try again.")),
      },
    );
  }

  function handleAdvance() {
    if (!batch) {
      return;
    }
    setError(null);
    advanceBatch.mutate(
      { batchId: batch.id, body: {} },
      {
        onSuccess: (outcome) => setResults(outcome),
        onError: (mutationError) =>
          setError(errorDetail(mutationError, "Could not advance the batch. Please try again.")),
      },
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Batches</h1>
        <p className="text-sm text-muted-foreground">
          Group samples and advance them together. Each member is checked against its own gates, and
          a failing member never blocks the others.
        </p>
      </div>

      {!batch ? (
        <form
          onSubmit={handleCreate}
          className="flex max-w-xl flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="batch_name" className="text-sm font-medium">
              Batch name
            </label>
            <input
              id="batch_name"
              name="batch_name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            />
          </div>
          <div className="flex items-center gap-3">
            <SubmitButton pending={createBatch.isPending} pendingLabel="Creating…">
              Create batch
            </SubmitButton>
          </div>
        </form>
      ) : (
        <div className="flex flex-col gap-6">
          <section
            aria-labelledby="batch-members-heading"
            className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="batch-members-heading" className="text-lg font-semibold tracking-tight">
                {batch.name}
              </h2>
              <h3 className="text-sm text-muted-foreground">Members ({batch.member_ids.length})</h3>
            </div>

            {members.length === 0 ? (
              <p className="text-sm text-muted-foreground">No members yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {members.map((sample) => (
                  <li key={sample.id} className="flex flex-wrap items-center gap-2 text-sm">
                    <Link
                      href={`/samples/${sample.id}`}
                      className="font-medium text-brand hover:underline"
                    >
                      {sample.case_id}
                    </Link>
                    <StageBadge stage={sample.current_stage} />
                  </li>
                ))}
              </ul>
            )}

            <form onSubmit={handleAddMembers} className="flex flex-col gap-3">
              <fieldset className="flex flex-col gap-2">
                <legend className="text-sm font-medium">Add samples</legend>
                {samplesQuery.isLoading ? (
                  <p className="text-sm text-muted-foreground">Loading samples…</p>
                ) : available.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Every active sample is already a member.
                  </p>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {available.map((sample) => (
                      <label
                        key={sample.id}
                        className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm"
                      >
                        <input
                          type="checkbox"
                          aria-label={sample.case_id}
                          checked={selected.includes(sample.id)}
                          onChange={(event) => toggleSample(sample.id, event.target.checked)}
                        />
                        <span className="font-medium">{sample.case_id}</span>
                        <span className="text-xs text-muted-foreground">
                          {sentenceCase(sample.current_stage.name)}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>

              <div className="flex flex-wrap items-center gap-3">
                <SubmitButton
                  pending={addMembers.isPending}
                  pendingLabel="Adding…"
                  variant="outline"
                  disabled={available.length === 0}
                >
                  Add members
                </SubmitButton>
                <SubmitButton
                  type="button"
                  pending={advanceBatch.isPending}
                  pendingLabel="Advancing…"
                  onClick={handleAdvance}
                  disabled={batch.member_ids.length === 0}
                >
                  Advance batch
                </SubmitButton>
              </div>
            </form>
          </section>

          {results ? (
            <section
              aria-label="Batch advance results"
              className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
            >
              <h2 className="text-lg font-semibold tracking-tight">Advance results</h2>
              <ul className="flex flex-col gap-2">
                {results.map((result) => {
                  const sample = sampleById.get(result.sample_id);
                  return (
                    <li
                      key={result.sample_id}
                      className="flex flex-col gap-1 rounded-md border border-border px-3 py-2 text-sm"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium">{sample?.case_id ?? result.sample_id}</span>
                        <ResultBadge status={result.status} />
                      </div>
                      {result.detail ? (
                        <p className="text-xs text-destructive">{result.detail}</p>
                      ) : result.to_stage != null ? (
                        <p className="text-xs text-muted-foreground">
                          Moved from stage {result.from_stage ?? "—"} to stage {result.to_stage}.
                        </p>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}
        </div>
      )}

      <GateError detail={error} />
    </section>
  );
}
