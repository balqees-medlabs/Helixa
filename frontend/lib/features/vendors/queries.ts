"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiPath } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Vendor = components["schemas"]["VendorOut"];
export type VendorCreate = components["schemas"]["VendorCreate"];
export type VendorUpdate = components["schemas"]["VendorUpdate"];

export const VENDORS_QUERY_KEY = ["vendors"] as const;

export function useVendors({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: VENDORS_QUERY_KEY,
    queryFn: () => apiFetch("/vendors"),
    enabled,
  });
}

export function useCreateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: VendorCreate) => apiFetch("/vendors", { method: "post", body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: VENDORS_QUERY_KEY });
    },
  });
}

export function useUpdateVendor() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ vendorId, body }: { vendorId: string; body: VendorUpdate }) =>
      apiFetch(apiPath("/vendors/{vendor_id}", { vendor_id: vendorId }), {
        method: "patch",
        body,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: VENDORS_QUERY_KEY });
    },
  });
}
