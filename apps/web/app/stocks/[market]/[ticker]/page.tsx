"use client";

/**
 * 銘柄詳細（docs/ui/screens/03-stock-detail.md）。
 *
 * セクションごとに独立したクエリにしている。財務が取れなくても株価と開示は見られる、
 * という部分表示（partial）を成立させるため。
 */

import { use, useState } from "react";
import Link from "next/link";
import { Star } from "lucide-react";
import {
  formatDateIso,
  formatJpy,
  formatJpyLarge,
  formatMultiple,
  formatPct,
  formatUsd,
  formatVolume,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import { TimeSeriesChart } from "../../../../components/charts";
import { FilingListItem } from "../../../../components/filings";
import { FactorTable } from "../../../../components/recommendation-card";
import { PageHeader } from "../../../../components/page-header";
import {
  DelayedPriceNote,
  QuerySection,
  SkeletonChart,
  SkeletonTable,
} from "../../../../components/states";
import { ChartDataTable, DataTable, type Column } from "../../../../components/table";
import { Badge, Button, SectionCard, Tabs } from "../../../../components/ui";
import { DirectionValue, ForecastCell, NullableText, ScoreBadge } from "../../../../components/values";
import { ACTION_LABEL_JA, ACTION_TONE, CONVICTION_SHORT_JA, HORIZON_LABEL_JA } from "../../../../lib/labels";
import type {
  FinancialPeriod,
  Market,
  PeerRow,
  RecommendationHistoryRow,
  StockKeyMetric,
} from "../../../../lib/api-types";
import {
  useStock,
  useStockDocuments,
  useStockFeatures,
  useStockFinancials,
  useStockPeers,
  useStockPrices,
  useStockRecommendations,
} from "../../../../lib/queries";

type TabKey = "financials" | "factors" | "documents" | "history" | "peers";

function metricValue(m: StockKeyMetric): string | null {
  if (m.format === "text") return m.text_value ?? null;
  if (m.value === null) return null;
  switch (m.format) {
    case "jpy":
      return formatJpy(m.value);
    case "usd":
      return formatUsd(m.value);
    case "jpy-large":
      return formatJpyLarge(m.value);
    case "percent":
      return formatPct(m.value, { precision: 2 });
    case "multiple":
      return formatMultiple(m.value, 2);
    case "number":
      return m.value.toFixed(2);
  }
}

const financialColumns: Array<Column<FinancialPeriod>> = [
  {
    key: "period",
    header: "期間",
    primary: true,
    render: (r) => (
      <span>
        {r.period_label_ja}
        {r.is_forecast ? <Badge tone="info" className="ml-2">会社予想</Badge> : null}
      </span>
    ),
  },
  { key: "filed", header: "開示日", numeric: true, render: (r) => <span className="num">{formatDateIso(r.filed_at)}</span> },
  {
    key: "revenue",
    header: "売上",
    numeric: true,
    render: (r) => <NullableText value={r.revenue !== null ? formatJpyLarge(r.revenue) : null} />,
  },
  {
    key: "op",
    header: "営業利益",
    numeric: true,
    render: (r) => <NullableText value={r.op_income !== null ? formatJpyLarge(r.op_income) : null} />,
  },
  {
    key: "margin",
    header: "営業利益率",
    numeric: true,
    render: (r) => <NullableText value={r.op_margin !== null ? formatPct(r.op_margin, { precision: 1 }) : null} />,
  },
  {
    key: "net",
    header: "純利益",
    numeric: true,
    render: (r) => <NullableText value={r.net_income !== null ? formatJpyLarge(r.net_income) : null} />,
  },
  {
    key: "eps",
    header: "EPS",
    numeric: true,
    render: (r) => <NullableText value={r.eps !== null ? formatJpy(r.eps, 1) : null} />,
  },
  {
    key: "fcf",
    header: "フリーCF",
    numeric: true,
    render: (r) => <NullableText value={r.fcf !== null ? formatJpyLarge(r.fcf) : null} />,
  },
];

const peerColumns: Array<Column<PeerRow>> = [
  {
    key: "ticker",
    header: "銘柄",
    primary: true,
    render: (r) => (
      <span>
        <span className="num mr-2 text-fg-secondary">{r.ticker}</span>
        {r.name_local}
      </span>
    ),
  },
  { key: "score", header: "スコア", numeric: true, render: (r) => <ScoreBadge score={r.quant_score} size="sm" />, sortValue: (r) => r.quant_score },
  {
    key: "per",
    header: "PER",
    numeric: true,
    render: (r) => (
      <NullableText value={r.per !== null ? formatMultiple(r.per) : null} reasonJa="純利益が負のため算出できません" />
    ),
    sortValue: (r) => r.per,
  },
  { key: "pbr", header: "PBR", numeric: true, render: (r) => <NullableText value={r.pbr !== null ? formatMultiple(r.pbr, 2) : null} />, sortValue: (r) => r.pbr },
  { key: "roic", header: "ROIC", numeric: true, render: (r) => <NullableText value={r.roic !== null ? formatPct(r.roic, { precision: 1 }) : null} />, sortValue: (r) => r.roic },
  { key: "ret20", header: "20営業日", numeric: true, render: (r) => <DirectionValue value={r.ret_20d} format="percent" precision={1} />, sortValue: (r) => r.ret_20d },
  { key: "fx", header: "為替感応度", numeric: true, render: (r) => <NullableText value={r.fx_sensitivity !== null ? r.fx_sensitivity.toFixed(2) : null} />, sortValue: (r) => r.fx_sensitivity },
];

const historyColumns: Array<Column<RecommendationHistoryRow>> = [
  { key: "as_of", header: "生成日", primary: true, render: (r) => <span className="num">{formatDateIso(r.as_of)}</span> },
  { key: "action", header: "行動", render: (r) => <Badge tone={ACTION_TONE[r.action]}>{ACTION_LABEL_JA[r.action]}</Badge> },
  { key: "horizon", header: "期間", render: (r) => HORIZON_LABEL_JA[r.horizon] },
  { key: "conviction", header: "確信度", render: (r) => CONVICTION_SHORT_JA[r.conviction] },
  {
    key: "expected",
    header: "予測",
    numeric: true,
    render: (r) => <ForecastCell point={r.expected_ret} lo={r.expected_ret_lo} hi={r.expected_ret_hi} />,
  },
  {
    key: "realized",
    header: "実績（超過）",
    numeric: true,
    render: (r) =>
      r.realized_excess_ret === null ? (
        <NullableText value={null} reasonJa={r.pending_days ? `${r.pending_days}営業日後に確定します` : "未確定"} />
      ) : (
        <DirectionValue value={r.realized_excess_ret} format="percent" precision={1} />
      ),
  },
  {
    key: "outcome",
    header: "判定",
    render: (r) =>
      r.outcome === "pending" ? (
        <Badge tone="neutral">確定待ち</Badge>
      ) : r.outcome === "hit" ? (
        <Badge tone="success">的中</Badge>
      ) : (
        <Badge tone="warning">不的中</Badge>
      ),
  },
];

export default function StockDetailPage({
  params,
}: {
  params: Promise<{ market: string; ticker: string }>;
}) {
  const { market: rawMarket, ticker } = use(params);
  const market = (rawMarket === "US" ? "US" : "JP") as Market;
  const [tab, setTab] = useState<TabKey>("financials");

  const stock = useStock(market, ticker);
  const prices = useStockPrices(market, ticker, "1y");
  const financials = useStockFinancials(market, ticker);
  const features = useStockFeatures(market, ticker);
  const documents = useStockDocuments(market, ticker);
  const history = useStockRecommendations(market, ticker);
  const peers = useStockPeers(market, ticker);

  const meta = stock.data?.meta;

  return (
    <>
      <PageHeader
        title={stock.data?.data.name_local ?? ticker}
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={stock.isFetching && !stock.isPending}
        onRefresh={() => void stock.refetch()}
        actions={
          <Button variant="secondary" ariaLabel="ウォッチリストに追加">
            <Star size={14} aria-hidden="true" />
            ウォッチ
          </Button>
        }
      />

      <QuerySection
        label="銘柄情報"
        query={stock}
        skeleton={<SkeletonTable rows={3} cols={4} />}
      >
        {(data) => (
          <div className="space-y-4">
            <SectionCard
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <span className="num text-fg-secondary">{data.ticker}</span>
                  {data.name_local}
                  <Badge tone="neutral">{data.exchange}</Badge>
                  <Badge tone="neutral">{data.sector_name}</Badge>
                </span>
              }
              actions={<ScoreBadge score={data.quant_score} size="lg" showLabel />}
            >
              <div className="flex flex-wrap items-baseline gap-4">
                <span className="num text-metric-lg">
                  {data.currency === "JPY" ? formatJpy(data.ref_price) : formatUsd(data.ref_price)}
                </span>
                <DirectionValue value={data.ref_change_pct} format="percent" showArrow />
                <DirectionValue
                  value={data.ref_change_abs}
                  format={data.currency === "JPY" ? "currency-jpy" : "currency-usd"}
                />
                {data.next_earnings_date ? (
                  <Badge tone="info">次回決算 {formatDateIso(data.next_earnings_date)}</Badge>
                ) : null}
              </div>
              <DelayedPriceNote note={data.ref_note_ja} className="mt-1" />

              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 tablet:grid-cols-3 desktop:grid-cols-5">
                {data.key_metrics.map((m) => (
                  <div key={m.key} className="min-w-0">
                    <dt className="text-caption text-fg-tertiary truncate" title={m.tooltip_ja ?? undefined}>
                      {m.label_ja}
                    </dt>
                    <dd className="num text-metric-sm">
                      <NullableText value={metricValue(m)} reasonJa={m.tooltip_ja} />
                    </dd>
                  </div>
                ))}
              </dl>
            </SectionCard>

            <SectionCard title="株価（リサーチ用系列）">
              <QuerySection label="株価" query={prices} skeleton={<SkeletonChart height="chart-h-lg" />}>
                {(series) => (
                  <>
                    <TimeSeriesChart
                      data={series.bars.map((b) => ({ date: b.date, close: b.close }))}
                      series={[{ dataKey: "close", label: "終値" }]}
                      height="chart-h-lg"
                      yTickFormatter={(v) => (data.currency === "JPY" ? formatJpy(v) : formatUsd(v))}
                    />
                    <p className="text-caption text-fg-tertiary mt-1">
                      出所 {series.source} · 最新 {series.latest_as_of}
                      {series.delay_note_ja ? ` · ${series.delay_note_ja}` : null}
                    </p>
                    <ChartDataTable
                      caption="株価の推移"
                      headers={["日付", "終値", "出来高"]}
                      rows={series.bars.slice(-20).map((b) => [
                        b.date,
                        data.currency === "JPY" ? formatJpy(b.close) : formatUsd(b.close),
                        formatVolume(b.volume),
                      ])}
                    />
                  </>
                )}
              </QuerySection>
            </SectionCard>

            <Tabs
              label="銘柄詳細の内容"
              value={tab}
              onChange={setTab}
              options={[
                { value: "financials", label: "財務" },
                { value: "factors", label: "ファクター" },
                { value: "documents", label: "開示資料" },
                { value: "history", label: "推奨履歴" },
                { value: "peers", label: "同業比較" },
              ]}
            />

            {tab === "financials" ? (
              <SectionCard title="財務（開示日基準）">
                <QuerySection
                  label="財務"
                  query={financials}
                  skeleton={<SkeletonTable rows={4} cols={7} />}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "財務データがありません",
                    description:
                      "この銘柄の財務データはまだ取り込まれていません。無料プランのデータソースでは反映が遅れることがあります。",
                  }}
                >
                  {(rows) => (
                    <>
                      <DataTable
                        caption="期別の財務指標"
                        columns={financialColumns}
                        rows={rows}
                        getKey={(r) => r.period_label_ja}
                        dense
                      />
                      <p className="text-caption text-fg-tertiary mt-2">
                        各期の値は開示日時点の内容です（後日の訂正は反映されないことがあります）。
                      </p>
                    </>
                  )}
                </QuerySection>
              </SectionCard>
            ) : null}

            {tab === "factors" ? (
              <SectionCard title="ファクター内訳">
                <QuerySection label="ファクター" query={features} skeleton={<SkeletonTable rows={7} cols={4} />}>
                  {(f) => (
                    <>
                      <FactorTable factors={f.factors} />
                      <p className="text-caption text-fg-tertiary mt-2">
                        特徴量バージョン {f.feature_version} · {f.as_of} 時点
                        {f.note_ja ? ` · ${f.note_ja}` : null}
                      </p>
                    </>
                  )}
                </QuerySection>
              </SectionCard>
            ) : null}

            {tab === "documents" ? (
              <SectionCard title="開示資料" bodyClassName="p-0">
                <QuerySection
                  label="開示資料"
                  query={documents}
                  skeleton={<div className="p-5"><SkeletonTable rows={4} cols={3} /></div>}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "この銘柄の開示資料はありません",
                    description: "取り込み対象の期間内に開示がないか、取得に失敗しています。",
                  }}
                >
                  {(rows) => (
                    <ul>
                      {rows.map((row) => (
                        <FilingListItem key={row.doc_id} row={row} />
                      ))}
                    </ul>
                  )}
                </QuerySection>
              </SectionCard>
            ) : null}

            {tab === "history" ? (
              <SectionCard
                title="この銘柄への過去の推奨と実績"
                subtitle="予測と実績を並べて、当たっていたかどうかを確認できます"
              >
                <QuerySection
                  label="推奨履歴"
                  query={history}
                  skeleton={<SkeletonTable rows={5} cols={6} />}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "推奨履歴がありません",
                    description: "この銘柄はまだ推奨の対象になっていません。",
                  }}
                >
                  {(rows) => (
                    <DataTable
                      caption="推奨履歴と実績"
                      columns={historyColumns}
                      rows={rows}
                      getKey={(r) => r.rec_id}
                      dense
                    />
                  )}
                </QuerySection>
              </SectionCard>
            ) : null}

            {tab === "peers" ? (
              <SectionCard title="同業比較">
                <QuerySection
                  label="同業比較"
                  query={peers}
                  skeleton={<SkeletonTable rows={5} cols={7} />}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "比較対象がありません",
                    description: "同セクターで比較できる銘柄が見つかりませんでした。",
                  }}
                >
                  {(rows) => (
                    <DataTable
                      caption="同セクターの比較銘柄"
                      columns={peerColumns}
                      rows={rows}
                      getKey={(r) => `${r.market}-${r.ticker}`}
                      getHref={(r) => `/stocks/${r.market}/${r.ticker}`}
                      dense
                    />
                  )}
                </QuerySection>
              </SectionCard>
            ) : null}

            <p className="text-caption text-fg-tertiary">
              {data.name_en ?? NULL_PLACEHOLDER} ·{" "}
              <Link href="/recommendations" className="text-accent">
                推奨一覧に戻る
              </Link>
            </p>
          </div>
        )}
      </QuerySection>
    </>
  );
}
