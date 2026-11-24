"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { GateError } from "@/components/GateError";
import { StageBadge } from "@/components/StageBadge";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useSamples } from "@/lib/features/samples/queries";
import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";

const PAGE_SIZE = 25;

export default function SamplesPage() {
  const { can } = useAuth();
  const [offset, setOffset] = useState(0);
  const samplesQuery = useSamples(PAGE_SIZE, offset);
  const canRegister = can("genomics");

  const page = samplesQuery.data;
  const items = page?.items ?? [];

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">Samples</h1>
          <p className="text-sm text-muted-foreground">
            Every registered sample and the stage it is currently in.
          </p>
        </div>
        {canRegister ? (
          <Link
            href="/samples/register"
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Register sample
          </Link>
        ) : null}
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
      ) : items.length === 0 ? (
        <EmptyState
          title="No samples yet"
          description="Register the first sample to start the workflow."
          action={
            canRegister ? (
              <Link
                href="/samples/register"
                className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                Register sample
              </Link>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border bg-card">
            <table className="w-full border-collapse text-sm">
              <caption className="sr-only">Registered samples</caption>
              <thead>
                <tr className="border-b border-border text-start text-xs uppercase tracking-wide text-muted-foreground">
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Case
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Stage
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2 text-start font-medium">
                    Received
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((sample) => (
                  <tr key={sample.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        href={`/samples/${sample.id}`}
                        className="font-medium text-brand hover:underline"
                      >
                        {sample.case_id}
                      </Link>
                      {sample.external_ref ? (
                        <span className="ms-2 text-xs text-muted-foreground">
                          {sample.external_ref}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <StageBadge stage={sample.current_stage} />
                    </td>
                    <td className="px-4 py-3">{sentenceCase(sample.status)}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDateTime(sample.received_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <p>
              Showing {offset + 1}–{offset + items.length} of {page?.total ?? items.length}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                className="rounded-md border border-input px-3 py-1.5 disabled:opacity-50"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Previous
              </button>
              <button
                type="button"
                className="rounded-md border border-input px-3 py-1.5 disabled:opacity-50"
                disabled={!page || offset + PAGE_SIZE >= page.total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
