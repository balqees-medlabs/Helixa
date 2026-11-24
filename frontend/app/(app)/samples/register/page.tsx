"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";
import { z } from "zod";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useRegisterSample } from "@/lib/features/samples/queries";

const registerSchema = z.object({
  case_id: z
    .string()
    .trim()
    .min(1, "Enter the case identifier")
    .max(100, "Keep the case identifier under 100 characters"),
  external_ref: z
    .string()
    .trim()
    .max(200, "Keep the external reference under 200 characters")
    .optional(),
});

type FieldErrors = Partial<Record<"case_id" | "external_ref", string>>;

export default function RegisterSamplePage() {
  const { can, isLoading } = useAuth();
  const router = useRouter();
  const registerSample = useRegisterSample();

  const [caseId, setCaseId] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  const canRegister = can("genomics");

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading…
      </p>
    );
  }

  if (!canRegister) {
    return (
      <section className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Register sample</h1>
        <GateError detail="You do not have access to register samples." />
        <Link href="/samples" className="text-sm text-brand hover:underline">
          Back to samples
        </Link>
      </section>
    );
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const parsed = registerSchema.safeParse({ case_id: caseId, external_ref: externalRef });
    if (!parsed.success) {
      const nextErrors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (field === "case_id" || field === "external_ref") {
          nextErrors[field] = issue.message;
        }
      }
      setFieldErrors(nextErrors);
      return;
    }

    setFieldErrors({});
    registerSample.mutate(
      {
        case_id: parsed.data.case_id,
        external_ref: parsed.data.external_ref || null,
      },
      {
        onSuccess: (sample) => router.push(`/samples/${sample.id}`),
        onError: (error) => {
          if (error instanceof ApiError) {
            if (error.status === 403) {
              setFormError("You are not permitted to register samples.");
            } else {
              setFormError(error.detail);
            }
            return;
          }
          setFormError("Could not reach the server. Please try again.");
        },
      },
    );
  }

  return (
    <section className="flex max-w-xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <Link href="/samples" className="text-sm text-brand hover:underline">
          Samples
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Register sample</h1>
        <p className="text-sm text-muted-foreground">
          A new sample starts at the first stage and opens its consent checklist.
        </p>
      </div>

      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="case_id" className="text-sm font-medium">
            Case identifier
          </label>
          <input
            id="case_id"
            name="case_id"
            value={caseId}
            onChange={(event) => setCaseId(event.target.value)}
            aria-invalid={fieldErrors.case_id ? true : undefined}
            aria-describedby={fieldErrors.case_id ? "case-id-error" : undefined}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
          {fieldErrors.case_id ? (
            <p id="case-id-error" className="text-xs text-destructive">
              {fieldErrors.case_id}
            </p>
          ) : null}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="external_ref" className="text-sm font-medium">
            External reference (optional)
          </label>
          <input
            id="external_ref"
            name="external_ref"
            value={externalRef}
            onChange={(event) => setExternalRef(event.target.value)}
            aria-invalid={fieldErrors.external_ref ? true : undefined}
            aria-describedby={fieldErrors.external_ref ? "external-ref-error" : undefined}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
          {fieldErrors.external_ref ? (
            <p id="external-ref-error" className="text-xs text-destructive">
              {fieldErrors.external_ref}
            </p>
          ) : null}
        </div>

        <GateError detail={formError} />

        <div className="flex items-center gap-3">
          <SubmitButton pending={registerSample.isPending} pendingLabel="Registering…">
            Register sample
          </SubmitButton>
          <Link href="/samples" className="text-sm text-muted-foreground hover:text-brand">
            Cancel
          </Link>
        </div>
      </form>
    </section>
  );
}
