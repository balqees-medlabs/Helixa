import { HttpResponse, delay, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiFetch,
  resetSessionExpiredState,
  setSessionExpiredHandler,
} from "@/lib/api/client";

import { resetTestSession, signInAs } from "./msw/handlers";
import { server } from "./msw/server";

const EMPTY_PAGE = { items: [], total: 0, limit: 50, offset: 0 };

describe("apiFetch", () => {
  beforeEach(() => {
    resetSessionExpiredState();
    resetTestSession();
  });

  it("refreshes once and retries a 401", async () => {
    signInAs("genomics");
    let sampleCalls = 0;

    server.use(
      http.get("/api/samples", () => {
        sampleCalls += 1;
        return sampleCalls === 1
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(EMPTY_PAGE);
      }),
    );

    const page = await apiFetch("/samples");

    expect(page.total).toBe(0);
    expect(sampleCalls).toBe(2);
  });

  it("shares one refresh across concurrent 401s", async () => {
    signInAs("bioinformatics");
    let refreshCalls = 0;
    let sampleCalls = 0;

    server.use(
      http.post("/api/auth/refresh", async () => {
        refreshCalls += 1;
        await delay(20);
        return HttpResponse.json({});
      }),
      http.get("/api/samples", () => {
        sampleCalls += 1;
        return sampleCalls <= 2
          ? new HttpResponse(null, { status: 401 })
          : HttpResponse.json(EMPTY_PAGE);
      }),
    );

    await Promise.all([apiFetch("/samples"), apiFetch("/samples")]);

    expect(refreshCalls).toBe(1);
    expect(sampleCalls).toBe(4);
  });

  it("notifies the session-expired handler when refresh fails", async () => {
    const expired = vi.fn();
    const unsubscribe = setSessionExpiredHandler(expired);

    server.use(http.get("/api/samples", () => new HttpResponse(null, { status: 401 })));

    await expect(apiFetch("/samples")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledTimes(1);
    unsubscribe();
  });
});
