/**
 * 発行体の同一性。JP の 4 桁（7203）と J-Quants の 5 桁（72030）は同じ銘柄。
 */

export function canonicalJpTicker(ticker: string): string {
  const value = ticker.trim();
  if (value.length === 5 && value.endsWith("0")) return value.slice(0, 4);
  return value;
}

export function issuerKey(market: string, ticker: string): string {
  const t = market === "JP" ? canonicalJpTicker(ticker) : ticker.trim();
  return `${market}:${t}`;
}

function hasName(hit: { ticker: string; name_local?: string | null }): boolean {
  const name = (hit.name_local ?? "").trim();
  return Boolean(name) && name !== hit.ticker;
}

export function uniqueByIssuer<T extends { market: string; ticker: string; name_local?: string | null }>(
  rows: T[],
  extra?: (row: T) => string,
): T[] {
  const best = new Map<string, T>();
  const order: string[] = [];
  for (const row of rows) {
    const key = extra ? `${issuerKey(row.market, row.ticker)}:${extra(row)}` : issuerKey(row.market, row.ticker);
    const prev = best.get(key);
    if (!prev) {
      best.set(key, row);
      order.push(key);
      continue;
    }
    if (hasName(row) && !hasName(prev)) {
      best.set(key, row);
      continue;
    }
    if (hasName(row) === hasName(prev) && row.ticker.length < prev.ticker.length) {
      best.set(key, row);
    }
  }
  return order.map((key) => best.get(key)!);
}
