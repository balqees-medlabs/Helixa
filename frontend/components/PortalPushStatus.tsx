"use client";

import { useState } from "react";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { usePortalPush, useRetryPortalPush } from "@/lib/features/reports/queries";
import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

export function PushStatusChip({ status, className }: { status: string; className?: string }) {
  const tone =
    status === "success"
      ? "bg-success/10 text-success"
      : status === "failed"
        ? "bg-destructive/10 text-destructive"
        : "bg-secondary text-secondary-foreground";

  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", tone, className)}>
      {sentenceCase(status)}
    </span>
  );
}

export function PortalPushStatus({ pushId }: { pushId: string }) {
  const pushQuery = usePortalPush(pushId);
  const retry = useRetryPortalPush();
  const [error, setError] = useState<string | null>(null);

  function handleRetry() {
    setError(null);
    retry.mutate(pushId, {
      onError: (mutationError) =>
        setError(
          mutationError instanceof ApiError
            ? mutationError.detail
            : "Could not retry the portal push. Please try again.",
        ),
    });
  }

  if (pushQuery.isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading portal delivery…
      </p>
    );
  }

  if (pushQuery.isError || !pushQuery.data) {
    return (
      <GateError
        detail={
          pushQuery.error instanceof ApiError
            ? pushQuery.error.detail
            : "Could not load the portal delivery status."
        }
      />
    );
  }

  const push = pushQuery.data;
  const canRetry = push.status !== "success";

  return (
    <section
      aria-label="Portal delivery status"
      className="flex flex-col gap-3 rounded-md border border-border bg-background p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold tracking-tight">Portal delivery</h3>
        <PushStatusChip status={push.status} />
      </div>

      <dl className="grid gap-2 text-xs sm:grid-cols-3">
        <div>
          <dt className="uppercase tracking-wide text-muted-foreground">Attempts</dt>
          <dd className="tabular-nums">{push.attempts}</dd>
        </div>
        <div>
          <dt className="uppercase tracking-wide text-muted-foreground">Next attempt</dt>
          <dd>{formatDateTime(push.next_attempt_at)}</dd>
        </div>
        <div>
          <dt className="uppercase tracking-wide text-muted-foreground">Delivered</dt>
          <dd>{formatDateTime(push.delivered_at)}</dd>
        </div>
      </dl>

      {push.last_error ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs text-destructive">
          Last error: {push.last_error}
        </p>
      ) : null}

      {canRetry ? (
        <SubmitButton
          type="button"
          variant="outline"
          pending={retry.isPending}
          pendingLabel="Retrying…"
          onClick={handleRetry}
          className="w-fit px-2 py-1 text-xs"
        >
          Retry push
        </SubmitButton>
      ) : null}

      <GateError detail={error} className="px-2 py-1 text-xs" />
    </section>
  );
}
