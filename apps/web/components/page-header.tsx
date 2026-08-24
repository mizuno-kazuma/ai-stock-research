"use client";

import type { ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { formatDateTimeJst } from "@ai-stock/ui";

import { Button } from "./ui";
import { RefreshingIndicator } from "./states";

/** 曜日つきの日付。`2026年8月22日 (金) 時点` */
function asOfLabel(asOf: string | null | undefined): string | null {
  if (!asOf) return null;
  const d = new Date(`${asOf}T00:00:00+09:00`);
  if (Number.isNaN(d.getTime())) return `${asOf} 時点`;
  const wd = ["日", "月", "火", "水", "木", "金", "土"][d.getDay()];
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 (${wd}) 時点`;
}

export function PageHeader({
  title,
  asOf,
  computedAt,
  onRefresh,
  refreshing,
  actions,
  description,
}: {
  title: string;
  asOf?: string | null;
  computedAt?: string;
  onRefresh?: () => void;
  refreshing?: boolean;
  actions?: ReactNode;
  description?: string;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-h1 text-fg-primary" tabIndex={-1}>
          {title}
        </h1>
        <p className="text-caption text-fg-tertiary mt-0.5 num">
          {asOfLabel(asOf)}
          {computedAt ? ` · 生成 ${formatDateTimeJst(computedAt)}` : null}
        </p>
        {description ? <p className="text-body-sm text-fg-secondary mt-1 prose-block">{description}</p> : null}
      </div>
      <div className="flex items-center gap-2">
        <RefreshingIndicator active={Boolean(refreshing)} />
        {actions}
        {onRefresh ? (
          <Button variant="secondary" onClick={onRefresh}>
            <RefreshCw size={14} aria-hidden="true" />
            更新
          </Button>
        ) : null}
      </div>
    </div>
  );
}
