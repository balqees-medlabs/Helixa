"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Coverage = components["schemas"]["CoverageOut"];
export type PipelineResult = components["schemas"]["PipelineResultOut"];

export const pipelineKeys = {
  coverage: (sampleId: string) => ["samples", sampleId, "coverage"] as const,
  results: (sampleId: string) => ["samples", sampleId, "pipeline-results"] as const,
};

/** Coverage history, latest first (the latest verdict governs the gate). */
export function useSampleCoverage(sampleId: string) {
  return useQuery({
    queryKey: pipelineKeys.coverage(sampleId),
    queryFn: () => apiFetch(apiPath("/samples/{sample_id}/coverage", { sample_id: sampleId })),
    enabled: Boolean(sampleId),
  });
}

export function useSamplePipelineResults(sampleId: string) {
  return useQuery({
    queryKey: pipelineKeys.results(sampleId),
    queryFn: () =>
      apiFetch(apiPath("/samples/{sample_id}/pipeline-results", { sample_id: sampleId })),
    enabled: Boolean(sampleId),
  });
}
