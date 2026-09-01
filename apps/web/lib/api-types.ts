/**
 * 画面向け API 型。フィールド名とスキーマは OpenAPI 生成物が正。
 *
 * 生成: `uv run python scripts/gen_api_types.py`
 * 検証: `uv run python scripts/gen_api_types.py --check`（T-API-01）
 *
 * 画面の import パス（`./api-types`）と型名は維持する。OpenAPI 側のスキーマ名が
 * 違うものはエイリアス、OpenAPI に無い画面専用の形は末尾に残している。
 */

import type { components } from "./api-types.generated";

export type { components, operations, paths } from "./api-types.generated";

type Schema = components["schemas"];

/** OpenAPI で required だが画面モック／既存 UI がまだ持たないキーを任意にする */
type OptionalKeys<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/** 画面が読むキーから undefined を除く（null は残す） */
type RequiredKeys<T, K extends keyof T> = Omit<T, K> & { [P in K]-?: Exclude<T[P], undefined> };

/* ------------------------------------------------------------------ */
/* 1. 共通                                                            */
/* ------------------------------------------------------------------ */

export type Market = "JP" | "US";
/** 既定市場。`auto` は日本時間15時で JP / US を切り替える */
export type DefaultMarket = Market | "auto";
export type Horizon = "H5" | "H20";
export type Conviction = "low" | "medium" | "high";
export type RecAction = "watch" | "accumulate" | "reduce" | "avoid";
export type CriticVerdict = "approved" | "revised" | "rejected";
export type WarningSeverity = "info" | "warning" | "error";
export type CiLevel = 60 | 80 | 95;

/** 日付は `YYYY-MM-DD`、日時は ISO 8601 UTC。UI 側で JST に変換する */
export type IsoDate = string;
export type IsoDateTime = string;

export type DataFreshness = Schema["DataFreshness"];
export type ApiWarning = Schema["Warning_"];
/** OpenAPI の Meta に無い画面用カウンタは Envelope 外の誤配置。互換のため残す。 */
export type Meta = Schema["Meta"] & {
  excluded_count?: number | null;
  total?: number | null;
  total_matched?: number | null;
  truncated?: boolean;
};

/** `GET /health` 以外の JSON 成功レスポンス。warnings はクライアントで空配列補完する */
export interface Envelope<T> {
  data: T;
  warnings: ApiWarning[];
  meta: Meta;
}

/**
 * RFC 7807 Problem Details。OpenAPI の components.schemas には出てこない
 * （エラーは `HTTPValidationError` と手書きの JSONResponse）。
 */
export interface ProblemDetails {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  latest_available_as_of?: IsoDate;
  spent_today_usd?: number;
  daily_cap_usd?: number;
  resets_at?: IsoDateTime;
  errors?: Array<{ loc?: unknown; msg?: string; type?: string }>;
}

export type LivenessResponse = Schema["LivenessResponse"];
export type HTTPValidationError = Schema["HTTPValidationError"];
export type OkResponse = Schema["OkResponse"];

/* ------------------------------------------------------------------ */
/* 2.1 ダッシュボード                                                  */
/* ------------------------------------------------------------------ */

export type BenchmarkSummary = Schema["BenchmarkQuote"];
export type AdvanceDecline = Schema["AdvanceDecline"];
export type VolRegime = Schema["VolRegime"];
export type CorrelationRegime = Schema["CorrelationRegime"];
export type MarketSummary = {
  benchmark: NonNullable<Schema["MarketSummary"]["benchmark"]> & {
    close: number;
    change_pct: number | null;
    symbol: string;
  };
  advance_decline: NonNullable<Schema["MarketSummary"]["advance_decline"]> & {
    advancing: number;
    declining: number;
  };
  vol_regime: NonNullable<Schema["MarketSummary"]["vol_regime"]>;
  correlation_regime: NonNullable<Schema["MarketSummary"]["correlation_regime"]>;
};
export type FxForecastBrief = Schema["FxForecastBrief"];
export type FxSnapshot = Schema["DashboardFx"] & {
  history?: Array<{ date: IsoDate; value: number }>;
  forecast_h20: NonNullable<Schema["DashboardFx"]["forecast_h20"]> & {
    point: number;
    ci_lo_80: number;
    ci_hi_80: number;
    note_ja: string | null;
  };
};

export type DashboardData = OptionalKeys<
  Omit<Schema["Dashboard"], "fx" | "top_recommendations" | "market_summary" | "portfolio_snapshot" | "job_status" | "model_health" | "alerts" | "watchlist_filings">,
  "market" | "new_filings_count"
> & {
  market_summary: MarketSummary;
  fx: NonNullable<FxSnapshot>;
  portfolio_snapshot: PortfolioSnapshot;
  job_status: JobStatusBrief;
  model_health: ModelHealth;
  alerts: Alert[];
  watchlist_filings: DocumentSummaryRow[];
  top_recommendations: RecommendationCard[];
  watchlist: WatchlistRow[];
  jobs: AgentJob[];
};

export type PortfolioSnapshot = RequiredKeys<Schema["PortfolioSnapshot"], "market_value" | "unrealized_pnl_pct" | "top_movers"> & {
  total_value: number | null;
};
export type JobStatusBrief = RequiredKeys<Schema["JobStatusBrief"], "last_run">;
export type Alert = Omit<Schema["Alert"], "category"> & {
  category: AlertCategory;
};
export type WatchlistFiling = Schema["WatchlistFiling"];

/* ------------------------------------------------------------------ */
/* 2.2 推奨                                                            */
/* ------------------------------------------------------------------ */

export type Citation = Omit<Schema["Citation"], "doc_type"> & {
  doc_type?: Schema["Citation"]["doc_type"] | "form_10q";
};
export type FactorScores = Schema["FactorScores"];
export type FactorKey =
  | "value"
  | "momentum"
  | "quality"
  | "growth"
  | "lowvol"
  | "revision"
  | "liquidity";

/** OpenAPI に無い。画面のファクター表用。`FeatureRow` に近いが key が FactorKey。 */
export interface FactorDetail {
  key: FactorKey;
  label_ja: string;
  z: number | null;
  percentile_ja: string | null;
  raw_ja: string | null;
  contribution: number | null;
}

/**
 * ci_level / factor_details は OpenAPI 未定義（仕様欠落として報告）。
 * 画面が必須表示に使っているため optional で残す。
 */
export type RecommendationCard = Omit<Schema["RecommendationCard"], "citations"> & {
  citations: Citation[];
  ci_level?: CiLevel;
  factor_details?: FactorDetail[];
};

export type RecommendationListData = Schema["RecommendationList"];
export type FeedbackVerdict = Schema["RecommendationFeedbackRequest"]["verdict"];
export type RecommendationFeedbackRequest = Schema["RecommendationFeedbackRequest"];
export type RecommendationOutcome = Schema["RecommendationOutcome"];
export type RecommendationHistory = Schema["RecommendationHistory"];
export type RecommendationHistoryRow = Omit<Schema["RecommendationHistoryRow"], "generated_at"> & {
  generated_at?: string;
  as_of?: IsoDate;
  realized_excess_ret?: number | null;
  pending_days?: number | null;
};
export type RecommendationSummary = Schema["RecommendationSummary"];

/* ------------------------------------------------------------------ */
/* 2.3 スコアとスクリーナー                                             */
/* ------------------------------------------------------------------ */

export type FilterOp = Schema["ScreenerFilter"]["op"];
export type ScreenerFilter = Schema["ScreenerFilter"];
export type ScreenerSort = Schema["ScreenerSort"];
export type ScreenerRequest = Omit<Schema["ScreenerRequest"], "limit" | "offset"> & {
  limit?: number;
  offset?: number;
};
export type ScreenerResult = Schema["ScreenerResult"];
export type ScreenerPreset = OptionalKeys<Schema["ScreenerPreset"], "preset_id" | "name_ja"> & {
  id: string;
  label_ja: string;
  is_cautionary?: boolean;
  filters: ScreenerFilter[];
};
export type SavedScreen = Schema["SavedScreen"];
export type ScoreRow = Schema["ScoreRow"];

/** OpenAPI の `ScreenerResult.rows` は dict。画面の列定義用に残す。 */
export interface ScreenerRow {
  ticker: string;
  market: Market;
  name_local: string;
  sector_name: string;
  quant_score: number | null;
  ref_price: number | null;
  currency: string;
  change_pct: number | null;
  value_z: number | null;
  quality_z: number | null;
  revision_z: number | null;
  per: number | null;
  pbr: number | null;
  roic: number | null;
  mom_12m: number | null;
  realized_vol_60d: number | null;
  ml_pred_h20: number | null;
  ml_pred_h20_lo: number | null;
  ml_pred_h20_hi: number | null;
  reason_codes: string[];
  next_earnings_in_days: number | null;
}

export interface ScreenerData {
  rows: ScreenerRow[];
  universe_size: number;
}

/** OpenAPI に `/screener/fields` が無い。画面モック用。 */
export interface ScreenerField {
  key: string;
  label_ja: string;
  group: string;
  type: "number" | "percent" | "select" | "multiselect" | "boolean" | "date";
  unit?: string | null;
  min?: number | null;
  max?: number | null;
  ops: FilterOp[];
  tooltip_ja?: string | null;
}

/* ------------------------------------------------------------------ */
/* 2.4 銘柄詳細                                                        */
/* ------------------------------------------------------------------ */

export type Security = Schema["Security"];
export type KeyMetrics = Schema["KeyMetrics"];
export type StockDetailApi = Schema["StockDetail"];
export type PriceBar = RequiredKeys<Schema["PriceBar"], "close" | "volume">;
export type PriceSeriesData = Omit<OptionalKeys<Schema["PriceSeriesResponse"], "model_use_forbidden">, "bars"> & {
  bars: PriceBar[];
};
export type FinancialPeriod = Omit<Schema["FinancialPeriod"], "fiscal_period" | "is_restated"> & {
  fiscal_period?: string;
  is_restated?: boolean;
  period_label_ja: string;
  is_forecast?: boolean;
  op_income?: number | null;
  op_margin?: number | null;
  fcf?: number | null;
};
export type FinancialsResponse = Schema["FinancialsResponse"];
export type FeatureRow = Schema["FeatureRow"];
export type FeaturesResponse = Schema["FeaturesResponse"];
export type PeerRow = OptionalKeys<Schema["PeerRow"], "name_local"> & {
  name_local: string;
  quant_score: number | null;
  per: number | null;
  ret_20d: number | null;
  fx_sensitivity: number | null;
  pbr: number | null;
  roic: number | null;
};
export type PeersResponse = Schema["PeersResponse"];
export type SecuritySearchHit = Schema["SecuritySearchHit"];
export type SecuritySearchResult = Schema["SecuritySearchResult"];

/**
 * 画面は銘柄詳細を平坦化して読んでいる。OpenAPI は `security` ネスト +
 * `key_metrics` オブジェクト。マッピング前の画面形を残す。
 */
export interface StockKeyMetric {
  key: string;
  label_ja: string;
  value: number | null;
  format: "jpy" | "usd" | "jpy-large" | "percent" | "multiple" | "number" | "text";
  text_value?: string | null;
  tooltip_ja?: string | null;
}

export interface StockDetail {
  ticker: string;
  market: Market;
  name_local: string;
  name_en?: string | null;
  exchange: string;
  sector_name: string;
  currency: string;
  quant_score: number | null;
  ref_price: number | null;
  ref_change_pct: number | null;
  ref_change_abs: number | null;
  ref_source: string;
  ref_is_delayed: boolean;
  ref_note_ja: string;
  ref_as_of: IsoDateTime;
  key_metrics: StockKeyMetric[];
  next_earnings_date: IsoDate | null;
}

export interface StockFeatures {
  as_of: IsoDate;
  feature_version: string;
  factors: FactorDetail[];
  note_ja: string | null;
}

export type StockSearchHit = SecuritySearchHit & {
  quant_score?: number | null;
  group?: "securities" | "recent" | "holdings";
};

/* ------------------------------------------------------------------ */
/* 2.5 決算資料                                                        */
/* ------------------------------------------------------------------ */

export type GuidanceTone = NonNullable<Schema["Document"]["tone"]>;
export type Document = Schema["Document"];
export type DocumentList = Schema["DocumentList"];
export type DocumentSummary = OptionalKeys<
  Schema["DocumentSummary"],
  "summary_ja" | "model_id" | "computed_at" | "citations" | "summary_version" | "cache_hit"
> & {
  key_points_ja: string[];
  risks_ja: string[];
  guidance_tone: GuidanceTone;
  headline_ja: string;
  summary_ja?: string;
  model_id?: string;
  computed_at?: string;
  citations?: Citation[];
  summary_version?: number;
  cache_hit?: boolean;
  model?: string;
  prompt_version?: string;
  generated_at?: string;
  tone_reason_ja?: string | null;
  cost_usd?: number | null;
};
export type DocumentChunk = Schema["DocumentChunk"];

/** 一覧行。OpenAPI の Document に summary_preview_ja は無い。 */
/** 一覧行。OpenAPI の Document / WatchlistFiling より画面が厚い。 */
export interface DocumentSummaryRow {
  doc_id: string;
  ticker: string;
  market: Market;
  name_local: string;
  doc_type: string;
  title: string;
  filed_at: IsoDateTime;
  source: string;
  source_url?: string;
  has_summary: boolean;
  has_local_copy: boolean;
  local_copy_error_ja?: string | null;
  guidance_tone: GuidanceTone | null;
  summary_preview_ja: string | null;
  info_value_score: number | null;
  estimated_summary_cost_usd: number | null;
}

/* ------------------------------------------------------------------ */
/* 2.6 為替・マクロ                                                    */
/* ------------------------------------------------------------------ */

export type FxForecast = RequiredKeys<
  Schema["FxForecast"],
  "rmse_oos_60d" | "directional_accuracy_60d" | "dm_pvalue" | "n_validation" | "verdict_ja" | "label_ja"
>;
export type FxDetail = Schema["FxDetail"];
export type FxHistory = Schema["FxHistory"];
export type MacroSeriesApi = Schema["MacroSeries"];
export type MacroSeriesResponse = Schema["MacroSeriesResponse"];
export type RateDifferentialPoint = OptionalKeys<Schema["RateDifferentialPoint"], "spread_10y"> & {
  spread_10y?: number | null;
  diff: number;
  usdjpy: number;
};
export type RateDifferentialResponse = Schema["RateDifferentialResponse"];

/**
 * 為替画面が読む形。OpenAPI の FxDetail は official/reference 分離で
 * history / spot_note_ja を持たない。
 */
export interface FxData {
  pair: string;
  as_of: IsoDate;
  spot: number;
  change_pct: number;
  change_abs: number;
  spot_source: string;
  spot_note_ja: string;
  official_source_ja: string;
  history: Array<{ date: IsoDate; value: number }>;
  forecasts: FxForecast[];
  vol_forecast: {
    garch_vol_1d_ann: number | null;
    garch_vol_20d_ann: number | null;
    persistence: number | null;
  };
  cointegration: {
    tested_pairs: string[];
    rank: number;
    detected: boolean;
    note_ja: string;
  };
  rate_differential: {
    us_10y: number | null;
    jp_10y: number | null;
    diff: number | null;
    percentile_5y: number | null;
  };
}

export interface MacroSeries {
  id: string;
  label_ja: string;
  value: number | null;
  change: number | null;
  unit: "percent-point" | "level";
  vintage: IsoDate;
  source: string;
  points?: Array<{ date: IsoDate; value: number }>;
}

/** OpenAPI に `/macro/fx-sensitivity` が無い。 */
export interface FxSensitivityRow {
  ticker: string;
  market: Market;
  name_local: string;
  relation: "holding" | "watchlist";
  fx_sensitivity: number | null;
  op_income_impact_ja: string | null;
  ret_20d: number | null;
  correlation_20d: number | null;
  verdict_ja: string;
}

/* ------------------------------------------------------------------ */
/* 2.7 モデルラボ                                                      */
/* ------------------------------------------------------------------ */

export type ModelRun = OptionalKeys<Schema["ModelRun"], "cv_scheme"> & {
  kind: Schema["ModelRun"]["model_kind"];
  val_auc: number | null;
  rank_ic_60d: number | null;
  duration_sec: number | null;
};
export type ModelHealthApi = Schema["ModelHealth"];
export type ModelHealthBrief = Schema["ModelHealthBrief"];
export type FeatureImportance = OptionalKeys<Schema["FeatureImportance"], "feature" | "gain"> & {
  feature?: string;
  gain?: number;
  name: string;
  value: number;
  label_ja: string;
};
export type IcPoint = OptionalKeys<Schema["IcPoint"], "as_of" | "rank_ic"> & {
  as_of?: IsoDate;
  rank_ic?: number | null;
  date: IsoDate;
  ic: number;
  rolling_20d: number | null;
};
export type Quintile = Schema["Quintile"];
export type BacktestRequest = Omit<Schema["BacktestRequest"], "signal_source" | "universe_filter"> & {
  signal_source?: { type: string; weight_set_id?: string; model_run_id?: string | null };
  universe_filter?: Schema["BacktestRequest"]["universe_filter"];
};

export type BacktestRun = Schema["BacktestRun"];
export type FactorWeightSet = Schema["FactorWeightSet"];
export type FactorWeightsResponse = Schema["FactorWeightsResponse"];
export type JobAccepted = Schema["JobAccepted"];
export type EquityCurve = Schema["EquityCurve"];
export type EquityCurvePoint = Schema["EquityCurvePoint"];

export type ModelHealth = OptionalKeys<Schema["ModelHealth"], "degradation_detected" | "horizon" | "market"> &
  Schema["ModelHealthBrief"] & {
    status: "normal" | "watch" | "degraded" | "not_trained";
    rank_ic_20d: number | null;
    coverage_detail_ja?: string | null;
    drift_feature_count?: number | null;
    degradation_note_ja?: string | null;
    coverage_rate?: number | null;
  };

export interface BacktestCostAssumptions {
  fee_bps: number;
  slippage_bps: number;
  max_turnover_pct: number;
  pre_tax: boolean;
}

/** 画面は入れ子の `cost` と `ann_return` を読む。OpenAPI はフラット。 */
export type Backtest = OptionalKeys<Schema["BacktestRun"], "fee_bps" | "slippage_bps" | "max_turnover_pct"> & {
  fee_bps?: number;
  slippage_bps?: number;
  max_turnover_pct?: number;
  status: "significant" | "not_significant" | "failed" | "running";
  cost: BacktestCostAssumptions;
  sharpe: number | null;
  deflated_sharpe: number | null;
  information_ratio: number | null;
  ann_return: number | null;
  turnover_pct: number | null;
  total_cost_pct: number | null;
  n_trades: number | null;
};

export interface QuintileReturn {
  quintile: string;
  label_ja: string;
  excess_ret_ann: number;
}

/** OpenAPI に `/models/leakage-checks` が無い。 */
export interface LeakageCheck {
  id: string;
  label_ja: string;
  status: "pass" | "fail" | "skipped";
  detail_ja: string | null;
}

export interface FactorWeightRow {
  factor_key: FactorKey;
  label_ja: string;
  active_weight: number;
  proposed_weight: number | null;
  delta: number | null;
}

/** 画面の比較表。OpenAPI は FactorWeightsResponse（active/proposed セット）。 */
export interface FactorWeights {
  active_weight_set_id: string;
  proposed_weight_set_id: string | null;
  rows: FactorWeightRow[];
  fit_meta_ja: string | null;
  n_samples: number | null;
}

/* ------------------------------------------------------------------ */
/* 2.8 エージェント                                                    */
/* ------------------------------------------------------------------ */

export type JobStatus =
  | Schema["JobRun"]["status"]
  | "pending";

export type JobName =
  | "collector"
  | "analyst"
  | "researcher"
  | "strategist"
  | "critic"
  | "evaluator"
  | "weekly_review"
  | "model_retrain"
  | "garch_refit";

export type AgentJob = OptionalKeys<Omit<Schema["JobRun"], "status">, "attempt" | "retry_count"> & {
  status: JobStatus;
  failed_steps: string[];
  started_at: string;
  duration_sec: number | null;
  label_ja: string | null;
  progress?: { completed: number; total: number; eta_sec: number | null } | null;
  output_ja?: string | null;
};

export type LlmCall = OptionalKeys<Schema["LLMCall"], "at" | "purpose" | "model_id"> & {
  at?: string;
  purpose?: Schema["LLMCall"]["purpose"];
  model_id?: string;
  duration_sec: number;
  called_at: string;
  purpose_ja: string;
  model: string;
};
export type AgentMemory = Omit<
  Schema["AgentMemory"],
  "lesson_ja" | "n_observations" | "harmful_flag" | "use_count" | "confidence"
> & {
  /** OpenAPI の正は `lesson_ja`。画面は `text_ja` を読む。queries がコピーする。 */
  lesson_ja?: string;
  n_observations?: number;
  confidence: number | null;
  text_ja: string;
  n_samples: number | null;
  usage_count_30d: number;
  n_before: number | null;
  n_after: number | null;
  hit_rate_after: number | null;
  hit_rate_before: number | null;
};
export type AgentMemoryList = Schema["AgentMemoryList"];
export type CriticStats = Omit<Schema["CriticStats"], "reasons"> & {
  n_total: number;
  reasons: Array<{ code: string; label_ja: string; count: number }>;
};
export type MemoryCategory = Schema["AgentMemory"]["category"];

export type AgentCost = Schema["AgentCost"] & {
  /** OpenAPI の正は `today_usd` / `month_usd`。画面は spent_* を読む。 */
  spent_today_usd: number;
  spent_month_usd: number;
  breakdown: CostBreakdownRow[];
  calls: LlmCall[];
};

export interface CostBreakdownRow {
  purpose_ja: string;
  usd: number;
  calls: number;
  share_pct: number;
  cache_hit_ja: string | null;
}

/* ------------------------------------------------------------------ */
/* 2.9 ポートフォリオ・売買日誌                                          */
/* ------------------------------------------------------------------ */

export type Position = OptionalKeys<Omit<Schema["Position"], "current_view">, "is_open"> & {
  current_view?: RecAction | null;
  ref_price: number | null;
  holding_days: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  weight_pct: number | null;
  quant_score: number | null;
  next_earnings_in_days: number | null;
  market_value: number | null;
};
export type PositionList = Schema["PositionList"];
export type Portfolio = Schema["Portfolio"];
export type Trade = Schema["Trade"] & {
  is_pending_sync?: boolean;
  unrealized_pnl_pct?: number | null;
  thesis_ja: string;
  emotion_tag: EmotionTag | null;
};
export type TradeCreateRequest = Schema["TradeCreate"];
export type TradeAnalysis = Schema["TradeAnalysis"] & {
  recommendation_quality: RequiredKeys<Schema["RecommendationQuality"], "by_conviction" | "hit_rate" | "avg_excess_return" | "monotonic" | "note_ja"> & {
    by_conviction: Record<Conviction, number>;
    n_by_conviction: Record<Conviction, number>;
  };
  execution_quality: Omit<
    Schema["ExecutionQuality"],
    "avg_slippage_vs_ref_bps" | "avg_holding_days" | "planned_holding_days" | "by_emotion_tag"
  > & {
    avg_slippage_vs_ref_bps: number;
    avg_holding_days: number;
    planned_holding_days: number;
    by_emotion_tag: Record<EmotionTag, number>;
    n_by_emotion_tag: Record<EmotionTag, number>;
    note_ja: string | null;
  };
};
export type EmotionTag = NonNullable<Schema["Trade"]["emotion_tag"]>;

export interface PortfolioTotals {
  total_value: number;
  currency: string;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  realized_pnl_ytd: number;
  cash: number;
  n_positions: number;
  currency_split_ja: string;
  ref_price_note_ja: string;
}

export interface PerformancePoint {
  date: IsoDate;
  portfolio_index: number;
  benchmark_index: number;
}

/* ------------------------------------------------------------------ */
/* 2.10 ウォッチリスト・設定・アラート・システム                          */
/* ------------------------------------------------------------------ */

export type DirectionColors = "jp" | "us";
export type ThemeMode = "dark" | "light";
export type AlertCategory = "data" | "cost" | "model" | "runtime";

export interface Settings {
  "ui.direction_colors": DirectionColors;
  "ui.theme": ThemeMode;
  "ui.default_market": DefaultMarket;
  "ui.number_format": "jp" | "intl";
  "ui.density": "standard" | "dense";
  "llm.daily_cap_usd": number;
  "llm.monthly_cap_usd": number;
  "llm.kill_switch": boolean;
  "llm.alert_threshold_pct": number;
  "data.jquants_plan": "free" | "light" | "standard" | "premium";
  "data.tdnet_enabled": boolean;
  "data.universe": string;
  "analysis.default_horizon": Horizon;
  "analysis.max_recommendations": number;
  "analysis.max_per_sector": number;
  "analysis.weight_approval_mode": "manual" | "auto";
  "notify.web_push_enabled": boolean;
  "notify.webhook_url": string;
  "notify.quiet_hours": { from: string; to: string };
}

export type SettingsPatch = Partial<Settings>;
export type SettingsResponse = Schema["SettingsResponse"];

export type WatchlistItem = Schema["WatchlistItem"];
export type WatchlistResponse = Schema["WatchlistResponse"];

export type WatchlistRow = Omit<WatchlistItem, "list_name"> & {
  list_name?: string;
  name_local: string;
  ref_price: number | null;
  change_pct: number | null;
  ref_price_currency: string;
  quant_score: number | null;
  next_earnings_in_days: number | null;
  new_filing_count: number;
};

export type SystemComponent = Schema["HealthComponent"] & {
  label_ja?: string;
};

export type SystemHealth = Schema["SystemHealth"] & {
  version?: string;
  commit?: string;
  node_version?: string;
  os_ja?: string;
  last_backup_ja?: string;
  db_sizes_ja?: string;
  scheduler_alive?: boolean;
  next_run?: IsoDateTime | null;
  last_reboot_ja?: string | null;
  resume_note_ja?: string | null;
  test_results?: LeakageCheck[];
  components?: SystemComponent[];
};

export type FreshnessSource = DataFreshness & {
  api_key_ja?: string | null;
  label_ja?: string | null;
};

export type SystemFreshness = Omit<Schema["FreshnessResponse"], "sources"> & {
  worst_status?: "ok" | "delayed" | "stale" | "failed";
  sources: FreshnessSource[];
};
