"use client";

import { useEffect, useMemo, useState } from "react";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useSampleConsent, useSetConsent } from "@/lib/features/samples/queries";
import { formatDateTime } from "@/lib/format";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

export function ConsentChecklist({ sampleId, canEdit }: { sampleId: string; canEdit: boolean }) {
  const consentQuery = useSampleConsent(sampleId);
  const setConsent = useSetConsent(sampleId);
  const [draft, setDraft] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const consent = consentQuery.data;

  useEffect(() => {
    if (!consent) {
      return;
    }
    const next: Record<string, boolean> = {};
    for (const item of consent.items) {
      next[item.item] = item.complete;
    }
    setDraft(next);
  }, [consent]);

  const dirty = useMemo(() => {
    if (!consent) {
      return false;
    }
    return consent.items.some((item) => (draft[item.item] ?? item.complete) !== item.complete);
  }, [consent, draft]);

  if (consentQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading consent…</p>;
  }

  if (consentQuery.isError) {
    const detail =
      consentQuery.error instanceof ApiError
        ? consentQuery.error.detail
        : "Could not load the consent checklist.";
    return <GateError detail={detail} />;
  }

  if (!consent) {
    return null;
  }

  function handleSave() {
    if (!consent) {
      return;
    }
    setError(null);
    setConsent.mutate(
      consent.items.map((item) => ({
        item: item.item,
        required: item.required,
        complete: draft[item.item] ?? item.complete,
      })),
      {
        onError: (mutationError) => {
          setError(
            mutationError instanceof ApiError
              ? mutationError.detail
              : "Could not save the consent checklist. Please try again.",
          );
        },
      },
    );
  }

  return (
    <section
      aria-labelledby="consent-heading"
      className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4"
    >
      <div className="flex flex-col gap-1">
        <h2 id="consent-heading" className="text-lg font-semibold tracking-tight">
          Consent checklist
        </h2>
        <p className="text-sm text-muted-foreground">
          Consent and documentation must be complete before molecular processing.
        </p>
      </div>

      <p
        role="status"
        className={cn(
          "inline-flex w-fit items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
          consent.required_complete ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
        )}
      >
        Molecular gate {consent.required_complete ? "open" : "closed"}
      </p>

      {consent.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No consent items recorded.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {consent.items.map((item) => {
            const checked = draft[item.item] ?? item.complete;
            return (
              <li key={item.item}>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={checked}
                    disabled={!canEdit || setConsent.isPending}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, [item.item]: event.target.checked }))
                    }
                  />
                  <span>
                    <span className="font-medium">{sentenceCase(item.item)}</span>
                    {item.required ? (
                      <span className="ms-2 rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
                        Required
                      </span>
                    ) : null}
                    {item.complete && item.completed_at ? (
                      <span className="mt-1 block text-xs text-muted-foreground">
                        Completed {formatDateTime(item.completed_at)}
                      </span>
                    ) : null}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      <GateError detail={error} />

      {canEdit ? (
        <SubmitButton
          type="button"
          pending={setConsent.isPending}
          pendingLabel="Saving…"
          disabled={!dirty}
          onClick={handleSave}
        >
          Save consent
        </SubmitButton>
      ) : (
        <p className="text-xs text-muted-foreground">
          Only genomics staff and administrators can update the consent checklist.
        </p>
      )}
    </section>
  );
}
