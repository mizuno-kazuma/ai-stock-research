/**
 * 市場コードの正規化。
 *
 * `ui.default_market` は JP / US / auto を取る（docs/ui/screens/10-settings.md）。
 * API の `market` は JP / US だけなので、auto は日本時間 15 時で切り替える。
 */

import type { DefaultMarket, Market } from "./api-types";

/** これ未満は日本株、これ以降は米国株（JST） */
export const AUTO_MARKET_SWITCH_HOUR_JST = 15;

export function isMarket(value: unknown): value is Market {
  return value === "JP" || value === "US";
}

export function isDefaultMarket(value: unknown): value is DefaultMarket {
  return isMarket(value) || value === "auto";
}

export function jstHour(now: Date = new Date()): number {
  const hour = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    hour: "numeric",
    hourCycle: "h23",
  }).format(now);
  const parsed = Number(hour);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** 設定値や誤って残った `auto` を、API に渡せる JP / US にする。 */
export function resolveMarket(value: unknown, now: Date = new Date()): Market {
  if (isMarket(value)) return value;
  if (value === "auto") {
    return jstHour(now) < AUTO_MARKET_SWITCH_HOUR_JST ? "JP" : "US";
  }
  return "JP";
}
