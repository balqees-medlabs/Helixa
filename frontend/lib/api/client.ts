import type { paths } from "./schema";

export type ApiPath = keyof paths;
export type ApiMethod = "get" | "post" | "put" | "patch" | "delete";

type Operation<P extends ApiPath, M extends ApiMethod> = P extends ApiPath
  ? M extends keyof paths[P]
    ? NonNullable<paths[P][M]>
    : never
  : never;

type JsonOf<T> = T extends { content: { "application/json": infer Body } } ? Body : void;

type SuccessOf<Op> = Op extends { responses: infer Responses }
  ? Responses extends Record<number, unknown>
    ? JsonOf<Responses[Extract<keyof Responses, 200 | 201 | 202 | 204>]>
    : void
  : void;

type JsonBodyOf<Op> = Op extends {
  requestBody: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

export type ApiResponse<P extends ApiPath, M extends ApiMethod> = SuccessOf<Operation<P, M>>;
export type ApiJsonBody<P extends ApiPath, M extends ApiMethod> = JsonBodyOf<Operation<P, M>>;

type QueryValue = string | number | boolean | null | undefined;

export interface ApiRequestOptions<P extends ApiPath, M extends ApiMethod> {
  method?: M;
  body?: ApiJsonBody<P, M> | FormData | URLSearchParams | string | null;
  query?: Record<string, QueryValue>;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: unknown;

  constructor(status: number, detail: string, body: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

export type SessionExpiredHandler = (nextPath: string) => void;

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "/api").replace(/\/+$/, "");
const REFRESH_PATH = "/auth/refresh";
const NO_REFRESH_PATHS = new Set<ApiPath>(["/auth/login", REFRESH_PATH]);

let refreshInFlight: Promise<boolean> | null = null;
let sessionExpiredHandler: SessionExpiredHandler | null = null;
let sessionExpiredNotified = false;

export function setSessionExpiredHandler(handler: SessionExpiredHandler): () => void {
  sessionExpiredHandler = handler;
  return () => {
    if (sessionExpiredHandler === handler) {
      sessionExpiredHandler = null;
    }
  };
}

export function resetSessionExpiredState(): void {
  sessionExpiredNotified = false;
}

function buildUrl(path: ApiPath, query?: Record<string, QueryValue>): string {
  let url = `${API_BASE}${path}`;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        params.set(key, String(value));
      }
    }
    const qs = params.toString();
    if (qs) {
      url += `?${qs}`;
    }
  }
  return url;
}

function buildInit<P extends ApiPath, M extends ApiMethod>(
  options: ApiRequestOptions<P, M>,
  method: string,
): RequestInit {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  const body = options.body;
  if (body !== undefined && body !== null && !(body instanceof FormData)) {
    if (body instanceof URLSearchParams) {
      headers.set("Content-Type", "application/x-www-form-urlencoded");
    } else if (typeof body === "string") {
      headers.set("Content-Type", "text/plain");
    } else {
      headers.set("Content-Type", "application/json");
    }
  }

  return {
    method,
    headers,
    credentials: "include",
    body:
      body === undefined || body === null
        ? undefined
        : body instanceof FormData || body instanceof URLSearchParams || typeof body === "string"
          ? body
          : JSON.stringify(body),
    signal: options.signal,
  };
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function detailFrom(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail)) {
      const messages = detail
        .map((entry) =>
          entry && typeof entry === "object" && "msg" in entry
            ? String((entry as { msg: unknown }).msg)
            : null,
        )
        .filter((value): value is string => Boolean(value));
      if (messages.length) {
        return messages.join("; ");
      }
    }
    if (detail !== null && detail !== undefined) {
      return JSON.stringify(detail);
    }
  }
  if (typeof body === "string" && body.trim()) {
    return body;
  }
  return `Request failed (${status})`;
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = await readBody(response);
  return new ApiError(response.status, detailFrom(body, response.status), body);
}

async function performRefresh(): Promise<boolean> {
  try {
    const response = await fetch(buildUrl(REFRESH_PATH), {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function attemptedPath(): string {
  if (typeof window === "undefined") {
    return "/dashboard";
  }
  const path = `${window.location.pathname}${window.location.search}`;
  return path.startsWith("/login") ? "/dashboard" : path;
}

function notifySessionExpired(): void {
  if (sessionExpiredNotified) {
    return;
  }
  sessionExpiredNotified = true;
  const next = attemptedPath();

  if (sessionExpiredHandler) {
    sessionExpiredHandler(next);
    return;
  }

  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return undefined as T;
}

export async function apiFetch<P extends ApiPath, M extends ApiMethod = "get">(
  path: P,
  options: ApiRequestOptions<P, M> = {},
): Promise<ApiResponse<P, M>> {
  const method = (options.method ?? "get").toUpperCase();
  const url = buildUrl(path, options.query);

  let response = await fetch(url, buildInit(options, method));

  if (response.status === 401 && !NO_REFRESH_PATHS.has(path)) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      notifySessionExpired();
      throw await toApiError(response);
    }

    response = await fetch(url, buildInit(options, method));
    if (response.status === 401) {
      notifySessionExpired();
    }
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return parseResponse<ApiResponse<P, M>>(response);
}

export function apiGet<P extends ApiPath>(
  path: P,
  options: Omit<ApiRequestOptions<P, "get">, "method" | "body"> = {},
): Promise<ApiResponse<P, "get">> {
  return apiFetch(path, { ...options, method: "get" });
}

export function apiPost<P extends ApiPath>(
  path: P,
  body: ApiJsonBody<P, "post">,
  options: Omit<ApiRequestOptions<P, "post">, "method" | "body"> = {},
): Promise<ApiResponse<P, "post">> {
  return apiFetch(path, { ...options, method: "post", body });
}

export function apiMultipart<P extends ApiPath, M extends ApiMethod = "post">(
  path: P,
  formData: FormData,
  method: M = "post" as M,
  options: Omit<ApiRequestOptions<P, M>, "method" | "body"> = {},
): Promise<ApiResponse<P, M>> {
  return apiFetch(path, { ...options, method, body: formData });
}

export function apiPath<P extends ApiPath>(
  template: P,
  params: Record<string, string | number>,
): P {
  return template.replace(/\{([^}]+)\}/g, (match, key: string) => {
    const value = params[key];
    return value === undefined ? match : encodeURIComponent(String(value));
  }) as P;
}
