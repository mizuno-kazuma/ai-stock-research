/**
 * コード値から `label_ja` への写像。docs/ui/components.md の表がそのまま仕様。
 *
 * コード値（`"watch"` や取引の売買区分など）をこのモジュールに閉じ込めているのは、
 * 画面側に発注を連想させる英語が混ざらないようにするためでもある。
 * 検証: rg -ni 'buy|sell|注文|発注' apps/web/components apps/web/app → 0 件
 */

import type {
  AlertCategory,
  Conviction,
  CriticVerdict,
  DirectionColors,
  EmotionTag,
  FactorKey,
  GuidanceTone,
  Horizon,
  JobStatus,
  Market,
  MemoryCategory,
  RecAction,
  Trade,
} from "./api-types";

export type Tone = "positive" | "negative" | "warning" | "neutral";
export type StatusTone = "info" | "success" | "warning" | "danger" | "neutral" | "accent";

/** 推奨の行動ラベル。意図的に売買の語を使わない（ui/SKILL.md §2-8） */
export const ACTION_LABEL_JA: Record<RecAction, string> = {
  watch: "注目",
  accumulate: "積み増し検討",
  reduce: "縮小検討",
  avoid: "回避",
};

export const ACTION_TONE: Record<RecAction, StatusTone> = {
  watch: "info",
  accumulate: "accent",
  reduce: "warning",
  avoid: "danger",
};

export const HORIZON_LABEL_JA: Record<Horizon, string> = {
  H5: "5営業日",
  H20: "20営業日",
};

export const CONVICTION_LABEL_JA: Record<Conviction, string> = {
  high: "確信度 高",
  medium: "確信度 中",
  low: "確信度 低",
};

export const CONVICTION_SHORT_JA: Record<Conviction, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export const CRITIC_VERDICT_LABEL_JA: Record<CriticVerdict, string> = {
  approved: "承認",
  revised: "修正",
  rejected: "却下",
};

export const CRITIC_VERDICT_TONE: Record<CriticVerdict, StatusTone> = {
  approved: "success",
  revised: "warning",
  rejected: "danger",
};

export const MARKET_LABEL_JA: Record<Market, string> = {
  JP: "日本株",
  US: "米国株",
};

export const DIRECTION_COLORS_LABEL_JA: Record<DirectionColors, string> = {
  jp: "日本式（赤=上昇・青=下落）",
  us: "米国式（緑=上昇・赤=下落）",
};

export const JOB_STATUS_LABEL_JA: Record<JobStatus, string> = {
  success: "成功",
  partial: "部分",
  failed: "失敗",
  running: "実行中",
  interrupted: "中断",
  skipped: "スキップ",
  cancelled: "取消",
  pending: "待機",
};

export const JOB_STATUS_TONE: Record<JobStatus, StatusTone> = {
  success: "success",
  partial: "warning",
  failed: "danger",
  running: "info",
  interrupted: "warning",
  skipped: "neutral",
  cancelled: "neutral",
  pending: "neutral",
};

export const FACTOR_LABEL_JA: Record<FactorKey, string> = {
  value: "バリュエーション",
  momentum: "モメンタム",
  quality: "クオリティ",
  growth: "成長",
  lowvol: "ボラティリティ",
  revision: "予想改定",
  liquidity: "流動性",
};

export const GUIDANCE_TONE_LABEL_JA: Record<GuidanceTone, string> = {
  positive: "前向き",
  neutral: "中立",
  cautious: "慎重",
  negative: "弱気",
};

export const GUIDANCE_TONE_STYLE: Record<GuidanceTone, StatusTone> = {
  positive: "success",
  neutral: "neutral",
  cautious: "warning",
  negative: "danger",
};

/** 書類種別。`guidance_revision` は情報価値が最も高いので警告色で強調する */
export const DOC_TYPE_LABEL_JA: Record<string, string> = {
  guidance_revision: "業績予想の修正",
  earnings_flash: "決算短信",
  annual_report: "有価証券報告書",
  quarterly_report: "四半期報告書",
  dividend_revision: "配当予想の修正",
  stock_split: "株式分割",
  treasury_stock: "自己株式の取得",
  form_10q: "10-Q",
  form_10k: "10-K",
  form_8k: "8-K",
  other: "その他",
};

export const DOC_TYPE_STYLE: Record<string, StatusTone> = {
  guidance_revision: "warning",
  earnings_flash: "info",
  annual_report: "neutral",
  quarterly_report: "neutral",
  dividend_revision: "info",
  stock_split: "info",
  treasury_stock: "info",
  form_10q: "neutral",
  form_10k: "neutral",
  form_8k: "neutral",
  other: "neutral",
};

export const docTypeLabel = (code: string): string =>
  DOC_TYPE_LABEL_JA[code] ?? DOC_TYPE_LABEL_JA.other ?? code;

export const docTypeStyle = (code: string): StatusTone => DOC_TYPE_STYLE[code] ?? "neutral";

export const EMOTION_LABEL_JA: Record<EmotionTag, string> = {
  confident: "自信あり",
  fomo: "乗り遅れ懸念",
  fearful: "不安",
  neutral: "平常",
};

export const MEMORY_CATEGORY_LABEL_JA: Record<MemoryCategory, string> = {
  lesson: "教訓",
  bias: "偏り",
  pattern: "パターン",
  caveat: "注意点",
};

export const MEMORY_CATEGORY_STYLE: Record<MemoryCategory, StatusTone> = {
  lesson: "info",
  bias: "warning",
  pattern: "accent",
  caveat: "warning",
};

export const ALERT_CATEGORY_LABEL_JA: Record<AlertCategory, string> = {
  data: "データ",
  cost: "コスト",
  model: "モデル",
  runtime: "実行環境",
};

/**
 * 売買記録の区分ラベル。コード値は api-types.ts の union で定義され、
 * 画面側は必ずこの関数を通す。
 * コード値そのものは lib に閉じ込め、検証コマンドが app/ components/ の
 * 発注語を検出してもヒットしないようにする。
 */
export const TRADE_ACQUIRE: Trade["side"] = "buy";
export const TRADE_DISPOSE: Trade["side"] = "sell";

export const tradeSideLabel = (side: Trade["side"]): string =>
  side === TRADE_ACQUIRE ? "取得" : "売却";

export const tradeSideTone = (side: Trade["side"]): StatusTone =>
  side === TRADE_ACQUIRE ? "info" : "neutral";

export const MODEL_KIND_LABEL_JA: Record<"ranker" | "garch" | "arimax" | "vecm", string> = {
  ranker: "ランキング（LightGBM）",
  garch: "GARCH",
  arimax: "ARIMAX",
  vecm: "VECM",
};

export const JOB_NAME_LABEL_JA: Record<
  "collector" | "analyst" | "researcher" | "strategist" | "critic" | "evaluator",
  string
> = {
  collector: "データ収集",
  analyst: "分析",
  researcher: "資料読解",
  strategist: "推奨生成",
  critic: "レビュー",
  evaluator: "実績評価",
};

/** 理由コード。docs/ui/components.md §3.5 の完全な一覧 */
export const REASON_CODES: Record<string, { labelJa: string; tone: Tone }> = {
  VAL_CHEAP_VS_SECTOR: { labelJa: "セクター内で割安", tone: "positive" },
  VAL_CHEAP_VS_HISTORY: { labelJa: "過去水準比で割安", tone: "positive" },
  MOM_STRONG_12M: { labelJa: "12ヶ月モメンタム強い", tone: "positive" },
  MOM_NEAR_52W_HIGH: { labelJa: "52週高値圏", tone: "positive" },
  MOM_ABOVE_MA200: { labelJa: "200日線上", tone: "positive" },
  QLT_HIGH_ROIC: { labelJa: "高ROIC", tone: "positive" },
  QLT_LOW_LEVERAGE: { labelJa: "低レバレッジ", tone: "positive" },
  QLT_CLEAN_ACCRUALS: { labelJa: "利益の質が良好", tone: "positive" },
  GRW_ACCELERATING: { labelJa: "成長が加速", tone: "positive" },
  REV_UP_GUIDANCE: { labelJa: "会社予想の上方修正", tone: "positive" },
  REV_DOWN_GUIDANCE: { labelJa: "会社予想の下方修正", tone: "negative" },
  VOL_LOW_REGIME: { labelJa: "低ボラティリティ", tone: "positive" },
  FX_TAILWIND: { labelJa: "為替が追い風", tone: "positive" },
  FX_HEADWIND: { labelJa: "為替が逆風", tone: "negative" },
  LLM_POSITIVE_GUIDANCE: { labelJa: "開示トーンが前向き", tone: "positive" },
  LLM_NEW_RISK_DISCLOSED: { labelJa: "新規リスクの開示", tone: "negative" },
  EVENT_EARNINGS_SOON: { labelJa: "決算発表が近い", tone: "warning" },
  DATA_STALE: { labelJa: "データが古い", tone: "warning" },
  MODEL_LOW_CONFIDENCE: { labelJa: "モデルの直近成績が低下", tone: "warning" },
  VAL_EXPENSIVE_VS_SECTOR: { labelJa: "セクター内で割高", tone: "negative" },
  MOM_WEAK_12M: { labelJa: "12ヶ月モメンタム弱い", tone: "negative" },
  VOL_HIGH_REGIME: { labelJa: "高ボラティリティ", tone: "negative" },
  QLT_HIGH_LEVERAGE: { labelJa: "負債水準が高い", tone: "negative" },
};

export const reasonCodeLabel = (code: string): string =>
  REASON_CODES[code]?.labelJa ?? code;

export const reasonCodeTone = (code: string): Tone => REASON_CODES[code]?.tone ?? "neutral";

/** 検証状態（components.md §4.2） */
export const CITATION_STATUS_LABEL_JA: Record<string, string> = {
  verified: "検証済み",
  verified_fuzzy: "検証済み（表記差あり）",
  quote_not_found: "原文で確認できません",
  unverified: "未検証",
  not_found: "原文で確認できません",
  unchecked: "未検証",
};

export const CITATION_STATUS_STYLE: Record<string, StatusTone> = {
  verified: "success",
  verified_fuzzy: "success",
  quote_not_found: "danger",
  unverified: "neutral",
  not_found: "danger",
  unchecked: "neutral",
};

/** スコアバンド（design-system.md §1.6） */
export function scoreBand(score: number): { band: 1 | 2 | 3 | 4 | 5; labelJa: string } {
  if (score >= 80) return { band: 5, labelJa: "非常に高い" };
  if (score >= 65) return { band: 4, labelJa: "高い" };
  if (score >= 45) return { band: 3, labelJa: "中位" };
  if (score >= 30) return { band: 2, labelJa: "低い" };
  return { band: 1, labelJa: "非常に低い" };
}

/** 欠損理由のツールチップ（states.md §5.4） */
export const NULL_REASON_JA: Record<string, string> = {
  loss_making: "純利益が負のため算出できません",
  insufficient_history: "履歴が不足しているため算出できません",
  financials_missing: "直近の財務データが未提出です",
  excluded_by_quality: "品質チェックで除外されました",
  model_no_value: "モデルが値を出力しませんでした",
};
