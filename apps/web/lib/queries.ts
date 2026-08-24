/**
 * TanStack Query のフックとキー。画面はここだけを呼び、fetch を直接書かない。
 *
 * 再取得の方針は interaction-patterns.md §5 に合わせている:
 * - 自動更新はしない（勝手に数字が変わると判断を誤る）
 * - 手動更新はヘッダの更新ボタン、または画面ごとの再試行
 * - 再取得中も前の値を表示し続ける（placeholderData: keepPreviousData）
 */

"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import {
  ApiError,
  USE_MOCK,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  emptyResult,
  mapResult,
  unwrapItems,
  type ApiResult,
  type QueryParams,
} from "./api-client";
import {
  SCREENER_FIELD_CATALOG,
  mapAgentCost,
  mapAgentJob,
  mapAgentMemory,
  mapAlert,
  mapBacktest,
  mapCriticStats,
  mapDashboard,
  mapDocumentRow,
  mapDocumentSummary,
  mapEquityCurve,
  mapFactorWeights,
  mapFeatureImportanceList,
  mapFinancials,
  mapFxData,
  mapFxModels,
  mapIcSeries,
  mapMacroSeries,
  mapModelHealth,
  mapModelRun,
  mapPeers,
  mapPerformance,
  mapPortfolio,
  mapPosition,
  mapQuintileList,
  mapRateDifferential,
  mapRecHistory,
  mapRecommendationCard,
  mapRecommendationList,
  mapScreener,
  mapScreenerPreset,
  mapSearchHits,
  mapSettings,
  mapStockDetail,
  mapStockFeatures,
  mapSystemFreshness,
  mapTrade,
  mapTradeAnalysis,
  mapWatchlistRow,
} from "./api-map";
import type {
  AgentCost,
  AgentJob,
  AgentMemory,
  Alert,
  Backtest,
  BacktestRequest,
  CriticStats,
  DashboardData,
  DocumentSummary,
  DocumentSummaryRow,
  FactorWeights,
  FeatureImportance,
  FinancialPeriod,
  FxData,
  FxForecast,
  FxSensitivityRow,
  IcPoint,
  LeakageCheck,
  MacroSeries,
  Market,
  ModelHealth,
  ModelRun,
  PeerRow,
  PerformancePoint,
  Position,
  PortfolioTotals,
  PriceSeriesData,
  QuintileReturn,
  RateDifferentialPoint,
  RecommendationHistoryRow,
  RecommendationListData,
  ScreenerData,
  ScreenerField,
  ScreenerPreset,
  ScreenerRequest,
  Settings,
  SettingsPatch,
  StockDetail,
  StockFeatures,
  StockSearchHit,
  SystemFreshness,
  SystemHealth,
  Trade,
  TradeAnalysis,
  TradeCreateRequest,
  WatchlistRow,
} from "./api-types";

export const queryKeys = {
  dashboard: (market: Market) => ["dashboard", market] as const,
  recommendations: (params: QueryParams) => ["recommendations", params] as const,
  screener: (req: ScreenerRequest) => ["screener", req] as const,
  screenerFields: () => ["screener", "fields"] as const,
  screenerPresets: () => ["screener", "presets"] as const,
  stock: (market: Market, ticker: string) => ["stock", market, ticker] as const,
  stockPrices: (market: Market, ticker: string, range: string) =>
    ["stock", market, ticker, "prices", range] as const,
  stockFinancials: (market: Market, ticker: string) => ["stock", market, ticker, "financials"] as const,
  stockFeatures: (market: Market, ticker: string) => ["stock", market, ticker, "features"] as const,
  stockDocuments: (market: Market, ticker: string) => ["stock", market, ticker, "documents"] as const,
  stockRecommendations: (market: Market, ticker: string) => ["stock", market, ticker, "recs"] as const,
  stockPeers: (market: Market, ticker: string) => ["stock", market, ticker, "peers"] as const,
  stockSearch: (q: string) => ["stock", "search", q] as const,
  documents: (params: QueryParams) => ["documents", params] as const,
  documentSummary: (docId: string) => ["documents", docId, "summary"] as const,
  fx: (pair: string) => ["fx", pair] as const,
  fxModels: (pair: string) => ["fx", pair, "models"] as const,
  macroSeries: () => ["macro", "series"] as const,
  rateDifferential: () => ["macro", "rate-differential"] as const,
  fxSensitivity: () => ["macro", "fx-sensitivity"] as const,
  modelRuns: () => ["models", "runs"] as const,
  modelHealth: () => ["models", "health"] as const,
  featureImportance: (runId: string) => ["models", "runs", runId, "feature-importance"] as const,
  icSeries: (runId: string) => ["models", "runs", runId, "ic"] as const,
  quintiles: (runId: string) => ["models", "runs", runId, "quintiles"] as const,
  leakageChecks: () => ["models", "leakage-checks"] as const,
  backtests: () => ["backtests"] as const,
  backtestEquity: (id: string) => ["backtests", id, "equity"] as const,
  factorWeights: (market: Market) => ["factor-weights", market] as const,
  agentJobs: () => ["agent", "jobs"] as const,
  agentCost: () => ["agent", "cost"] as const,
  criticStats: () => ["agent", "critic-stats"] as const,
  agentMemory: () => ["agent", "memory"] as const,
  portfolio: () => ["portfolio"] as const,
  positions: () => ["portfolio", "positions"] as const,
  performance: (range: string) => ["portfolio", "performance", range] as const,
  trades: () => ["trades"] as const,
  tradeAnalysis: () => ["trades", "analysis"] as const,
  watchlist: () => ["watchlist"] as const,
  settings: () => ["settings"] as const,
  alerts: () => ["alerts"] as const,
  systemHealth: () => ["system", "health"] as const,
  systemFreshness: () => ["system", "freshness"] as const,
};

/** 全クエリ共通の既定値。retry は「意味のあるエラーだけ」に絞る */
type Options<T> = Omit<UseQueryOptions<ApiResult<T>, ApiError>, "queryKey" | "queryFn"> & {
  map?: (raw: unknown) => T;
};

function useApiQuery<T>(
  key: readonly unknown[],
  path: string,
  params?: QueryParams,
  options?: Options<T>,
) {
  const { map, ...queryOptions } = options ?? {};
  return useQuery<ApiResult<T>, ApiError>({
    queryKey: key,
    queryFn: async () => {
      const res = await apiGet<unknown>(path, { params });
      return map ? mapResult(res, map) : (res as ApiResult<T>);
    },
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
    ...queryOptions,
  });
}

/**
 * 更新系の共通ラッパ。エラー型を `ApiError` に固定して、画面側で `error.messageJa`
 * （日本語のメッセージ）をそのまま出せるようにする。
 */
function useApiMutation<TData, TVars>(
  mutationFn: (vars: TVars) => Promise<ApiResult<TData>>,
  onSuccess?: (res: ApiResult<TData>, vars: TVars) => void,
) {
  return useMutation<ApiResult<TData>, ApiError, TVars>({ mutationFn, onSuccess });
}

/* ---------------------------- ダッシュボード ---------------------------- */

async function fetchDashboard(market: Market): Promise<ApiResult<DashboardData>> {
  const [dash, jobsRes, watchRes, recsRes] = await Promise.all([
    apiGet<unknown>("/dashboard", { params: { market } }),
    apiGet<unknown>("/agent/jobs", { params: { limit: 50 } }).catch(() => null),
    apiGet<unknown>("/watchlist").catch(() => null),
    apiGet<unknown>("/recommendations", { params: { market } }).catch(() => null),
  ]);
  const mapped = mapDashboard(dash.data);
  const jobs = mapped.jobs.length ? mapped.jobs : unwrapItems(jobsRes?.data).map(mapAgentJob);
  const watchlist = mapped.watchlist.length ? mapped.watchlist : unwrapItems(watchRes?.data).map(mapWatchlistRow);
  const recItems = unwrapItems(recsRes?.data).map(mapRecommendationCard);
  const top =
    mapped.top_recommendations.some((r) => r.bear_case_ja.length >= 20)
      ? mapped.top_recommendations
      : recItems.slice(0, 5);
  return {
    ...dash,
    data: {
      ...mapped,
      jobs,
      watchlist,
      top_recommendations: top.length ? top : mapped.top_recommendations,
      job_status: {
        ...mapped.job_status,
        last_run: mapped.job_status.last_run || jobs[0]?.started_at || "",
      },
    },
  };
}

export const useDashboard = (market: Market) =>
  useQuery<ApiResult<DashboardData>, ApiError>({
    queryKey: queryKeys.dashboard(market),
    queryFn: () => fetchDashboard(market),
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
  });

/* ------------------------------- 推奨 --------------------------------- */

export const useRecommendations = (params: QueryParams) =>
  useApiQuery<RecommendationListData>(queryKeys.recommendations(params), "/recommendations", params, {
    map: mapRecommendationList,
  });

export function useRecommendationFeedback() {
  const qc = useQueryClient();
  return useApiMutation<{ accepted: boolean }, { recId: string; verdict: string; note?: string }>(
    (vars) =>
      apiPost<{ accepted: boolean }>(`/recommendations/${vars.recId}/feedback`, {
        verdict: vars.verdict,
        note_ja: vars.note,
      }),
    () => {
      void qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
  );
}

/* ----------------------------- スクリーナー ---------------------------- */

export function useScreener(req: ScreenerRequest, enabled = true) {
  return useQuery<ApiResult<ScreenerData>, ApiError>({
    queryKey: queryKeys.screener(req),
    queryFn: async (): Promise<ApiResult<ScreenerData>> => {
      const res = await apiPost<unknown>("/screener", req);
      const mapped = mapScreener(res.data);
      const extra = res.data && typeof res.data === "object" ? (res.data as Record<string, unknown>) : {};
      const totalMatched = typeof extra.total === "number" ? extra.total : undefined;
      const universeSize = typeof extra.universe_size === "number" ? extra.universe_size : totalMatched;
      return {
        ...res,
        data: mapped,
        meta: {
          ...res.meta,
          ...(totalMatched !== undefined ? { total_matched: totalMatched, total: universeSize ?? totalMatched } : {}),
          ...(typeof extra.truncated === "boolean" ? { truncated: extra.truncated } : {}),
          ...(typeof extra.excluded_count === "number" ? { excluded_count: extra.excluded_count } : {}),
        },
      };
    },
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
    enabled,
  });
}

export const useScreenerFields = () =>
  useQuery<ApiResult<ScreenerField[]>, ApiError>({
    queryKey: queryKeys.screenerFields(),
    queryFn: async () => emptyResult(SCREENER_FIELD_CATALOG),
    staleTime: 60 * 60 * 1000,
  });

export const useScreenerPresets = () =>
  useApiQuery<ScreenerPreset[]>(queryKeys.screenerPresets(), "/screener/presets", undefined, {
    staleTime: 60 * 60 * 1000,
    map: (raw) => (Array.isArray(raw) ? raw : unwrapItems(raw)).map(mapScreenerPreset),
  });

/* ------------------------------ 銘柄詳細 ------------------------------ */

export const useStock = (market: Market, ticker: string) =>
  useApiQuery<StockDetail>(queryKeys.stock(market, ticker), `/stocks/${market}/${ticker}`, undefined, {
    map: mapStockDetail,
  });

export const useStockPrices = (market: Market, ticker: string, range: string) =>
  useApiQuery<PriceSeriesData>(
    queryKeys.stockPrices(market, ticker, range),
    `/stocks/${market}/${ticker}/prices`,
    { range, series: "research" },
  );

export const useStockFinancials = (market: Market, ticker: string) =>
  useApiQuery<FinancialPeriod[]>(
    queryKeys.stockFinancials(market, ticker),
    `/stocks/${market}/${ticker}/financials`,
    { periods: 8 },
    { map: mapFinancials },
  );

export const useStockFeatures = (market: Market, ticker: string) =>
  useApiQuery<StockFeatures>(queryKeys.stockFeatures(market, ticker), `/stocks/${market}/${ticker}/features`, undefined, {
    map: mapStockFeatures,
  });

export const useStockDocuments = (market: Market, ticker: string) =>
  useApiQuery<DocumentSummaryRow[]>(
    queryKeys.stockDocuments(market, ticker),
    `/stocks/${market}/${ticker}/documents`,
    { limit: 20 },
    { map: (raw) => unwrapItems(raw).map(mapDocumentRow) },
  );

export const useStockRecommendations = (market: Market, ticker: string) =>
  useApiQuery<RecommendationHistoryRow[]>(
    queryKeys.stockRecommendations(market, ticker),
    `/stocks/${market}/${ticker}/recommendations`,
    undefined,
    { map: mapRecHistory },
  );

export const useStockPeers = (market: Market, ticker: string) =>
  useApiQuery<PeerRow[]>(queryKeys.stockPeers(market, ticker), `/stocks/${market}/${ticker}/peers`, undefined, {
    map: mapPeers,
  });

export const useStockSearch = (q: string) =>
  useApiQuery<StockSearchHit[]>(queryKeys.stockSearch(q), "/stocks/search", { q, limit: 10 }, {
    enabled: q.trim().length >= 1,
    staleTime: 30 * 1000,
    map: mapSearchHits,
  });

/* ------------------------------ 決算資料 ------------------------------ */

export const useDocuments = (params: QueryParams) =>
  useApiQuery<DocumentSummaryRow[]>(queryKeys.documents(params), "/documents", params, {
    map: (raw) => unwrapItems(raw).map(mapDocumentRow),
  });

export const useDocumentSummary = (docId: string | null) =>
  useApiQuery<DocumentSummary>(
    queryKeys.documentSummary(docId ?? "none"),
    `/documents/${docId}/summary`,
    undefined,
    { enabled: Boolean(docId), retry: false, map: mapDocumentSummary },
  );

export function useGenerateSummary() {
  const qc = useQueryClient();
  return useApiMutation<DocumentSummary, string>(
    async (docId) => mapResult(await apiPost<unknown>(`/documents/${docId}/summary`), mapDocumentSummary),
    (_res, docId) => {
      void qc.invalidateQueries({ queryKey: queryKeys.documentSummary(docId) });
      void qc.invalidateQueries({ queryKey: ["documents"] });
    },
  );
}

/* ---------------------------- 為替・マクロ ---------------------------- */

export function useFx(pair = "USDJPY") {
  return useQuery<ApiResult<FxData>, ApiError>({
    queryKey: queryKeys.fx(pair),
    queryFn: async () => {
      const detail = await apiGet<unknown>(`/fx/${pair}`);
      const raw = detail.data;
      const hasHistory =
        raw !== null &&
        typeof raw === "object" &&
        Array.isArray((raw as { history?: unknown }).history);
      let historyRaw: unknown = hasHistory ? (raw as { history: unknown }).history : undefined;
      if (historyRaw == null) {
        try {
          const hist = await apiGet<unknown>(`/fx/${pair}/history`, { params: { range: "5y" } });
          historyRaw = hist.data;
        } catch {
          historyRaw = [];
        }
      }
      return mapResult(detail, (d) => mapFxData(d, historyRaw));
    },
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
  });
}

export function useFxModels(pair = "USDJPY") {
  return useQuery<ApiResult<FxForecast[]>, ApiError>({
    queryKey: queryKeys.fxModels(pair),
    queryFn: async () => {
      if (USE_MOCK) {
        const res = await apiGet<unknown>(`/fx/${pair}/models`);
        return mapResult(res, (d) => (Array.isArray(d) ? d : unwrapItems(d)) as FxForecast[]);
      }
      const res = await apiGet<unknown>(`/fx/${pair}`);
      return mapResult(res, mapFxModels);
    },
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
  });
}

export const useMacroSeries = () =>
  useApiQuery<MacroSeries[]>(queryKeys.macroSeries(), "/macro/series", {
    ids: ["DGS10", "DGS2", "CPIAUCSL", "UNRATE", "IRLTLT01JPM156N", "DEXJPUS"],
    range: "5y",
  }, { map: mapMacroSeries });

export const useRateDifferential = () =>
  useApiQuery<RateDifferentialPoint[]>(queryKeys.rateDifferential(), "/macro/rate-differential", {
    range: "5y",
  }, { map: mapRateDifferential });

export function useFxSensitivity() {
  return useQuery<ApiResult<FxSensitivityRow[]>, ApiError>({
    queryKey: queryKeys.fxSensitivity(),
    queryFn: async () => {
      if (USE_MOCK) {
        const res = await apiGet<unknown>("/macro/fx-sensitivity");
        return mapResult(res, (d) => (Array.isArray(d) ? d : unwrapItems(d)) as FxSensitivityRow[]);
      }
      return emptyResult<FxSensitivityRow[]>([]);
    },
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });
}

/* ----------------------------- モデルラボ ----------------------------- */

export const useModelRuns = () =>
  useApiQuery<ModelRun[]>(queryKeys.modelRuns(), "/models/runs", { limit: 20 }, {
    map: (raw) => unwrapItems(raw).map(mapModelRun),
  });
export const useModelHealth = () =>
  useApiQuery<ModelHealth>(queryKeys.modelHealth(), "/models/health", undefined, { map: mapModelHealth });

export const useFeatureImportance = (runId: string | undefined) =>
  useApiQuery<FeatureImportance[]>(
    queryKeys.featureImportance(runId ?? "none"),
    `/models/runs/${runId}/feature-importance`,
    undefined,
    { enabled: Boolean(runId), map: mapFeatureImportanceList },
  );

export const useIcSeries = (runId: string | undefined) =>
  useApiQuery<IcPoint[]>(queryKeys.icSeries(runId ?? "none"), `/models/runs/${runId}/ic-timeseries`, undefined, {
    enabled: Boolean(runId),
    map: mapIcSeries,
  });

export function useQuintiles(runId: string | undefined) {
  return useQuery<ApiResult<QuintileReturn[]>, ApiError>({
    queryKey: queryKeys.quintiles(runId ?? "latest"),
    queryFn: async () => {
      if (USE_MOCK && runId) {
        const res = await apiGet<unknown>(`/models/runs/${runId}/quintiles`);
        return mapResult(res, mapQuintileList);
      }
      const res = await apiGet<unknown>("/models/health");
      return mapResult(res, mapQuintileList);
    },
    enabled: USE_MOCK ? Boolean(runId) : true,
    placeholderData: keepPreviousData,
    retry: (count, error) => error.isRetryable && count < 2,
  });
}

export function useLeakageChecks() {
  return useQuery<ApiResult<LeakageCheck[]>, ApiError>({
    queryKey: queryKeys.leakageChecks(),
    queryFn: async () => {
      if (USE_MOCK) {
        const res = await apiGet<unknown>("/models/leakage-checks");
        return mapResult(res, (d) => (Array.isArray(d) ? d : unwrapItems(d)) as LeakageCheck[]);
      }
      return emptyResult<LeakageCheck[]>([]);
    },
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });
}

export const useBacktests = () =>
  useApiQuery<Backtest[]>(queryKeys.backtests(), "/backtests", { limit: 20 }, {
    map: (raw) => unwrapItems(raw).map(mapBacktest),
  });

export const useFactorWeights = (market: Market) =>
  useApiQuery<FactorWeights>(queryKeys.factorWeights(market), "/factor-weights", { market, horizon: "H20" }, {
    map: mapFactorWeights,
  });

export const useEquityCurve = (backtestId: string | undefined) =>
  useApiQuery<PerformancePoint[]>(
    queryKeys.backtestEquity(backtestId ?? "none"),
    `/backtests/${backtestId}/equity-curve`,
    undefined,
    { enabled: Boolean(backtestId), map: mapEquityCurve },
  );

export function useActivateWeights() {
  const qc = useQueryClient();
  return useApiMutation<{ activated: boolean }, string>(
    (weightSetId) => apiPost<{ activated: boolean }>(`/factor-weights/${weightSetId}/activate`),
    () => {
      void qc.invalidateQueries({ queryKey: ["factor-weights"] });
    },
  );
}

export function useRejectWeights() {
  const qc = useQueryClient();
  return useApiMutation<{ rejected: boolean }, string>(
    (weightSetId) => apiPost<{ rejected: boolean }>(`/factor-weights/${weightSetId}/reject`),
    () => {
      void qc.invalidateQueries({ queryKey: ["factor-weights"] });
    },
  );
}

export function useCreateBacktest() {
  const qc = useQueryClient();
  return useApiMutation<{ job_run_id: number; status: string }, BacktestRequest>(
    (req) => apiPost<{ job_run_id: number; status: string }>("/backtests", req),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.backtests() });
    },
  );
}

/* ----------------------------- エージェント ---------------------------- */

export const useAgentJobs = () =>
  useApiQuery<AgentJob[]>(queryKeys.agentJobs(), "/agent/jobs", { limit: 50 }, {
    map: (raw) => unwrapItems(raw).map(mapAgentJob),
  });
export const useAgentCost = () =>
  useApiQuery<AgentCost>(queryKeys.agentCost(), "/agent/cost", { period: "daily", days: 30 }, { map: mapAgentCost });
export const useCriticStats = () =>
  useApiQuery<CriticStats>(queryKeys.criticStats(), "/agent/critic-stats", { days: 30 }, { map: mapCriticStats });
export const useAgentMemory = () =>
  useApiQuery<AgentMemory[]>(queryKeys.agentMemory(), "/agent/memory", undefined, {
    map: (raw) => unwrapItems(raw).map(mapAgentMemory),
  });

export function useRunJob() {
  const qc = useQueryClient();
  return useApiMutation<{ job_run_id: number }, string>(
    (jobName) => apiPost<{ job_run_id: number }>(`/agent/jobs/${jobName}/run`),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.agentJobs() });
    },
  );
}

export function useToggleMemory() {
  const qc = useQueryClient();
  return useApiMutation<AgentMemory, { memoryId: string; isActive: boolean }>(
    async (vars) =>
      mapResult(await apiPatch<unknown>(`/agent/memory/${vars.memoryId}`, { is_active: vars.isActive }), mapAgentMemory),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.agentMemory() });
    },
  );
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useApiMutation<{ cancelled: boolean }, number>(
    (jobRunId) => apiPost<{ cancelled: boolean }>(`/agent/jobs/${jobRunId}/cancel`),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.agentJobs() });
    },
  );
}

export function useRunDiagnostics() {
  return useApiMutation<{ report_ja: string }, void>(() =>
    apiPost<{ report_ja: string }>("/system/diagnostics"),
  );
}

export function useRunBackup() {
  return useApiMutation<{ ok: boolean; message_ja: string }, void>(() =>
    apiPost<{ ok: boolean; message_ja: string }>("/system/backup"),
  );
}

export function useRebuildVectors() {
  return useApiMutation<{ job_run_id: number }, void>(() =>
    apiPost<{ job_run_id: number }>("/system/vector-rebuild"),
  );
}

/* ---------------------------- ポートフォリオ --------------------------- */

export const usePortfolio = () =>
  useApiQuery<PortfolioTotals>(queryKeys.portfolio(), "/portfolio", undefined, { map: mapPortfolio });
export const usePositions = () =>
  useApiQuery<Position[]>(queryKeys.positions(), "/portfolio/positions", undefined, {
    map: (raw) => unwrapItems(raw).map(mapPosition),
  });
export const usePerformance = (range = "1y") =>
  useApiQuery<PerformancePoint[]>(queryKeys.performance(range), "/portfolio/performance", { range }, {
    map: mapPerformance,
  });
export const useTrades = () =>
  useApiQuery<Trade[]>(queryKeys.trades(), "/trades", { limit: 100 }, {
    map: (raw) => unwrapItems(raw).map(mapTrade),
  });
export const useTradeAnalysis = () =>
  useApiQuery<TradeAnalysis>(queryKeys.tradeAnalysis(), "/trades/analysis", undefined, { map: mapTradeAnalysis });

export function useCreateTrade() {
  const qc = useQueryClient();
  return useApiMutation<Trade, TradeCreateRequest>(
    async (req) => mapResult(await apiPost<unknown>("/trades", req), mapTrade),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.trades() });
      void qc.invalidateQueries({ queryKey: queryKeys.portfolio() });
    },
  );
}

export function useDeleteTrade() {
  const qc = useQueryClient();
  return useApiMutation<{ deleted: boolean }, string>(
    (tradeId) => apiDelete<{ deleted: boolean }>(`/trades/${tradeId}`),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.trades() });
    },
  );
}

/* ------------------------ ウォッチリスト・設定 ------------------------- */

export const useWatchlist = () =>
  useApiQuery<WatchlistRow[]>(queryKeys.watchlist(), "/watchlist", undefined, {
    map: (raw) => unwrapItems(raw).map(mapWatchlistRow),
  });
export const useSettingsQuery = () =>
  useApiQuery<Settings>(queryKeys.settings(), "/settings", undefined, { map: mapSettings });
export const useAlerts = () =>
  useApiQuery<Alert[]>(queryKeys.alerts(), "/alerts", { limit: 50 }, {
    map: (raw) => unwrapItems(raw).map(mapAlert),
  });
export const useSystemHealth = () => useApiQuery<SystemHealth>(queryKeys.systemHealth(), "/system/health");
export const useSystemFreshness = () =>
  useApiQuery<SystemFreshness>(queryKeys.systemFreshness(), "/system/freshness", undefined, {
    map: mapSystemFreshness,
  });

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useApiMutation<Settings, SettingsPatch>(
    async (patch) => mapResult(await apiPatch<unknown>("/settings", patch), mapSettings),
    (res) => {
      qc.setQueryData(queryKeys.settings(), res);
    },
  );
}

export function useMarkAlertRead() {
  const qc = useQueryClient();
  return useApiMutation<{ updated: number }, string>(
    (alertId) => apiPost<{ updated: number }>(`/alerts/${alertId}/read`),
    () => {
      void qc.invalidateQueries({ queryKey: queryKeys.alerts() });
    },
  );
}
