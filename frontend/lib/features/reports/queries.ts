"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiDownload, apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { POLL_MS } from "@/lib/query/client";

export type Report = components["schemas"]["ReportOut"];
export type PortalPush = components["schemas"]["PortalPushOut"];

export const reportKeys = {
  detail: (reportId: string) => ["reports", "detail", reportId] as const,
  push: (pushId: string) => ["portal-pushes", pushId] as const,
};

export function useUploadReport() {
  return useMutation({
    mutationFn: ({ sampleId, file }: { sampleId: string; file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetch(apiPath("/samples/{sample_id}/report", { sample_id: sampleId }), {
        method: "post",
        body: formData,
      });
    },
  });
}

export function useReport(reportId: string) {
  return useQuery({
    queryKey: reportKeys.detail(reportId),
    queryFn: () => apiFetch(apiPath("/reports/{report_id}", { report_id: reportId })),
    enabled: Boolean(reportId),
    retry: false,
  });
}

export function usePortalPush(pushId: string, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: reportKeys.push(pushId),
    queryFn: () => apiFetch(apiPath("/portal-pushes/{push_id}", { push_id: pushId })),
    enabled: enabled && Boolean(pushId),
    refetchInterval: POLL_MS,
  });
}

export function useRetryPortalPush() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (pushId: string) =>
      apiFetch(apiPath("/portal-pushes/{push_id}/retry", { push_id: pushId }), {
        method: "post",
      }),
    onSuccess: (push) => {
      queryClient.setQueryData(reportKeys.push(push.id), push);
      queryClient.invalidateQueries({ queryKey: reportKeys.detail(push.report_id) });
    },
  });
}

export async function downloadReportFile(report: Report): Promise<void> {
  const blob = await apiDownload(apiPath("/reports/{report_id}/file", { report_id: report.id }));
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = report.path.split("/").pop() ?? `${report.id}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
