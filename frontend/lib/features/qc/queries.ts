"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { BOARD_QUERY_KEY, METRICS_QUERY_KEY, sampleKeys } from "@/lib/features/samples/queries";

export type QcCreate = components["schemas"]["QcCreate"];
export type QcResult = components["schemas"]["QcOut"];

export function useRecordQc() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ sampleId, body }: { sampleId: string; body: QcCreate }) =>
      apiFetch(apiPath("/samples/{sample_id}/qc", { sample_id: sampleId }), {
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
