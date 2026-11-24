import type { components } from "@/lib/api/schema";
import { sentenceCase } from "@/lib/i18n/dir";
import { cn } from "@/lib/utils";

type Stage = Pick<components["schemas"]["StageOut"], "position" | "name">;

const STAGE_TONES = [
  "bg-secondary text-secondary-foreground",
  "bg-accent text-accent-foreground",
  "bg-brand/10 text-brand",
  "bg-secondary text-secondary-foreground",
  "bg-muted text-foreground",
  "bg-secondary text-secondary-foreground",
  "bg-accent text-accent-foreground",
  "bg-success/10 text-success",
];

export function StageBadge({ stage, className }: { stage: Stage; className?: string }) {
  const tone = STAGE_TONES[(stage.position - 1) % STAGE_TONES.length];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        tone,
        className,
      )}
    >
      <span className="tabular-nums opacity-70">{stage.position}</span>
      {sentenceCase(stage.name)}
    </span>
  );
}
