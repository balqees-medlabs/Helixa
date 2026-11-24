export interface StageDefinition {
  position: number;
  slug: string;
  name: string;
}

/** The 8 ordered clinical stages (constitution V.1); the board columns. */
export const STAGES: readonly StageDefinition[] = [
  { position: 1, slug: "received", name: "sample received" },
  { position: 2, slug: "consent_documentation", name: "consent & documentation" },
  { position: 3, slug: "molecular_processing", name: "molecular processing" },
  { position: 4, slug: "data_generation", name: "data generation" },
  { position: 5, slug: "trf_preparation", name: "TRF preparation" },
  { position: 6, slug: "trf_confirmation", name: "TRF confirmation" },
  { position: 7, slug: "data_conversion_qc", name: "data conversion & QC" },
  { position: 8, slug: "report_upload_archive", name: "report upload/archive/portal push" },
];

/** The internal calendar-day target (constitution V.5). */
export const INTERNAL_TARGET_DAYS = 18;

export function stageByPosition(position: number): StageDefinition {
  return STAGES.find((stage) => stage.position === position) ?? STAGES[0];
}

export function elapsedCalendarDays(receivedAt: string, now = Date.now()): number {
  const received = new Date(receivedAt).getTime();
  if (Number.isNaN(received)) {
    return 0;
  }
  return Math.max(0, (now - received) / 86_400_000);
}

export function isPastTarget(receivedAt: string, now = Date.now()): boolean {
  return elapsedCalendarDays(receivedAt, now) > INTERNAL_TARGET_DAYS;
}
