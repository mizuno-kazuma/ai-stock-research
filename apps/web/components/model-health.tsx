"use client";

/**
 * モデルの状態とバックテスト結果。
 *
 * バックテストはコスト前提（手数料・スリッページ・回転率上限）を結果より先に描画する。
 * 前提のない成績は解釈できないため、順序自体を仕様にしている。
 * Deflated Sharpe が有意でないものは「有意ではない」と明記する。
 */

import { formatBps, formatPct, formatScore } from "@ai-stock/ui";

import type { Backtest, ModelHealth } from "../lib/api-types";
import { Badge, Card } from "./ui";
import { DirectionValue, NullableText, RateWithN } from "./values";

const HEALTH_LABEL_JA = {
  normal: "正常",
  watch: "注視",
  degraded: "劣化",
  not_trained: "未学習",
} as const;

const HEALTH_TONE = {
  normal: "success",
  watch: "warning",
  degraded: "danger",
  not_trained: "neutral",
} as const;

export function ModelHealthPanel({ health, variant = "full" }: { health: ModelHealth; variant?: "full" | "compact" }) {
  const ic = health.rank_ic_20d;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={HEALTH_TONE[health.status]}>{HEALTH_LABEL_JA[health.status]}</Badge>
        <span className="text-caption text-fg-tertiary">
          Rank IC は「予測順位と実際の順位の相関」です。0.02〜0.05 が実務的な目安です。
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 tablet:grid-cols-4">
        <div>
          <p className="text-caption text-fg-tertiary">Rank IC（20営業日）</p>
          <p className="num text-metric">
            <NullableText value={ic !== null ? ic.toFixed(3) : null} reasonJa="モデルが未学習です" />
          </p>
          <p className="text-caption text-fg-tertiary">
            過去1年の中での位置:{" "}
            <NullableText
              value={health.rank_ic_percentile_1y !== null ? formatPct(health.rank_ic_percentile_1y, { precision: 0 }) : null}
            />
          </p>
        </div>
        <div>
          <p className="text-caption text-fg-tertiary">Rank IC（3ヶ月平均）</p>
          <p className="num text-metric">
            <NullableText value={health.rank_ic_3m != null ? health.rank_ic_3m.toFixed(3) : null} />
          </p>
        </div>
        <div>
          <p className="text-caption text-fg-tertiary">カバレッジ</p>
          <p className="num text-metric">
            <NullableText value={health.coverage_rate !== null ? formatPct(health.coverage_rate, { precision: 1 }) : null} />
          </p>
          <p className="text-caption text-fg-tertiary">
            <NullableText value={health.coverage_detail_ja} />
          </p>
        </div>
        <div>
          <p className="text-caption text-fg-tertiary">特徴量の分布変化</p>
          <p className="num text-metric">
            <NullableText
              value={health.drift_feature_count !== null && health.drift_feature_count !== undefined ? `${health.drift_feature_count}件` : null}
            />
          </p>
        </div>
      </div>

      {health.degradation_note_ja ? (
        <p className="notice notice-warning" role="status">
          {health.degradation_note_ja}
        </p>
      ) : null}

      {variant === "full" && health.coverage_note_ja ? (
        <p className="text-caption text-fg-tertiary">{health.coverage_note_ja}</p>
      ) : null}
    </div>
  );
}

const BT_STATUS = {
  significant: { labelJa: "統計的に有意", tone: "success" },
  not_significant: { labelJa: "有意ではありません", tone: "warning" },
  failed: { labelJa: "失敗", tone: "danger" },
  running: { labelJa: "実行中", tone: "info" },
} as const;

export function BacktestResultCard({ backtest }: { backtest: Backtest }) {
  const status = BT_STATUS[backtest.status];
  return (
    <Card className="p-4">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-h4 text-fg-primary">{backtest.strategy_name}</h3>
          <p className="text-caption text-fg-tertiary num">
            {backtest.period_start} 〜 {backtest.period_end} · {backtest.n_positions}銘柄 ·{" "}
            {backtest.rebalance_freq === "monthly" ? "毎月" : backtest.rebalance_freq === "weekly" ? "毎週" : "四半期"}リバランス
          </p>
        </div>
        <Badge tone={status.tone}>{status.labelJa}</Badge>
      </header>

      {/* コスト前提を結果より先に出す */}
      <div className="card-inset mt-3 p-3">
        <p className="text-caption text-fg-tertiary">コスト前提（この条件での成績です）</p>
        <ul className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 tablet:grid-cols-4">
          <li className="text-body-sm num">
            手数料 <span className="text-fg-primary">{formatBps(backtest.cost.fee_bps)}</span>
          </li>
          <li className="text-body-sm num">
            スリッページ <span className="text-fg-primary">{formatBps(backtest.cost.slippage_bps)}</span>
          </li>
          <li className="text-body-sm num">
            回転率上限{" "}
            <span className="text-fg-primary">{formatPct(backtest.cost.max_turnover_pct, { precision: 0 })}</span>
          </li>
          <li className="text-body-sm">{backtest.cost.pre_tax ? "税引前" : "税引後"}</li>
        </ul>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 tablet:grid-cols-4">
        <Stat label="年率リターン（コスト後）">
          <DirectionValue value={backtest.ann_return} format="percent" precision={1} />
        </Stat>
        <Stat label="シャープレシオ">
          <NullableText value={backtest.sharpe !== null ? formatScore(backtest.sharpe) : null} />
        </Stat>
        <Stat label="Deflated Sharpe">
          <NullableText value={backtest.deflated_sharpe !== null ? backtest.deflated_sharpe.toFixed(2) : null} />
          <span className="text-caption text-fg-tertiary ml-1">
            （試行 {backtest.n_trials ?? "—"}回を考慮）
          </span>
        </Stat>
        <Stat label="最大ドローダウン">
          <DirectionValue value={backtest.max_drawdown} format="percent" precision={1} />
        </Stat>
        <Stat label="勝率">
          <RateWithN rate={backtest.hit_rate} n={backtest.n_trades} />
        </Stat>
        <Stat label="回転率（実績）">
          <NullableText value={backtest.turnover_pct !== null ? formatPct(backtest.turnover_pct, { precision: 0 }) : null} />
        </Stat>
        <Stat label="コスト合計">
          <NullableText value={backtest.total_cost_pct !== null ? formatPct(backtest.total_cost_pct, { precision: 2 }) : null} />
        </Stat>
        <Stat label="情報比率">
          <NullableText value={backtest.information_ratio !== null ? backtest.information_ratio.toFixed(2) : null} />
        </Stat>
      </dl>

      {backtest.status === "not_significant" ? (
        <p className="notice notice-warning mt-3" role="status">
          試行回数を考慮すると、この成績は偶然と区別できません（Deflated Sharpe{" "}
          {backtest.deflated_sharpe?.toFixed(2) ?? "—"}）。運用判断の根拠には使えません。
        </p>
      ) : null}
    </Card>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-fg-tertiary">{label}</dt>
      <dd className="num text-metric-sm mt-0.5">{children}</dd>
    </div>
  );
}
