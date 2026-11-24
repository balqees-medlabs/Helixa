"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { BOARD_QUERY_KEY, METRICS_QUERY_KEY, sampleKeys } from "@/lib/features/samples/queries";

export type Batch = components["schemas"]["BatchOut"];
export type MemberAdvanceResult = components["schemas"]["MemberAdvanceResult"];
export type BatchAdvanceRequest = components["schemas"]["BatchAdvanceRequest"];

export const BATCHES_QUERY_KEY = ["batches"] as const;

export function useCreateBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (name: string) => apiFetch("/batches", { method: "post", body: { name } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: BATCHES_QUERY_KEY });
    },
  });
}

export function useAddBatchMembers() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ batchId, sampleIds }: { batchId: string; sampleIds: string[] }) =>
      apiFetch(apiPath("/batches/{batch_id}/members", { batch_id: batchId }), {
        method: "post",
        body: { sample_ids: sampleIds },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: BATCHES_QUERY_KEY });
    },
  });
}

export function useAdvanceBatch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ batchId, body }: { batchId: string; body: BatchAdvanceRequest }) =>
      apiFetch(apiPath("/batches/{batch_id}/advance", { batch_id: batchId }), {
        method: "post",
        body,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sampleKeys.all });
      queryClient.invalidateQueries({ queryKey: BOARD_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: METRICS_QUERY_KEY });
    },
  });
}
