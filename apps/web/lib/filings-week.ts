/**
 * 「今週の開示」の対象期間。API の `_filings_range` と同じく、
 * as_of を含む暦週の月曜から as_of 当日まで（タイムゾーンに依存しない暦日計算）。
 */

export function filingsWeekRange(asOf: string | null | undefined): { start: string; end: string } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(asOf ?? "");
  if (!m) return null;
  const y = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const endUtc = Date.UTC(y, month - 1, day, 12, 0, 0);
  const end = new Date(endUtc);
  if (end.getUTCFullYear() !== y || end.getUTCMonth() !== month - 1 || end.getUTCDate() !== day) {
    return null;
  }
  const mondayOffset = (end.getUTCDay() + 6) % 7;
  const start = new Date(endUtc - mondayOffset * 86_400_000);
  const iso = (dt: Date) =>
    `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`;
  return { start: iso(start), end: iso(end) };
}

/** 字幕・空状態用。`8/17–8/22`。年をまたぐときだけ年を付ける。 */
export function formatFilingsWeekLabel(asOf: string | null | undefined): string | null {
  const range = filingsWeekRange(asOf);
  if (!range) return null;
  const [sy, sm, sd] = range.start.split("-").map(Number);
  const [ey, em, ed] = range.end.split("-").map(Number);
  if (sy !== ey) return `${sy}/${sm}/${sd}–${ey}/${em}/${ed}`;
  if (sm === em && sd === ed) return `${sm}/${sd}`;
  return `${sm}/${sd}–${em}/${ed}`;
}
