"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useCreateRun, useRecordRunSample } from "@/lib/features/runs/queries";
import type { Run } from "@/lib/features/runs/queries";
import { useSamples } from "@/lib/features/samples/queries";
import { useVendors } from "@/lib/features/vendors/queries";
import { sentenceCase } from "@/lib/i18n/dir";

interface SampleRow {
  linkedSampleId: string;
  ngsSampleId: string;
  sampleType: "G" | "R";
  coverageTargetX: string;
  vendorId: string;
}

const EMPTY_ROW: SampleRow = {
  linkedSampleId: "",
  ngsSampleId: "",
  sampleType: "G",
  coverageTargetX: "",
  vendorId: "",
};

interface Props {
  onCreated?: (run: Run) => void;
}

/** Molecular intake (US1): create the run, then link each added sample to an
 * already-registered workflow Sample (D4) via POST /runs/{run_id}/samples. */
export function RunIntakeForm({ onCreated }: Props) {
  const [runFolder, setRunFolder] = useState("");
  const [instrument, setInstrument] = useState("");
  const [project, setProject] = useState("");
  const [runSide, setRunSide] = useState("");
  const [runDate, setRunDate] = useState("");
  const [storageLocation, setStorageLocation] = useState("");
  const [rows, setRows] = useState<SampleRow[]>([EMPTY_ROW]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const samplesQuery = useSamples();
  const vendorsQuery = useVendors();
  const createRun = useCreateRun();
  const recordRunSample = useRecordRunSample();
  const pending = createRun.isPending;

  const samples = samplesQuery.data?.items ?? [];
  const vendors = vendorsQuery.data ?? [];

  function updateRow(index: number, patch: Partial<SampleRow>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const folder = runFolder.trim();
    if (!folder) {
      setError("Enter the run folder name.");
      return;
    }
    const inst = instrument.trim();
    if (!inst) {
      setError("Enter the instrument identifier.");
      return;
    }
    if (!rows.some((row) => row.linkedSampleId && row.ngsSampleId.trim())) {
      setError("Add at least one sample to the run.");
      return;
    }

    createRun.mutate(
      {
        run_folder: folder,
        instrument: inst,
        project: project.trim() || undefined,
        run_side: runSide.trim() || undefined,
        run_date: runDate || undefined,
        storage_location: storageLocation.trim() || undefined,
      },
      {
        onSuccess: (run) => {
          setRunFolder("");
          setInstrument("");
          setProject("");
          setRunSide("");
          setRunDate("");
          setStorageLocation("");
          setRows([EMPTY_ROW]);
          setSuccess(`Run ${run.run_folder} recorded.`);
          onCreated?.(run);

          for (const row of rows) {
            if (!row.linkedSampleId || !row.ngsSampleId.trim()) {
              continue;
            }
            const targetX = row.coverageTargetX.trim();
            recordRunSample.mutate(
              {
                runId: run.id,
                body: {
                  sample_id: row.linkedSampleId,
                  ngs_sample_id: row.ngsSampleId.trim(),
                  sample_type: row.sampleType,
                  coverage_target_x: targetX ? Number(targetX) : undefined,
                  vendor_id: row.vendorId || undefined,
                },
              },
              {
                onError: (mutationError) =>
                  setError(
                    mutationError instanceof ApiError
                      ? mutationError.detail
                      : "Could not link the sample to the run.",
                  ),
              },
            );
          }
        },
        onError: (mutationError) =>
          setError(
            mutationError instanceof ApiError
              ? mutationError.detail
              : "Could not record the run. Please try again.",
          ),
      },
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex max-w-2xl flex-col gap-4 rounded-lg border border-border bg-card p-4"
    >
      <h2 className="text-lg font-semibold tracking-tight">Record a sequencing run</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="run_folder" className="text-sm font-medium">
            Run folder
          </label>
          <input
            id="run_folder"
            name="run_folder"
            value={runFolder}
            onChange={(event) => setRunFolder(event.target.value)}
            placeholder="20261118_AV242301_181126_AMJ_A1_WGS"
            required
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="instrument" className="text-sm font-medium">
            Instrument
          </label>
          <input
            id="instrument"
            name="instrument"
            value={instrument}
            onChange={(event) => setInstrument(event.target.value)}
            required
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="project" className="text-sm font-medium">
            Project
          </label>
          <input
            id="project"
            name="project"
            value={project}
            onChange={(event) => setProject(event.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="run_side" className="text-sm font-medium">
            Run side
          </label>
          <input
            id="run_side"
            name="run_side"
            value={runSide}
            onChange={(event) => setRunSide(event.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="run_date" className="text-sm font-medium">
            Run date
          </label>
          <input
            id="run_date"
            name="run_date"
            type="date"
            value={runDate}
            onChange={(event) => setRunDate(event.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="storage_location" className="text-sm font-medium">
            Storage location
          </label>
          <input
            id="storage_location"
            name="storage_location"
            value={storageLocation}
            onChange={(event) => setStorageLocation(event.target.value)}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      <fieldset className="flex flex-col gap-3">
        <legend className="text-sm font-medium">Samples this run will produce</legend>
        {rows.map((row, index) => (
          <div key={index} className="grid gap-4 sm:grid-cols-5">
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`linked_sample_${index}`} className="text-xs font-medium text-muted-foreground">
                Linked Sample
              </label>
              <select
                id={`linked_sample_${index}`}
                value={row.linkedSampleId}
                onChange={(event) => updateRow(index, { linkedSampleId: event.target.value })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                <option value="">Select a registered Sample…</option>
                {samples.map((sample) => (
                  <option key={sample.id} value={sample.id}>
                    {sentenceCase(sample.case_id)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`ngs_sample_id_${index}`} className="text-xs font-medium text-muted-foreground">
                NGS sample ID
              </label>
              <input
                id={`ngs_sample_id_${index}`}
                value={row.ngsSampleId}
                onChange={(event) => updateRow(index, { ngsSampleId: event.target.value })}
                placeholder="G-12345"
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`sample_type_${index}`} className="text-xs font-medium text-muted-foreground">
                Sample type
              </label>
              <select
                id={`sample_type_${index}`}
                value={row.sampleType}
                onChange={(event) =>
                  updateRow(index, { sampleType: event.target.value as SampleRow["sampleType"] })
                }
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                <option value="G">Clinical (G)</option>
                <option value="R">Lifestyle (R)</option>
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`coverage_target_${index}`} className="text-xs font-medium text-muted-foreground">
                Coverage target (×)
              </label>
              <input
                id={`coverage_target_${index}`}
                type="number"
                min={1}
                step={1}
                placeholder={row.sampleType === "G" ? "30" : "15"}
                value={row.coverageTargetX}
                onChange={(event) => updateRow(index, { coverageTargetX: event.target.value })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm tabular-nums"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={`vendor_${index}`} className="text-xs font-medium text-muted-foreground">
                Vendor
              </label>
              <select
                id={`vendor_${index}`}
                value={row.vendorId}
                onChange={(event) => updateRow(index, { vendorId: event.target.value })}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
              >
                <option value="">Optional…</option>
                {vendors.map((vendor) => (
                  <option key={vendor.id} value={vendor.id}>
                    {vendor.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ))}
        <div>
          <button
            type="button"
            onClick={() => setRows((current) => [...current, EMPTY_ROW])}
            className="rounded-md border border-input px-2 py-1 text-xs hover:bg-secondary"
          >
            Add sample
          </button>
        </div>
      </fieldset>

      <GateError detail={error} />
      {success ? (
        <p
          role="status"
          className="rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-success"
        >
          {success}
        </p>
      ) : null}

      <SubmitButton pending={pending} pendingLabel="Recording…">
        Record run
      </SubmitButton>
    </form>
  );
}
