/**
 * 数値表示コンポーネント。画面はここを経由して数字を出す。
 *
 * ここが担保していること:
 * - 方向（上昇・下落）は `--dir-*` トークン参照。ユーザーが日本式／米国式を切り替えても
 *   コンポーネントを直さなくてよい。色だけに頼らず必ず符号を併記する。
 * - 予測値は点推定だけでは出せない（`ForecastValue` が区間を必須引数にしている）。
 * - 比率は母数なしでは出せない（`RateWithN` が n を必須引数にしている）。
 * - null は `—`。0 に丸めない。
 */

import type { ReactNode } from "react";
import {
  directionOf,
  formatIntervalOnly,
  formatNumeric,
  formatPctPoint,
  formatRateWithN,
  formatScore,
  formatZ,
  NULL_PLACEHOLDER,
  type Direction,
  type NumericFormat,
  type Nullable,
} from "@ai-stock/ui";

import { CONVICTION_LABEL_JA, CONVICTION_SHORT_JA, scoreBand, type StatusTone } from "../lib/labels";
import type { CiLevel, Conviction } from "../lib/api-types";
import { Badge, cx } from "./ui";

const DIR_TEXT: Record<Direction, string> = {
  up: "text-dir-up",
  down: "text-dir-down",
  flat: "text-dir-flat",
};

/** 色が読めない環境でも方向が分かるように、符号のほかに矢印も添える */
const DIR_ARROW: Record<Direction, string> = { up: "▲", down: "▼", flat: "－" };

const DIR_LABEL: Record<Direction, string> = { up: "上昇", down: "下落", flat: "変化なし" };

export interface DirectionValueProps {
  value: Nullable<number>;
  format?: NumericFormat;
  precision?: number;
  /** 下落が良い指標（ドローダウンなど）で色を反転させる */
  invert?: boolean;
  showArrow?: boolean;
  className?: string;
  /** 括弧で添える副次情報（絶対額など） */
  suffix?: ReactNode;
}

export function DirectionValue({
  value,
  format = "percent",
  precision,
  invert = false,
  showArrow = false,
  className,
  suffix,
}: DirectionValueProps) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className={cx("num text-fg-muted", className)}>{NULL_PLACEHOLDER}</span>;
  }
  const dir = directionOf(value, invert);
  const text = formatNumeric(value, format, { sign: true, precision });
  return (
    <span className={cx("num", DIR_TEXT[dir], className)}>
      {showArrow ? (
        <span aria-hidden="true" className="mr-0.5 text-micro">
          {DIR_ARROW[dir]}
        </span>
      ) : null}
      {text}
      {suffix ? <span className="text-fg-tertiary ml-1">{suffix}</span> : null}
      <span className="visually-hidden">（{DIR_LABEL[dir]}）</span>
    </span>
  );
}

/** すでに % 単位の値（金利など）。方向色つき */
export function DirectionPctPoint({ value, className }: { value: Nullable<number>; className?: string }) {
  if (value === null || value === undefined) {
    return <span className={cx("num text-fg-muted", className)}>{NULL_PLACEHOLDER}</span>;
  }
  const dir = directionOf(value);
  return (
    <span className={cx("num", DIR_TEXT[dir], className)}>
      {formatPctPoint(value, { sign: true })}
      <span className="visually-hidden">（{DIR_LABEL[dir]}）</span>
    </span>
  );
}

export interface ForecastValueProps {
  point: Nullable<number>;
  /** 区間は必須。点推定だけの表示を型で禁じている */
  lo: Nullable<number>;
  hi: Nullable<number>;
  ciLevel: CiLevel;
  format?: NumericFormat;
  precision?: number;
  /** 過去の的中率とその母数。両方あるときだけ出す */
  hitRate?: Nullable<number>;
  nSamples?: Nullable<number>;
  /** API が生成した判定文。UI では加工しない */
  verdictJa?: string | null;
  layout?: "inline" | "stacked";
  className?: string;
}

export function ForecastValue({
  point,
  lo,
  hi,
  ciLevel,
  format = "percent",
  precision,
  hitRate,
  nSamples,
  verdictJa,
  layout = "stacked",
  className,
}: ForecastValueProps) {
  const dir = directionOf(point ?? null);
  const pointText =
    point === null || point === undefined
      ? NULL_PLACEHOLDER
      : formatNumeric(point, format, { sign: true, precision });
  const intervalText = formatIntervalOnly(lo, hi, { format, precision });

  if (layout === "inline") {
    return (
      <span className={cx("num", className)}>
        <span className={DIR_TEXT[dir]}>{pointText}</span>
        <span className="text-fg-tertiary ml-1">
          {intervalText} <span className="text-micro">{ciLevel}%区間</span>
        </span>
      </span>
    );
  }

  return (
    <div className={cx("min-w-0", className)}>
      <div className="num text-metric-sm">
        <span className={DIR_TEXT[dir]}>{pointText}</span>
        <span className="text-body-sm text-fg-secondary ml-2">{intervalText}</span>
      </div>
      <div className="text-caption text-fg-tertiary mt-0.5">
        {ciLevel}%信頼区間
        {hitRate !== undefined || nSamples !== undefined ? (
          <> · 過去の的中率 {formatRateWithN(hitRate ?? null, nSamples ?? null)}</>
        ) : null}
      </div>
      {verdictJa ? <p className="text-caption text-fg-secondary mt-1 prose-block">{verdictJa}</p> : null}
    </div>
  );
}

/** 予測の区間つき1行表示（表のセル用） */
export function ForecastCell({
  point,
  lo,
  hi,
  format = "percent",
}: {
  point: Nullable<number>;
  lo: Nullable<number>;
  hi: Nullable<number>;
  format?: NumericFormat;
}) {
  const dir = directionOf(point ?? null);
  const pointText =
    point === null || point === undefined
      ? NULL_PLACEHOLDER
      : formatNumeric(point, format, { sign: true });
  return (
    <span className="num">
      <span className={DIR_TEXT[dir]}>{pointText}</span>
      <span className="block text-micro text-fg-tertiary">{formatIntervalOnly(lo, hi, { format })}</span>
    </span>
  );
}

const BAND_TEXT: Record<1 | 2 | 3 | 4 | 5, string> = {
  5: "text-score-band-5 border-score-band-5",
  4: "text-score-band-4 border-score-band-4",
  3: "text-score-band-3 border-score-band-3",
  2: "text-score-band-2 border-score-band-2",
  1: "text-score-band-1 border-score-band-1",
};

export function ScoreBadge({
  score,
  size = "md",
  showLabel = false,
}: {
  score: Nullable<number>;
  size?: "sm" | "md" | "lg";
  showLabel?: boolean;
}) {
  if (score === null || score === undefined) {
    return <span className="num text-fg-muted">{NULL_PLACEHOLDER}</span>;
  }
  const { band, labelJa } = scoreBand(score);
  const sizeClass = size === "lg" ? "text-metric" : size === "sm" ? "text-body-sm" : "text-metric-sm";
  return (
    <span
      className={cx(
        "num inline-flex items-baseline gap-1 rounded-md border bg-sunken px-2 py-0.5",
        BAND_TEXT[band],
        sizeClass,
      )}
      title={`定量スコア ${formatScore(score)}（${labelJa}）`}
    >
      {formatScore(score)}
      {showLabel ? <span className="text-caption">{labelJa}</span> : null}
    </span>
  );
}

const CONVICTION_CLASS: Record<Conviction, string> = {
  high: "text-conviction-high border-conviction-high",
  medium: "text-conviction-medium border-conviction-medium",
  low: "text-conviction-low border-conviction-low",
};

export function ConvictionBadge({ conviction, short = false }: { conviction: Conviction; short?: boolean }) {
  return (
    <span
      className={cx(
        "badge border bg-sunken",
        CONVICTION_CLASS[conviction],
      )}
      title={CONVICTION_LABEL_JA[conviction]}
    >
      {short ? CONVICTION_SHORT_JA[conviction] : CONVICTION_LABEL_JA[conviction]}
    </span>
  );
}

/** 比率は必ず母数と一緒に出す */
export function RateWithN({
  rate,
  n,
  precision = 0,
  className,
}: {
  rate: Nullable<number>;
  n: Nullable<number>;
  precision?: number;
  className?: string;
}) {
  return <span className={cx("num", className)}>{formatRateWithN(rate, n, precision)}</span>;
}

/** z-score。符号つき、方向色は付けない（良し悪しが指標によって違う） */
export function ZValue({ value, className }: { value: Nullable<number>; className?: string }) {
  const missing = value === null || value === undefined;
  return (
    <span className={cx("num", missing ? "text-fg-muted" : "text-fg-primary", className)}>
      {formatZ(value)}
    </span>
  );
}

/** 欠損の可能性がある任意の値。欠損理由が分かるときは title に出す */
export function NullableText({
  value,
  reasonJa,
  className,
}: {
  value: string | null | undefined;
  reasonJa?: string | null;
  className?: string;
}) {
  if (value === null || value === undefined || value === "" || value === NULL_PLACEHOLDER) {
    return (
      <span className={cx("text-fg-muted", className)} title={reasonJa ?? "データがありません"}>
        {NULL_PLACEHOLDER}
      </span>
    );
  }
  return <span className={className}>{value}</span>;
}

/** 大きな指標カード。値はフォーマット済み文字列か DirectionValue を渡す */
export function MetricCard({
  label,
  value,
  sub,
  asOf,
  tone,
  hint,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  asOf?: string;
  tone?: StatusTone;
  hint?: string;
}) {
  return (
    <div className="card p-4 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-caption text-fg-tertiary truncate" title={hint}>
          {label}
        </span>
        {tone ? <Badge tone={tone}>{tone === "warning" ? "注意" : ""}</Badge> : null}
      </div>
      <div className="num text-metric mt-1 text-fg-primary">{value}</div>
      {sub ? <div className="text-caption text-fg-secondary mt-1">{sub}</div> : null}
      {asOf ? <div className="text-micro text-fg-muted mt-1">{asOf}</div> : null}
    </div>
  );
}

/** 変化率の短縮表示（見出し横などで使う） */
export function ChangePct({ value, precision = 2 }: { value: Nullable<number>; precision?: number }) {
  return <DirectionValue value={value} format="percent" precision={precision} />;
}
