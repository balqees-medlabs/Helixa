"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBadge } from "@/components/StageBadge";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useRecordQc } from "@/lib/features/qc/queries";
import type { QcCreate } from "@/lib/features/qc/queries";
import { useSamples } from "@/lib/features/samples/queries";
import { sentenceCase } from "@/lib/i18n/dir";

type QcKind = QcCreate["kind"];

const KINDS: Array<{ value: QcKind; label: string }> = [
  { value: "data_generation", label: "Data generation" },
  { value: "qc", label: "Quality control" },
];

export default function QcPage() {
  const { can, isLoading } = useAuth();
  const canRecord = can("bioinformatics");

  const samplesQuery = useSamples(200, 0);
  const recordQc = useRecordQc();

  const [sampleId, setSampleId] = useState("");
  const [kind, setKind] = useState<QcKind>("qc");
  const [passed, setPassed] = useState(true);
  const [detailText, setDetailText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const samples = samplesQuery.data?.items ?? [];

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  if (!canRecord) {
    return (
      <section className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">QC / data generation</h1>
        <EmptyState
          title="QC entry is not available to your role"
          description="Data-generation and quality-control outcomes are recorded by bioinformatics and administrators."
        />
      </section>
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (!sampleId) {
      setError("Select a sample.");
      return;
    }

    let detail: Record<string, unknown> = {};
    if (detailText.trim()) {
      try {
        const parsed: unknown = JSON.parse(detailText);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          setError('Detail must be a JSON object, for example {"note":"passed"}.');
          return;
        }
        detail = parsed as Record<string, unknown>;
      } catch {
        setError("Detail is not valid JSON. Leave it blank or enter a JSON object.");
        return;
      }
    }

    const sample = samples.find((entry) => entry.id === sampleId);
    recordQc.mutate(
      { sampleId, body: { kind, passed, detail } },
      {
        onSuccess: () => {
          const outcome = passed ? "passed" : "failed";
          const kindLabel = kind === "qc" ? "Quality control" : "Data generation";
          setSuccess(
            `${kindLabel} ${outcome} recorded for ${sample?.case_id ?? "the sample"}.` +
              (kind === "qc" && passed
                ? " The report/archive gate is now open."
                : kind === "qc"
                  ? " The report/archive gate stays closed."
                  : ""),
          );
          setDetailText("");
        },
        onError: (mutationError) => {
          setError(
            mutationError instanceof ApiError
              ? mutationError.detail
              : "Could not record the outcome. Please try again.",
          );
        },
      },
    );
  }

  return (
    <section className="flex max-w-2xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">QC / data generation</h1>
        <p className="text-sm text-muted-foreground">
          Record a data-generation or quality-control outcome for a sample. A passing
          quality-control result opens the report/archive gate; a failing one keeps it closed.
        </p>
      </div>

      {samplesQuery.isLoading ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading samples…
        </p>
      ) : samplesQuery.isError ? (
        <GateError
          detail={
            samplesQuery.error instanceof ApiError
              ? samplesQuery.error.detail
              : "Could not load samples. Please try again."
          }
        />
      ) : samples.length === 0 ? (
        <EmptyState
          title="No samples to record against"
          description="Register a sample before recording a QC or data-generation outcome."
        />
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="qc_sample" className="text-sm font-medium">
              Sample
            </label>
            <select
              id="qc_sample"
              name="qc_sample"
              value={sampleId}
              onChange={(event) => setSampleId(event.target.value)}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            >
              <option value="">Select a sample…</option>
              {samples.map((sample) => (
                <option key={sample.id} value={sample.id}>
                  {sample.case_id} — {sentenceCase(sample.current_stage.name)}
                </option>
              ))}
            </select>
            {sampleId ? (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                Current stage:
                <StageBadge
                  stage={
                    samples.find((sample) => sample.id === sampleId)?.current_stage ?? {
                      position: 1,
                      name: "sample received",
                    }
                  }
                />
              </p>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="qc_kind" className="text-sm font-medium">
                Kind
              </label>
              <select
                id="qc_kind"
                name="qc_kind"
                value={kind}
                onChange={(event) => setKind(event.target.value as QcKind)}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                {KINDS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="qc_outcome" className="text-sm font-medium">
                Outcome
              </label>
              <select
                id="qc_outcome"
                name="qc_outcome"
                value={passed ? "passed" : "failed"}
                onChange={(event) => setPassed(event.target.value === "passed")}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                <option value="passed">Passed</option>
                <option value="failed">Failed</option>
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="qc_detail" className="text-sm font-medium">
              Detail (JSON object, optional)
            </label>
            <textarea
              id="qc_detail"
              name="qc_detail"
              rows={4}
              value={detailText}
              onChange={(event) => setDetailText(event.target.value)}
              placeholder={'{"note": "Q30 above threshold"}'}
              className="rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm"
            />
          </div>

          <GateError detail={error} />
          {success ? (
            <p
              role="status"
              className="rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success"
            >
              {success}
            </p>
          ) : null}

          <div className="flex items-center gap-3">
            <SubmitButton
              pending={recordQc.isPending}
              pendingLabel="Recording…"
              disabled={!sampleId}
            >
              Record outcome
            </SubmitButton>
          </div>
        </form>
      )}
    </section>
  );
}
