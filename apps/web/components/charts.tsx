"use client";

/**
 * Recharts のラッパ。色は必ず CSS 変数（--chart-*, --dir-*）を参照する。
 * ここでも 16 進カラーは書かない。テーマと方向色の切替がそのまま図に反映される。
 *
 * 高さは chart-h-sm / md / lg（tokens.css）で段階的に縮む。横スクロールはさせない。
 * 数値のアニメーションは全図で無効（読み取り中に値が動くと誤読の原因になる）。
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { cx } from "./ui";

const AXIS_STYLE = { fill: "var(--chart-axis)", fontSize: 11 } as const;
const GRID_COLOR = "var(--chart-grid)";

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "var(--bg-surface-raised)",
    border: "1px solid var(--border-default)",
    borderRadius: "8px",
    fontSize: "12px",
    color: "var(--fg-primary)",
  },
  labelStyle: { color: "var(--fg-secondary)" },
  itemStyle: { color: "var(--fg-primary)" },
} as const;

/** 一覧の行に埋め込む極小の折れ線。軸も凡例も出さない */
export function Sparkline({
  data,
  dataKey = "value",
  tone = "chart-1",
}: {
  data: Array<Record<string, number | string>>;
  dataKey?: string;
  tone?: "chart-1" | "dir-up" | "dir-down";
}) {
  return (
    <div className="spark-h w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 2, left: 0 }}>
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={`var(--${tone})`}
            fill={`var(--${tone})`}
            fillOpacity={0.12}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export interface SeriesDef {
  dataKey: string;
  label: string;
  color?: string;
  dashed?: boolean;
}

/** 時系列の折れ線。ベースライン系列は破線 + baseline 色で描く */
export function TimeSeriesChart({
  data,
  series,
  xKey = "date",
  height = "chart-h-md",
  yTickFormatter,
  referenceValue,
  referenceLabel,
}: {
  data: Array<Record<string, number | string | null>>;
  series: SeriesDef[];
  xKey?: string;
  height?: string;
  yTickFormatter?: (value: number) => string;
  referenceValue?: number;
  referenceLabel?: string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey={xKey} tick={AXIS_STYLE} stroke={GRID_COLOR} minTickGap={48} />
          <YAxis
            tick={AXIS_STYLE}
            stroke={GRID_COLOR}
            width={56}
            tickFormatter={yTickFormatter}
            domain={["auto", "auto"]}
          />
          <Tooltip {...TOOLTIP_STYLE} />
          {referenceValue !== undefined ? (
            <ReferenceLine
              y={referenceValue}
              stroke="var(--chart-baseline)"
              strokeDasharray="4 4"
              label={{ value: referenceLabel, fill: "var(--chart-axis)", fontSize: 11, position: "right" }}
            />
          ) : null}
          {series.map((s, i) => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.label}
              stroke={s.color ?? `var(--chart-${(i % 5) + 1})`}
              strokeDasharray={s.dashed ? "4 4" : undefined}
              strokeWidth={1.8}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 予測の帯（80% / 95%）つきの時系列。実績と予測を1つの図に重ねる */
export function ForecastBandChart({
  data,
  height = "chart-h-md",
}: {
  data: Array<{
    date: string;
    actual?: number | null;
    point?: number | null;
    band80?: [number, number] | null;
    band95?: [number, number] | null;
  }>;
  height?: string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey="date" tick={AXIS_STYLE} stroke={GRID_COLOR} minTickGap={48} />
          <YAxis tick={AXIS_STYLE} stroke={GRID_COLOR} width={56} domain={["auto", "auto"]} />
          <Tooltip {...TOOLTIP_STYLE} />
          <Area
            dataKey="band95"
            stroke="none"
            fill="var(--chart-ci-95)"
            isAnimationActive={false}
            name="95%区間"
          />
          <Area
            dataKey="band80"
            stroke="none"
            fill="var(--chart-ci-80)"
            isAnimationActive={false}
            name="80%区間"
          />
          <Line
            type="monotone"
            dataKey="actual"
            name="実績"
            stroke="var(--chart-1)"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="point"
            name="予測（中央値）"
            stroke="var(--chart-2)"
            strokeDasharray="4 4"
            strokeWidth={1.8}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 横棒。特徴量重要度など、ラベルが長いものに使う */
export function HorizontalBarChart({
  data,
  height = "chart-h-lg",
  valueFormatter,
}: {
  data: Array<{ label: string; value: number }>;
  height?: string;
  valueFormatter?: (v: number) => string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid stroke={GRID_COLOR} horizontal={false} />
          <XAxis type="number" tick={AXIS_STYLE} stroke={GRID_COLOR} tickFormatter={valueFormatter} />
          <YAxis type="category" dataKey="label" tick={AXIS_STYLE} stroke={GRID_COLOR} width={168} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => valueFormatter?.(v) ?? v} />
          <Bar dataKey="value" fill="var(--chart-1)" isAnimationActive={false} radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 縦棒。正負で方向色を切り替える（分位別リターンなど） */
export function SignedBarChart({
  data,
  height = "chart-h-md",
  valueFormatter,
}: {
  data: Array<{ label: string; value: number }>;
  height?: string;
  valueFormatter?: (v: number) => string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey="label" tick={AXIS_STYLE} stroke={GRID_COLOR} />
          <YAxis tick={AXIS_STYLE} stroke={GRID_COLOR} width={56} tickFormatter={valueFormatter} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => valueFormatter?.(v) ?? v} />
          <ReferenceLine y={0} stroke="var(--chart-baseline)" />
          <Bar dataKey="value" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.label} fill={d.value >= 0 ? "var(--dir-up)" : "var(--dir-down)"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 日次の指標（棒）と移動平均（線）の重ね描き。Rank IC の推移に使う */
export function BarWithLineChart({
  data,
  barKey,
  lineKey,
  barLabel,
  lineLabel,
  height = "chart-h-md",
  valueFormatter,
}: {
  data: Array<Record<string, number | string | null>>;
  barKey: string;
  lineKey: string;
  barLabel: string;
  lineLabel: string;
  height?: string;
  valueFormatter?: (v: number) => string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey="date" tick={AXIS_STYLE} stroke={GRID_COLOR} minTickGap={48} />
          <YAxis tick={AXIS_STYLE} stroke={GRID_COLOR} width={56} tickFormatter={valueFormatter} />
          <Tooltip {...TOOLTIP_STYLE} formatter={(v: number) => valueFormatter?.(v) ?? v} />
          <ReferenceLine y={0} stroke="var(--chart-baseline)" />
          <Bar dataKey={barKey} name={barLabel} fill="var(--chart-1)" isAnimationActive={false} opacity={0.5} />
          <Line
            type="monotone"
            dataKey={lineKey}
            name={lineLabel}
            stroke="var(--chart-2)"
            strokeWidth={1.8}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** 散布図。金利差と為替の関係など */
export function ScatterPlot({
  data,
  xLabel,
  yLabel,
  height = "chart-h-md",
}: {
  data: Array<{ x: number; y: number }>;
  xLabel: string;
  yLabel: string;
  height?: string;
}) {
  return (
    <div className={cx("w-full", height)}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
          <CartesianGrid stroke={GRID_COLOR} />
          <XAxis
            type="number"
            dataKey="x"
            name={xLabel}
            tick={AXIS_STYLE}
            stroke={GRID_COLOR}
            domain={["auto", "auto"]}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={yLabel}
            tick={AXIS_STYLE}
            stroke={GRID_COLOR}
            width={56}
            domain={["auto", "auto"]}
          />
          <Tooltip {...TOOLTIP_STYLE} />
          <Scatter data={data} fill="var(--chart-1)" isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
