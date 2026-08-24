"use client";

/**
 * 為替・マクロ（docs/ui/screens/06-fx-macro.md）。
 *
 * この画面で最も重要なのは「予測がベースライン（ランダムウォーク）に勝てていない」という
 * 事実を予測値より先に見せること。判定文（verdict_ja）は API が生成したものをそのまま出す。
 * UI 側で判定ロジックを持たないので、「優位性がないのに強気に見せる」実装ミスが起こらない。
 */

import { ScatterPlot, TimeSeriesChart } from "../../components/charts";
import { PageHeader } from "../../components/page-header";
import {
  DelayedPriceNote,
  QuerySection,
  SkeletonChart,
  SkeletonTable,
} from "../../components/states";
import { ChartDataTable, DataTable, type Column } from "../../components/table";
import { Badge, Notice, SectionCard } from "../../components/ui";
import { DirectionPctPoint, DirectionValue, ForecastValue, NullableText, RateWithN } from "../../components/values";
import { formatJpy, formatPctPoint, formatRateWithN } from "@ai-stock/ui";
import type { FxForecast, FxSensitivityRow, MacroSeries } from "../../lib/api-types";
import { useFx, useFxModels, useFxSensitivity, useMacroSeries, useRateDifferential } from "../../lib/queries";

const forecastColumns: Array<Column<FxForecast>> = [
  { key: "horizon", header: "期間", primary: true, render: (r) => r.label_ja },
  { key: "point", header: "予測（中央値）", numeric: true, render: (r) => <span className="num">{formatJpy(r.point, 2)}</span> },
  {
    key: "band80",
    header: "80%区間",
    numeric: true,
    render: (r) => (
      <span className="num">
        [{formatJpy(r.ci_lo_80, 2)}, {formatJpy(r.ci_hi_80, 2)}]
      </span>
    ),
  },
  {
    key: "band95",
    header: "95%区間",
    numeric: true,
    render: (r) => (
      <span className="num">
        [{formatJpy(r.ci_lo_95, 2)}, {formatJpy(r.ci_hi_95, 2)}]
      </span>
    ),
  },
  {
    key: "hit",
    header: "方向的中率",
    numeric: true,
    render: (r) => <RateWithN rate={r.directional_accuracy_60d} n={r.n_validation} />,
  },
  { key: "model", header: "モデル", render: (r) => r.model_id },
  {
    key: "verdict",
    header: "ベースライン比較",
    render: (r) => (
      <span className="text-body-sm">
        {r.is_baseline ? (
          <Badge tone="neutral">ベースライン</Badge>
        ) : (
          <NullableText value={r.verdict_ja} />
        )}
      </span>
    ),
  },
];

const modelColumns: Array<Column<FxForecast>> = [
  {
    key: "model",
    header: "モデル",
    primary: true,
    render: (r) => (
      <span>
        {r.label_ja}
        {r.is_baseline ? <Badge tone="neutral" className="ml-2">基準</Badge> : null}
      </span>
    ),
  },
  {
    key: "rmse",
    header: "RMSE（60営業日）",
    numeric: true,
    render: (r) => <NullableText value={r.rmse_oos_60d !== null ? r.rmse_oos_60d.toFixed(3) : null} />,
    sortValue: (r) => r.rmse_oos_60d,
  },
  {
    key: "hit",
    header: "方向的中率",
    numeric: true,
    render: (r) => <RateWithN rate={r.directional_accuracy_60d} n={r.n_validation} />,
    sortValue: (r) => r.directional_accuracy_60d,
  },
  {
    key: "dm",
    header: "DM検定 p値",
    numeric: true,
    headerHint: "ベースラインとの予測精度の差が偶然かどうか。0.05未満で有意",
    render: (r) => <NullableText value={r.dm_pvalue !== null ? r.dm_pvalue.toFixed(2) : null} />,
    sortValue: (r) => r.dm_pvalue,
  },
  { key: "verdict", header: "判定", render: (r) => <NullableText value={r.verdict_ja} /> },
];

const macroColumns: Array<Column<MacroSeries>> = [
  { key: "label", header: "指標", primary: true, render: (r) => r.label_ja },
  {
    key: "value",
    header: "最新値",
    numeric: true,
    render: (r) => (
      <NullableText
        value={r.value !== null ? (r.unit === "percent-point" ? formatPctPoint(r.value) : r.value.toFixed(2)) : null}
      />
    ),
    sortValue: (r) => r.value,
  },
  {
    key: "change",
    header: "前回差",
    numeric: true,
    render: (r) =>
      r.unit === "percent-point" ? (
        <DirectionPctPoint value={r.change} />
      ) : (
        <DirectionValue value={r.change} format="number" precision={2} />
      ),
    sortValue: (r) => r.change,
  },
  { key: "vintage", header: "公表日", numeric: true, render: (r) => <span className="num">{r.vintage}</span> },
  { key: "source", header: "出所", render: (r) => r.source, hideOnCard: true },
];

const sensitivityColumns: Array<Column<FxSensitivityRow>> = [
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
  {
    key: "relation",
    header: "区分",
    render: (r) => <Badge tone={r.relation === "holding" ? "accent" : "neutral"}>{r.relation === "holding" ? "保有" : "ウォッチ"}</Badge>,
  },
  {
    key: "sens",
    header: "為替感応度",
    numeric: true,
    headerHint: "ドル円1%の変化に対する株価の反応（過去60営業日）",
    render: (r) => <NullableText value={r.fx_sensitivity !== null ? r.fx_sensitivity.toFixed(2) : null} />,
    sortValue: (r) => r.fx_sensitivity,
  },
  { key: "impact", header: "営業利益への影響", numeric: true, render: (r) => <NullableText value={r.op_income_impact_ja} /> },
  { key: "ret20", header: "20営業日", numeric: true, render: (r) => <DirectionValue value={r.ret_20d} format="percent" precision={1} />, sortValue: (r) => r.ret_20d },
  {
    key: "corr",
    header: "相関（20営業日）",
    numeric: true,
    render: (r) => <NullableText value={r.correlation_20d !== null ? r.correlation_20d.toFixed(2) : null} />,
    sortValue: (r) => r.correlation_20d,
  },
  { key: "verdict", header: "解釈", render: (r) => r.verdict_ja },
];

export default function MacroPage() {
  const fx = useFx();
  const models = useFxModels();
  const macro = useMacroSeries();
  const rateDiff = useRateDifferential();
  const sensitivity = useFxSensitivity();
  const meta = fx.data?.meta;

  return (
    <>
      <PageHeader
        title="為替・マクロ"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={fx.isFetching && !fx.isPending}
        onRefresh={() => void fx.refetch()}
      />

      <QuerySection label="為替" query={fx} skeleton={<SkeletonChart height="chart-h-lg" />}>
        {(data) => {
          const h20 = data.forecasts.find((f) => f.horizon_days === 20) ?? data.forecasts[0];
          return (
            <div className="space-y-4">
              {/* ベースライン比較の結論を最初に置く */}
              {h20?.verdict_ja ? (
                <Notice tone={h20.beats_baseline ? "info" : "warning"} role="status">
                  <p className="text-body text-fg-primary">{h20.verdict_ja}</p>
                  <p className="text-caption mt-1">
                    DM検定 p={h20.dm_pvalue?.toFixed(2) ?? "—"} · RMSE {h20.rmse_oos_60d?.toFixed(3) ?? "—"} vs
                    ベースライン {h20.baseline_rmse_oos_60d?.toFixed(3) ?? "—"} · 検証{" "}
                    {formatRateWithN(h20.directional_accuracy_60d, h20.n_validation)}
                  </p>
                </Notice>
              ) : null}

              <SectionCard
                title={`${data.pair} の推移`}
                actions={
                  <span className="flex items-baseline gap-2">
                    <span className="num text-metric">{formatJpy(data.spot, 2)}</span>
                    <DirectionValue value={data.change_pct} format="percent" />
                  </span>
                }
              >
                <TimeSeriesChart
                  data={data.history}
                  series={[{ dataKey: "value", label: data.pair }]}
                  height="chart-h-lg"
                  yTickFormatter={(v) => formatJpy(v, 1)}
                  referenceValue={data.spot}
                  referenceLabel="現在値"
                />
                <DelayedPriceNote note={data.spot_note_ja} className="mt-1" />
                <p className="text-caption text-fg-tertiary">公式値の出所: {data.official_source_ja}</p>
                <ChartDataTable
                  caption={`${data.pair} の推移`}
                  headers={["日付", "値"]}
                  rows={data.history.slice(-20).map((p) => [p.date, formatJpy(p.value, 2)])}
                />
              </SectionCard>

              <SectionCard title="予測（すべての期間）" subtitle="点推定は必ず区間と一緒に読んでください">
                <DataTable
                  caption="期間別の為替予測"
                  columns={forecastColumns}
                  rows={data.forecasts}
                  getKey={(r) => `${r.model_id}-${r.horizon_days}`}
                  dense
                />
                <div className="mt-3 grid gap-3 tablet:grid-cols-2">
                  {data.forecasts.map((f) => (
                    <div key={`${f.model_id}-${f.horizon_days}`} className="card-inset p-3">
                      <p className="text-caption text-fg-tertiary">{f.label_ja}先</p>
                      <ForecastValue
                        point={f.point}
                        lo={f.ci_lo_80}
                        hi={f.ci_hi_80}
                        ciLevel={80}
                        format="currency-jpy"
                        precision={2}
                        hitRate={f.directional_accuracy_60d}
                        nSamples={f.n_validation}
                        verdictJa={f.verdict_ja}
                      />
                    </div>
                  ))}
                </div>
              </SectionCard>

              <div className="grid gap-4 desktop:grid-cols-2">
                <SectionCard title="モデル比較（ベースライン含む）">
                  <QuerySection label="モデル比較" query={models} skeleton={<SkeletonTable rows={4} cols={5} />}>
                    {(rows) => (
                      <DataTable
                        caption="為替モデルの比較"
                        columns={modelColumns}
                        rows={rows}
                        getKey={(r) => r.model_id}
                        dense
                      />
                    )}
                  </QuerySection>
                </SectionCard>

                <SectionCard title="ボラティリティと共和分">
                  <dl className="grid grid-cols-2 gap-3">
                    <div>
                      <dt className="text-caption text-fg-tertiary">GARCH予測ボラ（1日・年率）</dt>
                      <dd className="num text-metric-sm">
                        <NullableText
                          value={
                            data.vol_forecast.garch_vol_1d_ann !== null
                              ? formatPctPoint(data.vol_forecast.garch_vol_1d_ann * 100, { precision: 1 })
                              : null
                          }
                        />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">GARCH予測ボラ（20日・年率）</dt>
                      <dd className="num text-metric-sm">
                        <NullableText
                          value={
                            data.vol_forecast.garch_vol_20d_ann !== null
                              ? formatPctPoint(data.vol_forecast.garch_vol_20d_ann * 100, { precision: 1 })
                              : null
                          }
                        />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">持続性（α+β）</dt>
                      <dd className="num text-metric-sm">
                        <NullableText
                          value={data.vol_forecast.persistence !== null ? data.vol_forecast.persistence.toFixed(3) : null}
                        />
                      </dd>
                    </div>
                    <div>
                      <dt className="text-caption text-fg-tertiary">日米金利差（10年）</dt>
                      <dd className="num text-metric-sm">
                        <NullableText value={data.rate_differential.diff !== null ? formatPctPoint(data.rate_differential.diff) : null} />
                      </dd>
                    </div>
                  </dl>
                  <p className="text-caption text-fg-tertiary mt-3">{data.cointegration.note_ja}</p>
                </SectionCard>
              </div>

              <SectionCard title="日米金利差と為替の関係">
                <QuerySection label="金利差" query={rateDiff} skeleton={<SkeletonChart />}>
                  {(points) => (
                    <>
                      <ScatterPlot
                        data={points.map((p) => ({ x: p.diff, y: p.usdjpy }))}
                        xLabel="日米10年金利差（%ポイント）"
                        yLabel="USD/JPY"
                      />
                      <p className="text-caption text-fg-tertiary mt-1">
                        直近60営業日。相関があっても因果とは限りません。
                      </p>
                      <ChartDataTable
                        caption="金利差と為替"
                        headers={["日付", "金利差", "USD/JPY"]}
                        rows={points.slice(-20).map((p) => [p.date, formatPctPoint(p.diff), formatJpy(p.usdjpy, 2)])}
                      />
                    </>
                  )}
                </QuerySection>
              </SectionCard>

              <SectionCard title="マクロ指標（FRED）">
                <QuerySection
                  label="マクロ指標"
                  query={macro}
                  skeleton={<SkeletonTable rows={6} cols={4} />}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "マクロ指標が取得できていません",
                    description: "FRED の API キーが未設定か、取得に失敗しています。設定画面で確認してください。",
                  }}
                >
                  {(rows) => (
                    <DataTable caption="マクロ指標" columns={macroColumns} rows={rows} getKey={(r) => r.id} dense />
                  )}
                </QuerySection>
              </SectionCard>

              <SectionCard title="為替感応度の高い保有・ウォッチ銘柄">
                <QuerySection
                  label="為替感応度"
                  query={sensitivity}
                  skeleton={<SkeletonTable rows={4} cols={6} />}
                  emptyWhen={(rows) => rows.length === 0}
                  empty={{
                    title: "対象の銘柄がありません",
                    description: "保有またはウォッチリストに銘柄を追加すると、為替の影響度が表示されます。",
                  }}
                >
                  {(rows) => (
                    <DataTable
                      caption="為替感応度"
                      columns={sensitivityColumns}
                      rows={rows}
                      getKey={(r) => `${r.market}-${r.ticker}`}
                      getHref={(r) => `/stocks/${r.market}/${r.ticker}`}
                      dense
                    />
                  )}
                </QuerySection>
              </SectionCard>
            </div>
          );
        }}
      </QuerySection>
    </>
  );
}
