/**
 * モックのルータ。`NEXT_PUBLIC_USE_MOCK=1` のとき api-client からここに来る。
 *
 * URL に `?mock_state=` を付けると状態を強制できる。states.md の全状態を
 * バックエンドなしで確認・テストするための唯一の入口。
 *   empty / not-ready / error / offline / partial / slow / degraded
 * 例: /recommendations?mock_state=empty
 */

import { ApiError, type ApiResult, type QueryParams } from "../api-client";
import type { ApiWarning, Meta, ProblemDetails } from "../api-types";
import * as fx from "./fixtures";

export type MockState =
  | "ok"
  | "empty"
  | "not-ready"
  | "error"
  | "offline"
  | "partial"
  | "slow"
  | "degraded";

const MOCK_STATES: MockState[] = [
  "ok",
  "empty",
  "not-ready",
  "error",
  "offline",
  "partial",
  "slow",
  "degraded",
];

function currentState(): MockState {
  if (typeof window === "undefined") return "ok";
  const raw = new URLSearchParams(window.location.search).get("mock_state");
  return MOCK_STATES.includes(raw as MockState) ? (raw as MockState) : "ok";
}

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const BASE_META: Meta = {
  as_of: fx.MOCK_AS_OF,
  computed_at: fx.MOCK_COMPUTED_AT,
  data_freshness: fx.FRESHNESS,
  is_seed_data: true,
};

/** J-Quants の遅延と TDnet の失敗は常に出す。鮮度と部分失敗の表示経路を必ず通す */
const BASE_WARNINGS: ApiWarning[] = [
  {
    code: "DATA_DELAYED",
    message_ja: "J-Quantsの価格データは無料プランのため12週遅延しています（最新 2026-05-30）",
    severity: "warning",
    source: "jquants",
  },
];

const PARTIAL_WARNINGS: ApiWarning[] = [
  ...BASE_WARNINGS,
  {
    code: "SOURCE_FAILED",
    message_ja: "TDnetの取得が3日連続で失敗しています。適時開示の一部が欠けている可能性があります",
    severity: "error",
    source: "tdnet",
    section: "filings",
  },
  {
    code: "QUAL_SKIPPED",
    message_ja: "資料読解が3件スキップされました。定性スコアは一部の銘柄で欠けています",
    severity: "warning",
    source: "researcher",
    section: "recommendations",
  },
];

function ok<T>(data: T, extra?: { warnings?: ApiWarning[]; meta?: Partial<Meta> }): ApiResult<T> {
  const state = currentState();
  return {
    data,
    warnings: [...(state === "partial" || state === "degraded" ? PARTIAL_WARNINGS : BASE_WARNINGS), ...(extra?.warnings ?? [])],
    meta: { ...BASE_META, ...extra?.meta },
    from_cache: false,
    fetched_at: new Date().toISOString(),
  };
}

function notReady(): never {
  const problem: ProblemDetails = {
    type: "https://ai-stock-research.local/problems/data-not-ready",
    title: "指定日のデータがまだ生成されていません",
    status: 409,
    latest_available_as_of: "2026-08-21",
  };
  throw new ApiError("not-ready", problem.title, 409, problem);
}

function serverError(): never {
  const problem: ProblemDetails = {
    type: "about:blank",
    title: "内部エラー",
    status: 500,
    detail: "バッチの途中でDuckDBの接続が切れました（モック）",
  };
  throw new ApiError("server", problem.title, 500, problem);
}

/** パスをセグメント配列にする（クエリは params 側で受け取る） */
function segments(path: string): string[] {
  return path.split("?")[0]!.split("/").filter(Boolean);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- モックは全エンドポイントの戻り値を1関数で束ねるため、境界で1度だけ any を使う
type Any = any;

function resolve(method: string, path: string, params?: QueryParams, body?: unknown): Any {
  const seg = segments(path);
  const state = currentState();
  const empty = state === "empty";

  // 1) /dashboard
  if (seg[0] === "dashboard") {
    if (state === "degraded") {
      return {
        ...fx.DASHBOARD,
        top_recommendations: [],
        model_health: {
          ...fx.MODEL_HEALTH,
          status: "degraded" as const,
          rank_ic_20d: 0.004,
          degradation_note_ja: "直近20営業日のRank ICが過去1年の下位5%にあります",
        },
      };
    }
    if (empty) {
      return { ...fx.DASHBOARD, top_recommendations: [], alerts: [], watchlist: [], watchlist_filings: [], new_filings_count: 0 };
    }
    return fx.DASHBOARD;
  }

  // 2) /recommendations
  if (seg[0] === "recommendations" && seg.length === 1) {
    if (empty) return { items: [], total: 0 };
    const market = params?.market;
    const conviction = params?.conviction;
    const action = params?.action;
    const criticVerdict = params?.critic_verdict;
    let items = fx.RECOMMENDATIONS;
    if (market) items = items.filter((r) => r.market === market);
    if (conviction) items = items.filter((r) => r.conviction === conviction);
    if (action) items = items.filter((r) => r.action === action);
    if (criticVerdict) items = items.filter((r) => r.critic_verdict === criticVerdict);
    return { items, total: items.length };
  }
  if (seg[0] === "recommendations" && seg[2] === "feedback") {
    return { accepted: true };
  }
  if (seg[0] === "recommendations" && seg.length === 2) {
    const found = fx.RECOMMENDATIONS.find((r) => r.rec_id === seg[1]);
    if (!found) throw new ApiError("not-found", "推奨が見つかりません", 404);
    return found;
  }

  // 3) /screener
  if (seg[0] === "screener" && seg.length === 1) {
    if (empty) return { rows: [], universe_size: 1842 };
    return { rows: fx.SCREENER_ROWS, universe_size: 1842 };
  }
  if (seg[0] === "screener" && seg[1] === "fields") return fx.SCREENER_FIELDS;
  if (seg[0] === "screener" && seg[1] === "presets") return fx.SCREENER_PRESETS;
  if (seg[0] === "screener" && seg[1] === "saved") return [];

  // 4) /scores
  if (seg[0] === "scores") return fx.SCREENER_ROWS;

  // 5) /stocks/...
  if (seg[0] === "stocks" && seg[1] === "search") {
    const q = String(params?.q ?? "").toLowerCase();
    if (!q) return fx.SEARCH_HITS.filter((h) => h.group !== "securities");
    return fx.SEARCH_HITS.filter(
      (h) => h.ticker.toLowerCase().includes(q) || h.name_local.toLowerCase().includes(q),
    );
  }
  if (seg[0] === "stocks" && seg.length >= 3) {
    const ticker = seg[2]!;
    const sub = seg[3];
    const detail = fx.stockDetailFor(ticker);
    if (!detail) throw new ApiError("not-found", "銘柄が見つかりません", 404);
    if (!sub) return detail;
    if (sub === "prices") return fx.priceSeries(ticker, detail.ref_price ?? 1000);
    if (sub === "financials") return ticker === "7203" ? fx.FINANCIALS_7203 : [];
    if (sub === "features") return ticker === "7203" ? fx.FEATURES_7203 : { ...fx.FEATURES_7203, factors: [] };
    if (sub === "documents") return fx.FILINGS.filter((f) => f.ticker === ticker);
    if (sub === "recommendations") return ticker === "7203" ? fx.REC_HISTORY_7203 : [];
    if (sub === "peers") return ticker === "7203" ? fx.PEERS_7203 : [];
  }

  // 6) /documents
  if (seg[0] === "documents" && seg.length === 1) {
    if (empty) return [];
    const docType = params?.doc_type;
    const rows = docType ? fx.FILINGS.filter((f) => f.doc_type === docType) : fx.FILINGS;
    return rows;
  }
  if (seg[0] === "documents" && seg[2] === "summary") {
    const found = fx.FILING_SUMMARIES[seg[1]!];
    if (method === "POST") {
      // オンデマンド生成。未要約の資料に対しても何か返す
      return (
        found ?? {
          ...fx.FILING_SUMMARIES.f001!,
          doc_id: seg[1]!,
          headline_ja: "要約を生成しました（モック）",
          cost_usd: 0.008,
          generated_at: new Date().toISOString(),
        }
      );
    }
    if (!found) throw new ApiError("not-found", "この資料の要約はまだありません", 404);
    return found;
  }
  if (seg[0] === "documents" && seg[2] === "chunks") return [];
  if (seg[0] === "documents" && seg.length === 2) {
    const found = fx.FILINGS.find((f) => f.doc_id === seg[1]);
    if (!found) throw new ApiError("not-found", "資料が見つかりません", 404);
    return found;
  }

  // 7) /fx, /macro
  if (seg[0] === "fx" && seg[2] === "history") return fx.FX_DATA.history;
  if (seg[0] === "fx" && seg[2] === "models") return fx.FX_MODEL_COMPARISON;
  if (seg[0] === "fx") return fx.FX_DATA;
  if (seg[0] === "macro" && seg[1] === "series") return fx.MACRO_SERIES;
  if (seg[0] === "macro" && seg[1] === "rate-differential") return fx.RATE_DIFF_SERIES;
  if (seg[0] === "macro" && seg[1] === "fx-sensitivity") return fx.FX_SENSITIVITY;

  // 8) /models, /backtests, /factor-weights
  if (seg[0] === "models" && seg[1] === "health") return fx.MODEL_HEALTH;
  if (seg[0] === "models" && seg[1] === "runs" && seg[3] === "feature-importance") return fx.FEATURE_IMPORTANCE;
  if (seg[0] === "models" && seg[1] === "runs" && seg[3] === "ic-timeseries") return fx.IC_SERIES;
  if (seg[0] === "models" && seg[1] === "runs" && seg[3] === "quintiles") return fx.QUINTILES;
  if (seg[0] === "models" && seg[1] === "runs" && seg[2]) {
    const run = fx.MODEL_RUNS.find((r) => r.run_id === seg[2]);
    if (!run) throw new ApiError("not-found", "学習実行が見つかりません", 404);
    return run;
  }
  if (seg[0] === "models" && seg[1] === "runs") return fx.MODEL_RUNS;
  if (seg[0] === "models" && seg[1] === "leakage-checks") return fx.LEAKAGE_CHECKS;
  if (seg[0] === "backtests" && seg.length === 1) {
    if (method === "POST") return { job_run_id: 1047, status: "running" };
    return empty ? [] : fx.BACKTESTS;
  }
  if (seg[0] === "backtests" && seg[2] === "equity-curve") {
    return fx.PERFORMANCE;
  }
  if (seg[0] === "backtests" && seg.length >= 2) {
    const bt = fx.BACKTESTS.find((b) => b.backtest_id === seg[1]);
    if (!bt) throw new ApiError("not-found", "バックテストが見つかりません", 404);
    return bt;
  }
  if (seg[0] === "factor-weights") {
    if (method === "POST" && seg[2] === "reject") return { rejected: true };
    if (method === "POST") return { activated: true };
    return fx.FACTOR_WEIGHTS;
  }

  // 9) /agent
  if (seg[0] === "agent" && seg[1] === "jobs" && seg.length === 2) {
    if (method === "DELETE") {
      const kept = fx.AGENT_JOBS.filter((j) => j.status === "running");
      const deleted = fx.AGENT_JOBS.length - kept.length;
      fx.AGENT_JOBS.splice(0, fx.AGENT_JOBS.length, ...kept);
      return { ok: true, message_ja: `実行履歴を${deleted}件削除しました。` };
    }
    return empty ? [] : fx.AGENT_JOBS;
  }
  if (seg[0] === "agent" && seg[1] === "jobs" && seg[3] === "run") return { job_run_id: 1048, status: "running" };
  if (seg[0] === "agent" && seg[1] === "jobs" && seg[3] === "cancel") return { cancelled: true };
  if (seg[0] === "agent" && seg[1] === "jobs") {
    const job = fx.AGENT_JOBS.find((j) => String(j.job_run_id) === seg[2]);
    if (!job) throw new ApiError("not-found", "ジョブが見つかりません", 404);
    return job;
  }
  if (seg[0] === "agent" && seg[1] === "cost") return fx.AGENT_COST;
  if (seg[0] === "agent" && seg[1] === "critic-stats") return fx.CRITIC_STATS;
  if (seg[0] === "agent" && seg[1] === "memory" && seg.length === 2) {
    const activeOnly = params?.is_active;
    if (activeOnly === true || activeOnly === "true") return fx.AGENT_MEMORY.filter((m) => m.is_active);
    return empty ? [] : fx.AGENT_MEMORY;
  }
  if (seg[0] === "agent" && seg[1] === "memory") {
    const target = fx.AGENT_MEMORY.find((m) => m.memory_id === seg[2]);
    if (!target) throw new ApiError("not-found", "教訓が見つかりません", 404);
    if (method === "PATCH") {
      const patch = (body ?? {}) as { is_active?: boolean };
      return { ...target, ...patch, updated_at: new Date().toISOString() };
    }
    return target;
  }

  // 10) /portfolio, /trades
  if (seg[0] === "portfolio" && seg[1] === "positions") return empty ? [] : fx.POSITIONS;
  if (seg[0] === "portfolio" && seg[1] === "performance") return fx.PERFORMANCE;
  if (seg[0] === "portfolio") return fx.PORTFOLIO_TOTALS;
  if (seg[0] === "trades" && seg[1] === "analysis") return fx.TRADE_ANALYSIS;
  if (seg[0] === "trades" && seg.length === 1) {
    if (method === "POST") {
      const req = (body ?? {}) as Record<string, unknown>;
      return {
        ...fx.TRADES[0]!,
        ...req,
        trade_id: `t${Date.now()}`,
      };
    }
    return empty ? [] : fx.TRADES;
  }
  if (seg[0] === "trades" && seg.length >= 2) {
    if (method === "DELETE") return { deleted: true };
    const trade = fx.TRADES.find((t) => t.trade_id === seg[1]);
    if (!trade) throw new ApiError("not-found", "記録が見つかりません", 404);
    return trade;
  }

  // 11) /watchlist, /settings, /alerts, /system
  if (seg[0] === "watchlist") {
    if (method === "POST" || method === "DELETE") return { ok: true };
    return empty ? [] : fx.WATCHLIST;
  }
  if (seg[0] === "settings") {
    if (method === "PATCH") {
      const patch = (body ?? {}) as Record<string, unknown>;
      Object.assign(fx.SETTINGS, patch);
      return fx.SETTINGS;
    }
    return fx.SETTINGS;
  }
  if (seg[0] === "alerts" && seg[1] === "read-all") return { updated: fx.ALERTS.length };
  if (seg[0] === "alerts" && seg[2] === "read") return { updated: 1 };
  if (seg[0] === "alerts") {
    if (params?.is_read === false || params?.is_read === "false") {
      return fx.ALERTS.filter((a) => !a.is_read);
    }
    return fx.ALERTS;
  }
  if (seg[0] === "system" && seg[1] === "health") return fx.SYSTEM_HEALTH;
  if (seg[0] === "system" && seg[1] === "freshness") return fx.SYSTEM_FRESHNESS;
  if (seg[0] === "system" && seg[1] === "diagnostics") {
    return {
      report_ja: [
        "診断結果（モック）",
        "ネットワーク  API サーバー 正常",
        "実行環境  PYTHONUTF8 正常",
        "外部API  J-Quants 正常（無料プラン）",
      ].join("\n"),
    };
  }
  if (seg[0] === "system" && seg[1] === "backup") {
    return { ok: true, message_ja: "バックアップを開始しました" };
  }
  if (seg[0] === "system" && seg[1] === "vector-rebuild") {
    return { job_run_id: 1100 };
  }
  if (seg[0] === "system" && seg[1] === "export") {
    return { ok: true };
  }

  throw new ApiError("not-found", `モックが未実装のパスです: ${path}`, 404);
}

export async function handleMock<T>(
  method: string,
  path: string,
  params?: QueryParams,
  body?: unknown,
): Promise<ApiResult<T>> {
  const state = currentState();
  await delay(state === "slow" ? 2600 : 180);

  if (state === "offline") throw new ApiError("offline", "オフラインです");
  if (state === "error") serverError();
  if (state === "not-ready") notReady();

  const data = resolve(method, path, params, body) as T;
  return ok(data);
}
