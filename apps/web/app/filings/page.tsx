"use client";

/**
 * 決算資料（docs/ui/screens/05-filings.md）。
 *
 * 一覧で資料を選ぶと右側（モバイルはボトムシート）に要約が出る。要約は原文の代わりでは
 * ないので、常に「原文を別タブで開く」導線を並べる。
 */

import { useState } from "react";
import { FileText, X } from "lucide-react";
import { formatUsdPrecise } from "@ai-stock/ui";

import { FilingListItem, FilingSummaryPanel, docFileHref } from "../../components/filings";
import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import { EmptyState, QuerySection, SkeletonTable, SkeletonText } from "../../components/states";
import { Button, Chip, SectionCard } from "../../components/ui";
import { DOC_TYPE_LABEL_JA } from "../../lib/labels";
import { useDocumentSummary, useDocuments, useGenerateSummary } from "../../lib/queries";

const DOC_TYPES = [
  "guidance_revision",
  "earnings_flash",
  "annual_report",
  "quarterly_report",
  "treasury_stock",
  "form_10q",
  "form_10k",
] as const;

export default function FilingsPage() {
  const prefs = usePrefs();
  const [docType, setDocType] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const query = useDocuments({ market: prefs.market, ...(docType ? { doc_type: docType } : {}), limit: 50 });
  const summary = useDocumentSummary(selected);
  const generate = useGenerateSummary();
  const meta = query.data?.meta;

  const openSummary = (docId: string) => {
    setSelected(docId);
    const row = query.data?.data.find((d) => d.doc_id === docId);
    if (row && !row.has_summary) generate.mutate(docId);
  };

  return (
    <div className="filings-page">
      <PageHeader
        title="決算資料"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={query.isFetching && !query.isPending}
        onRefresh={() => void query.refetch()}
        description="要約は言語モデルが生成したものです。数字の確認は必ず原文で行ってください。"
      />

      <SectionCard title="種類で絞り込む" className="shrink-0" bodyClassName="flex flex-wrap gap-2">
        <Chip selected={docType === null} onClick={() => setDocType(null)}>
          すべて
        </Chip>
        {DOC_TYPES.map((t) => (
          <Chip key={t} selected={docType === t} onClick={() => setDocType(t)}>
            {DOC_TYPE_LABEL_JA[t]}
          </Chip>
        ))}
      </SectionCard>

      <div className="filings-split">
        <SectionCard title="開示一覧" className="filings-pane" bodyClassName="p-0 filings-pane-body">
          <QuerySection
            label="開示一覧"
            query={query}
            section="filings"
            skeleton={
              <div className="p-5">
                <SkeletonTable rows={6} cols={3} />
              </div>
            }
            emptyWhen={(rows) => rows.length === 0}
            empty={{
              title: "該当する開示がありません",
              description:
                "絞り込みを外すか、期間を広げてください。TDnetの取得が失敗している場合は適時開示が欠けます。",
            }}
          >
            {(rows) => (
              <ul data-testid="filings-list">
                {rows.map((row) => (
                  <FilingListItem
                    key={row.doc_id}
                    row={row}
                    selected={selected === row.doc_id}
                    onOpenSummary={openSummary}
                  />
                ))}
              </ul>
            )}
          </QuerySection>
        </SectionCard>

        {/* 1280px 以上は右側に常設。未満ではボトムシートとして出す */}
        <div className="hidden desktop:block min-h-0 h-full">
          <SectionCard
            title="要約"
            className="filings-pane"
            bodyClassName="filings-pane-body"
            actions={
              selected ? (
                <a className="btn btn-ghost" href={docFileHref(selected)} target="_blank" rel="noopener noreferrer">
                  <FileText size={13} aria-hidden="true" />
                  原文（別タブ）
                </a>
              ) : null
            }
          >
            {!selected ? (
              <EmptyState
                title="資料を選んでください"
                description="左の一覧から資料を選ぶと、要点・リスク・トーン判定を表示します。"
              />
            ) : generate.isPending ? (
              <div className="space-y-2">
                <p className="text-body-sm text-fg-secondary">要約を生成しています…</p>
                <SkeletonText lines={6} />
              </div>
            ) : (
              <QuerySection label="要約" query={summary} skeleton={<SkeletonText lines={6} />}>
                {(s) => <FilingSummaryPanel summary={s} />}
              </QuerySection>
            )}
          </SectionCard>
        </div>
      </div>

      {/* モバイル: ボトムシート */}
      {selected ? (
        <div className="desktop:hidden">
          <div className="sheet-backdrop" onClick={() => setSelected(null)} aria-hidden="true" />
          <div className="sheet-panel p-4 overflow-auto" role="dialog" aria-modal="true" aria-label="資料の要約">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-h3">要約</h2>
              <div className="flex items-center gap-1">
                <a className="btn btn-ghost" href={docFileHref(selected)} target="_blank" rel="noopener noreferrer">
                  <FileText size={13} aria-hidden="true" />
                  原文
                </a>
                <Button variant="ghost" onClick={() => setSelected(null)} ariaLabel="閉じる">
                  <X size={16} aria-hidden="true" />
                </Button>
              </div>
            </div>
            <div className="mt-3">
              {generate.isPending ? (
                <SkeletonText lines={6} />
              ) : (
                <QuerySection label="要約" query={summary} skeleton={<SkeletonText lines={6} />}>
                  {(s) => <FilingSummaryPanel summary={s} />}
                </QuerySection>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {generate.isError ? (
        <p className="notice notice-warning mt-4" role="alert">
          要約を生成できませんでした。{generate.error.messageJa}
        </p>
      ) : null}

      {generate.isSuccess ? (
        <p className="text-caption text-fg-tertiary mt-4 num">
          直近の生成コスト {formatUsdPrecise(generate.data.data.cost_usd, 4)}
        </p>
      ) : null}
    </div>
  );
}
