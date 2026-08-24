"use client";

/**
 * データ鮮度の表示。全画面のヘッダに常設する（components.md §1.3）。
 *
 * 日本株のリサーチ用株価は無料プランで12週遅れる。これを隠すと判断を誤るので、
 * 集約ステータス（最新 / 一部遅延 / 取得エラー）を常に見える位置に出し、
 * 展開でソース別の日付と遅延理由を出す。
 */

import { useEffect, useRef, useState } from "react";
import { ChevronDown, Clock } from "lucide-react";

import { useSystemFreshness } from "../lib/queries";
import type { FreshnessSource } from "../lib/api-types";
import { cx } from "./ui";

const STATUS_TEXT = {
  ok: "text-status-success",
  delayed: "text-status-warning",
  stale: "text-status-warning",
  failed: "text-status-danger",
} as const;

const STATUS_DOT = {
  ok: "bg-status-success",
  delayed: "bg-status-warning",
  stale: "bg-status-warning",
  failed: "bg-status-danger",
} as const;

const AGGREGATE_LABEL = {
  ok: "最新",
  delayed: "一部遅延",
  stale: "一部遅延",
  failed: "取得エラー",
} as const;

function statusOf(s: FreshnessSource): keyof typeof STATUS_TEXT {
  const status = s.status;
  if (status === "ok" || status === "delayed" || status === "stale" || status === "failed") return status;
  return "ok";
}

export function DataFreshnessIndicator({ variant = "full" }: { variant?: "compact" | "full" }) {
  const query = useSystemFreshness();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const worst = query.data?.data.worst_status ?? "ok";
  const sources: FreshnessSource[] = query.data?.data.sources ?? [];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        className={cx("btn btn-ghost", STATUS_TEXT[worst])}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="true"
        title="データ鮮度の内訳を表示"
      >
        <span className={cx("size-2 rounded-full", STATUS_DOT[worst])} aria-hidden="true" />
        {variant === "full" ? <span className="hidden tablet:inline">データ鮮度: </span> : null}
        {query.isPending ? "確認中" : AGGREGATE_LABEL[worst]}
        <ChevronDown size={13} aria-hidden="true" />
      </button>

      {open ? (
        <div className="absolute right-0 mt-1 card p-3 shadow-md popover-panel">
          <p className="text-h4 mb-2 flex items-center gap-1.5">
            <Clock size={14} aria-hidden="true" />
            データ鮮度
          </p>
          {query.error ? (
            <p className="text-body-sm text-status-warning">鮮度情報を取得できませんでした</p>
          ) : (
            <ul className="space-y-2">
              {sources.map((s) => (
                <li key={s.source} className="flex items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block text-body-sm text-fg-primary truncate">{s.label_ja}</span>
                    {s.note_ja ? (
                      <span className={cx("block text-caption", STATUS_TEXT[statusOf(s)])}>{s.note_ja}</span>
                    ) : null}
                  </span>
                  <span className={cx("num text-body-sm shrink-0", STATUS_TEXT[statusOf(s)])}>{s.latest_as_of}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="text-caption text-fg-tertiary mt-3">
            リサーチ用株価と現在値は別系列です。現在値は約15分遅延の参考値で、約定価格ではありません。
          </p>
        </div>
      ) : null}
    </div>
  );
}
