import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "outline" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  outline: "border border-input bg-background text-foreground hover:bg-secondary",
  ghost: "text-foreground hover:bg-secondary",
};

export interface SubmitButtonProps extends ComponentProps<"button"> {
  pending?: boolean;
  pendingLabel?: string;
  variant?: Variant;
}

export function SubmitButton({
  pending = false,
  pendingLabel = "Working…",
  variant = "primary",
  disabled,
  children,
  className,
  type = "submit",
  ...props
}: SubmitButtonProps) {
  return (
    <button
      {...props}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant],
        className,
      )}
    >
      {pending ? pendingLabel : children}
    </button>
  );
}
