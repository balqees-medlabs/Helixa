import { cn } from "@/lib/utils";

export function GateError({ detail, className }: { detail?: string | null; className?: string }) {
  if (!detail) {
    return null;
  }

  return (
    <p
      role="alert"
      aria-live="polite"
      className={cn(
        "rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive",
        className,
      )}
    >
      {detail}
    </p>
  );
}
