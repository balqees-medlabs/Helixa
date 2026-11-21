"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Sample = components["schemas"]["SampleOut"];
export type SampleEvent = components["schemas"]["SampleEventOut"];
export type Consent = components["schemas"]["ConsentOut"];
export type ConsentItemInput = components["schemas"]["ConsentItemIn"];
export type SampleCreate = components["schemas"]["SampleCreate"];

/** Shared keys the board/metrics views will use once built (US3). */
export const BOARD_QUERY_KEY = ["board"] as const;
export const METRICS_QUERY_KEY = ["metrics"] as const;

export const sampleKeys = {
  all: ["samples"] as const,
  list: (limit: number, offset: number) => ["samples", "list", { limit, offset }] as const,
  detail: (id: string) => ["samples", "detail", id] as const,
  events: (id: string) => ["samples", "events", id] as const,
  consent: (id: string) => ["samples", "consent", id] as const,
};

export function useSamples(limit = 50, offset = 0) {
  return useQuery({
    queryKey: sampleKeys.list(limit, offset),
    queryFn: () => apiFetch("/samples", { query: { limit, offset } }),
  });
}

export function useSample(id: string) {
  return useQuery({
    queryKey: sampleKeys.detail(id),
    queryFn: () => apiFetch(apiPath("/samples/{sample_id}", { sample_id: id })),
    enabled: Boolean(id),
  });
}

export function useSampleEvents(id: string) {
  return useQuery({
    queryKey: sampleKeys.events(id),
    queryFn: () => apiFetch(apiPath("/samples/{sample_id}/events", { sample_id: id })),
    enabled: Boolean(id),
  });
}

export function useSampleConsent(id: string) {
  return useQuery({
    queryKey: sampleKeys.consent(id),
    queryFn: () => apiFetch(apiPath("/samples/{sample_id}/consent", { sample_id: id })),
    enabled: Boolean(id),
  });
}

export function useRegisterSample() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: SampleCreate) => apiFetch("/samples", { method: "post", body }),
    onSuccess: (sample) => {
      queryClient.setQueryData(sampleKeys.detail(sample.id), sample);
      queryClient.invalidateQueries({ queryKey: sampleKeys.all });
    },
  });
}

export function useAdvanceSample(sampleId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (fromStage: number) =>
      apiFetch(apiPath("/samples/{sample_id}/advance", { sample_id: sampleId }), {
        method: "post",
        body: { from_stage: fromStage },
      }),
    onSuccess: (sample) => {
      queryClient.setQueryData(sampleKeys.detail(sampleId), sample);
      queryClient.invalidateQueries({ queryKey: sampleKeys.detail(sampleId) });
      queryClient.invalidateQueries({ queryKey: sampleKeys.events(sampleId) });
      queryClient.invalidateQueries({ queryKey: sampleKeys.all });
      queryClient.invalidateQueries({ queryKey: BOARD_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: METRICS_QUERY_KEY });
    },
  });
}

export function useSetConsent(sampleId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (items: ConsentItemInput[]) =>
      apiFetch(apiPath("/samples/{sample_id}/consent", { sample_id: sampleId }), {
        method: "post",
        body: { items },
      }),
    onSuccess: (consent) => {
      queryClient.setQueryData(sampleKeys.consent(sampleId), consent);
      queryClient.invalidateQueries({ queryKey: sampleKeys.consent(sampleId) });
    },
  });
}
