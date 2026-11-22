"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { BOARD_QUERY_KEY, METRICS_QUERY_KEY } from "@/lib/features/samples/queries";

export type TatMetrics = components["schemas"]["TatMetrics"];
export type SampleTat = components["schemas"]["SampleTat"];
export type StageMetric = components["schemas"]["StageMetric"];
export type Vendor = components["schemas"]["VendorOut"];

export const USER_COUNT_QUERY_KEY = ["users", "count"] as const;

interface PollOptions {
  enabled?: boolean;
  refetchInterval?: number;
}

/** All samples for the shared board, refreshed on the poll cadence. */
export function useBoardSamples({ refetchInterval }: PollOptions = {}) {
  return useQuery({
    queryKey: BOARD_QUERY_KEY,
    queryFn: () => apiFetch("/samples", { query: { limit: 200 } }),
    refetchInterval,
  });
}

/** Turnaround metrics are admin-only; callers pass `enabled: can("admin")`. */
export function useTatMetrics({ enabled = true, refetchInterval }: PollOptions = {}) {
  return useQuery({
    queryKey: METRICS_QUERY_KEY,
    queryFn: () => apiFetch("/metrics/tat"),
    enabled,
    refetchInterval,
  });
}

export function useUserCount({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: USER_COUNT_QUERY_KEY,
    queryFn: () => apiFetch("/users", { query: { limit: 1, offset: 0 } }),
    enabled,
  });
}

export function useVendors({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["vendors"],
    queryFn: () => apiFetch("/vendors"),
    enabled,
  });
}

export function useUpdateStageSla() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ stageId, slaDays }: { stageId: string; slaDays: number }) =>
      apiFetch(apiPath("/stages/{stage_id}/sla", { stage_id: stageId }), {
        method: "patch",
        body: { sla_days: slaDays },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: METRICS_QUERY_KEY });
    },
  });
}
