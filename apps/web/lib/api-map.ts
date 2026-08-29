/**
 * OpenAPI の data 形を画面が読む形へ写す。
 *
 * モックはすでに画面形（配列や平坦オブジェクト）を返すことがあるので、
 * 両方を `??` で受けられるようにする。正本のフィールド名は OpenAPI。
 */

import { unwrapField, unwrapItems } from "./api-client";
import type {
  AgentCost,
  AgentJob,
  AgentMemory,
  Alert,
  AlertCategory,
  Backtest,
  CriticStats,
  DashboardData,
  DocumentSummary,
  DocumentSummaryRow,
  FactorDetail,
  FactorKey,
  FactorWeights,
  FeatureImportance,
  FinancialPeriod,
  FxData,
  FxForecast,
  IcPoint,
  LlmCall,
  MacroSeries,
  Market,
  ModelHealth,
  ModelRun,
  PeerRow,
  PerformancePoint,
  Position,
  PortfolioTotals,
  QuintileReturn,
  RecommendationCard,
  RecommendationHistoryRow,
  RecommendationListData,
  ScreenerData,
  ScreenerField,
  ScreenerPreset,
  ScreenerRow,
  Settings,
  StockDetail,
  StockFeatures,
  StockKeyMetric,
  StockSearchHit,
  SystemFreshness,
  Trade,
  TradeAnalysis,
  WatchlistRow,
} from "./api-types";
import { FACTOR_LABEL_JA } from "./labels";

function rec(v: unknown): Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function str(v: unknown, fallback = ""): string {
  return v == null ? fallback : String(v);
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function num0(v: unknown): number {
  return num(v) ?? 0;
}

function strArr(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x)) : [];
}

function asMarket(v: unknown): Market {
  return v === "US" ? "US" : "JP";
}

function asRatio(v: number | null): number | null {
  if (v == null) return null;
  return v > 1 ? v / 100 : v;
}

const FACTOR_KEYS: FactorKey[] = ["value", "momentum", "quality", "growth", "lowvol", "revision", "liquidity"];

function asFactorKey(v: unknown): FactorKey | null {
  return FACTOR_KEYS.includes(v as FactorKey) ? (v as FactorKey) : null;
}

const PURPOSE_JA: Record<string, string> = {
  doc_summary: "資料要約",
  thesis: "推奨の論拠生成",
  critic: "レビュー",
  evaluator: "教訓の抽出",
  weekly_review: "週次の深掘り",
  embedding: "埋め込み",
};

export const SCREENER_FIELD_CATALOG: ScreenerField[] = [
  { key: "quant_score", label_ja: "定量スコア", group: "スコア", type: "number", min: 0, max: 100, ops: ["gte", "lte", "between"], tooltip_ja: "ファクターの合成スコア（0〜100）" },
  { key: "per", label_ja: "PER（会社予想）", group: "バリュエーション", type: "number", unit: "倍", ops: ["gte", "lte", "between", "is_not_null"], tooltip_ja: "赤字企業は算出できないため null になります" },
  { key: "pbr", label_ja: "PBR", group: "バリュエーション", type: "number", unit: "倍", ops: ["gte", "lte", "between"] },
  { key: "roic", label_ja: "ROIC", group: "クオリティ", type: "percent", ops: ["gte", "lte", "between"] },
  { key: "mom_12m", label_ja: "12ヶ月モメンタム", group: "モメンタム", type: "percent", ops: ["gte", "lte", "between"] },
  { key: "realized_vol_60d", label_ja: "実現ボラティリティ(60営業日)", group: "リスク", type: "percent", ops: ["gte", "lte", "between"] },
  { key: "revision_z", label_ja: "予想改定 z", group: "予想改定", type: "number", ops: ["gte", "lte", "between"] },
  { key: "sector_name", label_ja: "セクター", group: "属性", type: "multiselect", ops: ["in", "not_in"] },
  { key: "next_earnings_in_days", label_ja: "次回決算までの営業日数", group: "イベント", type: "number", unit: "営業日", ops: ["gte", "lte", "is_null"] },
];

const DEFAULT_SETTINGS: Settings = {
  "ui.direction_colors": "jp",
  "ui.theme": "dark",
  "ui.default_market": "JP",
  "ui.number_format": "jp",
  "ui.density": "standard",
  "llm.daily_cap_usd": 1.5,
  "llm.monthly_cap_usd": 20,
  "llm.kill_switch": false,
  "llm.alert_threshold_pct": 0.8,
  "data.jquants_plan": "free",
  "data.tdnet_enabled": false,
  "data.universe": "all",
  "analysis.default_horizon": "H20",
  "analysis.max_recommendations": 12,
  "analysis.max_per_sector": 3,
  "analysis.weight_approval_mode": "manual",
  "notify.web_push_enabled": false,
  "notify.webhook_url": "",
  "notify.quiet_hours": { from: "22:00", to: "07:00" },
};

const KEY_METRIC_META: Array<{ key: keyof Record<string, unknown> | string; label_ja: string; format: StockKeyMetric["format"]; tooltip_ja?: string }> = [
  { key: "market_cap", label_ja: "時価総額", format: "jpy-large" },
  { key: "per_trailing", label_ja: "PER（実績）", format: "multiple" },
  { key: "per_forward", label_ja: "PER（会社予想）", format: "multiple" },
  { key: "pbr", label_ja: "PBR", format: "multiple" },
  { key: "ev_ebitda", label_ja: "EV/EBITDA", format: "multiple" },
  { key: "dividend_yield", label_ja: "配当利回り", format: "percent" },
  { key: "roe", label_ja: "ROE", format: "percent" },
  { key: "roic", label_ja: "ROIC", format: "percent" },
  { key: "equity_ratio", label_ja: "自己資本比率", format: "percent" },
  { key: "realized_vol_60d", label_ja: "実現ボラティリティ(60営業日)", format: "percent" },
  { key: "garch_vol", label_ja: "GARCH予測ボラティリティ", format: "percent" },
  { key: "adv_20d", label_ja: "平均売買代金(20営業日)", format: "jpy-large" },
  { key: "beta_market", label_ja: "ベータ", format: "number" },
  { key: "fx_sensitivity", label_ja: "為替感応度", format: "number", tooltip_ja: "ドル円1%の変化に対する株価の反応（過去60営業日の回帰係数）" },
];

function asAlertCategory(v: unknown): AlertCategory {
  if (v === "data" || v === "cost" || v === "model" || v === "runtime") return v;
  return "data";
}

function asJobStatus(v: unknown): AgentJob["status"] {
  const s = str(v);
  if (
    s === "running" ||
    s === "success" ||
    s === "partial" ||
    s === "failed" ||
    s === "cancelled" ||
    s === "pending" ||
    s === "skipped" ||
    s === "interrupted"
  ) {
    return s;
  }
  return "running";
}

export function mapRecommendationCard(raw: unknown): RecommendationCard {
  const d = rec(raw);
  return {
    ...(d as unknown as RecommendationCard),
    rec_id: str(d.rec_id),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    action: (d.action as RecommendationCard["action"]) ?? "watch",
    horizon: (d.horizon as RecommendationCard["horizon"]) ?? "H20",
    conviction: (d.conviction as RecommendationCard["conviction"]) ?? "medium",
    thesis_ja: str(d.thesis_ja),
    bear_case_ja: str(d.bear_case_ja),
    invalidation_ja: str(d.invalidation_ja),
    reason_codes: strArr(d.reason_codes),
    citations: Array.isArray(d.citations) ? (d.citations as RecommendationCard["citations"]) : [],
  };
}

export function mapRecommendationList(raw: unknown): RecommendationListData {
  const items = unwrapItems(raw).map(mapRecommendationCard);
  const d = rec(raw);
  return {
    items,
    total: num0(d.total) || items.length,
    limit: num(d.limit),
    offset: num(d.offset),
  } as RecommendationListData;
}

export function mapAgentJob(raw: unknown): AgentJob {
  const d = rec(raw);
  const checkpoint = rec(d.checkpoint);
  const progress =
    d.progress && typeof d.progress === "object"
      ? (d.progress as AgentJob["progress"])
      : checkpoint.completed != null
        ? {
            completed: num0(checkpoint.completed),
            total: num0(checkpoint.total),
            eta_sec: num(checkpoint.eta_sec),
          }
        : null;
  return {
    ...(d as unknown as AgentJob),
    job_run_id: num0(d.job_run_id),
    job_name: str(d.job_name),
    status: asJobStatus(d.status),
    trigger: (d.trigger as AgentJob["trigger"]) ?? "schedule",
    failed_steps: strArr(d.failed_steps),
    started_at: str(d.started_at),
    duration_sec: num(d.duration_sec),
    label_ja: d.label_ja == null ? str(d.job_name) : str(d.label_ja),
    output_ja:
      d.output_ja != null
        ? str(d.output_ja)
        : d.output_summary_ja != null
          ? str(d.output_summary_ja)
          : d.error_message != null
            ? str(d.error_message)
            : null,
    output_summary_ja:
      d.output_summary_ja != null
        ? str(d.output_summary_ja)
        : d.output_ja != null
          ? str(d.output_ja)
          : d.error_message != null
            ? str(d.error_message)
            : null,
    error_message: d.error_message != null ? str(d.error_message) : null,
    error_type: d.error_type != null ? str(d.error_type) : null,
    progress,
  };
}

export function mapAgentMemory(raw: unknown): AgentMemory {
  const d = rec(raw);
  const text = str(d.text_ja) || str(d.lesson_ja);
  return {
    ...(d as unknown as AgentMemory),
    memory_id: str(d.memory_id),
    category: (d.category as AgentMemory["category"]) ?? "lesson",
    scope: (d.scope as AgentMemory["scope"]) ?? "global",
    evidence_ja: str(d.evidence_ja),
    is_active: Boolean(d.is_active ?? true),
    lesson_ja: str(d.lesson_ja) || text,
    text_ja: text,
    confidence: num(d.confidence),
    n_samples: num(d.n_samples) ?? num(d.n_observations),
    usage_count_30d: num0(d.usage_count_30d) || num0(d.times_injected_30d) || num0(d.use_count),
    n_after: num(d.n_after) ?? num(d.effect_n_used),
    n_before: num(d.n_before) ?? num(d.effect_n_unused),
    hit_rate_after: num(d.hit_rate_after) ?? num(d.effect_hit_rate_used),
    hit_rate_before: num(d.hit_rate_before) ?? num(d.effect_hit_rate_unused),
  };
}

function mapLlmCall(raw: unknown): LlmCall {
  const d = rec(raw);
  const purpose = str(d.purpose);
  return {
    ...(d as unknown as LlmCall),
    at: str(d.at) || str(d.called_at),
    called_at: str(d.called_at) || str(d.at),
    purpose: (d.purpose as LlmCall["purpose"]) ?? "doc_summary",
    model_id: str(d.model_id) || str(d.model),
    model: str(d.model) || str(d.model_id),
    purpose_ja: str(d.purpose_ja) || PURPOSE_JA[purpose] || purpose,
    duration_sec: num0(d.duration_sec),
    input_tokens: num0(d.input_tokens),
    output_tokens: num0(d.output_tokens),
    cost_usd: num0(d.cost_usd),
    cache_hit: Boolean(d.cache_hit),
    status: str(d.status, "success"),
  };
}

export function mapAgentCost(raw: unknown): AgentCost {
  const d = rec(raw);
  const today = num0(d.spent_today_usd) || num0(d.today_usd);
  const month = num0(d.spent_month_usd) || num0(d.month_usd);
  const byPurpose = unwrapField(d, "by_purpose");
  const breakdown =
    Array.isArray(d.breakdown) && d.breakdown.length
      ? (d.breakdown as AgentCost["breakdown"])
      : byPurpose.map((row) => {
          const r = rec(row);
          const purpose = str(r.purpose);
          const hits = num(r.cache_hits);
          const misses = num(r.cache_misses);
          return {
            purpose_ja: str(r.label_ja) || PURPOSE_JA[purpose] || purpose,
            usd: num0(r.today_usd) || num0(r.usd),
            calls: num0(r.calls) || num0(r.cache_hits) + num0(r.cache_misses),
            share_pct: num0(r.share) || num0(r.share_pct),
            cache_hit_ja: hits != null && misses != null ? `${hits} / ${hits + misses}件` : null,
          };
        });
  const callsRaw = Array.isArray(d.calls) && d.calls.length ? d.calls : unwrapField(d, "recent_calls");
  return {
    ...(d as unknown as AgentCost),
    period: str(d.period, "daily"),
    today_usd: num0(d.today_usd) || today,
    daily_cap_usd: num0(d.daily_cap_usd),
    month_usd: num0(d.month_usd) || month,
    monthly_cap_usd: num0(d.monthly_cap_usd),
    projected_month_usd: num(d.projected_month_usd),
    kill_switch: Boolean(d.kill_switch),
    spent_today_usd: today,
    spent_month_usd: month,
    breakdown,
    calls: callsRaw.map(mapLlmCall),
  };
}

export function mapCriticStats(raw: unknown): CriticStats {
  const d = rec(raw);
  const reasons = unwrapField(d, "reasons").map((row) => {
    const r = rec(row);
    return { code: str(r.code), label_ja: str(r.label_ja) || str(r.code), count: num0(r.count) };
  });
  const nReviewed = num0(d.n_reviewed) || num0(d.n_total);
  return {
    ...(d as unknown as CriticStats),
    days: num0(d.days) || 30,
    n_reviewed: nReviewed,
    n_total: num0(d.n_total) || nReviewed,
    n_approved: num0(d.n_approved),
    n_revised: num0(d.n_revised),
    n_rejected: num0(d.n_rejected),
    rejection_rate: num0(d.rejection_rate),
    revision_rate: num0(d.revision_rate),
    reasons,
  };
}

export function mapAlert(raw: unknown): Alert {
  const d = rec(raw);
  return {
    ...(d as unknown as Alert),
    alert_id: str(d.alert_id),
    severity: (d.severity as Alert["severity"]) ?? "info",
    category: asAlertCategory(d.category),
    title_ja: str(d.title_ja),
    is_read: Boolean(d.is_read),
    created_at: str(d.created_at),
  };
}

export function mapWatchlistRow(raw: unknown): WatchlistRow {
  const d = rec(raw);
  return {
    ...(d as unknown as WatchlistRow),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    ref_price: num(d.ref_price),
    change_pct: num(d.change_pct),
    ref_price_currency: str(d.ref_price_currency, "JPY"),
    quant_score: num(d.quant_score) ?? num(d.total_score),
    next_earnings_in_days: num(d.next_earnings_in_days) ?? num(d.days_to_earnings),
    new_filing_count: num0(d.new_filing_count) || num0(d.filings_today),
  };
}

export function mapModelRun(raw: unknown): ModelRun {
  const d = rec(raw);
  const metrics = rec(d.metrics);
  const started = str(d.started_at);
  const finished = str(d.finished_at);
  let duration = num(d.duration_sec);
  if (duration == null && started && finished) {
    const a = Date.parse(started);
    const b = Date.parse(finished);
    if (Number.isFinite(a) && Number.isFinite(b)) duration = Math.max(0, (b - a) / 1000);
  }
  return {
    ...(d as unknown as ModelRun),
    run_id: str(d.run_id),
    model_kind: (d.model_kind as ModelRun["model_kind"]) ?? "ranker",
    kind: (d.kind as ModelRun["kind"]) ?? (d.model_kind as ModelRun["kind"]) ?? "ranker",
    status: str(d.status, "success"),
    val_auc: num(d.val_auc) ?? num(metrics.val_auc),
    rank_ic_60d: num(d.rank_ic_60d) ?? num(metrics.rank_ic_60d) ?? num(metrics.rank_ic),
    duration_sec: duration,
  };
}

function asHealthStatus(v: unknown): ModelHealth["status"] {
  if (v === "normal" || v === "watch" || v === "degraded" || v === "not_trained") return v;
  return "normal";
}

export function mapModelHealth(raw: unknown): ModelHealth {
  const d = rec(raw);
  return {
    ...(d as unknown as ModelHealth),
    status: asHealthStatus(d.status),
    rank_ic_20d: num(d.rank_ic_20d),
    rank_ic_3m: num(d.rank_ic_3m),
    rank_ic_percentile_1y: num(d.rank_ic_percentile_1y),
    coverage_rate: num(d.coverage_rate) ?? num(d.coverage_pct),
    coverage_pct: num(d.coverage_pct) ?? num(d.coverage_rate),
    coverage_detail_ja: d.coverage_detail_ja != null ? str(d.coverage_detail_ja) : d.coverage_note_ja != null ? str(d.coverage_note_ja) : null,
    degradation_detected: Boolean(d.degradation_detected),
    degradation_note_ja: d.degradation_note_ja != null ? str(d.degradation_note_ja) : null,
  };
}

export function mapFeatureImportance(raw: unknown): FeatureImportance {
  const d = rec(raw);
  const name = str(d.name) || str(d.feature);
  return {
    ...(d as unknown as FeatureImportance),
    feature: str(d.feature) || name,
    name,
    label_ja: str(d.label_ja, name),
    gain: num0(d.gain) || num0(d.value),
    value: num0(d.value) || num0(d.gain),
  };
}

export function mapFeatureImportanceList(raw: unknown): FeatureImportance[] {
  return unwrapField(raw, "items").map(mapFeatureImportance);
}

export function mapIcPoint(raw: unknown): IcPoint {
  const d = rec(raw);
  const date = str(d.date) || str(d.as_of);
  const ic = num0(d.ic) || num0(d.rank_ic);
  return {
    ...(d as unknown as IcPoint),
    as_of: str(d.as_of) || date,
    date,
    rank_ic: num(d.rank_ic) ?? ic,
    ic,
    rolling_20d: num(d.rolling_20d),
  };
}

export function mapIcSeries(raw: unknown): IcPoint[] {
  const points = unwrapField(raw, "points").map(mapIcPoint);
  return points.map((p, i) => {
    if (p.rolling_20d != null) return p;
    const window = points.slice(Math.max(0, i - 19), i + 1);
    if (window.length < 5) return p;
    const avg = window.reduce((a, b) => a + b.ic, 0) / window.length;
    return { ...p, rolling_20d: avg };
  });
}

export function mapQuintile(raw: unknown): QuintileReturn {
  const d = rec(raw);
  const q = d.quintile;
  const label = str(d.label_ja) || (q != null ? `第${q}分位` : "");
  return {
    quintile: String(q ?? label),
    label_ja: label,
    excess_ret_ann: num0(d.excess_ret_ann) || num0(d.mean_excess_return),
  };
}

export function mapQuintileList(raw: unknown): QuintileReturn[] {
  if (Array.isArray(raw)) return raw.map(mapQuintile);
  const d = rec(raw);
  const rows = unwrapField(d, "quintiles");
  if (rows.length) return rows.map(mapQuintile);
  return unwrapItems(d).map(mapQuintile);
}

export function mapBacktest(raw: unknown): Backtest {
  const d = rec(raw);
  const nested = rec(d.cost);
  const fee = num(nested.fee_bps) ?? num(d.fee_bps) ?? 0;
  const slip = num(nested.slippage_bps) ?? num(d.slippage_bps) ?? 0;
  const turn = asRatio(num(nested.max_turnover_pct) ?? num(d.max_turnover_pct)) ?? 0;
  let status: Backtest["status"];
  if (d.status === "significant" || d.status === "not_significant" || d.status === "failed" || d.status === "running") {
    status = d.status;
  } else if (d.status === "success" || d.status === "completed") {
    status = d.is_significant ? "significant" : "not_significant";
  } else if (typeof d.is_significant === "boolean") {
    status = d.is_significant ? "significant" : "not_significant";
  } else if (d.status === "error") {
    status = "failed";
  } else {
    status = "running";
  }
  const costTurnover = nested.max_turnover_pct != null ? (asRatio(num(nested.max_turnover_pct)) ?? turn) : turn;
  return {
    ...(d as unknown as Backtest),
    backtest_id: str(d.backtest_id),
    strategy_name: str(d.strategy_name),
    market: asMarket(d.market),
    status,
    fee_bps: fee,
    slippage_bps: slip,
    max_turnover_pct: turn,
    cost: {
      fee_bps: fee,
      slippage_bps: slip,
      max_turnover_pct: costTurnover,
      pre_tax: nested.pre_tax != null ? Boolean(nested.pre_tax) : true,
    },
    sharpe: num(d.sharpe),
    deflated_sharpe: num(d.deflated_sharpe),
    information_ratio: num(d.information_ratio),
    ann_return: num(d.ann_return) ?? num(d.annualized_return) ?? num(d.cagr) ?? num(d.gross_annualized_return),
    turnover_pct: asRatio(num(d.turnover_pct) ?? num(d.realized_turnover_pct) ?? num(d.avg_turnover)),
    total_cost_pct: num(d.total_cost_pct) ?? (num(d.total_cost_bps) != null ? num0(d.total_cost_bps) / 10_000 : null),
    n_trades: num(d.n_trades),
  };
}

export function mapEquityCurve(raw: unknown): PerformancePoint[] {
  return unwrapField(raw, "points").map((row) => {
    const r = rec(row);
    return {
      date: str(r.date),
      portfolio_index: num0(r.portfolio_index) || num0(r.equity),
      benchmark_index: num0(r.benchmark_index) || num0(r.benchmark) || num0(r.equity),
    };
  });
}

export function mapPerformance(raw: unknown): PerformancePoint[] {
  if (Array.isArray(raw)) return raw.map((row) => {
    const r = rec(row);
    return {
      date: str(r.date),
      portfolio_index: num0(r.portfolio_index) || num0(r.equity),
      benchmark_index: num0(r.benchmark_index) || num0(r.benchmark),
    };
  });
  return mapEquityCurve(raw);
}

export function mapFactorWeights(raw: unknown): FactorWeights {
  const d = rec(raw);
  if (Array.isArray(d.rows)) {
    return d as unknown as FactorWeights;
  }
  const active = rec(d.active);
  const proposed = rec(d.proposed);
  const activeWeights = rec(active.weights);
  const proposedWeights = rec(proposed.weights);
  const keys = new Set([...Object.keys(activeWeights), ...Object.keys(proposedWeights), ...FACTOR_KEYS]);
  const rows = [...keys].flatMap((key) => {
    const fk = asFactorKey(key);
    if (!fk) return [];
    const aw = num0(activeWeights[fk]);
    const pw = proposed.weight_set_id ? num(proposedWeights[fk]) : null;
    return [
      {
        factor_key: fk,
        label_ja: FACTOR_LABEL_JA[fk],
        active_weight: aw,
        proposed_weight: pw,
        delta: pw != null ? pw - aw : null,
      },
    ];
  });
  return {
    active_weight_set_id: str(d.active_weight_set_id) || str(active.weight_set_id),
    proposed_weight_set_id: d.proposed_weight_set_id != null ? str(d.proposed_weight_set_id) : proposed.weight_set_id != null ? str(proposed.weight_set_id) : null,
    rows,
    fit_meta_ja: d.fit_meta_ja != null ? str(d.fit_meta_ja) : [active.fit_method, active.period_ja].filter(Boolean).join(" · ") || null,
    n_samples: num(d.n_samples) ?? num(active.n_samples) ?? num(proposed.n_samples),
  };
}

export function mapPosition(raw: unknown): Position {
  const d = rec(raw);
  return {
    ...(d as unknown as Position),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    quantity: num0(d.quantity),
    avg_cost: num0(d.avg_cost),
    currency: str(d.currency, "JPY"),
    ref_price: num(d.ref_price),
    holding_days: num(d.holding_days),
    unrealized_pnl: num(d.unrealized_pnl) ?? num(d.unrealized_pl_jpy),
    unrealized_pnl_pct: num(d.unrealized_pnl_pct) ?? num(d.unrealized_pl_pct),
    weight_pct: num(d.weight_pct) ?? num(d.weight),
    quant_score: num(d.quant_score) ?? num(d.total_score),
    next_earnings_in_days: num(d.next_earnings_in_days),
    market_value: num(d.market_value) ?? num(d.market_value_jpy),
    current_view: (d.current_view as Position["current_view"]) ?? null,
  };
}

export function mapPortfolio(raw: unknown): PortfolioTotals {
  const d = rec(raw);
  if (d.total_value != null && d.currency_split_ja != null) {
    return d as unknown as PortfolioTotals;
  }
  const split = rec(d.currency_split);
  const parts = Object.entries(split)
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${k === "USD" ? "米ドル" : k === "JPY" ? "円" : k} ${Math.round(num0(v) * 100)}%`);
  return {
    total_value: num0(d.total_value) || num0(d.market_value_jpy) || num0(d.market_value),
    currency: str(d.currency) || str(d.base_currency, "JPY"),
    unrealized_pnl: num0(d.unrealized_pnl) || num0(d.unrealized_pl_jpy),
    unrealized_pnl_pct: num0(d.unrealized_pnl_pct) || num0(d.unrealized_pl_pct),
    realized_pnl_ytd: num0(d.realized_pnl_ytd) || num0(d.realized_pl_ytd_jpy),
    cash: num0(d.cash) || num0(d.cash_jpy),
    n_positions: num0(d.n_positions),
    currency_split_ja: str(d.currency_split_ja) || parts.join(" / ") || "—",
    ref_price_note_ja: str(d.ref_price_note_ja, "評価額は15分遅延の参考価格ベースです"),
  };
}

export function mapTrade(raw: unknown): Trade {
  const d = rec(raw);
  return {
    ...(d as unknown as Trade),
    trade_id: str(d.trade_id),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    side: (d.side as Trade["side"]) ?? "buy",
    quantity: num0(d.quantity),
    price: num0(d.price),
    currency: str(d.currency, "JPY"),
    executed_at: str(d.executed_at),
    thesis_ja: str(d.thesis_ja),
    emotion_tag: (d.emotion_tag as Trade["emotion_tag"]) ?? null,
  };
}

export function mapTradeAnalysis(raw: unknown): TradeAnalysis {
  const d = rec(raw);
  const rq = rec(d.recommendation_quality);
  const eq = rec(d.execution_quality);
  const byConv = (rq.by_conviction as TradeAnalysis["recommendation_quality"]["by_conviction"]) ?? { high: 0, medium: 0, low: 0 };
  const nByConv =
    (rq.n_by_conviction as TradeAnalysis["recommendation_quality"]["n_by_conviction"]) ??
    (rq.by_conviction_n as TradeAnalysis["recommendation_quality"]["n_by_conviction"]) ?? { high: 0, medium: 0, low: 0 };
  const byEmo = (eq.by_emotion_tag as Record<string, number>) ?? {};
  const nByEmo = (eq.n_by_emotion_tag as Record<string, number>) ?? (eq.by_emotion_tag_n as Record<string, number>) ?? {};
  return {
    ...(d as unknown as TradeAnalysis),
    recommendation_quality: {
      n_recommendations: num0(rq.n_recommendations),
      hit_rate: num(rq.hit_rate),
      avg_excess_return: num(rq.avg_excess_return),
      by_conviction: { high: num0(byConv.high), medium: num0(byConv.medium), low: num0(byConv.low) },
      n_by_conviction: { high: num0(nByConv.high), medium: num0(nByConv.medium), low: num0(nByConv.low) },
      monotonic: rq.monotonic == null ? true : Boolean(rq.monotonic),
      note_ja: rq.note_ja != null ? str(rq.note_ja) : "",
    },
    execution_quality: {
      n_trades: num0(eq.n_trades),
      n_from_recommendation: num0(eq.n_from_recommendation),
      n_discretionary: num0(eq.n_discretionary),
      hit_rate_from_rec: num(eq.hit_rate_from_rec),
      hit_rate_discretionary: num(eq.hit_rate_discretionary),
      avg_slippage_vs_ref_bps: num0(eq.avg_slippage_vs_ref_bps),
      avg_holding_days: num0(eq.avg_holding_days),
      planned_holding_days: num0(eq.planned_holding_days),
      by_emotion_tag: byEmo as TradeAnalysis["execution_quality"]["by_emotion_tag"],
      n_by_emotion_tag: nByEmo as TradeAnalysis["execution_quality"]["n_by_emotion_tag"],
      note_ja: eq.note_ja != null ? str(eq.note_ja) : null,
    },
  };
}

export function mapSettings(raw: unknown): Settings {
  const d = rec(raw);
  const values = d.values && typeof d.values === "object" ? rec(d.values) : d;
  const quiet = rec(values["notify.quiet_hours"]);
  return {
    ...DEFAULT_SETTINGS,
    ...(values as Partial<Settings>),
    "notify.quiet_hours": {
      from: str(quiet.from, DEFAULT_SETTINGS["notify.quiet_hours"].from),
      to: str(quiet.to, DEFAULT_SETTINGS["notify.quiet_hours"].to),
    },
  };
}

export function mapScreenerPreset(raw: unknown): ScreenerPreset {
  const d = rec(raw);
  return {
    ...(d as unknown as ScreenerPreset),
    preset_id: str(d.preset_id) || str(d.id),
    name_ja: str(d.name_ja) || str(d.label_ja),
    id: str(d.id) || str(d.preset_id),
    label_ja: str(d.label_ja) || str(d.name_ja),
    description_ja: d.description_ja != null ? str(d.description_ja) : null,
    filters: Array.isArray(d.filters) ? (d.filters as ScreenerPreset["filters"]) : [],
    is_cautionary: Boolean(d.is_cautionary),
  };
}

export function mapScreenerRow(raw: unknown): ScreenerRow {
  const d = rec(raw);
  return {
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    sector_name: str(d.sector_name),
    quant_score: num(d.quant_score) ?? num(d.total_score),
    ref_price: num(d.ref_price),
    currency: str(d.currency, "JPY"),
    change_pct: num(d.change_pct),
    value_z: num(d.value_z),
    quality_z: num(d.quality_z),
    revision_z: num(d.revision_z),
    per: num(d.per) ?? num(d.per_forward) ?? num(d.per_trailing),
    pbr: num(d.pbr),
    roic: num(d.roic),
    mom_12m: num(d.mom_12m) ?? num(d.momentum_z),
    realized_vol_60d: num(d.realized_vol_60d),
    ml_pred_h20: num(d.ml_pred_h20),
    ml_pred_h20_lo: num(d.ml_pred_h20_lo),
    ml_pred_h20_hi: num(d.ml_pred_h20_hi),
    reason_codes: strArr(d.reason_codes),
    next_earnings_in_days: num(d.next_earnings_in_days) ?? num(d.days_to_earnings),
  };
}

export function mapScreener(raw: unknown): ScreenerData {
  const d = rec(raw);
  const rows = unwrapField(d, "rows").map(mapScreenerRow);
  return {
    rows,
    universe_size: num0(d.universe_size) || num0(d.total) || rows.length,
  };
}

export function mapDocumentRow(raw: unknown): DocumentSummaryRow {
  const d = rec(raw);
  return {
    doc_id: str(d.doc_id),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    doc_type: str(d.doc_type),
    title: str(d.title),
    filed_at: str(d.filed_at),
    source: str(d.source),
    has_summary: Boolean(d.has_summary),
    has_local_copy: Boolean(d.has_local_copy),
    guidance_tone: (d.guidance_tone as DocumentSummaryRow["guidance_tone"]) ?? (d.tone as DocumentSummaryRow["guidance_tone"]) ?? null,
    summary_preview_ja: d.summary_preview_ja != null ? str(d.summary_preview_ja) : null,
    info_value_score: num(d.info_value_score) ?? num(d.info_value_rank),
    estimated_summary_cost_usd: num(d.estimated_summary_cost_usd),
  };
}

export function mapDocumentSummary(raw: unknown): DocumentSummary {
  const d = rec(raw);
  const risks = Array.isArray(d.risks_ja) ? d.risks_ja.map(String) : Array.isArray(d.risk_factors_ja) ? d.risk_factors_ja.map(String) : [];
  return {
    ...(d as unknown as DocumentSummary),
    doc_id: str(d.doc_id),
    headline_ja: str(d.headline_ja),
    key_points_ja: Array.isArray(d.key_points_ja) ? d.key_points_ja.map(String) : [],
    risks_ja: risks,
    guidance_tone: (d.guidance_tone as DocumentSummary["guidance_tone"]) ?? "neutral",
    summary_ja: d.summary_ja != null ? str(d.summary_ja) : undefined,
    tone_reason_ja: d.tone_reason_ja != null ? str(d.tone_reason_ja) : d.tone_rationale_ja != null ? str(d.tone_rationale_ja) : null,
    model: d.model != null ? str(d.model) : d.model_id != null ? str(d.model_id) : undefined,
    generated_at: d.generated_at != null ? str(d.generated_at) : d.computed_at != null ? str(d.computed_at) : undefined,
    cost_usd: num(d.cost_usd),
  };
}

function mapKeyMetrics(metrics: Record<string, unknown>, currency: string): StockKeyMetric[] {
  const isUsd = currency === "USD";
  return KEY_METRIC_META.map((m) => {
    let format = m.format;
    if (m.format === "jpy-large" && isUsd) format = "usd";
    return {
      key: m.key,
      label_ja: m.label_ja,
      value: num(metrics[m.key]),
      format,
      tooltip_ja: m.tooltip_ja,
    };
  });
}

export function mapStockDetail(raw: unknown): StockDetail {
  const d = rec(raw);
  if (d.ticker && Array.isArray(d.key_metrics)) {
    return d as unknown as StockDetail;
  }
  const security = rec(d.security);
  const metrics = rec(d.key_metrics);
  const currency = str(d.currency) || str(security.currency, "JPY");
  const keyMetrics = Array.isArray(d.key_metrics)
    ? (d.key_metrics as StockKeyMetric[])
    : mapKeyMetrics(metrics, currency);
  return {
    ticker: str(d.ticker) || str(security.ticker),
    market: asMarket(d.market ?? security.market),
    name_local: str(d.name_local) || str(security.name_local),
    name_en: d.name_en != null ? str(d.name_en) : security.name_en != null ? str(security.name_en) : null,
    exchange: str(d.exchange) || str(security.exchange_ja) || str(security.exchange),
    sector_name: str(d.sector_name) || str(security.sector_name),
    currency,
    quant_score: num(d.quant_score) ?? num(d.total_score),
    ref_price: num(d.ref_price),
    ref_change_pct: num(d.ref_change_pct),
    ref_change_abs: num(d.ref_change_abs),
    ref_source: str(d.ref_source),
    ref_is_delayed: d.ref_is_delayed == null ? true : Boolean(d.ref_is_delayed),
    ref_note_ja: str(d.ref_note_ja, "15分遅延の参考値です。発注には使えません"),
    ref_as_of: str(d.ref_as_of),
    key_metrics: keyMetrics,
    next_earnings_date: d.next_earnings_date != null ? str(d.next_earnings_date) : metrics.next_earnings_date != null ? str(metrics.next_earnings_date) : null,
  };
}

export function mapFinancialPeriod(raw: unknown): FinancialPeriod {
  const d = rec(raw);
  return {
    ...(d as unknown as FinancialPeriod),
    filed_at: str(d.filed_at),
    period_label_ja: str(d.period_label_ja) || str(d.fiscal_period),
    is_forecast: Boolean(d.is_forecast),
    revenue: num(d.revenue),
    op_income: num(d.op_income) ?? num(d.operating_income),
    op_margin: num(d.op_margin) ?? num(d.operating_margin),
    net_income: num(d.net_income),
    eps: num(d.eps),
    fcf: num(d.fcf) ?? num(d.free_cash_flow),
  };
}

export function mapFinancials(raw: unknown): FinancialPeriod[] {
  return unwrapField(raw, "periods").map(mapFinancialPeriod);
}

function mapFactorDetail(raw: unknown, index: number): FactorDetail {
  const d = rec(raw);
  const key = asFactorKey(d.key) ?? asFactorKey(d.group) ?? FACTOR_KEYS[index % FACTOR_KEYS.length]!;
  const pct = num(d.sector_percentile);
  return {
    key,
    label_ja: str(d.label_ja) || FACTOR_LABEL_JA[key],
    z: num(d.z) ?? num(d.z_score),
    percentile_ja: d.percentile_ja != null ? str(d.percentile_ja) : pct != null ? `上位 ${Math.round((1 - pct) * 100)}%` : null,
    raw_ja: d.raw_ja != null ? str(d.raw_ja) : d.raw_label_ja != null ? str(d.raw_label_ja) : null,
    contribution: num(d.contribution),
  };
}

export function mapStockFeatures(raw: unknown): StockFeatures {
  const d = rec(raw);
  if (Array.isArray(d.factors)) {
    return {
      as_of: str(d.as_of),
      feature_version: str(d.feature_version),
      factors: (d.factors as unknown[]).map(mapFactorDetail),
      note_ja: d.note_ja != null ? str(d.note_ja) : null,
    };
  }
  const rows = unwrapField(d, "rows");
  return {
    as_of: str(d.as_of),
    feature_version: str(d.feature_version),
    factors: rows.map(mapFactorDetail),
    note_ja: d.note_ja != null ? str(d.note_ja) : d.n_missing != null ? `欠損 ${d.n_missing}項目` : null,
  };
}

export function mapPeerRow(raw: unknown): PeerRow {
  const d = rec(raw);
  return {
    ...(d as unknown as PeerRow),
    ticker: str(d.ticker),
    market: asMarket(d.market),
    name_local: str(d.name_local, str(d.ticker)),
    quant_score: num(d.quant_score) ?? num(d.total_score),
    per: num(d.per) ?? num(d.per_forward),
    pbr: num(d.pbr),
    roic: num(d.roic),
    ret_20d: num(d.ret_20d) ?? num(d.return_20d),
    fx_sensitivity: num(d.fx_sensitivity),
  };
}

export function mapPeers(raw: unknown): PeerRow[] {
  return unwrapField(raw, "peers").map(mapPeerRow);
}

export function mapRecHistoryRow(raw: unknown): RecommendationHistoryRow {
  const d = rec(raw);
  const generated = str(d.generated_at) || str(d.as_of);
  return {
    ...(d as unknown as RecommendationHistoryRow),
    rec_id: str(d.rec_id),
    generated_at: generated,
    as_of: str(d.as_of) || generated.slice(0, 10),
    action: (d.action as RecommendationHistoryRow["action"]) ?? "watch",
    horizon: (d.horizon as RecommendationHistoryRow["horizon"]) ?? "H20",
    conviction: (d.conviction as RecommendationHistoryRow["conviction"]) ?? "medium",
    expected_ret: num(d.expected_ret),
    expected_ret_lo: num(d.expected_ret_lo),
    expected_ret_hi: num(d.expected_ret_hi),
    realized_excess_ret: num(d.realized_excess_ret) ?? num(d.realized_ret),
    outcome: str(d.outcome, "pending"),
    pending_days: num(d.pending_days) ?? num(d.pending_business_days_left),
  };
}

export function mapRecHistory(raw: unknown): RecommendationHistoryRow[] {
  if (Array.isArray(raw)) return raw.map(mapRecHistoryRow);
  return unwrapField(raw, "rows").map(mapRecHistoryRow);
}

export function mapSearchHits(raw: unknown): StockSearchHit[] {
  return unwrapItems(raw).map((row) => {
    const d = rec(row);
    return {
      ...(d as unknown as StockSearchHit),
      ticker: str(d.ticker),
      market: asMarket(d.market),
      name_local: str(d.name_local, str(d.ticker)),
    };
  });
}

function mapFxForecast(raw: unknown): FxForecast {
  const d = rec(raw);
  return {
    ...(d as unknown as FxForecast),
    horizon_days: num0(d.horizon_days) || 20,
    model_id: str(d.model_id),
    point: num0(d.point),
    ci_lo_80: num0(d.ci_lo_80),
    ci_hi_80: num0(d.ci_hi_80),
    ci_lo_95: num(d.ci_lo_95),
    ci_hi_95: num(d.ci_hi_95),
    is_baseline: Boolean(d.is_baseline),
    rmse_oos_60d: num(d.rmse_oos_60d) ?? num(d.rmse),
    directional_accuracy_60d: num(d.directional_accuracy_60d) ?? num(d.direction_hit_rate),
    dm_pvalue: num(d.dm_pvalue) ?? num(d.dm_p_value),
    n_validation: num(d.n_validation) ?? num(d.n),
    verdict_ja: str(d.verdict_ja),
    label_ja: str(d.label_ja) || str(d.model_id),
  };
}

function mapHistoryPoints(history: unknown): Array<{ date: string; value: number }> {
  if (Array.isArray(history)) {
    return history.map((row) => {
      const r = rec(row);
      return { date: str(r.date), value: num0(r.value) };
    });
  }
  return unwrapField(history, "points").map((row) => {
    const r = rec(row);
    return { date: str(r.date), value: num0(r.value) };
  });
}

export function mapFxData(raw: unknown, historyRaw?: unknown): FxData {
  const d = rec(raw);
  const official = rec(d.official);
  const reference = rec(d.reference);
  const vol = rec(d.vol_forecast);
  const coint = rec(d.cointegration);
  const rd = rec(d.rate_differential);
  const spot = num0(d.spot) || num0(reference.value) || num0(official.value);
  const history = historyRaw != null ? mapHistoryPoints(historyRaw) : mapHistoryPoints(d.history);
  const forecasts = unwrapField(d, "forecasts").map(mapFxForecast);
  return {
    pair: str(d.pair, "USDJPY"),
    as_of: str(d.as_of),
    spot,
    change_pct: num0(d.change_pct) || num0(reference.change_pct),
    change_abs: num0(d.change_abs) || num0(reference.change_abs),
    spot_source: str(d.spot_source) || str(reference.source) || str(official.source),
    spot_note_ja: str(d.spot_note_ja, "参考値です。約定には使えません"),
    official_source_ja: str(d.official_source_ja) || (official.source ? str(official.source) : ""),
    history,
    forecasts,
    vol_forecast: {
      garch_vol_1d_ann: num(vol.garch_vol_1d_ann),
      garch_vol_20d_ann: num(vol.garch_vol_20d_ann),
      persistence: num(vol.persistence),
    },
    cointegration: {
      tested_pairs: strArr(coint.tested_pairs),
      rank: num0(coint.rank),
      detected: Boolean(coint.detected),
      note_ja: str(coint.note_ja),
    },
    rate_differential: {
      us_10y: num(rd.us_10y),
      jp_10y: num(rd.jp_10y),
      diff: num(rd.diff),
      percentile_5y: num(rd.percentile_5y),
    },
  };
}

export function mapFxModels(raw: unknown): FxForecast[] {
  const d = rec(raw);
  const comparison = unwrapField(d, "model_comparison");
  if (comparison.length) {
    return comparison.map((row) => {
      const r = rec(row);
      return mapFxForecast({
        ...r,
        rmse_oos_60d: r.rmse,
        directional_accuracy_60d: r.direction_hit_rate,
        dm_pvalue: r.dm_p_value,
        n_validation: r.n,
        point: r.point ?? 0,
        ci_lo_80: r.ci_lo_80 ?? 0,
        ci_hi_80: r.ci_hi_80 ?? 0,
        horizon_days: r.horizon_days ?? 20,
      });
    });
  }
  const forecasts = unwrapField(d, "forecasts").map(mapFxForecast);
  const byModel = new Map<string, FxForecast>();
  for (const f of forecasts) {
    const prev = byModel.get(f.model_id);
    if (!prev || f.horizon_days === 20) byModel.set(f.model_id, f);
  }
  return [...byModel.values()];
}

export function mapMacroSeries(raw: unknown): MacroSeries[] {
  return unwrapField(raw, "series").map((row) => {
    const r = rec(row);
    const unitRaw = str(r.unit);
    const unit: MacroSeries["unit"] = unitRaw === "percent-point" || unitRaw === "percent" ? "percent-point" : r.unit === "percent-point" ? "percent-point" : "level";
    return {
      id: str(r.id) || str(r.series_id),
      label_ja: str(r.label_ja) || str(r.series_id),
      value: num(r.value) ?? num(r.latest),
      change: num(r.change) ?? num(r.change_mom),
      unit: r.unit === "percent-point" || r.unit === "level" ? (r.unit as MacroSeries["unit"]) : unit,
      vintage: str(r.vintage) || str(r.vintage_date) || str(r.as_of),
      source: str(r.source, "fred"),
      points: unwrapField(r, "points").map((p) => {
        const pt = rec(p);
        return { date: str(pt.date) || str(pt.observation_date), value: num0(pt.value) };
      }),
    };
  });
}

export function mapRateDifferential(raw: unknown): Array<{ date: string; diff: number; usdjpy: number; spread_10y?: number | null }> {
  if (Array.isArray(raw)) {
    return raw.map((row) => {
      const r = rec(row);
      return {
        date: str(r.date),
        diff: num0(r.diff) || num0(r.spread_10y),
        usdjpy: num0(r.usdjpy),
        spread_10y: num(r.spread_10y),
      };
    });
  }
  return unwrapField(raw, "points").map((row) => {
    const r = rec(row);
    return {
      date: str(r.date),
      diff: num0(r.diff) || num0(r.spread_10y),
      usdjpy: num0(r.usdjpy),
      spread_10y: num(r.spread_10y),
    };
  });
}

export function mapSystemFreshness(raw: unknown): SystemFreshness {
  const d = rec(raw);
  const sources = unwrapField(d, "sources").map((row) => {
    const r = rec(row);
    return {
      ...(r as unknown as SystemFreshness["sources"][number]),
      source: str(r.source),
      latest_as_of: r.latest_as_of != null ? str(r.latest_as_of) : null,
      status: r.status != null ? str(r.status) : null,
    };
  });
  const rank: Record<string, number> = { failed: 3, stale: 2, delayed: 1, ok: 0 };
  let worst: NonNullable<SystemFreshness["worst_status"]> = "ok";
  for (const s of sources) {
    const st = s.status ?? "ok";
    if ((rank[st] ?? 0) > (rank[worst] ?? 0) && (st === "ok" || st === "delayed" || st === "stale" || st === "failed")) {
      worst = st;
    }
  }
  return {
    ...(d as unknown as SystemFreshness),
    sources,
    worst_status: (d.worst_status as SystemFreshness["worst_status"]) ?? worst,
  };
}

export function mapDashboard(raw: unknown): DashboardData {
  const d = rec(raw);
  const fx = rec(d.fx);
  const forecast = rec(fx.forecast_h20);
  const ms = rec(d.market_summary);
  const bench = rec(ms.benchmark);
  const ad = rec(ms.advance_decline);
  const jobs = unwrapItems(d.jobs).map(mapAgentJob);
  const watchlist = unwrapItems(d.watchlist).map(mapWatchlistRow);
  const alerts = unwrapField(d, "alerts").map(mapAlert);
  const filings = unwrapField(d, "watchlist_filings").map(mapDocumentRow);
  const recs = unwrapField(d, "top_recommendations").map(mapRecommendationCard);
  const jobStatus = rec(d.job_status);
  const portfolio = rec(d.portfolio_snapshot);
  return {
    ...(d as unknown as DashboardData),
    market_summary: {
      benchmark: {
        ...(bench as DashboardData["market_summary"]["benchmark"]),
        symbol: str(bench.symbol, "TOPIX"),
        close: num0(bench.close),
        change_pct: num(bench.change_pct),
      },
      advance_decline: {
        advancing: num0(ad.advancing),
        declining: num0(ad.declining),
        unchanged: num0(ad.unchanged),
      },
      vol_regime: (ms.vol_regime as DashboardData["market_summary"]["vol_regime"]) ?? { level: "normal", percentile: null, message_ja: null },
      correlation_regime: (ms.correlation_regime as DashboardData["market_summary"]["correlation_regime"]) ?? { avg_pairwise_corr_60d: null, level: null },
    },
    fx: {
      pair: str(fx.pair, "USDJPY"),
      spot: num(fx.spot),
      change_pct: num(fx.change_pct),
      forecast_h20: {
        point: num0(forecast.point),
        ci_lo_80: num0(forecast.ci_lo_80),
        ci_hi_80: num0(forecast.ci_hi_80),
        note_ja: forecast.note_ja != null ? str(forecast.note_ja) : null,
        beats_baseline: forecast.beats_baseline == null ? null : Boolean(forecast.beats_baseline),
      },
      history: Array.isArray(fx.history) ? (fx.history as NonNullable<DashboardData["fx"]["history"]>) : undefined,
    },
    portfolio_snapshot: {
      ...(portfolio as unknown as DashboardData["portfolio_snapshot"]),
      n_positions: num0(portfolio.n_positions),
      market_value: num(portfolio.market_value) ?? num(portfolio.total_value),
      total_value: num(portfolio.total_value) ?? num(portfolio.market_value),
      unrealized_pnl_pct: num(portfolio.unrealized_pnl_pct),
      top_movers: Array.isArray(portfolio.top_movers) ? (portfolio.top_movers as DashboardData["portfolio_snapshot"]["top_movers"]) : [],
    },
    job_status: {
      last_run: jobStatus.last_run != null ? str(jobStatus.last_run) : jobs[0]?.started_at ?? "",
      status: jobStatus.status as DashboardData["job_status"]["status"],
      failed_steps: strArr(jobStatus.failed_steps),
    },
    model_health: mapModelHealth(d.model_health ?? {}),
    alerts,
    watchlist_filings: filings,
    top_recommendations: recs,
    watchlist,
    jobs,
  };
}
