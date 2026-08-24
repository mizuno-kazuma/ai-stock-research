/**
 * 表示フォーマッタ。docs/ui/SKILL.md §8 の表がそのまま仕様。
 *
 * 原則:
 * - 数値の表示ロジックを画面に散らさない。表示は必ずここを通す。
 * - `null` / `undefined` / `NaN` を `0` として表示しない。`NULL_PLACEHOLDER` を返す。
 * - 符号の有無が意味を持つ値は、色ではなく符号で方向を伝える。
 */

export const NULL_PLACEHOLDER = "—";

export type Nullable<T> = T | null | undefined;

export type Direction = "up" | "down" | "flat";

export type NumericFormat =
  | "percent"
  | "currency-jpy"
  | "currency-usd"
  | "number"
  | "zscore";

const isMissing = (value: Nullable<number>): value is null | undefined =>
  value === null || value === undefined || Number.isNaN(value);

const group = (value: number, fractionDigits = 0): string =>
  value.toLocaleString("ja-JP", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });

const signOf = (value: number, fractionDigits: number): string => {
  // 表示桁で丸めた結果が 0 になる値は「変化なし」として扱う。
  // -0.001% を「-0.00%」と出すと下落したように読めてしまう。
  const rounded = Number(value.toFixed(fractionDigits + 2));
  if (rounded > 0) return "+";
  if (rounded < 0) return "-";
  return "\u00B1";
};

const withSign = (value: number, body: string, fractionDigits: number): string =>
  `${signOf(value, fractionDigits)}${body}`;

/** 円価格。`3,125円` */
export function formatJpy(value: Nullable<number>, fractionDigits = 0): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return `${group(value, fractionDigits)}円`;
}

/** ドル価格。`$189.42` */
export function formatUsd(value: Nullable<number>, fractionDigits = 2): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  const sign = value < 0 ? "-" : "";
  return `${sign}$${group(Math.abs(value), fractionDigits)}`;
}

/** 小額のドル（LLMコストなど）。`$0.0077` */
export function formatUsdPrecise(value: Nullable<number>, fractionDigits = 4): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return `$${value.toFixed(fractionDigits)}`;
}

/** 大きい円金額を日本語単位で。`42兆1,800億円` / `5,120億円` */
export function formatJpyLarge(value: Nullable<number>): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);

  if (abs < 1e4) return `${sign}${group(Math.round(abs))}円`;
  if (abs < 1e8) return `${sign}${group(Math.round(abs / 1e4))}万円`;

  const totalOku = Math.round(abs / 1e8);
  const cho = Math.floor(totalOku / 1e4);
  const oku = totalOku % 1e4;

  if (cho > 0) {
    return oku > 0
      ? `${sign}${group(cho)}兆${group(oku)}億円`
      : `${sign}${group(cho)}兆円`;
  }
  return `${sign}${group(oku)}億円`;
}

export interface PercentOptions {
  /** 符号を常に付ける。方向を表す値では必ず true にする */
  sign?: boolean;
  precision?: number;
}

/** 変化率。API は比率（0.0823）で返すので、ここで100倍する。`+8.23%` */
export function formatPct(value: Nullable<number>, options: PercentOptions = {}): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  const precision = options.precision ?? 2;
  const body = `${Math.abs(value * 100).toFixed(precision)}%`;
  return options.sign ? withSign(value, body, precision) : `${(value * 100).toFixed(precision)}%`;
}

/** すでにパーセント単位の値（4.18 = 4.18%）。FRED のマクロ指標など */
export function formatPctPoint(
  value: Nullable<number>,
  options: PercentOptions = {},
): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  const precision = options.precision ?? 2;
  const body = `${Math.abs(value).toFixed(precision)}%`;
  return options.sign ? withSign(value, body, precision) : `${value.toFixed(precision)}%`;
}

/** 0-100 のスコア。`78.4` */
export function formatScore(value: Nullable<number>): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return value.toFixed(1);
}

/** z-score。符号を常に付ける。`+1.42` / `-0.21` */
export function formatZ(value: Nullable<number>, precision = 2): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return withSign(value, Math.abs(value).toFixed(precision), precision);
}

/** 倍率。`9.2倍` */
export function formatMultiple(value: Nullable<number>, precision = 1): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return `${value.toFixed(precision)}倍`;
}

/** 出来高。`8,234,100株` */
export function formatVolume(value: Nullable<number>): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return `${group(Math.round(value))}株`;
}

/** ベーシスポイント。`5.0bps` */
export function formatBps(value: Nullable<number>, precision = 1): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  return `${value.toFixed(precision)}bps`;
}

/** 汎用の数値ディスパッチャ。DirectionValue / ForecastValue が使う */
export function formatNumeric(
  value: Nullable<number>,
  format: NumericFormat,
  options: { sign?: boolean; precision?: number } = {},
): string {
  if (isMissing(value)) return NULL_PLACEHOLDER;
  switch (format) {
    case "percent":
      return formatPct(value, { sign: options.sign, precision: options.precision ?? 2 });
    case "currency-jpy": {
      const precision = options.precision ?? 0;
      const body = formatJpy(Math.abs(value), precision);
      return options.sign ? withSign(value, body, precision) : formatJpy(value, precision);
    }
    case "currency-usd": {
      const precision = options.precision ?? 2;
      const body = formatUsd(Math.abs(value), precision);
      return options.sign ? withSign(value, body, precision) : formatUsd(value, precision);
    }
    case "zscore":
      return formatZ(value, options.precision ?? 2);
    case "number": {
      const precision = options.precision ?? 2;
      const body = Math.abs(value).toFixed(precision);
      return options.sign ? withSign(value, body, precision) : value.toFixed(precision);
    }
  }
}

/** 点推定と信頼区間。`+2.4% [-3.1%, +7.9%]` */
export function formatInterval(
  point: Nullable<number>,
  lo: Nullable<number>,
  hi: Nullable<number>,
  options: { format?: NumericFormat; precision?: number } = {},
): string {
  const format = options.format ?? "percent";
  const precision = options.precision ?? (format === "percent" ? 1 : 2);
  if (isMissing(point) || isMissing(lo) || isMissing(hi)) return NULL_PLACEHOLDER;
  const fmt = (v: number) => formatNumeric(v, format, { sign: true, precision });
  return `${fmt(point)} [${fmt(lo)}, ${fmt(hi)}]`;
}

/** 区間のみ。`[-3.1%, +7.9%]` */
export function formatIntervalOnly(
  lo: Nullable<number>,
  hi: Nullable<number>,
  options: { format?: NumericFormat; precision?: number } = {},
): string {
  const format = options.format ?? "percent";
  const precision = options.precision ?? (format === "percent" ? 1 : 2);
  if (isMissing(lo) || isMissing(hi)) return NULL_PLACEHOLDER;
  const fmt = (v: number) => formatNumeric(v, format, { sign: true, precision });
  return `[${fmt(lo)}, ${fmt(hi)}]`;
}

/**
 * 母数付きの比率。`58% (n=34)`
 * 比率を単独で出すことは仕様違反なので、母数のない版は用意しない。
 */
export function formatRateWithN(
  rate: Nullable<number>,
  sampleSize: Nullable<number>,
  precision = 0,
): string {
  const ratePart = isMissing(rate)
    ? NULL_PLACEHOLDER
    : `${(rate * 100).toFixed(precision)}%`;
  const nPart = isMissing(sampleSize) ? NULL_PLACEHOLDER : String(Math.round(sampleSize));
  return `${ratePart} (n=${nPart})`;
}

/** 欠損値。`—`（呼び出し側で fg-muted を当てる） */
export function formatNullable<T>(
  value: Nullable<T>,
  formatter?: (v: NonNullable<T>) => string,
): string {
  if (value === null || value === undefined) return NULL_PLACEHOLDER;
  if (typeof value === "number" && Number.isNaN(value)) return NULL_PLACEHOLDER;
  return formatter ? formatter(value as NonNullable<T>) : String(value);
}

/** 表の中の日付は ISO のまま。`2026-08-22` */
export function formatDateIso(value: Nullable<string>): string {
  if (!value) return NULL_PLACEHOLDER;
  return value.slice(0, 10);
}

/** 文中の日付。`2026年8月22日` */
export function formatDateJa(value: Nullable<string>): string {
  if (!value) return NULL_PLACEHOLDER;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return NULL_PLACEHOLDER;
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

const JST_OPTIONS: Intl.DateTimeFormatOptions = {
  timeZone: "Asia/Tokyo",
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
};

/** 日時は JST に変換して表示。`2026年8月22日 18:35` */
export function formatDateTimeJst(value: Nullable<string>): string {
  if (!value) return NULL_PLACEHOLDER;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return NULL_PLACEHOLDER;
  const parts = new Intl.DateTimeFormat("ja-JP", JST_OPTIONS).formatToParts(d);
  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${pick("year")}年${pick("month")}月${pick("day")}日 ${pick("hour")}:${pick("minute")}`;
}

/** 時刻のみ。`18:35` */
export function formatTimeJst(value: Nullable<string>): string {
  if (!value) return NULL_PLACEHOLDER;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return NULL_PLACEHOLDER;
  const parts = new Intl.DateTimeFormat("ja-JP", JST_OPTIONS).formatToParts(d);
  const pick = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? "";
  return `${pick("hour")}:${pick("minute")}`;
}

/** 秒数を日本語の所要時間に。`4分12秒` */
export function formatDuration(seconds: Nullable<number>): string {
  if (isMissing(seconds)) return NULL_PLACEHOLDER;
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m === 0) return `${s}秒`;
  return `${m}分${String(s).padStart(2, "0")}秒`;
}

/** 方向の判定。0 は flat（符号なし） */
export function directionOf(value: Nullable<number>, invert = false): Direction {
  if (isMissing(value) || value === 0) return "flat";
  const up = value > 0;
  return (invert ? !up : up) ? "up" : "down";
}
