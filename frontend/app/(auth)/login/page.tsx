"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import type { FormEvent } from "react";
import { z } from "zod";

import { GateError } from "@/components/GateError";
import { SubmitButton } from "@/components/SubmitButton";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { INVALID_CREDENTIALS } from "@/lib/auth/authService";
import { landingDashboardFor } from "@/lib/auth/roles";
import { safeNextPath } from "@/lib/auth/guards";

const credentialsSchema = z.object({
  email: z.string().trim().min(1, "Enter your email address").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

type FieldErrors = Partial<Record<"email" | "password", string>>;

function SignInForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    const parsed = credentialsSchema.safeParse({ email, password });
    if (!parsed.success) {
      const nextErrors: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const field = issue.path[0];
        if (field === "email" || field === "password") {
          nextErrors[field] = issue.message;
        }
      }
      setFieldErrors(nextErrors);
      return;
    }

    setFieldErrors({});
    setPending(true);
    try {
      const user = await login(parsed.data.email, parsed.data.password);
      const target = safeNextPath(searchParams.get("next")) ?? landingDashboardFor(user.roles);
      router.replace(target);
    } catch (error) {
      setFormError(
        error instanceof ApiError && (error.status === 401 || error.status === 403)
          ? INVALID_CREDENTIALS
          : "Could not sign in right now. Please try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="container flex min-h-screen items-center justify-center py-16">
      <section
        aria-labelledby="sign-in-heading"
        className="w-full max-w-sm rounded-lg border border-border bg-card p-6"
      >
        <p className="text-sm font-medium uppercase tracking-wide text-brand">Medlabs Genomics</p>
        <h1 id="sign-in-heading" className="mt-2 text-2xl font-semibold tracking-tight">
          Sign in
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">Use your Helixa account to continue.</p>

        <form noValidate onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              autoFocus
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={fieldErrors.email ? true : undefined}
              aria-describedby={fieldErrors.email ? "email-error" : undefined}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            />
            {fieldErrors.email ? (
              <p id="email-error" className="text-xs text-destructive">
                {fieldErrors.email}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={fieldErrors.password ? true : undefined}
              aria-describedby={fieldErrors.password ? "password-error" : undefined}
              className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
            />
            {fieldErrors.password ? (
              <p id="password-error" className="text-xs text-destructive">
                {fieldErrors.password}
              </p>
            ) : null}
          </div>

          <GateError detail={formError} />

          <SubmitButton pending={pending} pendingLabel="Signing in…" className="w-full">
            Sign in
          </SubmitButton>
        </form>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="container flex min-h-screen items-center justify-center py-16">
          <p role="status" className="text-sm text-muted-foreground">
            Loading sign in…
          </p>
        </main>
      }
    >
      <SignInForm />
    </Suspense>
  );
}
