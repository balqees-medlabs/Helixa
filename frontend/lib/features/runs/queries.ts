"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Run = components["schemas"]["RunOut"];
export type RunCreate = components["schemas"]["RunCreate"];
export type PipelineSampleCreate = components["schemas"]["PipelineSampleCreate"];

export const runsKeys = {
  all: ["runs"] as const,
  list: () => ["runs", "list"] as const,
  detail: (id: string) => ["runs", "detail", id] as const,
};

export function useRuns() {
  return useQuery({
    queryKey: runsKeys.list(),
    queryFn: () => apiFetch("/runs"),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: runsKeys.detail(id),
    queryFn: () => apiFetch(apiPath("/runs/{run_id}", { run_id: id })),
    enabled: Boolean(id),
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: RunCreate) => apiFetch("/runs", { method: "post", body }),
    onSuccess: (run) => {
      queryClient.setQueryData(runsKeys.detail(run.id), run);
      queryClient.invalidateQueries({ queryKey: runsKeys.all });
    },
  });
}

export function useRecordRunSample() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (variables: { runId: string; body: PipelineSampleCreate }) =>
      apiFetch(apiPath("/runs/{run_id}/samples", { run_id: variables.runId }), {
        method: "post",
        body: variables.body,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: runsKeys.all });
    },
  });
}
