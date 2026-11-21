"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo } from "react";
import type { ReactNode } from "react";

import { resetSessionExpiredState, setSessionExpiredHandler } from "@/lib/api/client";
import * as authService from "@/lib/auth/authService";
import type { SessionUser } from "@/lib/auth/authService";

export type { SessionUser };

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const pathname = usePathname();

  const sessionQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: authService.me,
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
      const nextUser = await authService.login(email, password);
      resetSessionExpiredState();
      queryClient.setQueryData(ME_QUERY_KEY, nextUser);
      return nextUser;
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authService.logout();
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
      if (pathname !== "/login") {
        router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
      }
    });
  }, [queryClient, pathname, router]);

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
