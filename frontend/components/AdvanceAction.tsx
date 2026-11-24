"use client";

import { useState } from "react";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAdvanceSample } from "@/lib/features/samples/queries";

/**
 * Advance is offered on any active sample; the frontend deliberately does not
 * encode the stage→role map (research D4). A 403 is shown as not permitted and
 * a 409/422 as the backend's reason verbatim (FR-009, SC-003).
 */
export function AdvanceAction({
  sampleId,
  fromStage,
  status,
  compact = false,
}: {
  sampleId: string;
  fromStage: number;
  status: string;
  compact?: boolean;
}) {
  const advance = useAdvanceSample(sampleId);
  const [error, setError] = useState<string | null>(null);

  if (status !== "active") {
    return (
      <p className="text-sm text-muted-foreground">
        This sample is {status}; only active samples can advance.
      </p>
    );
  }

  function handleAdvance() {
    setError(null);
    advance.mutate(fromStage, {
      onError: (mutationError) => {
        if (mutationError instanceof ApiError) {
          if (mutationError.status === 403) {
            setError(`Not permitted: ${mutationError.detail}`);
          } else if (mutationError.status === 409 || mutationError.status === 422) {
            setError(mutationError.detail);
          } else {
            setError(mutationError.detail || "Could not advance the sample. Please try again.");
          }
          return;
        }
        setError("Could not reach the server. Please try again.");
      },
    });
  }

  return (
    <div className="flex flex-col gap-3">
      {compact ? null : (
        <p className="text-sm text-muted-foreground">
          Advancing moves the sample to the next stage. The backend checks every gate and the reason
          for any refusal is shown here.
        </p>
      )}
      <GateError detail={error} />
      <SubmitButton
        type="button"
        pending={advance.isPending}
        pendingLabel="Advancing…"
        variant={compact ? "outline" : "primary"}
        className={compact ? "px-2 py-1 text-xs" : undefined}
        onClick={handleAdvance}
      >
        {compact ? "Advance" : "Advance sample"}
      </SubmitButton>
    </div>
  );
}
