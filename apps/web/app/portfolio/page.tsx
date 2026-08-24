"use client";

/**
 * ポートフォリオと売買日誌（docs/ui/screens/09-portfolio-journal.md）。
 *
 * 推奨の質と実行の質を分けて見せる。評価額は参考価格（遅延）であり、証券会社の残高ではない。
 */

import { Suspense, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  formatDateTimeJst,
  formatJpy,
  formatPct,
  formatUsd,
  formatVolume,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import { useOnlineStatus } from "../../components/app-shell";
import { TimeSeriesChart } from "../../components/charts";
import { Dialog, Field } from "../../components/dialog";
import { PageHeader } from "../../components/page-header";
import {
  DelayedPriceNote,
  EmptyState,
  LoadingRegion,
  QuerySection,
  Skeleton,
  SkeletonCards,
  SkeletonChart,
  SkeletonTable,
} from "../../components/states";
import { ChartDataTable, DataTable, type Column } from "../../components/table";
import { Badge, Button, Chip, Notice, SectionCard, SegmentedControl, Tabs } from "../../components/ui";
import { DirectionValue, MetricCard, NullableText, RateWithN, ScoreBadge } from "../../components/values";
import type { EmotionTag, Market, Position, Trade, TradeCreateRequest } from "../../lib/api-types";
import {
  ACTION_LABEL_JA,
  ACTION_TONE,
  EMOTION_LABEL_JA,
  MARKET_LABEL_JA,
  TRADE_ACQUIRE,
  TRADE_DISPOSE,
  tradeSideLabel,
  tradeSideTone,
} from "../../lib/labels";
import { enqueueTrade, flushTradeQueue, listQueuedTrades } from "../../lib/offline-queue";
import {
  useCreateTrade,
  usePerformance,
  usePortfolio,
  usePositions,
  useTradeAnalysis,
  useTrades,
} from "../../lib/queries";
import { useQueryParamState } from "../../lib/use-tab";

const TABS = ["positions", "journal", "analysis"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = { positions: "保有", journal: "売買日誌", analysis: "分析" };

const EMOTIONS: EmotionTag[] = ["confident", "neutral", "fearful", "fomo"];

function priceText(value: number | null, currency: string) {
  return currency === "USD" ? formatUsd(value) : formatJpy(value);
}

const positionColumns: Array<Column<Position>> = [
  {
    key: "name",
    header: "銘柄",
    primary: true,
    render: (r) => (
      <span>
        <span className="num mr-2 text-fg-secondary">{r.ticker}</span>
        {r.name_local}
      </span>
    ),
    sortValue: (r) => r.ticker,
  },
  { key: "market", header: "市場", render: (r) => MARKET_LABEL_JA[r.market] },
  { key: "qty", header: "数量", numeric: true, render: (r) => <span className="num">{formatVolume(r.quantity)}</span>, sortValue: (r) => r.quantity },
  {
    key: "avg",
    header: "平均取得単価",
    numeric: true,
    hideOnCard: true,
    render: (r) => <span className="num">{priceText(r.avg_cost, r.currency)}</span>,
    sortValue: (r) => r.avg_cost,
  },
  {
    key: "ref",
    header: "参考価格",
    numeric: true,
    render: (r) => <NullableText value={r.ref_price !== null ? priceText(r.ref_price, r.currency) : null} />,
    sortValue: (r) => r.ref_price,
  },
  {
    key: "value",
    header: "評価額",
    numeric: true,
    render: (r) => <NullableText value={r.market_value !== null ? priceText(r.market_value, r.currency) : null} />,
    sortValue: (r) => r.market_value,
  },
  {
    key: "pnl",
    header: "評価損益",
    numeric: true,
    render: (r) => (
      <DirectionValue
        value={r.unrealized_pnl_pct}
        format="percent"
        suffix={r.unrealized_pnl !== null ? priceText(r.unrealized_pnl, r.currency) : undefined}
      />
    ),
    sortValue: (r) => r.unrealized_pnl_pct,
  },
  {
    key: "weight",
    header: "比率",
    numeric: true,
    render: (r) => <NullableText value={r.weight_pct !== null ? formatPct(r.weight_pct, { precision: 1 }) : null} />,
    sortValue: (r) => r.weight_pct,
  },
  { key: "score", header: "総合スコア", numeric: true, render: (r) => <ScoreBadge score={r.quant_score} size="sm" />, sortValue: (r) => r.quant_score },
  {
    key: "view",
    header: "現在の見立て",
    render: (r) =>
      r.current_view ? (
        <Badge tone={ACTION_TONE[r.current_view]}>{ACTION_LABEL_JA[r.current_view]}</Badge>
      ) : (
        <span className="text-fg-muted">{NULL_PLACEHOLDER}</span>
      ),
  },
  { key: "days", header: "保有日数", numeric: true, render: (r) => <span className="num">{r.holding_days}営業日</span>, sortValue: (r) => r.holding_days },
  {
    key: "earn",
    header: "決算",
    numeric: true,
    render: (r) => (
      <NullableText value={r.next_earnings_in_days !== null ? `${r.next_earnings_in_days}営業日後` : null} reasonJa="決算日が未確定です" />
    ),
    sortValue: (r) => r.next_earnings_in_days,
  },
];

function PositionsTab({ market }: { market: "all" | Market }) {
  const totalsQ = usePortfolio();
  const posQ = usePositions();
  const perfQ = usePerformance("1y");

  return (
    <div className="space-y-4">
      <QuerySection label="評価サマリ" query={totalsQ} skeleton={<SkeletonCards count={4} className="grid-cols-2 desktop:grid-cols-4" />}>
        {(t) => (
          <>
            <div className="grid grid-cols-2 gap-3 desktop:grid-cols-4">
              <MetricCard label="評価額" value={formatJpy(t.total_value)} sub={`${t.n_positions}銘柄`} />
              <MetricCard
                label="評価損益"
                value={<DirectionValue value={t.unrealized_pnl_pct} format="percent" suffix={formatJpy(t.unrealized_pnl)} />}
              />
              <MetricCard label="実現損益（年初来）" value={<DirectionValue value={t.realized_pnl_ytd} format="currency-jpy" />} />
              <MetricCard label="現金" value={formatJpy(t.cash)} />
            </div>
            <p className="text-caption text-fg-secondary">{t.currency_split_ja}（1ドル152.34円で換算）</p>
            <DelayedPriceNote note={t.ref_price_note_ja} />
          </>
        )}
      </QuerySection>

      <div className="grid gap-4 desktop:grid-cols-12">
        <SectionCard title="推移" className="desktop:col-span-8">
          <QuerySection
            label="推移"
            query={perfQ}
            skeleton={<SkeletonChart />}
          >
            {(points) => (
              <>
                <TimeSeriesChart
                  data={points.map((p) => ({
                    date: p.date,
                    portfolio_index: p.portfolio_index,
                    benchmark_index: p.benchmark_index,
                  }))}
                  series={[
                    { dataKey: "portfolio_index", label: "ポートフォリオ" },
                    { dataKey: "benchmark_index", label: "ベンチマーク", dashed: true },
                  ]}
                />
                <p className="text-caption text-fg-tertiary mt-2">
                  手動入力された売買記録から算出しています。入力漏れがある場合は数値が正しくありません。
                </p>
                <ChartDataTable
                  caption="ポートフォリオ推移"
                  headers={["日付", "ポートフォリオ", "ベンチマーク"]}
                  rows={points.map((p) => [p.date, String(p.portfolio_index), String(p.benchmark_index)])}
                />
              </>
            )}
          </QuerySection>
        </SectionCard>
        <SectionCard title="構成" className="desktop:col-span-4">
          <QuerySection label="構成" query={posQ} skeleton={<SkeletonTable rows={4} cols={2} />}>
            {(rows) => {
              const filtered = market === "all" ? rows : rows.filter((r) => r.market === market);
              const top = [...filtered].sort((a, b) => (b.weight_pct ?? -1) - (a.weight_pct ?? -1))[0];
              return (
                <ul className="space-y-2">
                  {filtered.slice(0, 5).map((r) => (
                    <li key={r.ticker} className="flex justify-between gap-2 text-body-sm">
                      <span>
                        {r.ticker} {r.name_local}
                      </span>
                      <span className="num">{r.weight_pct !== null ? formatPct(r.weight_pct, { precision: 1 }) : NULL_PLACEHOLDER}</span>
                    </li>
                  ))}
                  {top?.weight_pct !== null && top?.weight_pct !== undefined && top.weight_pct > 0.3 ? (
                    <Notice tone="warning">セクター集中が30%を超えています。</Notice>
                  ) : null}
                </ul>
              );
            }}
          </QuerySection>
        </SectionCard>
      </div>

      <SectionCard title="保有銘柄">
        <QuerySection
          label="保有銘柄"
          query={posQ}
          skeleton={<SkeletonTable rows={7} cols={8} />}
          emptyWhen={(d) => (market === "all" ? d : d.filter((r) => r.market === market)).length === 0}
          empty={{
            title: "保有銘柄がありません",
            description: "売買を記録すると保有状況が表示されます。",
          }}
        >
          {(rows) => {
            const filtered = market === "all" ? rows : rows.filter((r) => r.market === market);
            const missingPx = filtered.some((r) => r.ref_price === null);
            return (
              <>
                {missingPx ? (
                  <Notice tone="warning">参考価格を取得できませんでした。取得価額のみ表示しています。</Notice>
                ) : null}
                <DataTable
                  columns={positionColumns}
                  rows={filtered}
                  getKey={(r) => `${r.market}-${r.ticker}`}
                  getHref={(r) => `/stocks/${r.market}/${r.ticker}`}
                  caption="保有銘柄"
                />
                <p className="text-caption text-fg-tertiary mt-2">評価額と評価損益は参考価格ベースです。</p>
              </>
            );
          }}
        </QuerySection>
      </SectionCard>

      <div className="grid gap-4 desktop:grid-cols-2">
        <SectionCard title="リスク">
          <QuerySection label="リスク" query={posQ} skeleton={<SkeletonTable rows={4} cols={2} />}>
            {(rows) => {
              const sorted = [...rows].sort((a, b) => (b.weight_pct ?? -1) - (a.weight_pct ?? -1));
              const top = sorted[0];
              const top3 = sorted.slice(0, 3).reduce((s, r) => (r.weight_pct === null ? s : s + r.weight_pct), 0);
              const usd = rows.filter((r) => r.currency === "USD").reduce((s, r) => (r.weight_pct === null ? s : s + r.weight_pct), 0);
              const soon = rows.filter((r) => r.next_earnings_in_days !== null && r.next_earnings_in_days <= 3);
              return (
                <ul className="space-y-2 text-body-sm">
                  <li>
                    最大保有比率{" "}
                    <span className="num">
                      {top?.weight_pct !== null && top?.weight_pct !== undefined ? formatPct(top.weight_pct, { precision: 1 }) : NULL_PLACEHOLDER}
                    </span>
                    {top ? ` (${top.ticker} ${top.name_local})` : null}
                  </li>
                  <li>
                    上位3銘柄の比率 <span className="num">{formatPct(top3, { precision: 1 })}</span>
                  </li>
                  <li>
                    米ドル建て比率 <span className="num">{formatPct(usd, { precision: 1 })}</span>
                  </li>
                  <li>決算が近い銘柄 {soon.length}銘柄（3営業日以内）</li>
                </ul>
              );
            }}
          </QuerySection>
        </SectionCard>
        <SectionCard title="予定">
          <QuerySection
            label="予定"
            query={posQ}
            skeleton={<SkeletonTable rows={3} cols={2} />}
            emptyWhen={(d) => d.every((r) => r.next_earnings_in_days === null)}
            empty={{
              title: "保有銘柄で決算発表が近いものはありません",
              description: "決算日が近づくとここに表示されます。",
            }}
          >
            {(rows) => (
              <ul className="space-y-2">
                {rows
                  .filter((r) => r.next_earnings_in_days !== null)
                  .sort((a, b) => (a.next_earnings_in_days ?? 99) - (b.next_earnings_in_days ?? 99))
                  .map((r) => (
                    <li key={r.ticker} className="flex justify-between text-body-sm">
                      <span>
                        {r.ticker} {r.name_local}
                      </span>
                      <span className="num">{r.next_earnings_in_days}営業日後</span>
                    </li>
                  ))}
              </ul>
            )}
          </QuerySection>
        </SectionCard>
      </div>
    </div>
  );
}

function JournalTab({ onNew }: { onNew: () => void }) {
  const query = useTrades();
  const [side, setSide] = useState<"all" | "acquire" | "dispose">("all");
  const [linked, setLinked] = useState<"all" | "rec" | "disc">("all");
  const [emotion, setEmotion] = useState<EmotionTag | "all">("all");
  const [q, setQ] = useState("");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={onNew}>
          記録を作成
        </Button>
        <Chip selected={side === "all"} onClick={() => setSide("all")}>
          すべて
        </Chip>
        <Chip selected={side === "acquire"} onClick={() => setSide("acquire")}>
          {tradeSideLabel(TRADE_ACQUIRE)}
        </Chip>
        <Chip selected={side === "dispose"} onClick={() => setSide("dispose")}>
          {tradeSideLabel(TRADE_DISPOSE)}
        </Chip>
        <Chip selected={linked === "rec"} onClick={() => setLinked(linked === "rec" ? "all" : "rec")}>
          推奨連動
        </Chip>
        <Chip selected={linked === "disc"} onClick={() => setLinked(linked === "disc" ? "all" : "disc")}>
          裁量
        </Chip>
        {EMOTIONS.map((e) => (
          <Chip key={e} selected={emotion === e} onClick={() => setEmotion(emotion === e ? "all" : e)}>
            {EMOTION_LABEL_JA[e]}
          </Chip>
        ))}
        <input className="input max-w-xs" placeholder="判断メモを検索" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="grid gap-4 desktop:grid-cols-12">
        <div className="desktop:col-span-8">
          <QuerySection
            label="売買日誌"
            query={query}
            skeleton={<SkeletonCards count={4} />}
            emptyWhen={(d) => d.length === 0}
            empty={{
              title: "売買記録がありません",
              description: "手動で記録するか、証券会社のCSVを取り込んでください。",
              action: (
                <Button variant="primary" onClick={onNew}>
                  記録を作成
                </Button>
              ),
            }}
          >
            {(rows) => {
              const filtered = rows.filter((t) => {
                if (side === "acquire" && t.side !== TRADE_ACQUIRE) return false;
                if (side === "dispose" && t.side !== TRADE_DISPOSE) return false;
                if (linked === "rec" && !t.linked_rec_id) return false;
                if (linked === "disc" && t.linked_rec_id) return false;
                if (emotion !== "all" && t.emotion_tag !== emotion) return false;
                if (q && !t.thesis_ja.includes(q) && !(t.exit_plan_ja ?? "").includes(q)) return false;
                return true;
              });
              return (
                <ul className="space-y-3">
                  {filtered.map((t) => (
                    <TradeCard key={t.trade_id} trade={t} />
                  ))}
                </ul>
              );
            }}
          </QuerySection>
        </div>
        <SectionCard title="記入状況" className="desktop:col-span-4">
          <QuerySection label="記入状況" query={query} skeleton={<SkeletonTable rows={4} cols={1} />}>
            {(rows) => {
              const n = rows.length;
              const tagged = rows.filter((t) => t.emotion_tag).length;
              const thesis = rows.filter((t) => t.thesis_ja.length >= 10).length;
              const acquired = rows.filter((t) => t.side === TRADE_ACQUIRE);
              const exit = acquired.filter((t) => (t.exit_plan_ja ?? "").length >= 5).length;
              const linkedN = rows.filter((t) => t.linked_rec_id).length;
              return (
                <ul className="space-y-2 text-body-sm">
                  <li>記録件数 {n}件</li>
                  <li>判断メモ記入率 <RateWithN rate={n === 0 ? null : thesis / n} n={n} /></li>
                  <li>心理状態タグ付与率 <RateWithN rate={n === 0 ? null : tagged / n} n={n} /></li>
                  <li>
                    撤退計画記入率 <RateWithN rate={acquired.length === 0 ? null : exit / acquired.length} n={acquired.length} />
                  </li>
                  <li>推奨連動率 <RateWithN rate={n === 0 ? null : linkedN / n} n={n} /></li>
                </ul>
              );
            }}
          </QuerySection>
        </SectionCard>
      </div>
    </div>
  );
}

function TradeCard({ trade }: { trade: Trade }) {
  return (
    <li className="card p-4">
      {trade.is_pending_sync ? <Badge tone="warning">送信待ち</Badge> : null}
      <p className="text-caption text-fg-tertiary num">{formatDateTimeJst(trade.executed_at)}</p>
      <p className="text-body mt-1">
        <Badge tone={tradeSideTone(trade.side)}>{tradeSideLabel(trade.side)}</Badge>
        <span className="num mx-2">{trade.ticker}</span>
        {trade.name_local} {formatVolume(trade.quantity)} @ {priceText(trade.price, trade.currency)}
      </p>
      <p className="text-caption text-fg-secondary mt-1">
        心理状態: {trade.emotion_tag ? EMOTION_LABEL_JA[trade.emotion_tag] : NULL_PLACEHOLDER}
      </p>
      <p className="text-body-sm mt-2 prose-block">{trade.thesis_ja}</p>
      {trade.exit_plan_ja ? (
        <p className="text-caption text-fg-secondary mt-1">撤退計画 {trade.exit_plan_ja}</p>
      ) : null}
    </li>
  );
}

function TradeEntrySheet({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const online = useOnlineStatus();
  const create = useCreateTrade();
  const [ticker, setTicker] = useState("7203");
  const [side, setSide] = useState(TRADE_ACQUIRE);
  const [qty, setQty] = useState("100");
  const [price, setPrice] = useState("3125");
  const [thesis, setThesis] = useState("");
  const [exitPlan, setExitPlan] = useState("");
  const [emotion, setEmotion] = useState<EmotionTag | "">("");
  const [error, setError] = useState<string | null>(null);
  const [queuedNote, setQueuedNote] = useState<string | null>(null);

  const qtyNum = Number(qty);
  const priceNum = Number(price);
  const unitWarn = ticker === "7203" && qtyNum % 100 !== 0;
  const ref = 3125;
  const dev = ref > 0 && Number.isFinite(priceNum) ? Math.abs(priceNum - ref) / ref : 0;

  const save = async () => {
    setError(null);
    if (!ticker || !Number.isFinite(qtyNum) || qtyNum <= 0 || !Number.isFinite(priceNum) || priceNum <= 0) {
      setError("銘柄・数量・約定価格は必須です。");
      return;
    }
    if (thesis.trim().length < 10) {
      setError("判断メモは10文字以上で入力してください。");
      return;
    }
    if (!emotion) {
      setError("心理状態は必須です。後から復元できないため、記録時点の状態を選んでください。");
      return;
    }
    if (side === TRADE_ACQUIRE && exitPlan.trim().length < 5) {
      setError("取得の記録には撤退計画が必要です。");
      return;
    }
    const req: TradeCreateRequest = {
      ticker,
      market: ticker.match(/^[0-9]/) ? "JP" : "US",
      side,
      quantity: qtyNum,
      price: priceNum,
      fee: 0,
      currency: ticker.match(/^[0-9]/) ? "JPY" : "USD",
      executed_at: new Date().toISOString(),
      thesis_ja: thesis.trim(),
      emotion_tag: emotion,
      exit_plan_ja: exitPlan.trim() || undefined,
    };
    if (!online) {
      enqueueTrade(req as unknown as Record<string, unknown>);
      setQueuedNote("未送信の記録1件を含みます");
      onClose();
      return;
    }
    create.mutate(req, {
      onSuccess: () => onClose(),
      onError: (err) => setError(`${err.messageJa} 入力内容は保持されています。もう一度お試しください。`),
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="売買記録"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            閉じる
          </Button>
          <Button variant="primary" onClick={() => void save()} disabled={create.isPending}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {side === TRADE_ACQUIRE ? (
          <Notice tone="info">
            この推奨の弱気論拠（記録時点）を読んだうえで記録してください。折りたたまずに表示しています。
          </Notice>
        ) : null}
        <Field label="銘柄">
          <input className="input" value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </Field>
        <div className="flex gap-2" role="group" aria-label="売買">
          <Chip selected={side === TRADE_ACQUIRE} onClick={() => setSide(TRADE_ACQUIRE)}>
            {tradeSideLabel(TRADE_ACQUIRE)}
          </Chip>
          <Chip selected={side === TRADE_DISPOSE} onClick={() => setSide(TRADE_DISPOSE)}>
            {tradeSideLabel(TRADE_DISPOSE)}
          </Chip>
        </div>
        <Field label="数量">
          <input className="input input-numeric" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
          {unitWarn ? <span className="text-caption text-status-warning">この銘柄の売買単位は100株です</span> : null}
        </Field>
        <Field label="約定価格">
          <input className="input input-numeric" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
          {dev > 0.1 ? (
            <span className="text-caption text-status-warning">
              参考価格 {formatJpy(ref)} から {formatPct(dev, { precision: 1 })} 離れています。入力を確認してください。
            </span>
          ) : null}
        </Field>
        <Field label="判断メモ">
          <textarea className="input min-h-24" value={thesis} onChange={(e) => setThesis(e.target.value)} />
        </Field>
        <Field label="心理状態">
          <select className="input" value={emotion} onChange={(e) => setEmotion(e.target.value as EmotionTag | "")}>
            <option value="">選択してください</option>
            {EMOTIONS.map((em) => (
              <option key={em} value={em}>
                {EMOTION_LABEL_JA[em]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="撤退計画">
          <textarea className="input min-h-16" value={exitPlan} onChange={(e) => setExitPlan(e.target.value)} />
        </Field>
        {error ? <Notice tone="danger">{error}</Notice> : null}
        {queuedNote ? <Notice tone="warning">{queuedNote}</Notice> : null}
        {!online ? (
          <Notice tone="warning">オフラインです。保存すると送信待ちになり、接続復帰後に送ります。</Notice>
        ) : null}
      </div>
    </Dialog>
  );
}

function AnalysisTab() {
  const query = useTradeAnalysis();

  return (
    <QuerySection
      label="分析"
      query={query}
      skeleton={<SkeletonCards count={4} className="tablet:grid-cols-2" />}
    >
      {(a) => {
        if (a.execution_quality.n_trades < 10) {
          return (
            <EmptyState
              title="分析には最低10件の売買記録が必要です"
              description={`現在 ${a.execution_quality.n_trades}件です。少ない件数で的中率を出すと誤った結論になります。`}
            />
          );
        }
        const rec = a.recommendation_quality;
        const exe = a.execution_quality;
        return (
          <div className="grid gap-4 tablet:grid-cols-2">
            <SectionCard title="推奨の質">
              <p>推奨件数 {rec.n_recommendations}件</p>
              <p>
                的中率 <RateWithN rate={rec.hit_rate} n={rec.n_recommendations} />
              </p>
              <p>
                平均超過リターン <DirectionValue value={rec.avg_excess_return} format="percent" precision={2} />
              </p>
              <p className="text-caption text-fg-secondary mt-2">
                確信度別 高 {formatPct(rec.by_conviction.high, { precision: 0 })} (n={rec.n_by_conviction.high}) / 中{" "}
                {formatPct(rec.by_conviction.medium, { precision: 0 })} (n={rec.n_by_conviction.medium}) / 低{" "}
                {formatPct(rec.by_conviction.low, { precision: 0 })} (n={rec.n_by_conviction.low})
              </p>
              <Notice tone={rec.monotonic ? "info" : "warning"} className="mt-2">
                {rec.monotonic
                  ? "確信度が高いほど的中率が高く、確信度の付け方は妥当です。"
                  : "確信度と的中率の関係が単調ではありません。確信度の付け方に問題があります。"}
              </Notice>
              <p className="text-caption text-fg-tertiary mt-2">{rec.note_ja}</p>
              <p className="text-caption text-fg-muted mt-1">
                この指標は利用者が売買したかどうかに関係なく、全推奨を対象に算出しています。
              </p>
            </SectionCard>
            <SectionCard title="実行の質">
              <p>
                売買件数 {exe.n_trades}件（推奨連動 {exe.n_from_recommendation}件 / 裁量 {exe.n_discretionary}件）
              </p>
              <p>
                的中率（推奨連動） <RateWithN rate={exe.hit_rate_from_rec} n={exe.n_from_recommendation} />
              </p>
              <p>
                的中率（裁量） <RateWithN rate={exe.hit_rate_discretionary} n={exe.n_discretionary} />
              </p>
              <p>参考価格との平均乖離 {exe.avg_slippage_vs_ref_bps.toFixed(1)}bp</p>
              <p>
                平均保有日数 {exe.avg_holding_days.toFixed(1)}営業日（計画 {exe.planned_holding_days.toFixed(1)}営業日）
              </p>
              <p className="text-caption text-fg-secondary mt-2">{exe.note_ja}</p>
            </SectionCard>
            <SectionCard title="心理状態別の的中率">
              <ul className="space-y-1">
                {EMOTIONS.map((e) => (
                  <li key={e} className="flex justify-between text-body-sm">
                    <span>{EMOTION_LABEL_JA[e]}</span>
                    <RateWithN rate={exe.by_emotion_tag[e]} n={exe.n_by_emotion_tag[e]} />
                  </li>
                ))}
              </ul>
              <p className="text-caption text-fg-tertiary mt-2">
                サンプルが少ないタグは参考として表示しています。件数が20件を超えた時点で再評価してください。
              </p>
            </SectionCard>
            <SectionCard title="参考価格との差">
              <p>参考価格との平均乖離 {exe.avg_slippage_vs_ref_bps.toFixed(1)}bp</p>
              <p className="text-caption text-fg-tertiary mt-2">
                参考価格は15分遅延値のため、この乖離はスリッページそのものではなく、記録時点との時間差を含みます。
              </p>
            </SectionCard>
          </div>
        );
      }}
    </QuerySection>
  );
}

function PortfolioInner() {
  const qc = useQueryClient();
  const online = useOnlineStatus();
  const [tab, setTab] = useQueryParamState<Tab>("tab", TABS, "positions");
  const [scope, setScope] = useState<"all" | Market>("all");
  const [entryOpen, setEntryOpen] = useState(false);
  const [queued, setQueued] = useState(0);
  const totalsQ = usePortfolio();
  const create = useCreateTrade();

  useEffect(() => {
    setQueued(listQueuedTrades().length);
    if (!online) return;
    void flushTradeQueue<TradeCreateRequest>((payload) => create.mutateAsync(payload)).then((r) => {
      if (r.sent > 0) setQueued(listQueuedTrades().length);
    });
  }, [online, create]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT")) return;
      if (e.key === "n") {
        e.preventDefault();
        setEntryOpen(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      {queued > 0 ? (
        <Notice tone="warning" className="mb-3">
          未送信の記録が{queued}件あります。オンラインになったら画面を開いて送信してください。
          {online ? (
            <Button
              variant="secondary"
              className="ml-2"
              onClick={() => void flushTradeQueue<TradeCreateRequest>((p) => create.mutateAsync(p))}
            >
              送信
            </Button>
          ) : null}
        </Notice>
      ) : null}
      <PageHeader
        title="ポートフォリオ"
        asOf={totalsQ.data?.meta.as_of}
        computedAt={totalsQ.data?.meta.computed_at}
        refreshing={totalsQ.isFetching && !totalsQ.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["portfolio"] })}
        actions={
          <SegmentedControl
            label="市場"
            value={scope}
            onChange={setScope}
            options={[
              { value: "all", label: "すべて" },
              { value: "JP", label: "日本株" },
              { value: "US", label: "米国株" },
            ]}
          />
        }
      />
      <Tabs
        label="ポートフォリオのタブ"
        value={tab}
        onChange={setTab}
        options={TABS.map((t) => ({ value: t, label: TAB_LABEL[t] }))}
      />
      <div className="mt-4">
        {tab === "positions" ? <PositionsTab market={scope} /> : null}
        {tab === "journal" ? <JournalTab onNew={() => setEntryOpen(true)} /> : null}
        {tab === "analysis" ? <AnalysisTab /> : null}
      </div>
      <TradeEntrySheet open={entryOpen} onClose={() => setEntryOpen(false)} />
      {tab === "journal" ? (
        <button
          type="button"
          className="btn btn-primary fixed bottom-20 right-4 tablet:hidden tap-target"
          onClick={() => setEntryOpen(true)}
        >
          記録
        </button>
      ) : null}
    </>
  );
}

export default function PortfolioPage() {
  return (
    <Suspense
      fallback={
        <LoadingRegion label="ポートフォリオ">
          <Skeleton className="h-10 w-48" />
          <SkeletonCards count={4} className="mt-4 grid-cols-2" />
        </LoadingRegion>
      }
    >
      <PortfolioInner />
    </Suspense>
  );
}
