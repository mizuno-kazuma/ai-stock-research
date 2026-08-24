"use client";

/**
 * 状態表示。states.md の8状態をここに集約する。
 *   loading / loading-refresh / empty / not-ready / partial / error / stale / offline
 *
 * 設計上の要点:
 * - `QuerySection` はセクション単位のエラー境界になっている。1つのクエリが落ちても
 *   ページの他のセクションは描画され続ける（partial の扱い）。
 * - `warnings[]` は `QuerySection` が自動で描画する。画面側が忘れられない構造にしている。
 * - loading 中の骨組みは実寸と同じ高さを渡す（レイアウトが跳ねない）。
 */

import Link from "next/link";
import type { ReactNode } from "react";
import { AlertTriangle, CloudOff, Info, RefreshCw, SearchX, TriangleAlert } from "lucide-react";
import { formatDateTimeJst } from "@ai-stock/ui";

import type { ApiError, ApiResult } from "../lib/api-client";
import type { ApiWarning, DataFreshness } from "../lib/api-types";
import { Button, Notice, cx } from "./ui";

/* ------------------------------- 骨組み ------------------------------- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden="true" />;
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cx("h-4", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      <Skeleton className="h-8 w-full" />
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cx("h-6", c === 0 ? "w-2/6" : "w-1/6")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 3, className }: { count?: number; className?: string }) {
  return (
    <div className={cx("grid gap-4", className)} aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-40 w-full" />
      ))}
    </div>
  );
}

export function SkeletonChart({ height = "chart-h-md" }: { height?: string }) {
  return <Skeleton className={cx("w-full", height)} />;
}

/** 読み込み中であることを支援技術にも伝える */
export function LoadingRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <span className="visually-hidden">{label}を読み込んでいます</span>
      {children}
    </div>
  );
}

/* ------------------------- empty / error / 他 ------------------------- */

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <span className="text-fg-tertiary">{icon ?? <SearchX size={24} aria-hidden="true" />}</span>
      <p className="text-h4 text-fg-primary">{title}</p>
      <p className="text-body-sm text-fg-secondary prose-block">{description}</p>
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  label,
}: {
  error: ApiError;
  onRetry?: () => void;
  label?: string;
}) {
  const isNotReady = error.kind === "not-ready";
  const isOffline = error.kind === "offline";
  const latest = error.problem?.latest_available_as_of;

  return (
    <div className="flex flex-col items-start gap-3 py-6">
      <Notice
        tone={isNotReady || isOffline ? "warning" : "danger"}
        role="alert"
        icon={isOffline ? <CloudOff size={16} /> : <AlertTriangle size={16} />}
        className="w-full"
      >
        <p className="font-medium">{label ? `${label}を取得できませんでした` : "取得できませんでした"}</p>
        <p className="mt-0.5">{error.messageJa}</p>
        {error.kind === "cost-cap" && error.problem?.resets_at ? (
          <p className="mt-0.5">上限のリセット: {formatDateTimeJst(error.problem.resets_at)}</p>
        ) : null}
      </Notice>
      <div className="flex items-center gap-2">
        {onRetry ? (
          <Button variant="secondary" onClick={onRetry}>
            <RefreshCw size={14} aria-hidden="true" />
            再試行
          </Button>
        ) : null}
        {isNotReady && latest ? (
          <Link className="btn btn-outline" href={`?as_of=${latest}`}>
            利用できる最新（{latest}）を表示
          </Link>
        ) : null}
      </div>
    </div>
  );
}

/* ------------------------------ warnings ----------------------------- */

const SEVERITY_TONE = { info: "info", warning: "warning", error: "danger" } as const;

export function WarningBanner({ warning }: { warning: ApiWarning }) {
  const tone = SEVERITY_TONE[warning.severity];
  return (
    <Notice
      tone={tone}
      role={warning.severity === "error" ? "alert" : "status"}
      icon={warning.severity === "info" ? <Info size={16} /> : <TriangleAlert size={16} />}
    >
      <span className="text-fg-primary">{warning.message_ja}</span>
      {warning.source ? <span className="text-caption ml-2 opacity-80">出典: {warning.source}</span> : null}
    </Notice>
  );
}

export function WarningList({ warnings, className }: { warnings: ApiWarning[]; className?: string }) {
  if (warnings.length === 0) return null;
  return (
    <div className={cx("space-y-2", className)}>
      {warnings.map((w) => (
        <WarningBanner key={`${w.code}-${w.source ?? ""}-${w.section ?? ""}`} warning={w} />
      ))}
    </div>
  );
}

/* ------------------------------ 鮮度・遅延 ---------------------------- */

const FRESHNESS_TONE = {
  ok: "text-status-success",
  delayed: "text-status-warning",
  stale: "text-status-warning",
  failed: "text-status-danger",
} as const;

export function FreshnessBadge({ item }: { item: DataFreshness }) {
  const statusKey = item.status === "delayed" || item.status === "stale" || item.status === "failed" ? item.status : "ok";
  return (
    <span className={cx("text-caption num", FRESHNESS_TONE[statusKey])} title={item.note_ja ?? undefined}>
      {item.source} {item.latest_as_of}
      {item.note_ja ? <span className="ml-1">（{item.note_ja}）</span> : null}
    </span>
  );
}

/** 参考価格の注意書き。約定価格でないことを必ず添える */
export function DelayedPriceNote({ note, className }: { note: string; className?: string }) {
  return (
    <p className={cx("text-caption text-fg-tertiary", className)}>
      {note} · この価格は判断の参考用で、約定価格ではありません
    </p>
  );
}

/** 期待より古いデータに添えるマーカー */
export function StaleMarker({ asOf, expected }: { asOf: string; expected?: string | null }) {
  return (
    <span className="badge badge-warning" title={expected ? `期待値 ${expected}` : undefined}>
      <TriangleAlert size={11} aria-hidden="true" />
      {asOf} 時点（更新が止まっています）
    </span>
  );
}

/** オフライン時のキャッシュ表示。取得時刻を必ず出す */
export function CachedNote({ fetchedAt }: { fetchedAt: string }) {
  return (
    <Notice tone="warning" icon={<CloudOff size={16} />} role="status">
      オフラインのためキャッシュを表示しています（取得時刻 {formatDateTimeJst(fetchedAt)}）
    </Notice>
  );
}

/* ---------------------------- QuerySection --------------------------- */

/** TanStack Query の結果のうち、状態表示に必要な部分だけを受け取る */
export interface QueryLike<T> {
  data?: ApiResult<T>;
  isPending: boolean;
  isFetching: boolean;
  error: ApiError | null;
  refetch: () => void;
}

export interface QuerySectionProps<T> {
  /** 見出しに出す名前。エラー文言にも使う */
  label: string;
  query: QueryLike<T>;
  /** warnings をこのセクションに絞り込むキー。省略時はセクション指定なしの警告を出す */
  section?: string;
  skeleton: ReactNode;
  emptyWhen?: (data: T) => boolean;
  empty?: { title: string; description: string; action?: ReactNode };
  children: (data: T, result: ApiResult<T>) => ReactNode;
}

export function QuerySection<T>({
  label,
  query,
  section,
  skeleton,
  emptyWhen,
  empty,
  children,
}: QuerySectionProps<T>) {
  if (query.error && !query.data) {
    return <ErrorState error={query.error} onRetry={() => query.refetch()} label={label} />;
  }
  if (query.isPending || !query.data) {
    return <LoadingRegion label={label}>{skeleton}</LoadingRegion>;
  }

  const result = query.data;
  const warnings = result.warnings.filter((w) => (section ? w.section === section : !w.section));
  const isEmpty = emptyWhen?.(result.data) ?? false;

  return (
    <div className="space-y-3">
      {result.from_cache ? <CachedNote fetchedAt={result.fetched_at} /> : null}
      <WarningList warnings={warnings} />
      {query.error ? (
        // 再取得が失敗しても、前回の値は残したまま失敗だけ伝える
        <Notice tone="warning" role="status" icon={<TriangleAlert size={16} />}>
          最新の取得に失敗しました。表示は前回の内容です。{query.error.messageJa}
        </Notice>
      ) : null}
      {isEmpty && empty ? (
        <EmptyState title={empty.title} description={empty.description} action={empty.action} />
      ) : (
        children(result.data, result)
      )}
    </div>
  );
}

/** 再取得中に見出し横に出す小さな表示。既存の内容は消さない */
export function RefreshingIndicator({ active }: { active: boolean }) {
  if (!active) return null;
  return (
    <span className="text-caption text-fg-tertiary inline-flex items-center gap-1" role="status">
      <RefreshCw size={12} className="animate-spin" aria-hidden="true" />
      更新中
    </span>
  );
}
