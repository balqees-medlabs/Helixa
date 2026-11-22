"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { PortalPushStatus, PushStatusChip } from "@/components/PortalPushStatus";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { downloadReportFile, useReport, useUploadReport } from "@/lib/features/reports/queries";
import type { Report } from "@/lib/features/reports/queries";
import { useSamples } from "@/lib/features/samples/queries";
import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function uploadErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Could not upload the report. Please try again.";
  }
  if (error.status === 413) {
    return error.detail || "Report exceeds the size limit.";
  }
  if (error.status === 415) {
    return error.detail || "That report type is not supported.";
  }
  if (error.status === 409) {
    return error.detail || "Quality control must be passed before report upload.";
  }
  if (error.status === 422) {
    return error.detail || "The report file is not valid.";
  }
  return error.detail;
}

function reportErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Could not load the report. Please try again.";
  }
  if (error.status === 404) {
    return "Report not found.";
  }
  if (error.status === 403) {
    return "You are not permitted to view this report.";
  }
  return error.detail;
}

export default function ReportsPage() {
  const { can, isLoading } = useAuth();
  const canRead = can("admin", "bioinformatics", "genomics");
  const canUpload = can("bioinformatics");
  const isAdmin = can("admin");

  const samplesQuery = useSamples(200, 0);
  const upload = useUploadReport();

  const [sampleId, setSampleId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<Report[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [lookup, setLookup] = useState("");
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const reportQuery = useReport(selectedId);
  const samples = samplesQuery.data?.items ?? [];
  const sampleById = new Map(samples.map((sample) => [sample.id, sample]));
  const selectedReport =
    reportQuery.data ?? uploaded.find((report) => report.id === selectedId) ?? null;

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  if (!canRead) {
    return (
      <section className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <EmptyState
          title="Reports are not available to your role"
          description="Report retrieval is limited to administrators, bioinformatics and genomics."
        />
      </section>
    );
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUploadError(null);
    if (!sampleId) {
      setUploadError("Select a sample.");
      return;
    }
    if (!file) {
      setUploadError("Choose a PDF report to upload.");
      return;
    }

    upload.mutate(
      { sampleId, file },
      {
        onSuccess: (report) => {
          setUploaded((current) => [report, ...current.filter((entry) => entry.id !== report.id)]);
          setSelectedId(report.id);
          setFile(null);
          setFileInputKey((key) => key + 1);
        },
        onError: (error) => setUploadError(uploadErrorMessage(error)),
      },
    );
  }

  function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLookupError(null);
    const trimmed = lookup.trim();
    if (!trimmed) {
      setLookupError("Enter a report ID.");
      return;
    }
    setSelectedId(trimmed);
  }

  async function handleDownload(report: Report) {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadReportFile(report);
    } catch (error) {
      setDownloadError(
        error instanceof ApiError ? error.detail : "Could not download the report file.",
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Reports</h1>
        <p className="text-sm text-muted-foreground">
          Upload a QC-passed sample&apos;s PDF report, retrieve stored reports when permitted, and
          follow the push to the external portal.
        </p>
      </div>

      {canUpload ? (
        <form
          onSubmit={handleUpload}
          className="flex max-w-2xl flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <h2 className="text-lg font-semibold tracking-tight">Upload report</h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="report_sample" className="text-sm font-medium">
                Sample
              </label>
              <select
                id="report_sample"
                name="report_sample"
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
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="report_file" className="text-sm font-medium">
                Report file (PDF)
              </label>
              <input
                key={fileInputKey}
                id="report_file"
                name="report_file"
                type="file"
                onChange={handleFileChange}
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm file:me-3 file:rounded-sm file:border-0 file:bg-secondary file:px-2 file:py-1 file:text-xs"
              />
            </div>
          </div>

          <GateError detail={uploadError} />

          <div className="flex items-center gap-3">
            <SubmitButton
              pending={upload.isPending}
              pendingLabel="Uploading…"
              disabled={samples.length === 0}
            >
              Upload report
            </SubmitButton>
            <span className="text-xs text-muted-foreground">
              Only PDFs, and only once QC has passed.
            </span>
          </div>
        </form>
      ) : null}

      <form
        onSubmit={handleLookup}
        className="flex max-w-2xl flex-col gap-3 rounded-lg border border-border bg-card p-4"
      >
        <h2 className="text-lg font-semibold tracking-tight">Find a report</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-1 flex-col gap-1.5">
            <label htmlFor="report_id" className="text-sm font-medium">
              Report ID
            </label>
            <input
              id="report_id"
              name="report_id"
              value={lookup}
              onChange={(event) => setLookup(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="rounded-md border border-input bg-background px-3 py-1.5 font-mono text-sm"
            />
          </div>
          <SubmitButton variant="outline" pendingLabel="Loading…">
            Load report
          </SubmitButton>
        </div>
        <GateError detail={lookupError} />
        {reportQuery.isError ? <GateError detail={reportErrorMessage(reportQuery.error)} /> : null}
      </form>

      {uploaded.length > 0 ? (
        <section
          aria-labelledby="uploaded-reports-heading"
          className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4"
        >
          <h2 id="uploaded-reports-heading" className="text-lg font-semibold tracking-tight">
            Uploaded this session
          </h2>
          <ul className="flex flex-col gap-2">
            {uploaded.map((report) => (
              <li
                key={report.id}
                className="flex flex-wrap items-center justify-between gap-2 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {sampleById.get(report.sample_id)?.case_id ?? report.sample_id}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {formatBytes(report.size_bytes)} · {formatDateTime(report.uploaded_at)}
                  </span>
                  <PushStatusChip status={report.push_status} />
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedId(report.id)}
                  className="rounded-md border border-input px-2 py-1 text-xs hover:bg-secondary"
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {selectedReport ? (
        <section
          aria-label="Selected report"
          className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-lg font-semibold tracking-tight">
              Report {selectedReport.id.slice(0, 8)}
            </h2>
            <PushStatusChip status={selectedReport.push_status} />
          </div>

          <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Sample</dt>
              <dd>
                {sampleById.get(selectedReport.sample_id)?.case_id ?? selectedReport.sample_id}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Size</dt>
              <dd className="tabular-nums">{formatBytes(selectedReport.size_bytes)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">Uploaded</dt>
              <dd>{formatDateTime(selectedReport.uploaded_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Content type
              </dt>
              <dd>{selectedReport.content_type}</dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">SHA-256</dt>
              <dd className="break-all font-mono text-xs">{selectedReport.sha256}</dd>
            </div>
          </dl>

          <div className="flex flex-wrap items-center gap-3">
            <SubmitButton
              type="button"
              variant="outline"
              pending={downloading}
              pendingLabel="Downloading…"
              onClick={() => handleDownload(selectedReport)}
            >
              Download file
            </SubmitButton>
          </div>
          <GateError detail={downloadError} />

          {isAdmin && selectedReport.push_id ? (
            <PortalPushStatus pushId={selectedReport.push_id} />
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
