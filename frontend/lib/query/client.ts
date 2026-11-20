import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

/** Board and portal-push status views poll on this cadence (30–60s). */
export const POLL_MS = 45_000;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status < 500) {
            return false;
          }
          return failureCount < 1;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}
