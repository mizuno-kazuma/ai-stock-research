"use client";

/**
 * 開示資料の一覧行と要約パネル。
 *
 * PDF は必ず別タブで開く（interaction-patterns.md §3.2）。要約は「LLM が生成したもの」で
 * あることと、モデル・コスト・生成時刻を必ず添える。原文が正であることを見失わせない。
 */

import Link from "next/link";
import { ExternalLink, FileText, Sparkles } from "lucide-react";
import { formatDateTimeJst, formatUsdPrecise } from "@ai-stock/ui";

import { API_BASE_URL } from "../lib/api-client";
import type { DocumentSummary, DocumentSummaryRow } from "../lib/api-types";
import { GUIDANCE_TONE_LABEL_JA, GUIDANCE_TONE_STYLE, docTypeLabel, docTypeStyle } from "../lib/labels";
import { Badge, Button, Notice, cx } from "./ui";
import { NullableText } from "./values";

export function docFileHref(docId: string): string {
  return `${API_BASE_URL}/documents/${docId}/file?disposition=inline`;
}

export function FilingListItem({
  row,
  onOpenSummary,
  selected,
}: {
  row: DocumentSummaryRow;
  onOpenSummary?: (docId: string) => void;
  selected?: boolean;
}) {
  return (
    <li
      className={cx(
        "border-b border-divider px-4 py-3 last:border-b-0",
        selected ? "bg-selected" : "hover:bg-hover",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="num text-caption text-fg-tertiary">{formatDateTimeJst(row.filed_at)}</span>
        <Badge tone={docTypeStyle(row.doc_type)}>{docTypeLabel(row.doc_type)}</Badge>
        <Link href={`/stocks/${row.market}/${row.ticker}`} className="text-body-sm text-fg-primary hover:text-accent">
          <span className="num mr-1.5 text-fg-secondary">{row.ticker}</span>
          {row.name_local}
        </Link>
        {row.guidance_tone ? (
          <Badge tone={GUIDANCE_TONE_STYLE[row.guidance_tone]}>
            トーン: {GUIDANCE_TONE_LABEL_JA[row.guidance_tone]}
          </Badge>
        ) : null}
      </div>

      <p className="text-body-sm text-fg-primary mt-1">{row.title}</p>
      {row.summary_preview_ja ? (
        <p className="text-caption text-fg-secondary mt-0.5 prose-block">{row.summary_preview_ja}</p>
      ) : (
        <p className="text-caption text-fg-tertiary mt-0.5">
          要約はまだありません
          {row.estimated_summary_cost_usd !== null
            ? `（生成の見込みコスト ${formatUsdPrecise(row.estimated_summary_cost_usd, 3)}）`
            : null}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {onOpenSummary ? (
          <Button variant="ghost" onClick={() => onOpenSummary(row.doc_id)}>
            <Sparkles size={13} aria-hidden="true" />
            {row.has_summary ? "要約を見る" : "要約を生成"}
          </Button>
        ) : null}
        {row.has_local_copy ? (
          <a
            className="btn btn-ghost"
            href={docFileHref(row.doc_id)}
            target="_blank"
            rel="noopener noreferrer"
          >
            <FileText size={13} aria-hidden="true" />
            原文（別タブ）
            <ExternalLink size={11} aria-hidden="true" />
          </a>
        ) : (
          <span className="text-caption text-fg-tertiary">原文の取得に失敗しています</span>
        )}
        <span className="text-caption text-fg-muted ml-auto">
          情報価値 <NullableText value={row.info_value_score !== null ? String(row.info_value_score) : null} />
        </span>
      </div>
    </li>
  );
}

export function FilingSummaryPanel({ summary }: { summary: DocumentSummary }) {
  return (
    <div className="space-y-3">
      <Notice tone="neutral">
        この要約は言語モデルが生成したものです。判断の前に原文（該当ページ）を確認してください。
      </Notice>

      <h3 className="text-h3 text-fg-primary prose-block">{summary.headline_ja}</h3>

      <section>
        <h4 className="text-h4 text-fg-primary">要点</h4>
        <ul className="mt-1 list-disc pl-5 space-y-1">
          {summary.key_points_ja.map((p) => (
            <li key={p} className="text-body-sm text-fg-primary prose-block">
              {p}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h4 className="text-h4 text-fg-primary">リスク・弱気材料</h4>
        <ul className="mt-1 list-disc pl-5 space-y-1">
          {summary.risks_ja.length === 0 ? (
            <li className="text-body-sm text-fg-tertiary">原文にリスクの記載が見つかりませんでした</li>
          ) : (
            summary.risks_ja.map((r) => (
              <li key={r} className="text-body-sm text-fg-primary prose-block">
                {r}
              </li>
            ))
          )}
        </ul>
      </section>

      <section>
        <h4 className="text-h4 text-fg-primary">
          トーン判定: <Badge tone={GUIDANCE_TONE_STYLE[summary.guidance_tone]}>{GUIDANCE_TONE_LABEL_JA[summary.guidance_tone]}</Badge>
        </h4>
        <p className="argument-panel mt-1">{summary.tone_reason_ja}</p>
      </section>

      <footer className="border-t border-divider pt-2 text-caption text-fg-tertiary num">
        {summary.model} · プロンプト {summary.prompt_version} · コスト {formatUsdPrecise(summary.cost_usd, 4)} ·{" "}
        {formatDateTimeJst(summary.generated_at)} 生成
      </footer>
    </div>
  );
}
