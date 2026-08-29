/**
 * バックエンド（FastAPI）への薄い fetch ラッパ。
 *
 * ここが守る契約:
 * - すべてのレスポンスは `{ data, warnings, meta }`（09-api-spec.md §3）。`warnings` は
 *   空配列でも必ず存在する前提で、呼び出し側は毎回 WarningBanner に渡せる。
 * - エラーは RFC 7807 Problem Details。`ApiError.kind` に正規化して、画面が
 *   `not-ready` / `cost-cap` / `offline` を出し分けられるようにする。
 * - Service Worker がキャッシュから返した場合は `from_cache` と `fetched_at` が立つ。
 *   states.md §6 が要求する「取得時刻の併記」はこの2つで実現する。
 */

import type { ApiWarning, Envelope, Meta, ProblemDetails } from "./api-types";

/**
 * 既定は同一オリジンの `/api/v1`。Next.js が FastAPI へ中継する（next.config.ts）。
 * スマホ（Tailscale）から開いたとき、ブラウザが 127.0.0.1 を叩かないようにする。
 * 直接 FastAPI に向けたいときだけ `NEXT_PUBLIC_API_BASE_URL` を上書きする。
 */
export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1"
).replace(/\/$/, "");

/** モックモード。バックエンド未起動でも全画面を確認できるようにする */
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "1";

const DEFAULT_TIMEOUT_MS = 15_000;

export type ApiErrorKind =
  | "offline"
  | "timeout"
  | "network"
  | "validation"
  | "not-found"
  | "not-ready"
  | "cost-cap"
  | "rate-limited"
  | "server"
  | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly problem: ProblemDetails | null;

  constructor(kind: ApiErrorKind, message: string, status = 0, problem: ProblemDetails | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.problem = problem;
  }

  /** 再試行して意味があるか。TanStack Query の retry 判定に使う */
  get isRetryable(): boolean {
    return this.kind === "network" || this.kind === "timeout" || this.kind === "server";
  }

  /** 画面に出す日本語。states.md §4 の文言に合わせる */
  get messageJa(): string {
    switch (this.kind) {
      case "offline":
        return "オフラインです。接続が戻ると自動で再取得します。";
      case "timeout":
        return "応答がありませんでした。時間をおいて再試行してください。";
      case "network":
        return "バックエンドに接続できません。API が起動しているか確認してください。";
      case "not-ready":
        return this.problem?.latest_available_as_of
          ? `指定日のデータはまだありません。利用できる最新は ${this.problem.latest_available_as_of} です。`
          : "指定日のデータはまだ生成されていません。";
      case "cost-cap":
        return "本日のLLM予算上限に達しました。要約の生成は明朝まで停止します。";
      case "rate-limited":
        return "リクエストが多すぎます。少し待ってから再試行してください。";
      case "not-found":
        return "対象が見つかりませんでした。";
      case "validation":
        return this.problem?.detail ?? "入力内容を確認してください。";
      default:
        return this.problem?.detail ?? this.problem?.title ?? "取得に失敗しました。";
    }
  }
}

/** 呼び出し側が受け取る形。Envelope にキャッシュ由来の情報を足しただけ */
export interface ApiResult<T> extends Envelope<T> {
  from_cache: boolean;
  fetched_at: string;
}

export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;
export type QueryParams = Record<string, QueryValue>;

export function buildQuery(params?: QueryParams): string {
  if (!params) return "";
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const v of value) sp.append(key, String(v));
    } else {
      sp.append(key, String(value));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

const EMPTY_META: Meta = {
  as_of: "",
  computed_at: new Date(0).toISOString(),
  data_freshness: [],
  is_seed_data: false,
};

/** Envelope.data が `{ items, total }` でも配列でも、呼び出し側は配列として扱えるようにする */
export function unwrapItems<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object" && Array.isArray((data as { items?: unknown }).items)) {
    return (data as { items: T[] }).items;
  }
  return [];
}

/** `{ periods }` / `{ peers }` / `{ points }` のように、リストが名前付きフィールドに入っている応答用 */
export function unwrapField<T>(data: unknown, field: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === "object") {
    const rec = data as Record<string, unknown>;
    if (Array.isArray(rec[field])) return rec[field] as T[];
    if (Array.isArray(rec.items)) return rec.items as T[];
  }
  return [];
}

export function mapResult<TIn, TOut>(result: ApiResult<TIn>, mapper: (data: TIn) => TOut): ApiResult<TOut> {
  return { ...result, data: mapper(result.data) };
}

/** 仕様に無いエンドポイントを叩かず、セクションを空で返すとき使う */
export function emptyResult<T>(data: T): ApiResult<T> {
  return {
    data,
    warnings: [],
    meta: { ...EMPTY_META, computed_at: new Date().toISOString() },
    from_cache: false,
    fetched_at: new Date().toISOString(),
  };
}

function kindFromStatus(status: number, problem: ProblemDetails | null): ApiErrorKind {
  const type = problem?.type ?? "";
  if (type.includes("data-not-ready")) return "not-ready";
  if (type.includes("cost-cap")) return "cost-cap";
  switch (status) {
    case 400:
    case 422:
      return "validation";
    case 404:
      return "not-found";
    case 409:
      return "not-ready";
    case 429:
      return "rate-limited";
    default:
      return status >= 500 ? "server" : "unknown";
  }
}

async function readProblem(res: Response): Promise<ProblemDetails | null> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object") return body as ProblemDetails;
    return null;
  } catch {
    return null;
  }
}

function normalizeEnvelope<T>(body: unknown, res: Response): ApiResult<T> {
  const envelope = (body ?? {}) as Partial<Envelope<T>>;
  const fromCacheHeader = res.headers.get("x-from-cache");
  const fetchedAtHeader = res.headers.get("x-fetched-at");
  return {
    // Envelope を返さないエンドポイント（204 など）でも形をそろえる
    data: (envelope.data ?? null) as T,
    warnings: Array.isArray(envelope.warnings) ? (envelope.warnings as ApiWarning[]) : [],
    meta: envelope.meta ?? EMPTY_META,
    from_cache: fromCacheHeader === "1",
    fetched_at: fetchedAtHeader ?? new Date().toISOString(),
  };
}

export interface RequestOptions {
  params?: QueryParams;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** モックを迂回したいとき（設定画面の疎通確認など）だけ true にする */
  bypassMock?: boolean;
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  if (USE_MOCK && !options.bypassMock) {
    const { handleMock } = await import("./mock");
    return handleMock<T>(method, path, options.params, body);
  }

  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    throw new ApiError("offline", "オフラインです");
  }

  const url = `${API_BASE_URL}${path}${buildQuery(options.params)}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  const onAbort = () => controller.abort();
  options.signal?.addEventListener("abort", onAbort);

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (err) {
    if (options.signal?.aborted) throw err;
    if (controller.signal.aborted) throw new ApiError("timeout", "タイムアウトしました");
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      throw new ApiError("offline", "オフラインです");
    }
    throw new ApiError("network", err instanceof Error ? err.message : "ネットワークエラー");
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener("abort", onAbort);
  }

  if (!res.ok) {
    const problem = await readProblem(res);
    throw new ApiError(kindFromStatus(res.status, problem), problem?.title ?? res.statusText, res.status, problem);
  }

  if (res.status === 204) return normalizeEnvelope<T>(null, res);

  let parsed: unknown;
  try {
    parsed = await res.json();
  } catch {
    throw new ApiError("server", "レスポンスを解釈できませんでした", res.status);
  }
  return normalizeEnvelope<T>(parsed, res);
}

export const apiGet = <T>(path: string, options?: RequestOptions) =>
  request<T>("GET", path, undefined, options);

export const apiPost = <T>(path: string, body?: unknown, options?: RequestOptions) =>
  request<T>("POST", path, body, options);

export const apiPatch = <T>(path: string, body?: unknown, options?: RequestOptions) =>
  request<T>("PATCH", path, body, options);

export const apiDelete = <T>(path: string, options?: RequestOptions) =>
  request<T>("DELETE", path, undefined, options);

/** 集約系の警告からセクション単位に絞る。partial の描画位置を決めるのに使う */
export function warningsForSection(warnings: ApiWarning[], section: string): ApiWarning[] {
  return warnings.filter((w) => w.section === section);
}

export function globalWarnings(warnings: ApiWarning[]): ApiWarning[] {
  return warnings.filter((w) => !w.section);
}
