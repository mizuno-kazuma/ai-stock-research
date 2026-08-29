/**
 * モックデータ。sample.ts（Figma Make 出力）の内容を 09-api-spec.md の形に直したもの。
 *
 * 方針:
 * - 数値は素の数値。比率は小数（`+2.4%` → `0.024`）。整形は画面側の formatter に任せる。
 * - 欠損は `null`。`0` で埋めない。null 表示（`—`）の経路をモックでも通す。
 * - 乱数は使わない。SSR と CSR で値が変わるとハイドレーション不整合になるため、
 *   時系列は下の `seeded()` で決定的に生成する。
 */

import type {
  AgentCost,
  AgentJob,
  AgentMemory,
  Alert,
  Backtest,
  Citation,
  CriticStats,
  DashboardData,
  DataFreshness,
  DocumentSummary,
  DocumentSummaryRow,
  FactorDetail,
  FactorKey,
  FactorWeights,
  FeatureImportance,
  FinancialPeriod,
  FxData,
  FxSensitivityRow,
  IcPoint,
  LeakageCheck,
  MacroSeries,
  ModelHealth,
  ModelRun,
  PeerRow,
  PerformancePoint,
  Position,
  PortfolioTotals,
  PriceBar,
  PriceSeriesData,
  QuintileReturn,
  RecommendationCard,
  RecommendationHistoryRow,
  ScreenerField,
  ScreenerPreset,
  ScreenerRow,
  Settings,
  StockDetail,
  StockFeatures,
  StockSearchHit,
  SystemFreshness,
  SystemHealth,
  Trade,
  TradeAnalysis,
  WatchlistRow,
} from "../api-types";

export const MOCK_AS_OF = "2026-08-22";
export const MOCK_COMPUTED_AT = "2026-08-21T21:47:00Z";

/** 決定的な擬似乱数（mulberry32）。同じ seed なら常に同じ列を返す */
function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round = (v: number, digits = 4) => Number(v.toFixed(digits));

/** 営業日を遡って日付列を作る（週末は飛ばす） */
function businessDaysBack(count: number, endDate = MOCK_AS_OF): string[] {
  const out: string[] = [];
  const d = new Date(`${endDate}T00:00:00Z`);
  while (out.length < count) {
    const day = d.getUTCDay();
    if (day !== 0 && day !== 6) out.unshift(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() - 1);
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* 鮮度                                                                */
/* ------------------------------------------------------------------ */

/** J-Quants 無料プランの12週遅延をあえて残している。遅延表示の経路を常に通すため */
export const FRESHNESS: DataFreshness[] = [
  {
    source: "jquants",
    latest_as_of: "2026-05-30",
    expected_as_of: "2026-08-21",
    note_ja: "無料プランのため12週遅延しています",
    status: "delayed",
  },
  { source: "yfinance_jp", latest_as_of: "2026-08-22", expected_as_of: "2026-08-22", status: "ok" },
  { source: "yfinance_us", latest_as_of: "2026-08-21", expected_as_of: "2026-08-21", status: "ok" },
  { source: "edinet", latest_as_of: "2026-08-22", expected_as_of: "2026-08-22", status: "ok" },
  {
    source: "tdnet",
    latest_as_of: "2026-08-19",
    expected_as_of: "2026-08-22",
    note_ja: "3日連続で取得に失敗しています",
    status: "failed",
  },
  { source: "fred", latest_as_of: "2026-08-21", expected_as_of: "2026-08-21", status: "ok" },
];

/* ------------------------------------------------------------------ */
/* 推奨                                                                */
/* ------------------------------------------------------------------ */

const factorDetail = (
  key: FactorKey,
  labelJa: string,
  z: number | null,
  percentileJa: string | null,
  rawJa: string | null,
  contribution: number | null,
): FactorDetail => ({ key, label_ja: labelJa, z, percentile_ja: percentileJa, raw_ja: rawJa, contribution });

const toyotaCitations: Citation[] = [
  {
    doc_id: "f002",
    title: "2027年3月期 第1四半期決算短信〔IFRS〕(連結)",
    doc_type: "earnings_flash",
    filed_at: "2026-08-08",
    page: 3,
    quote:
      "北米市場における販売が計画を上回ったことから、通期の営業利益予想を5.0%上方修正いたします",
    verification: "verified",
  },
  {
    doc_id: "f010",
    title: "第122期 有価証券報告書",
    doc_type: "annual_report",
    filed_at: "2026-06-24",
    page: 24,
    quote:
      "北米市場において、競合他社による値引き圧力が継続しており、販売奨励金の増加リスクが存在する",
    verification: "verified",
  },
];

export const RECOMMENDATIONS: RecommendationCard[] = [
  {
    rec_id: "rec_001",
    as_of: MOCK_AS_OF,
    ticker: "7203",
    market: "JP",
    name_local: "トヨタ自動車",
    name_en: "Toyota Motor Corp.",
    sector_name: "輸送用機器",
    action: "watch",
    horizon: "H20",
    conviction: "medium",
    conviction_score: 62,
    thesis_ja:
      "北米向け販売が会社計画を上回り、2027年3月期の営業利益予想が5%上方修正された（8月8日開示）。セクター内でPERは下位25%圏にあり、ROICは12.4%で同セクター中位を上回る。為替前提が1ドル148円のため、152円台の現状は上振れ要因となる。",
    bear_case_ja:
      "上方修正の主因は為替効果で、数量ベースの改善は前年同期比+1.2%にとどまる。円高に転じた場合、上方修正分の大半が消える構造にある。加えて北米では競合の値引き圧力が続いており、下期の販売奨励金の増加リスクが開示されている。",
    invalidation_ja:
      "1ドル145円を下回る、または月次販売台数が2ヶ月連続で前年割れとなった場合、上方修正の前提が崩れるため本推奨は無効とする。",
    reason_codes: [
      "VAL_CHEAP_VS_SECTOR",
      "REV_UP_GUIDANCE",
      "MOM_STRONG_12M",
      "FX_TAILWIND",
      "EVENT_EARNINGS_SOON",
    ],
    expected_ret: 0.024,
    expected_ret_lo: -0.031,
    expected_ret_hi: 0.079,
    ci_level: 80,
    hit_rate_prior: 0.58,
    n_prior_samples: 34,
    quant_score: 78.4,
    quant_rank: 12,
    quant_percentile: 0.94,
    qual_score: 8.4,
    qual_confidence: 0.72,
    qual_doc_count: 2,
    total_score: 82.1,
    factor_scores: {
      value: 1.42,
      quality: 0.88,
      momentum: 1.05,
      growth: 0.31,
      revision: 1.67,
      lowvol: -0.24,
      liquidity: 0.92,
    },
    factor_details: [
      factorDetail("value", "バリュエーション", 1.42, "上位 8%", "PER 11.2倍", 0.28),
      factorDetail("quality", "クオリティ", 0.88, "上位 22%", "ROIC 12.4%", 0.14),
      factorDetail("momentum", "モメンタム", 1.05, "上位 15%", "12M +18.4%", 0.21),
      factorDetail("growth", "成長", 0.31, "上位 38%", "EPS成長 +8.2%", 0.04),
      factorDetail("revision", "予想改定", 1.67, "上位 5%", "+5.0% 上方修正", 0.31),
      factorDetail("lowvol", "ボラティリティ", -0.24, "下位 42%", "22.4%", -0.02),
      factorDetail("liquidity", "流動性", 0.92, "上位 18%", "412億円/日", 0.04),
    ],
    entry_ref_price: 3125,
    entry_ref_source: "yfinance",
    entry_ref_note_ja: "15分遅延の参考値です。発注価格ではありません",
    stop_ref_price: 2890,
    target_ref_price: 3420,
    suggested_size_pct: 0.03,
    currency: "JPY",
    source_doc_ids: ["f002", "f010"],
    citations: toyotaCitations,
    data_freshness: FRESHNESS.slice(0, 4),
    critic_verdict: "approved",
    critic_notes_ja: null,
    flags: [],
    generated_at: "2026-08-21T21:38:00Z",
  },
  {
    rec_id: "rec_002",
    as_of: MOCK_AS_OF,
    ticker: "6758",
    market: "JP",
    name_local: "ソニーグループ",
    name_en: "Sony Group Corp.",
    sector_name: "電気機器",
    action: "reduce",
    horizon: "H20",
    conviction: "medium",
    conviction_score: 54,
    thesis_ja:
      "ゲーム部門の下方修正幅は8%と限定的で、音楽・映画部門が引き続き好調。長期的な成長ストーリーは損なわれていないが、短期的な期待値調整が必要。",
    bear_case_ja:
      "ゲーム部門ハードウェアの販売計画未達は構造的な問題の可能性がある。競合との値引き競争が下期も続く場合、追加の下方修正リスクが残る。半導体調達コストの上昇も下期の圧力となる。",
    invalidation_ja:
      "ゲーム部門の月次販売台数が2ヶ月連続で前年割れとなった場合、または追加の下方修正が発表された場合。",
    reason_codes: [
      "REV_DOWN_GUIDANCE",
      "LLM_NEW_RISK_DISCLOSED",
      "VAL_EXPENSIVE_VS_SECTOR",
      "MOM_WEAK_12M",
    ],
    expected_ret: -0.018,
    expected_ret_lo: -0.064,
    expected_ret_hi: 0.028,
    ci_level: 80,
    hit_rate_prior: 0.54,
    n_prior_samples: 28,
    quant_score: 52.1,
    quant_rank: 618,
    quant_percentile: 0.51,
    qual_score: -6.2,
    qual_confidence: 0.64,
    qual_doc_count: 1,
    total_score: 45.9,
    factor_scores: {
      value: -0.84,
      quality: 0.42,
      momentum: -1.12,
      growth: -0.68,
      revision: -1.84,
      lowvol: 0.18,
      liquidity: 0.76,
    },
    factor_details: [
      factorDetail("value", "バリュエーション", -0.84, "下位 28%", "PER 18.4倍", -0.18),
      factorDetail("quality", "クオリティ", 0.42, "上位 35%", "ROIC 8.2%", 0.07),
      factorDetail("momentum", "モメンタム", -1.12, "下位 18%", "12M -8.4%", -0.22),
      factorDetail("growth", "成長", -0.68, "下位 32%", "EPS成長 -3.1%", -0.08),
      factorDetail("revision", "予想改定", -1.84, "下位 8%", "-8.0% 下方修正", -0.34),
      factorDetail("lowvol", "ボラティリティ", 0.18, "上位 48%", "24.8%", 0.01),
      factorDetail("liquidity", "流動性", 0.76, "上位 25%", "380億円/日", 0.03),
    ],
    entry_ref_price: 2840,
    entry_ref_source: "yfinance",
    entry_ref_note_ja: "15分遅延の参考値です。発注価格ではありません",
    stop_ref_price: 2680,
    target_ref_price: 2980,
    suggested_size_pct: null,
    currency: "JPY",
    source_doc_ids: ["f001"],
    citations: [
      {
        doc_id: "f001",
        title: "2027年3月期 通期業績予想の修正に関するお知らせ",
        doc_type: "guidance_revision",
        filed_at: "2026-08-22",
        page: 1,
        quote:
          "ゲーム&ネットワークサービス分野において、ハードウェアの販売台数が計画を下回ったことから、通期の営業利益予想を8.0%下方修正いたします",
        verification: "verified",
      },
    ],
    data_freshness: FRESHNESS.slice(0, 4),
    critic_verdict: "revised",
    critic_notes_ja:
      "確信度を「高」から「中」に引き下げ。弱気論拠が定型的で、ゲーム部門の具体的な販売計画未達に触れていなかったため差し戻し、再生成した。",
    flags: [],
    generated_at: "2026-08-21T21:38:00Z",
  },
  {
    rec_id: "rec_003",
    as_of: MOCK_AS_OF,
    ticker: "AAPL",
    market: "US",
    name_local: "Apple Inc.",
    name_en: "Apple Inc.",
    sector_name: "Information Technology",
    action: "watch",
    horizon: "H20",
    conviction: "low",
    conviction_score: 38,
    thesis_ja:
      "サービス部門の成長が続いており、Apple Intelligenceによるデバイス買い替え需要が来期以降の成長ドライバーとなる可能性がある。",
    bear_case_ja:
      "中国市場でのシェア低下が続いており、規制リスクも高まっている。バリュエーションはS&P500の中で割高圏にあり、成長期待が既に織り込まれている可能性がある。",
    invalidation_ja: "中国売上が前年比-15%を超えた場合、またはAI機能の普及が想定を大きく下回った場合。",
    reason_codes: ["LLM_POSITIVE_GUIDANCE", "QLT_HIGH_ROIC", "GRW_ACCELERATING", "VAL_EXPENSIVE_VS_SECTOR"],
    expected_ret: 0.016,
    expected_ret_lo: -0.042,
    expected_ret_hi: 0.074,
    ci_level: 80,
    hit_rate_prior: 0.52,
    n_prior_samples: 18,
    quant_score: 71.2,
    quant_rank: 88,
    quant_percentile: 0.82,
    qual_score: 4.8,
    qual_confidence: 0.58,
    qual_doc_count: 1,
    total_score: 74.6,
    factor_scores: {
      value: -0.42,
      quality: 1.84,
      momentum: 0.68,
      growth: 1.12,
      revision: 0.58,
      lowvol: 0.84,
      liquidity: 2.4,
    },
    factor_details: [
      factorDetail("value", "バリュエーション", -0.42, "下位 35%", "PER 28.4倍", -0.09),
      factorDetail("quality", "クオリティ", 1.84, "上位 4%", "ROIC 34.2%", 0.32),
      factorDetail("momentum", "モメンタム", 0.68, "上位 28%", "12M +12.4%", 0.13),
      factorDetail("growth", "成長", 1.12, "上位 18%", "EPS成長 +14.2%", 0.14),
      factorDetail("revision", "予想改定", 0.58, "上位 32%", "+2.4% 上方修正", 0.1),
      factorDetail("lowvol", "ボラティリティ", 0.84, "上位 22%", "18.4%", 0.05),
      factorDetail("liquidity", "流動性", 2.4, "上位 1%", "$8.4B/日", 0.1),
    ],
    entry_ref_price: 189.42,
    entry_ref_source: "yfinance",
    entry_ref_note_ja: "前営業日終値です。発注価格ではありません",
    stop_ref_price: 176,
    target_ref_price: 201,
    suggested_size_pct: 0.02,
    currency: "USD",
    source_doc_ids: ["f003"],
    citations: [
      {
        doc_id: "f003",
        title: "Quarterly report for the period ended 2026-06-27",
        doc_type: "form_10q",
        filed_at: "2026-07-30",
        page: 12,
        quote:
          "Services revenue grew 14% year-over-year to $24.2 billion, driven by growth across all geographic segments",
        verification: "verified",
      },
    ],
    data_freshness: [FRESHNESS[2] as DataFreshness, FRESHNESS[5] as DataFreshness],
    critic_verdict: "approved",
    critic_notes_ja: null,
    flags: ["low_sample"],
    generated_at: "2026-08-21T21:38:00Z",
  },
  {
    rec_id: "rec_004",
    as_of: MOCK_AS_OF,
    ticker: "9984",
    market: "JP",
    name_local: "ソフトバンクグループ",
    name_en: "SoftBank Group Corp.",
    sector_name: "情報・通信業",
    action: "avoid",
    horizon: "H20",
    conviction: "low",
    conviction_score: 26,
    thesis_ja: "AI投資ポートフォリオの評価額回復が株価の下支えとなる可能性がある。",
    bear_case_ja:
      "ARM株の評価に業績が大きく依存しており、ARM株価の変動リスクが高い。LTV（負債価値比率）が高水準で維持されており、金利上昇局面では財務リスクが増大する。",
    invalidation_ja: "ARM株が-20%を超える下落となった場合、またはLTVが25%を超えた場合。",
    reason_codes: ["VOL_HIGH_REGIME", "QLT_HIGH_LEVERAGE", "MODEL_LOW_CONFIDENCE"],
    expected_ret: -0.032,
    expected_ret_lo: -0.124,
    expected_ret_hi: 0.06,
    ci_level: 80,
    hit_rate_prior: 0.44,
    n_prior_samples: 16,
    quant_score: 34.2,
    quant_rank: 1288,
    quant_percentile: 0.32,
    qual_score: -10.8,
    qual_confidence: 0.41,
    qual_doc_count: 0,
    total_score: 28.4,
    factor_scores: {
      value: 2.1,
      quality: -2.4,
      momentum: -0.84,
      growth: -1.2,
      revision: -0.42,
      lowvol: -2.8,
      liquidity: 1.2,
    },
    factor_details: [
      factorDetail("value", "バリュエーション", 2.1, "上位 3%", "PBR 1.4倍", 0.38),
      factorDetail("quality", "クオリティ", -2.4, "下位 2%", "ROIC -4.2%", -0.42),
      factorDetail("momentum", "モメンタム", -0.84, "下位 22%", "12M -18.4%", -0.16),
      factorDetail("growth", "成長", -1.2, "下位 15%", null, -0.14),
      factorDetail("revision", "予想改定", -0.42, "下位 38%", "変更なし", -0.07),
      factorDetail("lowvol", "ボラティリティ", -2.8, "下位 1%", "48.4%", -0.18),
      factorDetail("liquidity", "流動性", 1.2, "上位 12%", "980億円/日", 0.05),
    ],
    entry_ref_price: 8240,
    entry_ref_source: "yfinance",
    entry_ref_note_ja: "15分遅延の参考値です。発注価格ではありません",
    stop_ref_price: 7600,
    target_ref_price: 8640,
    suggested_size_pct: null,
    currency: "JPY",
    source_doc_ids: [],
    citations: [],
    data_freshness: FRESHNESS.slice(0, 4),
    critic_verdict: "rejected",
    critic_notes_ja: "却下 · 引用1件が原文で確認できません。弱気論拠が定型的で実質がない。",
    flags: ["citation_unverified", "low_sample"],
    generated_at: "2026-08-21T21:38:00Z",
  },
];

/* ------------------------------------------------------------------ */
/* ダッシュボード                                                      */
/* ------------------------------------------------------------------ */

export const WATCHLIST: WatchlistRow[] = [
  { ticker: "7203", market: "JP", name_local: "トヨタ自動車", ref_price: 3125, ref_price_currency: "JPY", change_pct: 0.0124, quant_score: 78.4, next_earnings_in_days: 3, new_filing_count: 2 },
  { ticker: "6758", market: "JP", name_local: "ソニーグループ", ref_price: 2840, ref_price_currency: "JPY", change_pct: -0.0082, quant_score: 52.1, next_earnings_in_days: null, new_filing_count: 1 },
  { ticker: "9984", market: "JP", name_local: "ソフトバンクグループ", ref_price: 8240, ref_price_currency: "JPY", change_pct: 0.0214, quant_score: 34.2, next_earnings_in_days: 18, new_filing_count: 0 },
  { ticker: "7974", market: "JP", name_local: "任天堂", ref_price: 9480, ref_price_currency: "JPY", change_pct: -0.0031, quant_score: 68.8, next_earnings_in_days: 8, new_filing_count: 0 },
  { ticker: "AAPL", market: "US", name_local: "Apple Inc.", ref_price: 189.42, ref_price_currency: "USD", change_pct: -0.0083, quant_score: 71.2, next_earnings_in_days: 45, new_filing_count: 1 },
  { ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", ref_price: 142.18, ref_price_currency: "USD", change_pct: 0.0328, quant_score: 82.4, next_earnings_in_days: 12, new_filing_count: 1 },
  { ticker: "9432", market: "JP", name_local: "日本電信電話", ref_price: 148.2, ref_price_currency: "JPY", change_pct: 0.0068, quant_score: 61.4, next_earnings_in_days: 22, new_filing_count: 1 },
  { ticker: "6098", market: "JP", name_local: "リクルートホールディングス", ref_price: 8920, ref_price_currency: "JPY", change_pct: 0.0142, quant_score: 74.8, next_earnings_in_days: 5, new_filing_count: 0 },
];

export const MODEL_HEALTH: ModelHealth = {
  market: "JP",
  horizon: "H20",
  rank_ic_20d: 0.031,
  rank_ic_percentile_1y: 0.58,
  rank_ic_3m: 0.028,
  status: "normal",
  coverage_rate: 0.924,
  coverage_pct: 0.924,
  coverage_detail_ja: "1,842 / 1,994銘柄",
  coverage_note_ja: "残りは上場後1年未満または流動性基準未達です",
  drift_feature_count: 0,
  degradation_note_ja: null,
};

export const ALERTS: Alert[] = [
  { alert_id: "al_001", severity: "error", category: "data", title_ja: "TDnetの取得が3日連続で失敗しています", body_ja: "取得スクリプトのセレクタが変わった可能性があります。", created_at: "2026-08-21T21:14:00Z", is_read: false, link: "/settings" },
  { alert_id: "al_002", severity: "warning", category: "data", title_ja: "J-Quantsの価格データが5営業日更新されていません", body_ja: null, created_at: "2026-08-21T21:12:00Z", is_read: false, link: "/settings" },
  { alert_id: "al_003", severity: "warning", category: "cost", title_ja: "LLMの日次予算の80%（$1.20 / $1.50）に達しました", body_ja: null, created_at: "2026-08-21T21:31:00Z", is_read: false, link: "/agent" },
  { alert_id: "al_004", severity: "info", category: "data", title_ja: "6758 ソニーグループが業績予想の修正を開示しました", body_ja: null, created_at: "2026-08-22T06:04:00Z", is_read: true, link: "/filings" },
  { alert_id: "al_005", severity: "info", category: "model", title_ja: "7203 トヨタ自動車の決算発表が3営業日後です", body_ja: null, created_at: "2026-08-21T21:47:00Z", is_read: true, link: "/stocks/JP/7203" },
  { alert_id: "al_006", severity: "info", category: "data", title_ja: "AAPL Apple Inc. の10-Qが開示されました", body_ja: null, created_at: "2026-08-22T00:30:00Z", is_read: true, link: "/filings" },
];

export const AGENT_JOBS: AgentJob[] = [
  { job_run_id: 1041, job_name: "collector", label_ja: "データ収集", status: "success", trigger: "schedule", started_at: "2026-08-21T21:12:00Z", duration_sec: 412, output_ja: "価格 1,994銘柄 · 開示 12件", output_summary_ja: "価格 1,994銘柄 · 開示 12件", failed_steps: [], progress: null },
  { job_run_id: 1042, job_name: "analyst", label_ja: "分析", status: "success", trigger: "schedule", started_at: "2026-08-21T21:19:00Z", duration_sec: 248, output_ja: "特徴量 42項目 × 1,842銘柄", output_summary_ja: "特徴量 42項目 × 1,842銘柄", failed_steps: [], progress: null },
  { job_run_id: 1043, job_name: "researcher", label_ja: "資料読解", status: "partial", trigger: "schedule", started_at: "2026-08-21T21:31:00Z", duration_sec: 196, output_ja: "資料 8件 · $0.18", output_summary_ja: "資料 8件 · $0.18", failed_steps: ["tdnet_fetch"], progress: null },
  { job_run_id: 1044, job_name: "strategist", label_ja: "推奨生成", status: "success", trigger: "schedule", started_at: "2026-08-21T21:38:00Z", duration_sec: 222, output_ja: "候補 34件 → 推奨 12件 · $0.21", output_summary_ja: "候補 34件 → 推奨 12件 · $0.21", failed_steps: [], progress: null },
  { job_run_id: 1045, job_name: "critic", label_ja: "レビュー", status: "success", trigger: "schedule", started_at: "2026-08-21T21:44:00Z", duration_sec: 138, output_ja: "承認 10件 · 修正 2件 · 却下 2件", output_summary_ja: "承認 10件 · 修正 2件 · 却下 2件", failed_steps: [], progress: null },
  { job_run_id: 1046, job_name: "evaluator", label_ja: "実績評価", status: "success", trigger: "schedule", started_at: "2026-08-21T21:47:00Z", duration_sec: 64, output_ja: "実績確定 18件 · 教訓 1件", output_summary_ja: "実績確定 18件 · 教訓 1件", failed_steps: [], progress: null },
];

const usdjpyHistory = (() => {
  const rand = seeded(4711);
  const dates = businessDaysBack(60);
  let v = 148.2;
  return dates.map((date) => {
    v = v + (rand() - 0.42) * 0.9;
    return { date, value: round(v, 2) };
  });
})();

export const DASHBOARD: DashboardData = {
  as_of: MOCK_AS_OF,
  market_summary: {
    benchmark: { symbol: "TOPIX", close: 2847.32, change_pct: 0.0084 },
    advance_decline: { advancing: 1142, declining: 764, unchanged: 88 },
    vol_regime: { level: "normal", percentile: 0.48, message_ja: "ボラティリティは過去1年の中位圏です" },
    correlation_regime: { avg_pairwise_corr_60d: 0.34, level: "normal" },
  },
  fx: {
    pair: "USDJPY",
    spot: 152.34,
    change_pct: 0.0041,
    forecast_h20: {
      point: 152.8,
      ci_lo_80: 150.9,
      ci_hi_80: 154.7,
      beats_baseline: false,
      note_ja: "ランダムウォークに対する優位性は確認できていません（DM検定 p=0.31）",
    },
    history: usdjpyHistory,
  },
  top_recommendations: RECOMMENDATIONS.slice(0, 3),
  portfolio_snapshot: {
    n_positions: 7,
    unrealized_pnl_pct: 0.062,
    day_change_pct: 0.0046,
    total_value: 8472150,
    market_value: 8472150,
    currency: "JPY",
    top_movers: [
      { ticker: "NVDA", name_local: "NVIDIA Corp.", change_pct: 0.0328 },
      { ticker: "9984", name_local: "ソフトバンクグループ", change_pct: 0.0214 },
      { ticker: "6758", name_local: "ソニーグループ", change_pct: -0.0082 },
    ],
  },
  new_filings_count: 6,
  watchlist: WATCHLIST,
  watchlist_filings: [],
  model_health: MODEL_HEALTH,
  alerts: ALERTS,
  job_status: { last_run: "2026-08-21T21:47:00Z", status: "partial", failed_steps: ["tdnet_fetch"] },
  jobs: AGENT_JOBS,
};

/* ------------------------------------------------------------------ */
/* スクリーナー                                                        */
/* ------------------------------------------------------------------ */

export const SCREENER_ROWS: ScreenerRow[] = [
  { ticker: "7203", market: "JP", name_local: "トヨタ自動車", sector_name: "輸送用機器", quant_score: 78.4, ref_price: 3125, currency: "JPY", change_pct: 0.0124, value_z: 1.42, quality_z: 0.88, revision_z: 1.67, per: 10.4, pbr: 1.18, roic: 0.124, mom_12m: 0.184, realized_vol_60d: 0.224, ml_pred_h20: 0.024, ml_pred_h20_lo: -0.031, ml_pred_h20_hi: 0.079, reason_codes: ["VAL_CHEAP_VS_SECTOR", "REV_UP_GUIDANCE"], next_earnings_in_days: 3 },
  { ticker: "7269", market: "JP", name_local: "スズキ", sector_name: "輸送用機器", quant_score: 74.2, ref_price: 6840, currency: "JPY", change_pct: 0.0084, value_z: 0.94, quality_z: 0.72, revision_z: 0.38, per: 12.4, pbr: 1.24, roic: 0.112, mom_12m: 0.148, realized_vol_60d: 0.208, ml_pred_h20: 0.018, ml_pred_h20_lo: -0.034, ml_pred_h20_hi: 0.07, reason_codes: ["VAL_CHEAP_VS_SECTOR", "MOM_STRONG_12M"], next_earnings_in_days: 8 },
  { ticker: "6098", market: "JP", name_local: "リクルートホールディングス", sector_name: "サービス業", quant_score: 74.8, ref_price: 8920, currency: "JPY", change_pct: 0.0142, value_z: -0.62, quality_z: 1.48, revision_z: 0.84, per: 28.4, pbr: 4.82, roic: 0.184, mom_12m: 0.224, realized_vol_60d: 0.262, ml_pred_h20: 0.021, ml_pred_h20_lo: -0.038, ml_pred_h20_hi: 0.08, reason_codes: ["GRW_ACCELERATING", "MOM_STRONG_12M"], next_earnings_in_days: 5 },
  { ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", sector_name: "Information Technology", quant_score: 82.4, ref_price: 142.18, currency: "USD", change_pct: 0.0328, value_z: -1.24, quality_z: 2.38, revision_z: 1.92, per: 32.4, pbr: 24.8, roic: 0.842, mom_12m: 1.484, realized_vol_60d: 0.428, ml_pred_h20: 0.031, ml_pred_h20_lo: -0.062, ml_pred_h20_hi: 0.124, reason_codes: ["GRW_ACCELERATING", "MOM_NEAR_52W_HIGH", "VOL_HIGH_REGIME"], next_earnings_in_days: 12 },
  { ticker: "7267", market: "JP", name_local: "本田技研工業", sector_name: "輸送用機器", quant_score: 71.8, ref_price: 1640, currency: "JPY", change_pct: 0.0062, value_z: 1.18, quality_z: 0.44, revision_z: 0.12, per: 8.9, pbr: 0.72, roic: 0.091, mom_12m: 0.084, realized_vol_60d: 0.234, ml_pred_h20: 0.014, ml_pred_h20_lo: -0.04, ml_pred_h20_hi: 0.068, reason_codes: ["VAL_CHEAP_VS_SECTOR"], next_earnings_in_days: 22 },
  { ticker: "9432", market: "JP", name_local: "日本電信電話", sector_name: "情報・通信業", quant_score: 61.4, ref_price: 148.2, currency: "JPY", change_pct: 0.0068, value_z: 0.68, quality_z: 0.34, revision_z: -0.08, per: 11.2, pbr: 1.32, roic: 0.078, mom_12m: 0.042, realized_vol_60d: 0.142, ml_pred_h20: 0.006, ml_pred_h20_lo: -0.028, ml_pred_h20_hi: 0.04, reason_codes: ["VOL_LOW_REGIME"], next_earnings_in_days: 22 },
  { ticker: "4063", market: "JP", name_local: "信越化学工業", sector_name: "化学", quant_score: 76.4, ref_price: 5840, currency: "JPY", change_pct: 0.0024, value_z: 0.42, quality_z: 1.62, revision_z: 0.28, per: 16.4, pbr: 2.14, roic: 0.148, mom_12m: 0.124, realized_vol_60d: 0.226, ml_pred_h20: 0.019, ml_pred_h20_lo: -0.032, ml_pred_h20_hi: 0.07, reason_codes: ["QLT_HIGH_ROIC"], next_earnings_in_days: 18 },
  { ticker: "6861", market: "JP", name_local: "キーエンス", sector_name: "電気機器", quant_score: 72.8, ref_price: 65400, currency: "JPY", change_pct: 0.0112, value_z: -1.02, quality_z: 2.14, revision_z: 0.46, per: 32.4, pbr: 6.18, roic: 0.284, mom_12m: 0.182, realized_vol_60d: 0.244, ml_pred_h20: 0.017, ml_pred_h20_lo: -0.036, ml_pred_h20_hi: 0.07, reason_codes: ["QLT_HIGH_ROIC", "GRW_ACCELERATING"], next_earnings_in_days: 12 },
  { ticker: "MSFT", market: "US", name_local: "Microsoft Corp.", sector_name: "Information Technology", quant_score: 78.8, ref_price: 428.42, currency: "USD", change_pct: 0.0084, value_z: -0.88, quality_z: 2.02, revision_z: 0.62, per: 32.1, pbr: 12.4, roic: 0.424, mom_12m: 0.248, realized_vol_60d: 0.212, ml_pred_h20: 0.022, ml_pred_h20_lo: -0.03, ml_pred_h20_hi: 0.074, reason_codes: ["GRW_ACCELERATING", "QLT_HIGH_ROIC"], next_earnings_in_days: 28 },
  { ticker: "8058", market: "JP", name_local: "三菱商事", sector_name: "卸売業", quant_score: 68.4, ref_price: 2840, currency: "JPY", change_pct: 0.0184, value_z: 1.34, quality_z: 0.38, revision_z: 0.24, per: 8.4, pbr: 1.02, roic: 0.088, mom_12m: 0.284, realized_vol_60d: 0.248, ml_pred_h20: 0.016, ml_pred_h20_lo: -0.04, ml_pred_h20_hi: 0.072, reason_codes: ["VAL_CHEAP_VS_SECTOR", "MOM_STRONG_12M"], next_earnings_in_days: 18 },
  { ticker: "7270", market: "JP", name_local: "SUBARU", sector_name: "輸送用機器", quant_score: 68.4, ref_price: 2480, currency: "JPY", change_pct: -0.0042, value_z: 1.02, quality_z: 0.36, revision_z: -0.14, per: 10.2, pbr: 0.98, roic: 0.084, mom_12m: 0.068, realized_vol_60d: 0.252, ml_pred_h20: 0.011, ml_pred_h20_lo: -0.044, ml_pred_h20_hi: 0.066, reason_codes: ["VAL_CHEAP_VS_SECTOR"], next_earnings_in_days: 22 },
  { ticker: "AAPL", market: "US", name_local: "Apple Inc.", sector_name: "Information Technology", quant_score: 71.2, ref_price: 189.42, currency: "USD", change_pct: -0.0083, value_z: -0.42, quality_z: 1.84, revision_z: 0.58, per: 28.4, pbr: 42.1, roic: 0.342, mom_12m: 0.124, realized_vol_60d: 0.184, ml_pred_h20: 0.016, ml_pred_h20_lo: -0.042, ml_pred_h20_hi: 0.074, reason_codes: ["QLT_HIGH_ROIC"], next_earnings_in_days: 45 },
  { ticker: "7201", market: "JP", name_local: "日産自動車", sector_name: "輸送用機器", quant_score: 28.4, ref_price: 412, currency: "JPY", change_pct: -0.0128, value_z: 1.88, quality_z: -2.14, revision_z: -1.42, per: null, pbr: 0.42, roic: -0.021, mom_12m: -0.184, realized_vol_60d: 0.384, ml_pred_h20: -0.024, ml_pred_h20_lo: -0.098, ml_pred_h20_hi: 0.05, reason_codes: ["QLT_HIGH_LEVERAGE", "MOM_WEAK_12M"], next_earnings_in_days: 26 },
];

export const SCREENER_FIELDS: ScreenerField[] = [
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

export const SCREENER_PRESETS: ScreenerPreset[] = [
  { id: "quality_value", label_ja: "クオリティ × バリュー", description_ja: "ROIC が高く、セクター内で PER が低い銘柄", filters: [{ field: "roic", op: "gte", value: 0.1 }, { field: "per", op: "lte", value: 15 }] },
  { id: "revision_up", label_ja: "予想改定が上向き", description_ja: "会社予想の上方修正が出た銘柄", filters: [{ field: "revision_z", op: "gte", value: 1 }] },
  { id: "low_vol", label_ja: "低ボラティリティ", description_ja: "実現ボラティリティが低い銘柄", filters: [{ field: "realized_vol_60d", op: "lte", value: 0.2 }] },
  { id: "high_score", label_ja: "定量スコア上位", description_ja: "定量スコア 70 以上", filters: [{ field: "quant_score", op: "gte", value: 70 }] },
  { id: "deep_value_caution", label_ja: "超割安（注意）", description_ja: "PBR 0.6倍未満。業績悪化を織り込んでいる銘柄が多く含まれます", filters: [{ field: "pbr", op: "lte", value: 0.6 }], is_cautionary: true },
];

/* ------------------------------------------------------------------ */
/* 銘柄詳細                                                            */
/* ------------------------------------------------------------------ */

export const STOCK_DETAIL_7203: StockDetail = {
  ticker: "7203",
  market: "JP",
  name_local: "トヨタ自動車",
  name_en: "Toyota Motor Corp.",
  exchange: "東証プライム",
  sector_name: "輸送用機器",
  currency: "JPY",
  quant_score: 78.4,
  ref_price: 3125,
  ref_change_pct: 0.0124,
  ref_change_abs: 38,
  ref_source: "yfinance",
  ref_is_delayed: true,
  ref_note_ja: "15分遅延の参考値です。発注には使えません",
  ref_as_of: "2026-08-22T06:10:00Z",
  next_earnings_date: "2026-11-06",
  key_metrics: [
    { key: "market_cap", label_ja: "時価総額", value: 42180000000000, format: "jpy-large" },
    { key: "per_actual", label_ja: "PER（実績）", value: 11.2, format: "multiple" },
    { key: "per_forecast", label_ja: "PER（会社予想）", value: 10.4, format: "multiple" },
    { key: "pbr", label_ja: "PBR", value: 1.18, format: "multiple" },
    { key: "ev_ebitda", label_ja: "EV/EBITDA", value: 8.4, format: "multiple" },
    { key: "dividend_yield", label_ja: "配当利回り", value: 0.0284, format: "percent" },
    { key: "roe", label_ja: "ROE", value: 0.116, format: "percent" },
    { key: "roic", label_ja: "ROIC", value: 0.124, format: "percent" },
    { key: "equity_ratio", label_ja: "自己資本比率", value: 0.382, format: "percent" },
    { key: "realized_vol_60d", label_ja: "実現ボラティリティ(60営業日)", value: 0.224, format: "percent" },
    { key: "garch_vol", label_ja: "GARCH予測ボラティリティ", value: 0.218, format: "percent" },
    { key: "adv_20d", label_ja: "平均売買代金(20営業日)", value: 41200000000, format: "jpy-large" },
    { key: "beta", label_ja: "ベータ（TOPIX比）", value: 1.04, format: "number" },
    { key: "fx_sensitivity", label_ja: "為替感応度", value: 0.42, format: "number", tooltip_ja: "ドル円1%の変化に対する株価の反応（過去60営業日の回帰係数）" },
    { key: "next_earnings", label_ja: "次回決算", value: null, format: "text", text_value: "2026年11月6日（3営業日後）" },
  ],
};

export function priceSeries(ticker: string, base = 3125): PriceSeriesData {
  const rand = seeded(ticker.split("").reduce((a, c) => a + c.charCodeAt(0), 17));
  const dates = businessDaysBack(120);
  let close = base * 0.86;
  const bars: PriceBar[] = dates.map((date) => {
    const drift = (rand() - 0.46) * base * 0.016;
    close = Math.max(base * 0.6, close + drift);
    const open = round(close - (rand() - 0.5) * base * 0.008, 2);
    const high = round(Math.max(open, close) + rand() * base * 0.006, 2);
    const low = round(Math.min(open, close) - rand() * base * 0.006, 2);
    return {
      date,
      open,
      high,
      low,
      close: round(close, 2),
      volume: Math.round(8_000_000 + rand() * 6_000_000),
    };
  });
  // 最終値は参考価格に一致させる（画面上の見出しと図が食い違わないように）
  const last = bars[bars.length - 1];
  if (last) last.close = base;
  return {
    ticker,
    market: /^[A-Z]/.test(ticker) && ticker.length <= 5 && /[A-Z]/.test(ticker) && !/^\d/.test(ticker) ? "US" : "JP",
    series: "research",
    source: "yfinance",
    is_delayed: true,
    delay_note_ja: "15分遅延の参考値です",
    latest_as_of: MOCK_AS_OF,
    bars,
  };
}

export const FINANCIALS_7203: FinancialPeriod[] = [
  { period_label_ja: "2027/3期 1Q", filed_at: "2026-08-08", is_forecast: false, revenue: 12340000000000, op_income: 1204000000000, op_margin: 0.098, net_income: 892000000000, eps: 279.4, fcf: 614000000000, currency: "JPY" },
  { period_label_ja: "2027/3期 通期（予）", filed_at: "2026-08-08", is_forecast: true, revenue: 44200000000000, op_income: 4500000000000, op_margin: 0.102, net_income: 3200000000000, eps: 1003, fcf: 2100000000000, currency: "JPY" },
  { period_label_ja: "2026/3期", filed_at: "2026-05-08", is_forecast: false, revenue: 42210000000000, op_income: 4281000000000, op_margin: 0.101, net_income: 3011000000000, eps: 944.3, fcf: 1980000000000, currency: "JPY" },
  { period_label_ja: "2025/3期", filed_at: "2025-05-09", is_forecast: false, revenue: 37154500000000, op_income: 4295700000000, op_margin: 0.116, net_income: 3070200000000, eps: 962.3, fcf: 1824000000000, currency: "JPY" },
];

export const FEATURES_7203: StockFeatures = {
  as_of: MOCK_AS_OF,
  feature_version: "v3",
  factors: RECOMMENDATIONS[0]?.factor_details ?? [],
  note_ja: "z 値はセクター中立化後の値です。母集団は流動性基準を満たす1,842銘柄。",
};

export const PEERS_7203: PeerRow[] = [
  { ticker: "7267", market: "JP", name_local: "本田技研工業", quant_score: 71.8, per: 8.9, pbr: 0.72, roic: 0.091, ret_20d: 0.042, fx_sensitivity: 0.38 },
  { ticker: "7270", market: "JP", name_local: "SUBARU", quant_score: 68.4, per: 10.2, pbr: 0.98, roic: 0.084, ret_20d: 0.038, fx_sensitivity: 0.44 },
  { ticker: "7201", market: "JP", name_local: "日産自動車", quant_score: 28.4, per: null, pbr: 0.42, roic: -0.021, ret_20d: -0.084, fx_sensitivity: 0.28 },
  { ticker: "7261", market: "JP", name_local: "マツダ", quant_score: 62.4, per: 7.4, pbr: 0.84, roic: 0.078, ret_20d: 0.021, fx_sensitivity: 0.36 },
  { ticker: "7269", market: "JP", name_local: "スズキ", quant_score: 74.2, per: 12.4, pbr: 1.24, roic: 0.112, ret_20d: 0.064, fx_sensitivity: 0.32 },
];

export const REC_HISTORY_7203: RecommendationHistoryRow[] = [
  { rec_id: "rec_001", as_of: "2026-08-22", action: "watch", horizon: "H20", conviction: "medium", expected_ret: 0.024, expected_ret_lo: -0.031, expected_ret_hi: 0.079, realized_excess_ret: null, outcome: "pending", pending_days: 20 },
  { rec_id: "rec_h02", as_of: "2026-07-18", action: "watch", horizon: "H20", conviction: "medium", expected_ret: 0.021, expected_ret_lo: -0.034, expected_ret_hi: 0.076, realized_excess_ret: 0.038, outcome: "hit", pending_days: null },
  { rec_id: "rec_h03", as_of: "2026-06-24", action: "accumulate", horizon: "H20", conviction: "high", expected_ret: 0.032, expected_ret_lo: -0.018, expected_ret_hi: 0.082, realized_excess_ret: 0.024, outcome: "hit", pending_days: null },
  { rec_id: "rec_h04", as_of: "2026-05-20", action: "watch", horizon: "H20", conviction: "medium", expected_ret: 0.018, expected_ret_lo: -0.042, expected_ret_hi: 0.078, realized_excess_ret: -0.012, outcome: "miss", pending_days: null },
  { rec_id: "rec_h05", as_of: "2026-04-15", action: "watch", horizon: "H5", conviction: "low", expected_ret: 0.008, expected_ret_lo: -0.021, expected_ret_hi: 0.037, realized_excess_ret: 0.014, outcome: "hit", pending_days: null },
];

export const SEARCH_HITS: StockSearchHit[] = [
  { ticker: "7203", market: "JP", name_local: "トヨタ自動車", name_en: "Toyota Motor Corp.", sector_name: "輸送用機器", quant_score: 78.4, group: "holdings" },
  { ticker: "6758", market: "JP", name_local: "ソニーグループ", name_en: "Sony Group Corp.", sector_name: "電気機器", quant_score: 52.1, group: "holdings" },
  { ticker: "9984", market: "JP", name_local: "ソフトバンクグループ", name_en: "SoftBank Group Corp.", sector_name: "情報・通信業", quant_score: 34.2, group: "securities" },
  { ticker: "AAPL", market: "US", name_local: "Apple Inc.", name_en: "Apple Inc.", sector_name: "Information Technology", quant_score: 71.2, group: "recent" },
  { ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", name_en: "NVIDIA Corp.", sector_name: "Information Technology", quant_score: 82.4, group: "securities" },
];

/* ------------------------------------------------------------------ */
/* 決算資料                                                            */
/* ------------------------------------------------------------------ */

export const FILINGS: DocumentSummaryRow[] = [
  { doc_id: "f001", ticker: "6758", market: "JP", name_local: "ソニーグループ", doc_type: "guidance_revision", title: "2027年3月期 通期業績予想の修正に関するお知らせ", filed_at: "2026-08-22T06:04:00Z", source: "edinet", has_summary: true, has_local_copy: true, guidance_tone: "cautious", summary_preview_ja: "通期営業利益予想を8%下方修正。ゲーム部門の販売計画未達が主因。", info_value_score: 92, estimated_summary_cost_usd: null },
  { doc_id: "f002", ticker: "7203", market: "JP", name_local: "トヨタ自動車", doc_type: "earnings_flash", title: "2027年3月期 第1四半期決算短信〔IFRS〕(連結)", filed_at: "2026-08-22T06:00:00Z", source: "edinet", has_summary: true, has_local_copy: true, guidance_tone: "positive", summary_preview_ja: "北米販売が計画超過。通期営業利益予想を5%上方修正。", info_value_score: 88, estimated_summary_cost_usd: null },
  { doc_id: "f003", ticker: "AAPL", market: "US", name_local: "Apple Inc.", doc_type: "form_10q", title: "Quarterly report for the period ended 2026-06-27", filed_at: "2026-08-22T00:30:00Z", source: "sec_edgar", has_summary: true, has_local_copy: true, guidance_tone: "positive", summary_preview_ja: "サービス売上が前年比+14%。中国は減収。", info_value_score: 74, estimated_summary_cost_usd: null },
  { doc_id: "f004", ticker: "9432", market: "JP", name_local: "日本電信電話", doc_type: "treasury_stock", title: "自己株式取得に係る事項の決定に関するお知らせ", filed_at: "2026-08-21T23:45:00Z", source: "edinet", has_summary: false, has_local_copy: true, guidance_tone: null, summary_preview_ja: null, info_value_score: 41, estimated_summary_cost_usd: 0.006 },
  { doc_id: "f005", ticker: "6098", market: "JP", name_local: "リクルートホールディングス", doc_type: "earnings_flash", title: "2026年3月期 第1四半期決算短信", filed_at: "2026-08-21T23:30:00Z", source: "edinet", has_summary: false, has_local_copy: false, guidance_tone: null, summary_preview_ja: null, info_value_score: 58, estimated_summary_cost_usd: 0.009 },
  { doc_id: "f006", ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", doc_type: "form_10q", title: "Quarterly report for quarterly period ended 2026-07-26", filed_at: "2026-08-20T20:30:00Z", source: "sec_edgar", has_summary: true, has_local_copy: true, guidance_tone: "positive", summary_preview_ja: "データセンター売上が前年比+62%。供給制約は緩和。", info_value_score: 86, estimated_summary_cost_usd: null },
  { doc_id: "f007", ticker: "7974", market: "JP", name_local: "任天堂", doc_type: "earnings_flash", title: "2027年3月期 第1四半期決算短信〔日本基準〕", filed_at: "2026-08-20T07:00:00Z", source: "edinet", has_summary: true, has_local_copy: true, guidance_tone: "positive", summary_preview_ja: "ハードウェア販売が計画超過。ソフト販売本数も増加。", info_value_score: 71, estimated_summary_cost_usd: null },
  { doc_id: "f008", ticker: "4063", market: "JP", name_local: "信越化学工業", doc_type: "earnings_flash", title: "2027年3月期 第1四半期決算短信", filed_at: "2026-08-20T06:30:00Z", source: "edinet", has_summary: true, has_local_copy: true, guidance_tone: "neutral", summary_preview_ja: "半導体材料は回復基調。塩ビは需要低迷が続く。", info_value_score: 62, estimated_summary_cost_usd: null },
  { doc_id: "f009", ticker: "8058", market: "JP", name_local: "三菱商事", doc_type: "earnings_flash", title: "2027年3月期 第1四半期決算短信", filed_at: "2026-08-20T06:15:00Z", source: "edinet", has_summary: false, has_local_copy: true, guidance_tone: null, summary_preview_ja: null, info_value_score: 54, estimated_summary_cost_usd: 0.008 },
];

DASHBOARD.watchlist_filings = FILINGS.slice(0, 6);

export const FILING_SUMMARIES: Record<string, DocumentSummary> = {
  f001: {
    doc_id: "f001",
    headline_ja: "通期営業利益予想を8%下方修正。ゲーム部門の販売計画未達が主因。",
    key_points_ja: [
      "2027年3月期の通期営業利益予想を1兆3,000億円から1兆1,960億円へ8.0%下方修正 (p.1)",
      "ゲーム&ネットワークサービス部門のハードウェア販売が計画を12%下回った (p.2)",
      "音楽・映画部門は計画を上回り、下方修正幅を一部相殺 (p.2)",
      "配当予想は据え置き、年間75円 (p.3)",
    ],
    risks_ja: [
      "北米市場における競合の値引き競争の継続 (p.4)",
      "半導体調達コストの上昇圧力 (p.4)",
      "為替前提は1ドル148円、現状の152円との差は下期に織り込み予定 (p.3)",
    ],
    guidance_tone: "cautious",
    tone_reason_ja:
      "下方修正の主因を外部環境ではなく自社の販売計画未達と説明しており、下期の回復見通しについて具体的な施策が示されていない点を慎重と判定した。",
    model: "gemini-3.7-flash",
    prompt_version: "v4",
    cost_usd: 0.009,
    generated_at: "2026-08-22T06:12:00Z",
  },
  f002: {
    doc_id: "f002",
    headline_ja: "北米販売が計画を上回り、通期営業利益予想を5%上方修正。",
    key_points_ja: [
      "通期営業利益予想を4兆2,800億円から4兆5,000億円へ5.0%上方修正 (p.3)",
      "北米の小売販売台数が計画を4%上回った (p.4)",
      "為替前提は1ドル148円で据え置き (p.3)",
    ],
    risks_ja: [
      "北米で競合の値引き圧力が継続し、販売奨励金が増加するリスク (p.24)",
      "数量ベースの改善は前年同期比+1.2%にとどまる (p.5)",
    ],
    guidance_tone: "positive",
    tone_reason_ja:
      "上方修正の根拠を数量と価格の両面で具体的に説明しており、下期の前提も保守的に置いている点を前向きと判定した。",
    model: "gemini-3.7-flash",
    prompt_version: "v4",
    cost_usd: 0.011,
    generated_at: "2026-08-22T06:14:00Z",
  },
};

/* ------------------------------------------------------------------ */
/* 為替・マクロ                                                        */
/* ------------------------------------------------------------------ */

export const FX_DATA: FxData = {
  pair: "USDJPY",
  as_of: MOCK_AS_OF,
  spot: 152.34,
  change_pct: 0.0041,
  change_abs: 0.62,
  spot_source: "yfinance",
  spot_note_ja: "yfinance の参考値（2026年8月22日 18:35 時点）",
  official_source_ja: "FRED DEXJPUS · 2026年8月21日",
  history: usdjpyHistory,
  forecasts: [
    { horizon_days: 5, model_id: "arimax_101", label_ja: "5営業日", point: 152.48, ci_lo_80: 151.2, ci_hi_80: 153.76, ci_lo_95: 150.42, ci_hi_95: 154.54, is_baseline: false, dm_statistic: -1.02, dm_pvalue: 0.31, beats_baseline: false, rmse_oos_60d: 1.826, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.51, n_validation: 248, verdict_ja: "ランダムウォークに対する優位性は確認できません（DM検定 p=0.31）" },
    { horizon_days: 20, model_id: "arimax_101", label_ja: "20営業日", point: 152.8, ci_lo_80: 150.9, ci_hi_80: 154.7, ci_lo_95: 149.4, ci_hi_95: 156.3, is_baseline: false, dm_statistic: -1.02, dm_pvalue: 0.31, beats_baseline: false, rmse_oos_60d: 1.826, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.51, n_validation: 248, verdict_ja: "ランダムウォークに対する優位性は確認できません（DM検定 p=0.31）" },
    { horizon_days: 60, model_id: "arimax_101", label_ja: "60営業日", point: 153.2, ci_lo_80: 148.4, ci_hi_80: 158.0, ci_lo_95: 145.8, ci_hi_95: 160.6, is_baseline: false, dm_statistic: -0.81, dm_pvalue: 0.42, beats_baseline: false, rmse_oos_60d: 2.184, baseline_rmse_oos_60d: 2.201, directional_accuracy_60d: 0.5, n_validation: 186, verdict_ja: "ランダムウォークに対する優位性は確認できません（DM検定 p=0.42）" },
  ],
  vol_forecast: { garch_vol_1d_ann: 0.084, garch_vol_20d_ann: 0.092, persistence: 0.94 },
  cointegration: {
    tested_pairs: ["USDJPY-US10Y", "USDJPY-RATE_DIFF"],
    rank: 0,
    detected: false,
    note_ja: "共和分は検出されませんでした（Johansen 検定、有意水準5%）",
  },
  // 09-api-spec.md の例に合わせて金利は「%ポイントの数値」（4.18 = 4.18%）で持つ
  rate_differential: { us_10y: 4.18, jp_10y: 0.76, diff: 3.42, percentile_5y: 0.78 },
};

export const FX_MODEL_COMPARISON: FxData["forecasts"] = [
  { horizon_days: 20, model_id: "random_walk", label_ja: "ランダムウォーク", point: 152.34, ci_lo_80: 150.5, ci_hi_80: 154.18, ci_lo_95: 148.7, ci_hi_95: 155.98, is_baseline: true, dm_statistic: null, dm_pvalue: null, beats_baseline: null, rmse_oos_60d: 1.842, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.5, n_validation: 248, verdict_ja: "ベースライン" },
  { horizon_days: 20, model_id: "arimax_101", label_ja: "ARIMAX(1,0,1)", point: 152.8, ci_lo_80: 150.9, ci_hi_80: 154.7, ci_lo_95: 149.4, ci_hi_95: 156.3, is_baseline: false, dm_statistic: -1.02, dm_pvalue: 0.31, beats_baseline: false, rmse_oos_60d: 1.826, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.51, n_validation: 248, verdict_ja: "優位性なし" },
  { horizon_days: 20, model_id: "vecm_2", label_ja: "VECM(2)", point: 151.9, ci_lo_80: 149.8, ci_hi_80: 154.0, ci_lo_95: 148.1, ci_hi_95: 155.7, is_baseline: false, dm_statistic: 0.36, dm_pvalue: 0.72, beats_baseline: false, rmse_oos_60d: 1.871, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.49, n_validation: 248, verdict_ja: "優位性なし" },
  { horizon_days: 20, model_id: "garch_mr", label_ja: "GARCH平均回帰", point: 152.1, ci_lo_80: 150.2, ci_hi_80: 154.0, ci_lo_95: 148.6, ci_hi_95: 155.6, is_baseline: false, dm_statistic: 0.55, dm_pvalue: 0.58, beats_baseline: false, rmse_oos_60d: 1.858, baseline_rmse_oos_60d: 1.842, directional_accuracy_60d: 0.5, n_validation: 248, verdict_ja: "優位性なし" },
];

export const MACRO_SERIES: MacroSeries[] = [
  { id: "DGS10", label_ja: "米10年国債利回り", value: 4.18, change: -0.12, unit: "percent-point", vintage: "2026-08-21", source: "fred" },
  { id: "DGS2", label_ja: "米2年国債利回り", value: 4.42, change: -0.08, unit: "percent-point", vintage: "2026-08-21", source: "fred" },
  { id: "CPIAUCSL", label_ja: "米CPI（前年同月比）", value: 2.8, change: -0.1, unit: "percent-point", vintage: "2026-08-13", source: "fred" },
  { id: "UNRATE", label_ja: "米失業率", value: 4.2, change: 0.1, unit: "percent-point", vintage: "2026-08-02", source: "fred" },
  { id: "IRLTLT01JPM156N", label_ja: "日10年国債利回り", value: 0.76, change: 0.04, unit: "percent-point", vintage: "2026-08-21", source: "fred" },
  { id: "DEXJPUS", label_ja: "ドル円", value: 152.34, change: 0.62, unit: "level", vintage: "2026-08-21", source: "fred" },
];

export const RATE_DIFF_SERIES = (() => {
  const rand = seeded(913);
  const dates = businessDaysBack(60);
  let diff = 3.1;
  let fx = 148.2;
  return dates.map((date) => {
    diff = round(diff + (rand() - 0.48) * 0.08, 3);
    fx = round(fx + (rand() - 0.42) * 0.9, 2);
    return { date, diff, usdjpy: fx };
  });
})();

export const FX_SENSITIVITY: FxSensitivityRow[] = [
  { ticker: "7203", market: "JP", name_local: "トヨタ自動車", relation: "holding", fx_sensitivity: 0.42, op_income_impact_ja: "+450億円/1円", ret_20d: 0.062, correlation_20d: 0.68, verdict_ja: "円安メリット" },
  { ticker: "7267", market: "JP", name_local: "本田技研工業", relation: "watchlist", fx_sensitivity: 0.38, op_income_impact_ja: "+280億円/1円", ret_20d: 0.042, correlation_20d: 0.64, verdict_ja: "円安メリット" },
  { ticker: "6758", market: "JP", name_local: "ソニーグループ", relation: "holding", fx_sensitivity: 0.28, op_income_impact_ja: "+120億円/1円", ret_20d: -0.008, correlation_20d: 0.42, verdict_ja: "円安メリット（小）" },
  { ticker: "9432", market: "JP", name_local: "日本電信電話", relation: "watchlist", fx_sensitivity: -0.12, op_income_impact_ja: null, ret_20d: 0.006, correlation_20d: -0.18, verdict_ja: "円高メリット（小）" },
];

/* ------------------------------------------------------------------ */
/* モデルラボ                                                          */
/* ------------------------------------------------------------------ */

export const MODEL_RUNS: ModelRun[] = [
  { run_id: "run_20260822_lgbm", model_kind: "ranker", kind: "ranker", started_at: "2026-08-21T20:10:00Z", status: "success", val_auc: 0.548, rank_ic_60d: 0.029, duration_sec: 742 },
  { run_id: "run_20260815_lgbm", model_kind: "ranker", kind: "ranker", started_at: "2026-08-14T20:10:00Z", status: "success", val_auc: 0.541, rank_ic_60d: 0.027, duration_sec: 728 },
  { run_id: "run_20260822_garch", model_kind: "garch", kind: "garch", started_at: "2026-08-21T20:30:00Z", status: "success", val_auc: null, rank_ic_60d: null, duration_sec: 92 },
  { run_id: "run_20260822_arimax", model_kind: "arimax", kind: "arimax", started_at: "2026-08-21T20:34:00Z", status: "success", val_auc: null, rank_ic_60d: null, duration_sec: 61 },
];

export const FEATURE_IMPORTANCE: FeatureImportance[] = [
  { name: "rev_guidance_op_3m", label_ja: "予想改定（営業利益・3ヶ月）", value: 0.142 },
  { name: "mom_12m_ex1m", label_ja: "12ヶ月モメンタム（直近1M除外）", value: 0.118 },
  { name: "earnings_yield", label_ja: "益回り", value: 0.096 },
  { name: "roic", label_ja: "ROIC", value: 0.081 },
  { name: "accruals_ratio", label_ja: "利益の質", value: 0.074 },
  { name: "realized_vol_60d", label_ja: "実現ボラティリティ(60営業日)", value: 0.068 },
  { name: "adv_20d_log", label_ja: "平均売買代金（対数）", value: 0.061 },
  { name: "fx_sensitivity", label_ja: "為替感応度", value: 0.054 },
  { name: "pbr", label_ja: "PBR", value: 0.048 },
  { name: "beta", label_ja: "ベータ", value: 0.038 },
];

export const IC_SERIES: IcPoint[] = (() => {
  const rand = seeded(20260822);
  const dates = businessDaysBack(60);
  const window: number[] = [];
  return dates.map((date) => {
    const ic = round((rand() - 0.42) * 0.14, 4);
    window.push(ic);
    if (window.length > 20) window.shift();
    const rolling = window.length === 20 ? round(window.reduce((a, b) => a + b, 0) / 20, 4) : null;
    return { date, ic, rolling_20d: rolling };
  });
})();

export const QUINTILES: QuintileReturn[] = [
  { quintile: "Q1", label_ja: "Q1（最下位）", excess_ret_ann: -0.042 },
  { quintile: "Q2", label_ja: "Q2", excess_ret_ann: -0.008 },
  { quintile: "Q3", label_ja: "Q3", excess_ret_ann: 0.021 },
  { quintile: "Q4", label_ja: "Q4", excess_ret_ann: 0.044 },
  { quintile: "Q5", label_ja: "Q5（最上位）", excess_ret_ann: 0.091 },
];

export const LEAKAGE_CHECKS: LeakageCheck[] = [
  { id: "T-LEAK-01", label_ja: "禁止された交差検証手法を使用していない", status: "pass", detail_ja: null },
  { id: "T-LEAK-02", label_ja: "参考現在値（prices_live）をモデルに渡していない", status: "pass", detail_ja: null },
  { id: "T-LEAK-03", label_ja: "学習期間と検証期間が重複していない", status: "pass", detail_ja: null },
  { id: "T-LEAK-04", label_ja: "合成ランダムデータでRank ICがゼロ近傍", status: "pass", detail_ja: "IC=0.004, n=248" },
  { id: "T-LEAK-05", label_ja: "バックテストのエントリーが翌営業日始値", status: "pass", detail_ja: null },
  { id: "T-PIT-01", label_ja: "財務データは開示日基準で参照", status: "pass", detail_ja: null },
];

export const BACKTESTS: Backtest[] = [
  { backtest_id: "bt_001", strategy_name: "標準戦略 v1", market: "JP", period_start: "2024-08-01", period_end: "2026-08-01", rebalance_freq: "monthly", n_positions: 20, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.3, pre_tax: true }, ann_return: 0.088, sharpe: 0.62, sortino: 0.88, max_drawdown: -0.128, hit_rate: 0.54, n_trades: 486, information_ratio: 0.41, turnover_pct: 0.28, total_cost_pct: 0.018, deflated_sharpe: 0.18, n_trials: 24, status: "not_significant", run_at: "2026-08-10T12:00:00Z" },
  { backtest_id: "bt_002", strategy_name: "高品質フィルタ", market: "JP", period_start: "2024-08-01", period_end: "2026-08-01", rebalance_freq: "monthly", n_positions: 15, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.2, pre_tax: true }, ann_return: 0.062, sharpe: 0.44, sortino: 0.61, max_drawdown: -0.094, hit_rate: 0.52, n_trades: 312, information_ratio: 0.28, turnover_pct: 0.18, total_cost_pct: 0.012, deflated_sharpe: 0.12, n_trials: 24, status: "not_significant", run_at: "2026-08-11T12:00:00Z" },
  { backtest_id: "bt_003", strategy_name: "実験的 v2", market: "JP", period_start: "2025-01-01", period_end: "2026-08-01", rebalance_freq: "monthly", n_positions: 20, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.3, pre_tax: true }, ann_return: 0.112, sharpe: 0.84, sortino: 1.18, max_drawdown: -0.082, hit_rate: 0.57, n_trades: 388, information_ratio: 0.58, turnover_pct: 0.29, total_cost_pct: 0.019, deflated_sharpe: 0.71, n_trials: 24, status: "significant", run_at: "2026-08-18T12:00:00Z" },
  { backtest_id: "bt_004", strategy_name: "バリューのみ", market: "JP", period_start: "2024-08-01", period_end: "2026-08-01", rebalance_freq: "quarterly", n_positions: 25, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.15, pre_tax: true }, ann_return: 0.044, sharpe: 0.38, sortino: 0.49, max_drawdown: -0.142, hit_rate: 0.51, n_trades: 198, information_ratio: 0.19, turnover_pct: 0.14, total_cost_pct: 0.009, deflated_sharpe: 0.08, n_trials: 24, status: "not_significant", run_at: "2026-08-19T12:00:00Z" },
  { backtest_id: "bt_005", strategy_name: "モメンタム強化", market: "JP", period_start: "2024-08-01", period_end: "2026-08-01", rebalance_freq: "monthly", n_positions: 20, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.3, pre_tax: true }, ann_return: null, sharpe: null, sortino: null, max_drawdown: null, hit_rate: null, n_trades: null, information_ratio: null, turnover_pct: null, total_cost_pct: null, deflated_sharpe: null, n_trials: 24, status: "running", run_at: "2026-08-22T06:10:00Z" },
  { backtest_id: "bt_006", strategy_name: "失敗した試行", market: "JP", period_start: "2025-01-01", period_end: "2026-08-01", rebalance_freq: "weekly", n_positions: 10, cost: { fee_bps: 5, slippage_bps: 10, max_turnover_pct: 0.4, pre_tax: true }, ann_return: null, sharpe: null, sortino: null, max_drawdown: null, hit_rate: null, n_trades: null, information_ratio: null, turnover_pct: null, total_cost_pct: null, deflated_sharpe: null, n_trials: 24, status: "failed", run_at: "2026-08-21T09:00:00Z" },
];

export const FACTOR_WEIGHTS: FactorWeights = {
  active_weight_set_id: "ws_20260701_a",
  proposed_weight_set_id: "ws_20260801_b",
  rows: [
    { factor_key: "value", label_ja: "バリュエーション", active_weight: 0.22, proposed_weight: 0.26, delta: 0.04 },
    { factor_key: "quality", label_ja: "クオリティ", active_weight: 0.18, proposed_weight: 0.2, delta: 0.02 },
    { factor_key: "momentum", label_ja: "モメンタム", active_weight: 0.24, proposed_weight: 0.22, delta: -0.02 },
    { factor_key: "growth", label_ja: "成長", active_weight: 0.12, proposed_weight: 0.1, delta: -0.02 },
    { factor_key: "revision", label_ja: "予想改定", active_weight: 0.14, proposed_weight: 0.14, delta: 0 },
    { factor_key: "lowvol", label_ja: "ボラティリティ", active_weight: 0.06, proposed_weight: 0.05, delta: -0.01 },
    { factor_key: "liquidity", label_ja: "流動性", active_weight: 0.04, proposed_weight: 0.03, delta: -0.01 },
  ],
  fit_meta_ja:
    "Ridge回帰（非負制約）· 対象 214件の推奨実績 · 期間 2026年2月 - 2026年8月 · 現行重みと50%ブレンド",
  n_samples: 214,
};

/* ------------------------------------------------------------------ */
/* エージェント                                                        */
/* ------------------------------------------------------------------ */

export const AGENT_COST: AgentCost = {
  period: "daily",
  today_usd: 0.48,
  daily_cap_usd: 1.5,
  month_usd: 8.42,
  monthly_cap_usd: 20,
  projected_month_usd: 11.6,
  kill_switch: false,
  spent_today_usd: 0.48,
  spent_month_usd: 8.42,
  breakdown: [
    { purpose_ja: "資料要約", usd: 0.18, calls: 32, share_pct: 0.38, cache_hit_ja: "24 / 32件" },
    { purpose_ja: "推奨の論拠生成", usd: 0.21, calls: 12, share_pct: 0.44, cache_hit_ja: null },
    { purpose_ja: "レビュー", usd: 0.09, calls: 12, share_pct: 0.19, cache_hit_ja: null },
    { purpose_ja: "教訓の抽出", usd: 0, calls: 0, share_pct: 0, cache_hit_ja: "週次のみ" },
  ],
  calls: [
    { called_at: "2026-08-21T21:31:12Z", purpose_ja: "資料要約", model: "gemini-3.7-flash", input_tokens: 42812, output_tokens: 1204, cost_usd: 0.0077, cache_hit: true, duration_sec: 4.2, status: "success" },
    { called_at: "2026-08-21T21:38:22Z", purpose_ja: "推奨の論拠生成", model: "claude-sonnet-5", input_tokens: 8412, output_tokens: 2840, cost_usd: 0.0678, cache_hit: false, duration_sec: 8.4, status: "success" },
    { called_at: "2026-08-21T21:44:08Z", purpose_ja: "レビュー", model: "claude-sonnet-5", input_tokens: 6284, output_tokens: 1840, cost_usd: 0.0465, cache_hit: false, duration_sec: 6.8, status: "success" },
    { called_at: "2026-08-21T21:31:48Z", purpose_ja: "資料要約", model: "gemini-3.7-flash", input_tokens: 38420, output_tokens: 1080, cost_usd: 0.0069, cache_hit: true, duration_sec: 3.8, status: "success" },
  ],
};

export const CRITIC_STATS: CriticStats = {
  days: 30,
  n_reviewed: 296,
  n_approved: 190,
  n_total: 296,
  n_rejected: 42,
  n_revised: 64,
  rejection_rate: 0.142,
  revision_rate: 0.216,
  reasons: [
    { code: "CITATION_NOT_FOUND", label_ja: "引用が原文で確認できない", count: 18 },
    { code: "BEAR_CASE_INSUBSTANTIAL", label_ja: "弱気論拠が定型的で実質がない", count: 11 },
    { code: "STALE_DATA_USED", label_ja: "古いデータに基づいている", count: 6 },
    { code: "DELAYED_PRICE_MISUSED", label_ja: "遅延データを現在値として扱う", count: 3 },
    { code: "CONVICTION_UNSUPPORTED", label_ja: "確信度がサンプル数に見合わない", count: 2 },
    { code: "INTERVAL_MISSING", label_ja: "信頼区間が欠けている", count: 1 },
    { code: "PIT_VIOLATION", label_ja: "開示日より前の情報を使用", count: 1 },
  ],
};

export const AGENT_MEMORY: AgentMemory[] = [
  {
    memory_id: "m001",
    category: "bias",
    scope: "market",
    scope_value: "JP",
    is_active: true,
    text_ja:
      "決算発表の3営業日前に生成した推奨の的中率は42% (n=38) で、それ以外の期間の57% (n=176) を大きく下回る。決算直前は確信度を一段引き下げるか、推奨を見送る。",
    evidence_ja: "2026年2月 - 2026年8月の推奨実績 214件を集計",
    confidence: 0.78,
    n_samples: 214,
    usage_count_30d: 28,
    hit_rate_before: 0.54,
    hit_rate_after: 0.59,
    n_before: 64,
    n_after: 28,
    updated_at: "2026-08-15T00:00:00Z",
  },
  {
    memory_id: "m002",
    category: "pattern",
    scope: "global",
    scope_value: null,
    is_active: true,
    text_ja:
      "為替感応度が+0.4以上の銘柄は、ドル円が急変した翌日のスコアが不安定になりやすい。急変後3営業日は確信度を引き下げる。",
    evidence_ja: "2025年1月 - 2026年8月の実績",
    confidence: 0.52,
    n_samples: 96,
    usage_count_30d: 14,
    hit_rate_before: null,
    hit_rate_after: null,
    n_before: null,
    n_after: 12,
    updated_at: "2026-08-10T00:00:00Z",
  },
  {
    memory_id: "m003",
    category: "caveat",
    scope: "market",
    scope_value: "JP",
    is_active: true,
    text_ja:
      "有価証券報告書の提出翌日は、決算短信からの追加情報が少ないため推奨の質が下がりやすい。有報提出日の翌日は定性評価をスキップ可能。",
    evidence_ja: "2026年4月 - 2026年8月",
    confidence: null,
    n_samples: 48,
    usage_count_30d: 6,
    hit_rate_before: null,
    hit_rate_after: null,
    n_before: null,
    n_after: null,
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    memory_id: "m004",
    category: "bias",
    scope: "global",
    scope_value: null,
    is_active: false,
    text_ja: "低ボラ銘柄を優先する（的中率が高い傾向）",
    evidence_ja: "2025年6月 - 2026年2月 n=44。使用時 44% (n=32) vs 未使用 56% (n=112) で有害と判定。",
    confidence: 0.22,
    n_samples: 144,
    usage_count_30d: 0,
    hit_rate_before: 0.56,
    hit_rate_after: 0.44,
    n_before: 112,
    n_after: 32,
    updated_at: "2026-07-20T00:00:00Z",
  },
];

/* ------------------------------------------------------------------ */
/* ポートフォリオ                                                      */
/* ------------------------------------------------------------------ */

export const PORTFOLIO_TOTALS: PortfolioTotals = {
  total_value: 8472150,
  currency: "JPY",
  unrealized_pnl: 495120,
  unrealized_pnl_pct: 0.062,
  realized_pnl_ytd: 182400,
  cash: 1240000,
  n_positions: 7,
  currency_split_ja: "円 78% / 米ドル 22%",
  ref_price_note_ja: "評価額は15分遅延の参考価格ベースです",
};

export const POSITIONS: Position[] = [
  { ticker: "7203", market: "JP", name_local: "トヨタ自動車", quantity: 300, avg_cost: 2948, ref_price: 3125, currency: "JPY", market_value: 937500, unrealized_pnl: 53100, unrealized_pnl_pct: 0.06, weight_pct: 0.111, quant_score: 78.4, current_view: "watch", holding_days: 42, next_earnings_in_days: 3 },
  { ticker: "6758", market: "JP", name_local: "ソニーグループ", quantity: 400, avg_cost: 3120, ref_price: 2840, currency: "JPY", market_value: 1136000, unrealized_pnl: -112000, unrealized_pnl_pct: -0.087, weight_pct: 0.134, quant_score: 52.1, current_view: "reduce", holding_days: 84, next_earnings_in_days: null },
  { ticker: "4063", market: "JP", name_local: "信越化学工業", quantity: 100, avg_cost: 5640, ref_price: 5840, currency: "JPY", market_value: 584000, unrealized_pnl: 20000, unrealized_pnl_pct: 0.035, weight_pct: 0.069, quant_score: 76.4, current_view: "watch", holding_days: 28, next_earnings_in_days: 18 },
  { ticker: "8058", market: "JP", name_local: "三菱商事", quantity: 500, avg_cost: 2620, ref_price: 2840, currency: "JPY", market_value: 1420000, unrealized_pnl: 110000, unrealized_pnl_pct: 0.084, weight_pct: 0.168, quant_score: 68.4, current_view: null, holding_days: 62, next_earnings_in_days: 18 },
  { ticker: "9432", market: "JP", name_local: "日本電信電話", quantity: 2000, avg_cost: 152.4, ref_price: 148.2, currency: "JPY", market_value: 296400, unrealized_pnl: -8400, unrealized_pnl_pct: -0.028, weight_pct: 0.035, quant_score: 61.4, current_view: null, holding_days: 18, next_earnings_in_days: 22 },
  { ticker: "AAPL", market: "US", name_local: "Apple Inc.", quantity: 50, avg_cost: 182.4, ref_price: 189.42, currency: "USD", market_value: 9471, unrealized_pnl: 351, unrealized_pnl_pct: 0.039, weight_pct: 0.171, quant_score: 71.2, current_view: "watch", holding_days: 120, next_earnings_in_days: 45 },
  { ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", quantity: 30, avg_cost: 112.8, ref_price: 142.18, currency: "USD", market_value: 4265, unrealized_pnl: 882, unrealized_pnl_pct: 0.261, weight_pct: 0.077, quant_score: 82.4, current_view: "watch", holding_days: 84, next_earnings_in_days: 12 },
];

export const PERFORMANCE: PerformancePoint[] = (() => {
  const rand = seeded(88041);
  const dates = businessDaysBack(120);
  let p = 100;
  let b = 100;
  return dates.map((date) => {
    const shock = (rand() - 0.5) * 0.9;
    p = round(p * (1 + (0.0006 + shock * 0.011)), 3);
    b = round(b * (1 + (0.0004 + shock * 0.009)), 3);
    return { date, portfolio_index: p, benchmark_index: b };
  });
})();

export const TRADES: Trade[] = [
  { trade_id: "t001", ticker: "7203", market: "JP", name_local: "トヨタ自動車", side: "buy", quantity: 100, price: 3125, fee: 275, currency: "JPY", executed_at: "2026-08-22T00:15:00Z", broker: "SBI", account_type: "特定", linked_rec_id: "rec_001", thesis_ja: "上方修正と割安さを評価。北米の競争環境は懸念だが為替の追い風が上回ると判断した。", emotion_tag: "confident", exit_plan_ja: "3,420円で半分、2,890円割れで全部撤退。", unrealized_pnl_pct: 0 },
  { trade_id: "t002", ticker: "7203", market: "JP", name_local: "トヨタ自動車", side: "buy", quantity: 200, price: 3010, fee: 530, currency: "JPY", executed_at: "2026-07-18T01:30:00Z", broker: "SBI", account_type: "特定", linked_rec_id: "rec_h02", thesis_ja: "推奨銘柄。割安かつモメンタムが良好。", emotion_tag: "neutral", exit_plan_ja: "3,300円で利確、2,820円で撤退。", unrealized_pnl_pct: 0.038 },
  { trade_id: "t003", ticker: "6758", market: "JP", name_local: "ソニーグループ", side: "buy", quantity: 400, price: 3120, fee: 1100, currency: "JPY", executed_at: "2026-06-15T00:45:00Z", broker: "SBI", account_type: "特定", linked_rec_id: null, thesis_ja: "決算後の急騰を見て飛び乗り。推奨なし。", emotion_tag: "fomo", exit_plan_ja: null, unrealized_pnl_pct: -0.087 },
  { trade_id: "t004", ticker: "9984", market: "JP", name_local: "ソフトバンクグループ", side: "sell", quantity: 200, price: 8480, fee: 1500, currency: "JPY", executed_at: "2026-05-20T05:20:00Z", broker: "SBI", account_type: "特定", linked_rec_id: null, thesis_ja: "ARM株下落による評価額悪化を懸念して撤退。", emotion_tag: "fearful", exit_plan_ja: null, unrealized_pnl_pct: null },
  { trade_id: "t005", ticker: "AAPL", market: "US", name_local: "Apple Inc.", side: "buy", quantity: 50, price: 182.4, fee: 0, currency: "USD", executed_at: "2026-04-10T13:30:00Z", broker: "楽天", account_type: "特定", linked_rec_id: "rec_003", thesis_ja: "サービス部門の成長継続とAI統合による買い替え需要。", emotion_tag: "confident", exit_plan_ja: "$210で半分売却。$168割れで全撤退。", unrealized_pnl_pct: 0.039 },
  { trade_id: "t006", ticker: "NVDA", market: "US", name_local: "NVIDIA Corp.", side: "buy", quantity: 30, price: 112.8, fee: 0, currency: "USD", executed_at: "2026-03-15T13:00:00Z", broker: "楽天", account_type: "特定", linked_rec_id: null, thesis_ja: "AIデータセンター需要の構造的成長。", emotion_tag: "confident", exit_plan_ja: "目標$160。$95割れで撤退。", unrealized_pnl_pct: 0.261 },
];

export const TRADE_ANALYSIS: TradeAnalysis = {
  recommendation_quality: {
    n_recommendations: 214,
    hit_rate: 0.552,
    avg_excess_return: 0.011,
    by_conviction: { high: 0.61, medium: 0.55, low: 0.48 },
    n_by_conviction: { high: 42, medium: 118, low: 54 },
    monotonic: true,
    note_ja: "確信度と的中率の順序は保たれています（高 61% > 中 55% > 低 48%）。",
  },
  execution_quality: {
    n_trades: 38,
    n_from_recommendation: 24,
    n_discretionary: 14,
    hit_rate_from_rec: 0.58,
    hit_rate_discretionary: 0.43,
    avg_slippage_vs_ref_bps: 12.4,
    avg_holding_days: 46,
    planned_holding_days: 20,
    by_emotion_tag: { confident: 0.57, fomo: 0.36, fearful: 0.44, neutral: 0.55 },
    n_by_emotion_tag: { confident: 14, fomo: 8, fearful: 5, neutral: 11 },
    note_ja:
      "平均保有期間46営業日は計画の20営業日を大きく超えています。「乗り遅れ懸念」で入った記録の的中率は36% (n=8) と低いです。",
  },
};

/* ------------------------------------------------------------------ */
/* 設定・システム                                                      */
/* ------------------------------------------------------------------ */

export const SETTINGS: Settings = {
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

export const SYSTEM_HEALTH: SystemHealth = {
  status: "degraded",
  data_dir_on_windows_mount: true,
  is_seed_data: true,
  components: [
    { name: "api", label_ja: "API", status: "ok", last_success: "2026-08-22T06:47:00Z", message_ja: null },
    { name: "scheduler", label_ja: "スケジューラ", status: "ok", last_success: "2026-08-21T21:47:00Z", next_run: "2026-08-22T21:00:00Z", message_ja: null },
    { name: "duckdb", label_ja: "DuckDB", status: "ok", last_success: "2026-08-21T21:47:00Z", message_ja: null },
    { name: "tdnet", label_ja: "TDnet 取得", status: "failed", last_success: "2026-08-19T07:00:00Z", message_ja: "3日連続で失敗しています", spent_today_usd: null },
    { name: "llm", label_ja: "LLM", status: "ok", last_success: "2026-08-21T21:44:00Z", message_ja: null, spent_today_usd: 0.48 },
  ],
  disk: { data_dir_gb: 38.3, free_gb: 214.6 },
  uptime_sec: 225000,
  version: "0.9.2",
  commit: "a3f91c2",
  python_version: "3.12.7",
  node_version: "22.14.0",
  os_ja: "Windows 11 + Ubuntu 24.04 (WSL2, mirrored networking)",
  last_backup_ja: "2026年8月22日 03:00（成功） · /mnt/d/ai-stock-backup",
  db_sizes_ja: "DuckDB 24.1GB · Parquet 12.8GB · SQLite 82MB · LanceDB 1.2GB",
  scheduler_alive: true,
  next_run: "2026-08-22T21:00:00Z",
  last_reboot_ja: "2026年8月20日 03:14（Windows Update）",
  resume_note_ja: "再起動後、中断していた2件のジョブをチェックポイントから自動再開しました。",
  test_results: LEAKAGE_CHECKS,
};

export const SYSTEM_FRESHNESS: SystemFreshness = {
  sources: [
    { source: "jquants", label_ja: "J-Quants", latest_as_of: "2026-05-30", expected_as_of: "2026-08-21", note_ja: "無料プランのため12週遅延しています", status: "delayed", api_key_ja: "設定済み" },
    { source: "yfinance_jp", label_ja: "yfinance (日本株)", latest_as_of: "2026-08-22", expected_as_of: "2026-08-22", note_ja: "15分遅延", status: "ok", api_key_ja: "不要" },
    { source: "yfinance_us", label_ja: "yfinance (米国株)", latest_as_of: "2026-08-21", expected_as_of: "2026-08-21", note_ja: "15分遅延", status: "ok", api_key_ja: "不要" },
    { source: "edinet", label_ja: "EDINET", latest_as_of: "2026-08-22", expected_as_of: "2026-08-22", note_ja: null, status: "ok", api_key_ja: "設定済み" },
    { source: "tdnet", label_ja: "TDnet", latest_as_of: "2026-08-19", expected_as_of: "2026-08-22", note_ja: "取得が3日連続で失敗しています", status: "failed", api_key_ja: "不要" },
    { source: "sec_edgar", label_ja: "SEC EDGAR", latest_as_of: "2026-08-21", expected_as_of: "2026-08-21", note_ja: null, status: "ok", api_key_ja: "不要" },
    { source: "fred", label_ja: "FRED", latest_as_of: "2026-08-21", expected_as_of: "2026-08-21", note_ja: null, status: "ok", api_key_ja: "設定済み" },
  ],
  worst_status: "failed",
};

/* ------------------------------------------------------------------ */
/* 銘柄詳細のフォールバック                                             */
/* ------------------------------------------------------------------ */

/** 7203 以外の銘柄でも詳細画面が壊れないように、一覧の行から詳細を組み立てる */
export function stockDetailFor(ticker: string): StockDetail | null {
  if (ticker === "7203") return STOCK_DETAIL_7203;
  const row =
    SCREENER_ROWS.find((r) => r.ticker === ticker) ??
    WATCHLIST.find((w) => w.ticker === ticker) ??
    null;
  if (!row) return null;
  const isJp = row.market === "JP";
  const price = "ref_price" in row ? row.ref_price : null;
  const screener = SCREENER_ROWS.find((r) => r.ticker === ticker);
  return {
    ticker: row.ticker,
    market: row.market,
    name_local: row.name_local,
    name_en: null,
    exchange: isJp ? "東証プライム" : "NASDAQ",
    sector_name: screener?.sector_name ?? "—",
    currency: isJp ? "JPY" : "USD",
    quant_score: row.quant_score,
    ref_price: price,
    ref_change_pct: screener?.change_pct ?? null,
    ref_change_abs: null,
    ref_source: "yfinance",
    ref_is_delayed: true,
    ref_note_ja: "15分遅延の参考値です。発注には使えません",
    ref_as_of: "2026-08-22T06:10:00Z",
    next_earnings_date: null,
    key_metrics: [
      { key: "per_forecast", label_ja: "PER（会社予想）", value: screener?.per ?? null, format: "multiple" },
      { key: "pbr", label_ja: "PBR", value: screener?.pbr ?? null, format: "multiple" },
      { key: "roic", label_ja: "ROIC", value: screener?.roic ?? null, format: "percent" },
      { key: "mom_12m", label_ja: "12ヶ月モメンタム", value: screener?.mom_12m ?? null, format: "percent" },
      { key: "realized_vol_60d", label_ja: "実現ボラティリティ(60営業日)", value: screener?.realized_vol_60d ?? null, format: "percent" },
      { key: "next_earnings", label_ja: "次回決算", value: null, format: "text", text_value: screener?.next_earnings_in_days != null ? `${screener.next_earnings_in_days}営業日後` : null },
    ],
  };
}
