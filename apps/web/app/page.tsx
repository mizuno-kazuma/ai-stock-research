"use client";

/**
 * ダッシュボード（docs/ui/screens/01-dashboard.md）。
 *
 * バッチが失敗した日は「失敗したこと」がその日の最重要情報なので、実行状況を
 * 市場サマリより上に置く。並び順自体が仕様。
 */

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Bell } from "lucide-react";
import {
  formatDateTimeJst,
  formatJpy,
  formatJpyLarge,
  formatUsd,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import { Sparkline } from "../components/charts";
import { FilingListItem } from "../components/filings";
import { JobStatusStrip } from "../components/jobs";
import { ModelHealthPanel } from "../components/model-health";
import { PageHeader } from "../components/page-header";
import { usePrefs } from "../components/prefs";
import { RecommendationCard } from "../components/recommendation-card";
import {
  EmptyState,
  QuerySection,
  SkeletonCards,
  SkeletonChart,
  SkeletonTable,
} from "../components/states";
import { DataTable, type Column } from "../components/table";
import { Badge, SectionCard } from "../components/ui";
import { DirectionValue, ForecastValue, MetricCard, NullableText, ScoreBadge } from "../components/values";
import { ALERT_CATEGORY_LABEL_JA } from "../lib/labels";
import type { Alert, WatchlistRow } from "../lib/api-types";
import { formatFilingsWeekLabel } from "../lib/filings-week";
import { useDashboard } from "../lib/queries";

const watchlistColumns: Array<Column<WatchlistRow>> = [
  {
    key: "ticker",
    header: "銘柄",
    primary: true,
    render: (r) => (
      <span className="min-w-0">
        <span className="num mr-2 text-fg-secondary">{r.ticker}</span>
        {r.name_local}
      </span>
    ),
    sortValue: (r) => r.ticker,
  },
  {
    key: "price",
    header: "参考価格",
    numeric: true,
    render: (r) => (
      <NullableText value={r.ref_price_currency === "JPY" ? formatJpy(r.ref_price) : formatUsd(r.ref_price)} />
    ),
    sortValue: (r) => r.ref_price,
  },
  {
    key: "change",
    header: "前日比",
    numeric: true,
    render: (r) => <DirectionValue value={r.change_pct} format="percent" />,
    sortValue: (r) => r.change_pct,
  },
  {
    key: "score",
    header: "スコア",
    numeric: true,
    render: (r) => <ScoreBadge score={r.quant_score} size="sm" />,
    sortValue: (r) => r.quant_score,
  },
  {
    key: "earnings",
    header: "決算",
    numeric: true,
    render: (r) => (
      <NullableText
        value={r.next_earnings_in_days !== null ? `${r.next_earnings_in_days}営業日後` : null}
        reasonJa="決算日が未確定です"
      />
    ),
    sortValue: (r) => r.next_earnings_in_days,
  },
  {
    key: "filings",
    header: "開示",
    numeric: true,
    render: (r) => (r.new_filing_count > 0 ? <Badge tone="info">{r.new_filing_count}件</Badge> : <span className="text-fg-muted">—</span>),
    sortValue: (r) => r.new_filing_count,
  },
];

function AlertRow({ alert }: { alert: Alert }) {
  const tone = alert.severity === "error" ? "danger" : alert.severity === "warning" ? "warning" : "info";
  const body = (
    <span className="min-w-0">
      <span className="flex items-center gap-2">
        <Badge tone={tone}>{ALERT_CATEGORY_LABEL_JA[alert.category]}</Badge>
        <span className="text-body-sm text-fg-primary">{alert.title_ja}</span>
      </span>
      <span className="block text-micro text-fg-muted num mt-0.5">{formatDateTimeJst(alert.created_at)}</span>
    </span>
  );
  return (
    <li className="border-b border-divider px-4 py-2.5 last:border-b-0">
      {alert.link ? (
        <Link href={alert.link} className="block hover:text-accent">
          {body}
        </Link>
      ) : (
        body
      )}
    </li>
  );
}

export default function DashboardPage() {
  const prefs = usePrefs();
  const qc = useQueryClient();
  const query = useDashboard(prefs.market);
  const meta = query.data?.meta;

  return (
    <>
      <PageHeader
        title="ダッシュボード"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={query.isFetching && !query.isPending}
        onRefresh={() => void qc.invalidateQueries()}
      />

      <QuerySection
        label="ダッシュボード"
        query={query}
        skeleton={
          <div className="space-y-4">
            <SkeletonTable rows={1} cols={6} />
            <SkeletonCards count={4} className="tablet:grid-cols-2 desktop:grid-cols-4" />
            <SkeletonCards count={2} />
          </div>
        }
      >
        {(data) => {
          const isJp = prefs.market === "JP";
          const fx = data.fx;
          const portfolio = data.portfolio_snapshot;
          const filingsWeek = formatFilingsWeekLabel(data.as_of ?? meta?.as_of);

          return (
            <div className="space-y-4">
              {/* 1. バッチの実行状況（最上段） */}
              <SectionCard
                title="バッチの実行状況"
                actions={
                  <Link href="/agent" className="btn btn-ghost">
                    詳細
                    <ArrowRight size={13} aria-hidden="true" />
                  </Link>
                }
              >
                <JobStatusStrip jobs={data.jobs} lastRun={data.job_status.last_run} />
              </SectionCard>

              {/* 2. 指標カード */}
              <div className="grid grid-cols-2 gap-3 desktop:grid-cols-4">
                <MetricCard
                  label={`市場指数（${data.market_summary.benchmark.symbol}）`}
                  value={<span className="num">{data.market_summary.benchmark.close.toLocaleString("ja-JP")}</span>}
                  sub={<DirectionValue value={data.market_summary.benchmark.change_pct} format="percent" />}
                  asOf={`騰落 ${data.market_summary.advance_decline.advancing} / ${data.market_summary.advance_decline.declining}`}
                />
                <MetricCard
                  label="USD/JPY（参考値）"
                  value={<span className="num">{formatJpy(fx.spot, 2)}</span>}
                  sub={<DirectionValue value={fx.change_pct} format="percent" />}
                  asOf="約15分遅延の参考値"
                />
                <MetricCard
                  label="ポートフォリオ評価額"
                  value={
                    <NullableText
                      value={portfolio.market_value != null ? formatJpyLarge(portfolio.market_value) : null}
                      reasonJa="保有記録がありません"
                    />
                  }
                  sub={<DirectionValue value={portfolio.unrealized_pnl_pct} format="percent" />}
                  asOf={`${portfolio.n_positions}銘柄 · 参考価格ベース`}
                />
                <MetricCard
                  label="当日損益"
                  value={<DirectionValue value={portfolio.day_change_pct} format="percent" />}
                  sub={
                    <span className="text-caption text-fg-tertiary">
                      上昇: {portfolio.top_movers[0]?.ticker ?? NULL_PLACEHOLDER}
                    </span>
                  }
                  asOf="参考価格ベース"
                />
              </div>

              <div className="grid gap-4 desktop:grid-cols-3">
                {/* 3. 今週の注目 */}
                <div className="desktop:col-span-2 space-y-4">
                  <SectionCard
                    title="今週の注目"
                    subtitle="推奨は投資判断の材料です。売買の指示ではありません"
                    actions={
                      <Link href="/recommendations" className="btn btn-ghost">
                        すべての推奨を見る
                        <ArrowRight size={13} aria-hidden="true" />
                      </Link>
                    }
                    bodyClassName="space-y-3"
                  >
                    {data.top_recommendations.length === 0 ? (
                      <EmptyState
                        title="本日の推奨はありません"
                        description="レビューの基準を満たす候補がなかったか、バッチが完了していません。スクリーナーで条件を指定して探すこともできます。"
                        action={
                          <Link href="/screener" className="btn btn-secondary">
                            スクリーナーを開く
                          </Link>
                        }
                      />
                    ) : (
                      data.top_recommendations.map((rec) => (
                        <RecommendationCard key={rec.rec_id} rec={rec} variant="compact" />
                      ))
                    )}
                  </SectionCard>
                </div>

                {/* 4. アラート */}
                <SectionCard
                  title={
                    <span className="inline-flex items-center gap-1.5">
                      <Bell size={14} aria-hidden="true" />
                      アラート
                    </span>
                  }
                  bodyClassName="p-0"
                >
                  {data.alerts.length === 0 ? (
                    <p className="px-4 py-6 text-body-sm text-fg-tertiary">
                      新しいアラートはありません。データ取得・コスト・モデルの異常はここに出ます。
                    </p>
                  ) : (
                    <ul aria-live="polite">
                      {data.alerts.map((a) => (
                        <AlertRow key={a.alert_id} alert={a} />
                      ))}
                    </ul>
                  )}
                </SectionCard>
              </div>

              <div className="grid gap-4 desktop:grid-cols-2">
                {/* 5. 今週の開示 */}
                <SectionCard
                  title="今週の開示"
                  subtitle={`${data.new_filings_count}件${filingsWeek ? ` · ${filingsWeek}` : ""}`}
                  actions={
                    <Link href="/filings" className="btn btn-ghost">
                      すべて見る
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  }
                  bodyClassName="p-0"
                >
                  {data.watchlist_filings.length === 0 ? (
                    <p className="px-4 py-6 text-body-sm text-fg-tertiary">
                      {filingsWeek
                        ? `保有・ウォッチ銘柄の今週（${filingsWeek}）の開示はありません。`
                        : "保有・ウォッチ銘柄の今週の開示はありません。"}
                      <Link href="/filings" className="text-accent ml-1">
                        全銘柄の開示一覧
                      </Link>
                    </p>
                  ) : (
                    <ul>
                      {data.watchlist_filings.slice(0, 6).map((row) => (
                        <FilingListItem key={row.doc_id} row={row} />
                      ))}
                    </ul>
                  )}
                </SectionCard>

                {/* 6. ウォッチリスト */}
                <SectionCard
                  title="ウォッチリスト"
                  actions={
                    <Link href="/screener" className="btn btn-ghost">
                      銘柄を追加
                    </Link>
                  }
                >
                  {data.watchlist.length === 0 ? (
                    <EmptyState
                      title="ウォッチリストが空です"
                      description="スクリーナーで条件に合う銘柄を探し、行の操作から追加できます。"
                    />
                  ) : (
                    <DataTable
                      caption="ウォッチリストの銘柄"
                      columns={watchlistColumns}
                      rows={data.watchlist.slice(0, 8)}
                      getKey={(r) => `${r.market}-${r.ticker}`}
                      getHref={(r) => `/stocks/${r.market}/${r.ticker}`}
                      dense
                    />
                  )}
                </SectionCard>
              </div>

              <div className="grid gap-4 desktop:grid-cols-2">
                {/* 7. 為替 */}
                <SectionCard
                  title="為替（USD/JPY）"
                  actions={
                    <Link href="/macro" className="btn btn-ghost">
                      詳細
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  }
                >
                  <div className="flex items-baseline gap-3">
                    <span className="num text-metric-lg">{formatJpy(fx.spot, 2)}</span>
                    <DirectionValue value={fx.change_pct} format="percent" />
                  </div>
                  {fx.history && fx.history.length > 0 ? (
                    <Sparkline data={fx.history} />
                  ) : (
                    <SkeletonChart height="spark-h" />
                  )}
                  <div className="mt-2">
                    <p className="text-caption text-fg-tertiary">20営業日先の予測</p>
                    <ForecastValue
                      point={fx.forecast_h20.point}
                      lo={fx.forecast_h20.ci_lo_80}
                      hi={fx.forecast_h20.ci_hi_80}
                      ciLevel={80}
                      format="currency-jpy"
                      precision={2}
                      verdictJa={fx.forecast_h20.note_ja}
                    />
                  </div>
                </SectionCard>

                {/* 8. モデルの状態 */}
                <SectionCard
                  title="モデルの状態"
                  actions={
                    <Link href="/model-lab" className="btn btn-ghost">
                      モデルラボ
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  }
                >
                  <ModelHealthPanel health={data.model_health} variant="compact" />
                </SectionCard>
              </div>

              <p className="text-caption text-fg-tertiary">
                {isJp ? "日本株" : "米国株"}を表示しています。ボラティリティは
                {data.market_summary.vol_regime.message_ja}
              </p>
            </div>
          );
        }}
      </QuerySection>
    </>
  );
}
