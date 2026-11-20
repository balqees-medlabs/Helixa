"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo } from "react";
import type { ReactNode } from "react";

import {
  ApiError,
  apiFetch,
  resetSessionExpiredState,
  setSessionExpiredHandler,
} from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type SessionUser = components["schemas"]["UserOut"];

interface AuthContextValue {
  user: SessionUser | null;
  roles: string[];
  isLoading: boolean;
  can: (...slugs: string[]) => boolean;
  login: (email: string, password: string) => Promise<SessionUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const ME_QUERY_KEY = ["me"] as const;

async function loadSession(): Promise<SessionUser | null> {
  try {
    return await apiFetch("/auth/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null;
    }
    throw error;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const sessionQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: loadSession,
    retry: false,
    staleTime: 30_000,
  });

  const user = sessionQuery.data ?? null;
  const roles = useMemo(() => user?.roles ?? [], [user]);

  const can = useCallback(
    (...slugs: string[]) => {
      if (roles.includes("admin")) {
        return true;
      }
      return slugs.some((slug) => roles.includes(slug));
    },
    [roles],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const nextUser = await apiFetch("/auth/login", {
        method: "post",
        body: { email, password },
      });
      resetSessionExpiredState();
      queryClient.setQueryData(ME_QUERY_KEY, nextUser);
      return nextUser;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await apiFetch("/auth/logout", { method: "post" });
    } finally {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== ME_QUERY_KEY[0],
      });
      resetSessionExpiredState();
    }
  }, [queryClient]);

  useEffect(() => {
    return setSessionExpiredHandler((nextPath) => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== ME_QUERY_KEY[0],
      });
      if (typeof window !== "undefined" && window.location.pathname !== "/login") {
        window.location.assign(`/login?next=${encodeURIComponent(nextPath)}`);
      }
    });
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      roles,
      isLoading: sessionQuery.isLoading,
      can,
      login,
      logout,
    }),
    [user, roles, sessionQuery.isLoading, can, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
