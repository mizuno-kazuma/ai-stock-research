"use client";

/**
 * モデルラボ（docs/ui/screens/07-model-lab.md）。
 *
 * この画面の仕事は「モデルが十分でない」と結論しやすくすること。
 * Rank IC 0.03 前後を現実的な水準として常に見せ、バックテストはコスト前提を結果より先に出す。
 */

import { Suspense, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  formatBps,
  formatDuration,
  formatPct,
  formatRateWithN,
  formatScore,
  formatZ,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import { BarWithLineChart, HorizontalBarChart, SignedBarChart, TimeSeriesChart } from "../../components/charts";
import { ConfirmDialog, Dialog, Field } from "../../components/dialog";
import { BacktestResultCard } from "../../components/model-health";
import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import {
  EmptyState,
  LoadingRegion,
  QuerySection,
  Skeleton,
  SkeletonCards,
  SkeletonChart,
  SkeletonTable,
} from "../../components/states";
import { ChartDataTable, DataTable, type Column } from "../../components/table";
import { Badge, Button, Notice, SectionCard, Tabs } from "../../components/ui";
import { DirectionValue, MetricCard, NullableText, RateWithN } from "../../components/values";
import { useOnlineStatus } from "../../components/app-shell";
import type { Backtest, BacktestRequest, FeatureImportance, IcPoint, LeakageCheck, ModelRun, QuintileReturn } from "../../lib/api-types";
import { MODEL_KIND_LABEL_JA } from "../../lib/labels";
import {
  useActivateWeights,
  useBacktests,
  useCreateBacktest,
  useEquityCurve,
  useFactorWeights,
  useFeatureImportance,
  useIcSeries,
  useLeakageChecks,
  useModelHealth,
  useModelRuns,
  useQuintiles,
  useRejectWeights,
} from "../../lib/queries";
import { useOptionalQueryParam, useQueryParamState } from "../../lib/use-tab";

const TABS = ["health", "runs", "backtests", "weights"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  health: "モデルの状態",
  runs: "学習履歴",
  backtests: "バックテスト",
  weights: "ファクター重み",
};

const IC_NOTE =
  "Rank IC 0.03 前後はこの種のモデルとして現実的な水準です。0.10 を超える値が継続する場合は、リーク（未来情報の混入）を疑って検証してください。";

const runColumns: Array<Column<ModelRun>> = [
  { key: "run_id", header: "実行ID", primary: true, render: (r) => <span className="num">{r.run_id}</span>, sortValue: (r) => r.run_id },
  { key: "kind", header: "種別", render: (r) => MODEL_KIND_LABEL_JA[r.kind] },
  {
    key: "status",
    header: "状態",
    render: (r) => (
      <Badge tone={r.status === "success" ? "success" : r.status === "failed" ? "danger" : "info"}>
        {r.status === "success" ? "稼働中" : r.status === "failed" ? "失敗" : "実行中"}
      </Badge>
    ),
  },
  {
    key: "ic",
    header: "Rank IC (60日)",
    numeric: true,
    render: (r) => <NullableText value={r.rank_ic_60d !== null ? formatZ(r.rank_ic_60d, 3) : null} />,
    sortValue: (r) => r.rank_ic_60d,
  },
];

const btColumns: Array<Column<Backtest>> = [
  { key: "name", header: "戦略", primary: true, render: (r) => r.strategy_name, sortValue: (r) => r.strategy_name },
  {
    key: "status",
    header: "状態",
    render: (r) => (
      <Badge tone={r.status === "significant" ? "success" : r.status === "failed" ? "danger" : r.status === "running" ? "info" : "warning"}>
        {r.status === "significant" ? "有意" : r.status === "not_significant" ? "有意ではない" : r.status === "failed" ? "失敗" : "実行中"}
      </Badge>
    ),
  },
  {
    key: "cost",
    header: "コスト前提",
    render: (r) => (
      <span className="num text-caption">
        手数料 {formatBps(r.cost.fee_bps)} · スリッページ {formatBps(r.cost.slippage_bps)} · 回転率上限{" "}
        {formatPct(r.cost.max_turnover_pct, { precision: 0 })}
      </span>
    ),
  },
  {
    key: "sharpe",
    header: "シャープ",
    numeric: true,
    render: (r) => <NullableText value={r.sharpe !== null ? formatScore(r.sharpe) : null} />,
    sortValue: (r) => r.sharpe,
  },
  {
    key: "dsr",
    header: "DSR",
    numeric: true,
    render: (r) => <NullableText value={r.deflated_sharpe !== null ? r.deflated_sharpe.toFixed(2) : null} />,
    sortValue: (r) => r.deflated_sharpe,
  },
];

function isMonotonic(rows: QuintileReturn[]): boolean {
  for (let i = 1; i < rows.length; i += 1) {
    const prev = rows[i - 1]?.excess_ret_ann;
    const cur = rows[i]?.excess_ret_ann;
    if (prev === undefined || cur === undefined) return false;
    if (cur < prev) return false;
  }
  return rows.length > 1;
}

function HealthTab() {
  const healthQ = useModelHealth();
  const runsQ = useModelRuns();
  const ranker = runsQ.data?.data.find((r) => r.kind === "ranker");
  const icQ = useIcSeries(ranker?.run_id);
  const quintileQ = useQuintiles(ranker?.run_id);
  const featQ = useFeatureImportance(ranker?.run_id);
  const leakQ = useLeakageChecks();
  const [metric, setMetric] = useState<"gain" | "split" | "permutation">("gain");

  const icStats = useMemo(() => {
    const values = (icQ.data?.data ?? []).map((p) => p.ic);
    if (values.length === 0) return null;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
    const plus = values.filter((v) => v > 0).length;
    return { mean, std: Math.sqrt(variance), plus, n: values.length };
  }, [icQ.data]);

  const failedLeak = (leakQ.data?.data ?? []).some((c) => c.status === "fail");

  return (
    <div className="space-y-4">
      {failedLeak ? (
        <Notice tone="danger" role="alert">
          リーク検出テストが失敗しています。本日のスコアと推奨は信用できません。
        </Notice>
      ) : null}

      <QuerySection
        label="モデルの状態"
        query={healthQ}
        skeleton={<SkeletonCards count={4} className="grid-cols-2 desktop:grid-cols-4" />}
        emptyWhen={(d) => d.status === "not_trained"}
        empty={{
          title: "モデルがまだ学習されていません",
          description: "Analystジョブの初回実行後に表示されます。",
        }}
      >
        {(health) => (
          <>
            {health.status === "degraded" && health.degradation_note_ja ? (
              <Notice tone="danger" role="alert">
                モデルの成績低下を検出しました。{health.degradation_note_ja}
              </Notice>
            ) : null}
            <div className="grid grid-cols-2 gap-3 desktop:grid-cols-4">
              <MetricCard
                label="Rank IC (直近20営業日)"
                value={<NullableText value={health.rank_ic_20d !== null ? health.rank_ic_20d.toFixed(3) : null} />}
                sub="n=20日"
                hint="予測順位と実現超過リターンのSpearman相関"
              />
              <MetricCard
                label="Rank IC (直近3ヶ月)"
                value={<NullableText value={health.rank_ic_3m != null ? health.rank_ic_3m.toFixed(3) : null} />}
                sub={health.rank_ic_percentile_1y !== null ? `過去1年の位置 ${formatPct(health.rank_ic_percentile_1y, { precision: 0 })}` : undefined}
              />
              <MetricCard
                label="カバー率"
                value={
                  <NullableText
                    value={health.coverage_rate !== null ? formatPct(health.coverage_rate, { precision: 1 }) : null}
                  />
                }
                sub={<NullableText value={health.coverage_detail_ja} />}
              />
              <MetricCard
                label="劣化検出"
                value={health.status === "degraded" ? "検出あり" : health.status === "watch" ? "注視" : "検出なし"}
                sub="直近20日平均が3ヶ月平均の-50%を下回った場合に検出"
                tone={health.status === "degraded" ? "warning" : undefined}
              />
            </div>
            <p className="text-body-sm text-fg-secondary prose-block">{IC_NOTE}</p>
          </>
        )}
      </QuerySection>

      <SectionCard title="Rank ICの推移" subtitle="ゼロが「予測力なし」です">
        <QuerySection
          label="Rank ICの推移"
          query={icQ}
          skeleton={<SkeletonChart height="chart-h-md" />}
          emptyWhen={(d) => d.length === 0}
          empty={{
            title: "Rank ICの履歴がまだありません",
            description: "運用開始から20営業日経過後に表示されます。",
          }}
        >
          {(series: IcPoint[]) => (
            <>
              <BarWithLineChart
                data={series.map((p) => ({ date: p.date, ic: p.ic, rolling_20d: p.rolling_20d }))}
                barKey="ic"
                lineKey="rolling_20d"
                barLabel="日次 Rank IC"
                lineLabel="20営業日移動平均"
                height="chart-h-md"
                valueFormatter={(v) => v.toFixed(3)}
              />
              <p className="text-caption text-fg-tertiary mt-2">
                Rank IC は各日のクロスセクションにおける予測値と実現超過リターンのSpearman順位相関です。0が「予測力なし」を意味します。
              </p>
              {icStats ? (
                <p className="text-caption text-fg-secondary mt-1">
                  期間中の平均 {icStats.mean.toFixed(3)}、標準偏差 {icStats.std.toFixed(3)}、プラスの日{" "}
                  {formatRateWithN(icStats.plus / icStats.n, icStats.n)}
                </p>
              ) : null}
              <ChartDataTable
                caption="Rank ICの推移"
                headers={["日付", "日次 Rank IC", "20営業日移動平均"]}
                rows={series.map((p) => [p.date, p.ic.toFixed(4), p.rolling_20d !== null ? p.rolling_20d.toFixed(4) : NULL_PLACEHOLDER])}
              />
            </>
          )}
        </QuerySection>
      </SectionCard>

      <div className="grid gap-4 desktop:grid-cols-2">
        <SectionCard title="分位別リターン (20営業日)">
          <QuerySection label="分位別リターン" query={quintileQ} skeleton={<SkeletonChart />}>
            {(rows) => {
              const mono = isMonotonic(rows);
              const q1 = rows[0]?.excess_ret_ann ?? null;
              const q5 = rows[rows.length - 1]?.excess_ret_ann ?? null;
              const spread = q1 !== null && q5 !== null ? q5 - q1 : null;
              return (
                <>
                  <SignedBarChart
                    data={rows.map((r) => ({ label: r.label_ja, value: r.excess_ret_ann }))}
                    valueFormatter={(v) => formatPct(v, { precision: 1, sign: true })}
                  />
                  <p className="text-body-sm mt-2">
                    第5分位 - 第1分位 <DirectionValue value={spread} format="percent" precision={2} />
                  </p>
                  <Notice tone={mono ? "info" : "warning"} className="mt-2">
                    {mono
                      ? "分位が上がるほどリターンが高く、単調性が確認できます"
                      : "分位とリターンの関係が単調ではありません。スコアの序列に意味がない可能性があります"}
                  </Notice>
                  <p className="text-caption text-fg-tertiary mt-2">
                    セクター中立化した超過リターンの平均。手数料・スリッページは含みません。
                  </p>
                  <ChartDataTable
                    caption="分位別リターン"
                    headers={["分位", "超過リターン（年率）"]}
                    rows={rows.map((r) => [r.label_ja, formatPct(r.excess_ret_ann, { sign: true, precision: 2 })])}
                  />
                </>
              );
            }}
          </QuerySection>
        </SectionCard>

        <SectionCard
          title="特徴量の重要度（上位20）"
          actions={
            <select
              className="input"
              value={metric}
              onChange={(e) => setMetric(e.target.value as typeof metric)}
              aria-label="指標"
            >
              <option value="gain">Gain</option>
              <option value="split">Split</option>
              <option value="permutation" disabled>
                Permutation（週次のみ）
              </option>
            </select>
          }
        >
          {metric === "permutation" ? (
            <p className="text-caption text-status-warning">
              Permutation importanceは計算に時間がかかるため、週次でのみ算出しています
            </p>
          ) : (
            <QuerySection
              label="特徴量の重要度"
              query={featQ}
              skeleton={<SkeletonChart height="chart-h-lg" />}
              emptyWhen={(d) => d.length === 0}
              empty={{
                title: "特徴量の重要度は学習済みモデルが必要です",
                description: "Analystジョブの完了後に表示されます。",
              }}
            >
              {(rows: FeatureImportance[]) => (
                <>
                  <HorizontalBarChart
                    data={rows.slice(0, 20).map((r) => ({ label: r.label_ja, value: r.value }))}
                    valueFormatter={(v) => v.toFixed(3)}
                  />
                  <p className="text-caption text-fg-tertiary mt-2">
                    重要度は「予測に寄与した度合い」であり、因果関係を示すものではありません。相関の高い特徴量の間では重要度が分散します。
                  </p>
                </>
              )}
            </QuerySection>
          )}
        </SectionCard>
      </div>

      <SectionCard title="特徴量の相関">
        <p className="text-body-sm text-fg-secondary desktop:hidden">相関ヒートマップはデスクトップで表示されます</p>
        <div className="hidden desktop:block">
          <p className="text-body-sm text-fg-secondary">
            相関行列は学習実行の成果物です。欠けているペアは空白セルとして扱います。
          </p>
          <p className="text-caption text-fg-muted mt-2">欠損ペアは空白 · 対角は 1.00</p>
        </div>
      </SectionCard>

      <SectionCard title="検証構造">
        <dl className="grid grid-cols-2 gap-3 tablet:grid-cols-3">
          <div>
            <dt className="text-caption text-fg-tertiary">手法</dt>
            <dd>Purged Walk-Forward CV</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-tertiary">分割数</dt>
            <dd className="num">8</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-tertiary">学習期間</dt>
            <dd>252営業日（拡張型）</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-tertiary">検証期間</dt>
            <dd>42営業日</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-tertiary">パージ</dt>
            <dd>20営業日（予測ホライズンと同じ）</dd>
          </div>
          <div>
            <dt className="text-caption text-fg-tertiary">エンバーゴ</dt>
            <dd>5営業日</dd>
          </div>
        </dl>
        <div className="mt-3 space-y-1" aria-hidden="true">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex h-3 overflow-hidden rounded-sm">
              <span className="bg-accent" style={{ flex: 6 + i }} />
              <span className="bg-status-warning" style={{ flex: 1 }} title="パージ" />
              <span className="bg-status-warning opacity-60" style={{ flex: 0.4 }} title="エンバーゴ" />
              <span className="bg-status-success" style={{ flex: 1.2 }} />
            </div>
          ))}
        </div>
        <p className="text-caption text-fg-tertiary mt-2">
          学習期間と検証期間の間に、予測ホライズン分のパージとエンバーゴを設けています。KFoldやシャッフルを伴う分割は使用していません。
        </p>
        <QuerySection label="リーク検出" query={leakQ} skeleton={<SkeletonTable rows={6} cols={2} />}>
          {(checks: LeakageCheck[]) => (
            <>
              <ul className="mt-3 space-y-2">
                {checks.map((c) => (
                  <li key={c.id} className="flex items-start justify-between gap-3">
                    <span>
                      <span className="num text-caption text-fg-tertiary mr-2">{c.id}</span>
                      {c.label_ja}
                      {c.detail_ja ? <span className="block text-caption text-fg-muted">{c.detail_ja}</span> : null}
                    </span>
                    <Badge tone={c.status === "pass" ? "success" : c.status === "fail" ? "danger" : "warning"}>
                      {c.status === "pass" ? "合格" : c.status === "fail" ? "失敗" : "未取得"}
                    </Badge>
                  </li>
                ))}
              </ul>
              <p className="text-caption text-fg-tertiary mt-2">
                これらはCIで自動実行されているテストの直近結果です。1件でも失敗している場合、スコアと推奨は信用できません。
              </p>
            </>
          )}
        </QuerySection>
      </SectionCard>
    </div>
  );
}

function RunsTab({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const query = useModelRuns();
  return (
    <QuerySection
      label="学習履歴"
      query={query}
      skeleton={<SkeletonTable rows={6} cols={4} />}
      emptyWhen={(d) => d.length === 0}
      empty={{
        title: "モデルがまだ学習されていません",
        description: "Analystジョブの初回実行後に表示されます。",
      }}
    >
      {(runs) => {
        const selected = runs.find((r) => r.run_id === selectedId) ?? runs[0];
        return (
          <div className="grid gap-4 desktop:grid-cols-12">
            <div className="desktop:col-span-4">
              <DataTable
                columns={runColumns}
                rows={runs}
                getKey={(r) => r.run_id}
                caption="学習実行"
                getHref={(r) => `/model-lab?tab=runs&run_id=${r.run_id}`}
              />
            </div>
            <div className="desktop:col-span-8">
              {selected ? (
                <SectionCard title="実行の詳細">
                  <dl className="grid grid-cols-2 gap-3">
                    <div>
                      <dt className="text-caption text-fg-tertiary">実行ID</dt>
                      <dd className="num">{selected.run_id}</dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">種別</dt>
                      <dd>{MODEL_KIND_LABEL_JA[selected.kind]}</dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">学習日時</dt>
                      <dd className="num">{selected.started_at}</dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">所要時間</dt>
                      <dd>{formatDuration(selected.duration_sec)}</dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">検証 AUC</dt>
                      <dd>
                        <NullableText value={selected.val_auc !== null ? selected.val_auc.toFixed(3) : null} />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">Rank IC (60日)</dt>
                      <dd>
                        <NullableText value={selected.rank_ic_60d !== null ? formatZ(selected.rank_ic_60d, 3) : null} />
                      </dd>
                    </div>
                  </dl>
                  <p className="text-caption text-fg-secondary mt-3">
                    探索試行回数はこの値はDeflated Sharpe Ratioの計算に使用されます。試行回数を記録しないバックテストは信用できません。
                  </p>
                  <Button variant="ghost" className="mt-2" onClick={() => onSelect(selected.run_id)}>
                    この実行を選択
                  </Button>
                </SectionCard>
              ) : null}
            </div>
          </div>
        );
      }}
    </QuerySection>
  );
}

function NewBacktestForm({
  open,
  onClose,
  online,
}: {
  open: boolean;
  onClose: () => void;
  online: boolean;
}) {
  const create = useCreateBacktest();
  const [name, setName] = useState("");
  const [fee, setFee] = useState("");
  const [slip, setSlip] = useState("");
  const [turn, setTurn] = useState("");
  const [trials, setTrials] = useState("");
  const [error, setError] = useState<string | null>(null);
  const ready =
    name.trim().length > 0 && fee !== "" && slip !== "" && turn !== "" && trials !== "";

  const submit = () => {
    if (!ready) {
      setError(
        "手数料・スリッページ・回転率上限・試行回数は必須です。これらを省略したバックテストは実運用の成績を大きく過大評価します。",
      );
      return;
    }
    const req: BacktestRequest = {
      strategy_name: name.trim(),
      market: "JP",
      period_start: "2024-08-01",
      period_end: "2026-07-01",
      rebalance_freq: "monthly",
      n_positions: 20,
      fee_bps: Number(fee),
      slippage_bps: Number(slip),
      max_turnover_pct: Number(turn) / 100,
      n_trials: Number(trials),
      signal_source: { type: "quant_score" },
    };
    create.mutate(req, {
      onSuccess: () => onClose(),
      onError: (err) => setError(err.messageJa),
    });
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="バックテストを実行"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            キャンセル
          </Button>
          <Button variant="primary" onClick={submit} disabled={!ready || !online || create.isPending}>
            実行
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="戦略名">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={64} required />
        </Field>
        <Field label="手数料 (bp)" hint="例: 5.0（楽天証券の現物取引を想定）">
          <input className="input input-numeric" inputMode="decimal" value={fee} onChange={(e) => setFee(e.target.value)} placeholder="例: 5.0（楽天証券の現物取引を想定）" />
        </Field>
        <Field label="スリッページ (bp)" hint="例: 10.0（流動性の高い大型株の想定）">
          <input className="input input-numeric" inputMode="decimal" value={slip} onChange={(e) => setSlip(e.target.value)} placeholder="例: 10.0（流動性の高い大型株の想定）" />
        </Field>
        <Field label="回転率上限 (%/期間)" hint="例: 30.0">
          <input className="input input-numeric" inputMode="decimal" value={turn} onChange={(e) => setTurn(e.target.value)} placeholder="例: 30.0" />
        </Field>
        <Field label="試行回数" hint="この戦略を含め、試した設定の総数。Deflated Sharpe に使います">
          <input
            className="input input-numeric"
            inputMode="numeric"
            value={trials}
            onChange={(e) => setTrials(e.target.value)}
            placeholder="例: 1"
          />
        </Field>
        <p className="text-caption text-fg-secondary">
          この実行は探索試行回数に加算され、Deflated Sharpe Ratioの計算に反映されます。現在の累積試行回数: 120
        </p>
        {error ? <Notice tone="danger">{error}</Notice> : null}
      </div>
    </Dialog>
  );
}

function BacktestsTab({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const query = useBacktests();
  const online = useOnlineStatus();
  const [open, setOpen] = useState(false);
  const selected = query.data?.data.find((b) => b.backtest_id === selectedId) ?? query.data?.data[0];
  const equityQ = useEquityCurve(selected?.backtest_id);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-caption text-fg-tertiary desktop:hidden">バックテストの実行はデスクトップから行ってください</p>
        <Button variant="primary" className="hidden desktop:inline-flex" onClick={() => setOpen(true)} disabled={!online}>
          {online ? "バックテストを実行" : "オフラインでは実行できません"}
        </Button>
      </div>
      <QuerySection
        label="バックテスト"
        query={query}
        skeleton={<SkeletonTable rows={5} cols={5} />}
        emptyWhen={(d) => d.length === 0}
        empty={{
          title: "バックテストの実行履歴がありません",
          description: "手数料・スリッページ・回転率上限を指定して実行してください。",
          action: (
            <Button variant="primary" onClick={() => setOpen(true)}>
              バックテストを実行
            </Button>
          ),
        }}
      >
        {(rows) => (
          <>
            <DataTable
              columns={btColumns}
              rows={rows}
              getKey={(r) => r.backtest_id}
              caption="バックテスト一覧"
              getHref={(r) => `/model-lab?tab=backtests&backtest_id=${r.backtest_id}`}
            />
            {selected ? (
              <div className="mt-4 space-y-4">
                {selected.status === "running" ? (
                  <Notice tone="info">実行中（経過 3分12秒 / 推定 8分）</Notice>
                ) : null}
                {selected.status === "failed" ? (
                  <Notice tone="danger">失敗した実行です。入力を確認して再実行してください。</Notice>
                ) : null}
                <BacktestResultCard backtest={selected} />
                <div className="grid gap-4 desktop:grid-cols-12">
                  <SectionCard title="資産曲線" className="desktop:col-span-8">
                    <QuerySection label="資産曲線" query={equityQ} skeleton={<SkeletonChart />}>
                      {(points) => (
                        <>
                          <TimeSeriesChart
                            data={points.map((p) => ({
                              date: p.date,
                              portfolio_index: p.portfolio_index,
                              benchmark_index: p.benchmark_index,
                            }))}
                            series={[
                              { dataKey: "portfolio_index", label: "戦略" },
                              { dataKey: "benchmark_index", label: "ベンチマーク", dashed: true },
                            ]}
                          />
                          <ChartDataTable
                            caption="資産曲線"
                            headers={["日付", "戦略", "ベンチマーク"]}
                            rows={points.map((p) => [p.date, String(p.portfolio_index), String(p.benchmark_index)])}
                          />
                        </>
                      )}
                    </QuerySection>
                  </SectionCard>
                  <SectionCard title="補足" className="desktop:col-span-4">
                    <p className="text-caption text-fg-secondary">
                      月次勝率 <RateWithN rate={selected.hit_rate} n={selected.n_trades} />
                    </p>
                    <p className="text-caption text-fg-tertiary mt-2">
                      試行回数 {selected.n_trials ?? NULL_PLACEHOLDER} · 検証期間{" "}
                      {selected.period_start} 〜 {selected.period_end}
                    </p>
                    <Button variant="ghost" className="mt-2" onClick={() => onSelect(selected.backtest_id)}>
                      この結果を選択
                    </Button>
                  </SectionCard>
                </div>
              </div>
            ) : null}
          </>
        )}
      </QuerySection>
      <NewBacktestForm open={open} onClose={() => setOpen(false)} online={online} />
    </div>
  );
}

function WeightsTab() {
  const prefs = usePrefs();
  const online = useOnlineStatus();
  const query = useFactorWeights(prefs.market);
  const activate = useActivateWeights();
  const reject = useRejectWeights();
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);

  return (
    <QuerySection label="ファクター重み" query={query} skeleton={<SkeletonTable rows={7} cols={4} />}>
      {(data) => (
        <div className="space-y-4">
          <div className="grid gap-4 desktop:grid-cols-2">
            <SectionCard title={`稼働中の重み (${data.active_weight_set_id})`}>
              <ul className="space-y-2">
                {data.rows.map((r) => (
                  <li key={r.factor_key} className="flex justify-between gap-3">
                    <span>{r.label_ja}</span>
                    <span className="num">{r.active_weight.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </SectionCard>
            <SectionCard title={data.proposed_weight_set_id ? `提案された重み (${data.proposed_weight_set_id})` : "提案された重み"}>
              {!data.proposed_weight_set_id ? (
                <EmptyState title="提案されている重みの変更はありません" description="Evaluatorが十分な実績を集計すると提案されます。" />
              ) : (
                <>
                  <table className="data-table data-table--dense">
                    <thead>
                      <tr>
                        <th>ファクターグループ</th>
                        <th className="is-numeric">現在</th>
                        <th className="is-numeric">提案</th>
                        <th className="is-numeric">変化</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.rows.map((r) => (
                        <tr key={r.factor_key}>
                          <td>{r.label_ja}</td>
                          <td className="is-numeric num">{r.active_weight.toFixed(2)}</td>
                          <td className="is-numeric num">
                            <NullableText value={r.proposed_weight !== null ? r.proposed_weight.toFixed(2) : null} />
                          </td>
                          <td className="is-numeric">
                            <DirectionValue value={r.delta} format="number" precision={2} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-caption text-fg-secondary mt-2">{data.fit_meta_ja}</p>
                  <p className="text-caption text-fg-tertiary mt-1">
                    重みの変更は承認するまで適用されません。承認後の最初の推奨生成から反映されます。
                  </p>
                  <p className="text-caption text-fg-tertiary desktop:hidden mt-2">重みの承認はデスクトップから行ってください</p>
                  <div className="mt-3 hidden desktop:flex gap-2">
                    <Button
                      variant="primary"
                      disabled={!online}
                      onClick={() => setConfirm("approve")}
                    >
                      承認して適用
                    </Button>
                    <Button variant="secondary" disabled={!online} onClick={() => setConfirm("reject")}>
                      却下
                    </Button>
                  </div>
                </>
              )}
            </SectionCard>
          </div>
          <SectionCard title="重みの推移">
            <HorizontalBarChart
              data={data.rows.map((r) => ({ label: r.label_ja, value: r.active_weight }))}
              valueFormatter={(v) => v.toFixed(2)}
            />
          </SectionCard>
          <ConfirmDialog
            open={confirm === "approve"}
            onClose={() => setConfirm(null)}
            title="重みを承認しますか"
            confirmLabel="承認して適用"
            onConfirm={() => {
              if (data.proposed_weight_set_id) activate.mutate(data.proposed_weight_set_id);
              setConfirm(null);
            }}
          >
            承認後の最初の推奨生成から反映されます。差分は上の表のとおりです。
          </ConfirmDialog>
          <ConfirmDialog
            open={confirm === "reject"}
            onClose={() => setConfirm(null)}
            title="提案を却下しますか"
            confirmLabel="却下"
            danger
            onConfirm={() => {
              if (data.proposed_weight_set_id) reject.mutate(data.proposed_weight_set_id);
              setConfirm(null);
            }}
          >
            却下すると提案は破棄され、稼働中の重みは変わりません。
          </ConfirmDialog>
        </div>
      )}
    </QuerySection>
  );
}

function ModelLabInner() {
  const qc = useQueryClient();
  const [tab, setTab] = useQueryParamState<Tab>("tab", TABS, "health");
  const [runId, setRunId] = useOptionalQueryParam("run_id");
  const [backtestId, setBacktestId] = useOptionalQueryParam("backtest_id");
  const healthQ = useModelHealth();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT")) return;
      const map: Record<string, Tab> = { "1": "health", "2": "runs", "3": "backtests", "4": "weights" };
      const next = map[e.key];
      if (next) {
        e.preventDefault();
        setTab(next);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setTab]);

  return (
    <>
      <PageHeader
        title="モデルラボ"
        asOf={healthQ.data?.meta.as_of}
        computedAt={healthQ.data?.meta.computed_at}
        refreshing={healthQ.isFetching && !healthQ.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["models"] })}
        description="成績が良く見えても、リークとコスト前提を先に確認してください。"
      />
      <Tabs
        label="モデルラボのタブ"
        value={tab}
        onChange={setTab}
        options={TABS.map((t) => ({ value: t, label: TAB_LABEL[t] }))}
      />
      <div className="mt-4">
        {tab === "health" ? <HealthTab /> : null}
        {tab === "runs" ? <RunsTab selectedId={runId} onSelect={setRunId} /> : null}
        {tab === "backtests" ? <BacktestsTab selectedId={backtestId} onSelect={setBacktestId} /> : null}
        {tab === "weights" ? <WeightsTab /> : null}
      </div>
    </>
  );
}

export default function ModelLabPage() {
  return (
    <Suspense
      fallback={
        <LoadingRegion label="モデルラボ">
          <Skeleton className="h-10 w-48" />
          <SkeletonCards count={4} className="mt-4 grid-cols-2" />
        </LoadingRegion>
      }
    >
      <ModelLabInner />
    </Suspense>
  );
}
