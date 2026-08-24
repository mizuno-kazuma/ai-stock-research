"use client";

/**
 * スクリーナー（docs/ui/screens/04-screener.md）。
 *
 * 条件は「フィールド・演算子・値」の3点で組み立てる。母集団の件数と除外件数を常に出し、
 * 何件のうち何件が残ったのかが分かるようにする。
 */

import { useMemo, useState } from "react";
import { Plus, RotateCcw, Trash2 } from "lucide-react";
import { formatJpy, formatMultiple, formatPct, formatUsd } from "@ai-stock/ui";

import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import { QuerySection, SkeletonTable } from "../../components/states";
import { DataTable, type Column } from "../../components/table";
import { Badge, Button, Chip, SectionCard } from "../../components/ui";
import { DirectionValue, ForecastCell, NullableText, ScoreBadge, ZValue } from "../../components/values";
import { reasonCodeLabel, reasonCodeTone } from "../../lib/labels";
import type { FilterOp, ScreenerFilter, ScreenerRequest, ScreenerRow } from "../../lib/api-types";
import { useScreener, useScreenerFields, useScreenerPresets } from "../../lib/queries";

const OP_LABEL_JA: Partial<Record<FilterOp, string>> = {
  gte: "以上",
  lte: "以下",
  gt: "より大きい",
  lt: "より小さい",
  eq: "に等しい",
  ne: "に等しくない",
  is_null: "が欠損",
  is_not_null: "が存在する",
};

const columns: Array<Column<ScreenerRow>> = [
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
  { key: "sector", header: "セクター", render: (r) => r.sector_name, sortValue: (r) => r.sector_name },
  {
    key: "score",
    header: "スコア",
    numeric: true,
    render: (r) => <ScoreBadge score={r.quant_score} size="sm" />,
    sortValue: (r) => r.quant_score,
  },
  {
    key: "price",
    header: "参考価格",
    numeric: true,
    render: (r) => <NullableText value={r.currency === "JPY" ? formatJpy(r.ref_price) : formatUsd(r.ref_price)} />,
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
    key: "pred",
    header: "予測（20営業日）",
    numeric: true,
    headerHint: "点推定と80%信頼区間",
    render: (r) => <ForecastCell point={r.ml_pred_h20} lo={r.ml_pred_h20_lo} hi={r.ml_pred_h20_hi} />,
    sortValue: (r) => r.ml_pred_h20,
  },
  {
    key: "per",
    header: "PER",
    numeric: true,
    headerHint: "赤字企業は算出できないため — になります",
    render: (r) => (
      <NullableText
        value={r.per !== null ? formatMultiple(r.per) : null}
        reasonJa="純利益が負のため算出できません"
      />
    ),
    sortValue: (r) => r.per,
  },
  {
    key: "roic",
    header: "ROIC",
    numeric: true,
    render: (r) => <NullableText value={r.roic !== null ? formatPct(r.roic, { precision: 1 }) : null} />,
    sortValue: (r) => r.roic,
  },
  {
    key: "mom",
    header: "12ヶ月",
    numeric: true,
    render: (r) => <DirectionValue value={r.mom_12m} format="percent" precision={1} />,
    sortValue: (r) => r.mom_12m,
  },
  {
    key: "value_z",
    header: "割安 z",
    numeric: true,
    hideOnCard: true,
    render: (r) => <ZValue value={r.value_z} />,
    sortValue: (r) => r.value_z,
  },
  {
    key: "earnings",
    header: "決算",
    numeric: true,
    render: (r) => (
      <NullableText value={r.next_earnings_in_days !== null ? `${r.next_earnings_in_days}営業日後` : null} />
    ),
    sortValue: (r) => r.next_earnings_in_days,
  },
  {
    key: "reasons",
    header: "特徴",
    hideOnTable: true,
    render: (r) => (
      <span className="flex flex-wrap gap-1">
        {r.reason_codes.map((c) => (
          <Chip key={c} tone={reasonCodeTone(c)}>
            {reasonCodeLabel(c)}
          </Chip>
        ))}
      </span>
    ),
  },
];

const DEFAULT_FILTERS: ScreenerFilter[] = [{ field: "quant_score", op: "gte", value: 60 }];

export default function ScreenerPage() {
  const prefs = usePrefs();
  const [filters, setFilters] = useState<ScreenerFilter[]>(DEFAULT_FILTERS);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const fields = useScreenerFields();
  const presets = useScreenerPresets();

  const request: ScreenerRequest = useMemo(
    () => ({
      market: prefs.market,
      filters,
      sort: [{ field: "quant_score", dir: "desc" }],
      limit: 100,
    }),
    [prefs.market, filters],
  );

  const query = useScreener(request);
  const meta = query.data?.meta;
  const fieldList = fields.data?.data ?? [];

  const updateFilter = (index: number, patch: Partial<ScreenerFilter>) =>
    setFilters((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));

  const addFilter = () =>
    setFilters((prev) => [...prev, { field: fieldList[0]?.key ?? "quant_score", op: "gte", value: 0 }]);

  return (
    <>
      <PageHeader
        title="スクリーナー"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={query.isFetching && !query.isPending}
        onRefresh={() => void query.refetch()}
        description="条件に合う銘柄を絞り込みます。スコアは順位づけの材料で、売買の指示ではありません。"
      />

      <SectionCard
        title="条件"
        subtitle={
          meta?.total_matched !== undefined
            ? `母集団 ${meta.total ?? "—"}銘柄中 ${meta.total_matched}銘柄が該当`
            : undefined
        }
        actions={
          <>
            <Button variant="ghost" onClick={() => { setFilters(DEFAULT_FILTERS); setActivePreset(null); }}>
              <RotateCcw size={13} aria-hidden="true" />
              初期化
            </Button>
            <Button variant="secondary" onClick={addFilter}>
              <Plus size={13} aria-hidden="true" />
              条件を追加
            </Button>
          </>
        }
        bodyClassName="space-y-3"
      >
        <div className="flex flex-wrap gap-2">
          {(presets.data?.data ?? []).map((p) => (
            <Chip
              key={p.id}
              selected={activePreset === p.id}
              tone={p.is_cautionary ? "warning" : undefined}
              title={p.description_ja ?? undefined}
              onClick={() => {
                setFilters(p.filters);
                setActivePreset(p.id);
              }}
            >
              {p.label_ja}
            </Chip>
          ))}
        </div>

        {activePreset && presets.data?.data.find((p) => p.id === activePreset)?.is_cautionary ? (
          <p className="notice notice-warning" role="status">
            {presets.data.data.find((p) => p.id === activePreset)?.description_ja}
          </p>
        ) : null}

        <ul className="space-y-2">
          {filters.map((f, i) => {
            const field = fieldList.find((x) => x.key === f.field);
            const needsValue = f.op !== "is_null" && f.op !== "is_not_null";
            return (
              <li key={`${f.field}-${i}`} className="flex flex-wrap items-center gap-2">
                <select
                  className="input tablet:w-56"
                  value={f.field}
                  onChange={(e) => updateFilter(i, { field: e.target.value })}
                  aria-label="条件のフィールド"
                >
                  {fieldList.length === 0 ? <option value={f.field}>{f.field}</option> : null}
                  {fieldList.map((x) => (
                    <option key={x.key} value={x.key}>
                      {x.label_ja}
                    </option>
                  ))}
                </select>
                <select
                  className="input tablet:w-36"
                  value={f.op}
                  onChange={(e) => updateFilter(i, { op: e.target.value as FilterOp })}
                  aria-label="条件の演算子"
                >
                  {(field?.ops ?? (["gte", "lte", "eq"] as FilterOp[])).map((op) => (
                    <option key={op} value={op}>
                      {OP_LABEL_JA[op] ?? op}
                    </option>
                  ))}
                </select>
                {needsValue ? (
                  <input
                    className="input input-numeric tablet:w-32"
                    inputMode="decimal"
                    value={typeof f.value === "number" || typeof f.value === "string" ? String(f.value) : ""}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const num = Number(raw);
                      updateFilter(i, { value: raw === "" ? null : Number.isNaN(num) ? raw : num });
                    }}
                    aria-label="条件の値"
                  />
                ) : null}
                {field?.unit ? <span className="text-caption text-fg-tertiary">{field.unit}</span> : null}
                <Button
                  variant="ghost"
                  onClick={() => setFilters((prev) => prev.filter((_, idx) => idx !== i))}
                  ariaLabel="この条件を削除"
                >
                  <Trash2 size={13} aria-hidden="true" />
                </Button>
                {field?.tooltip_ja ? (
                  <span className="text-caption text-fg-tertiary">{field.tooltip_ja}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      </SectionCard>

      <div className="mt-4">
        <QuerySection
          label="スクリーニング結果"
          query={query}
          skeleton={<SkeletonTable rows={8} cols={7} />}
          emptyWhen={(data) => data.rows.length === 0}
          empty={{
            title: "条件に一致する銘柄がありません",
            description:
              "条件が厳しすぎる可能性があります。スコアの下限を下げる、または PER の上限を緩めると候補が出ます。",
          }}
        >
          {(data) => (
            <SectionCard
              title="結果"
              subtitle={`${data.rows.length}件 / 母集団 ${data.universe_size}銘柄`}
              actions={
                meta?.truncated ? <Badge tone="warning">上限まで表示しています</Badge> : null
              }
            >
              <DataTable
                caption="スクリーニング結果"
                columns={columns}
                rows={data.rows}
                getKey={(r) => `${r.market}-${r.ticker}`}
                getHref={(r) => `/stocks/${r.market}/${r.ticker}`}
                initialSort={{ key: "score", dir: "desc" }}
                cardSubtitle={(r) => r.sector_name}
                dense
              />
              <p className="text-caption text-fg-tertiary mt-3">
                参考価格は約15分遅延で、約定価格ではありません。PER が「—」の銘柄は純利益が負で算出できないものです（0倍ではありません）。
              </p>
            </SectionCard>
          )}
        </QuerySection>
      </div>
    </>
  );
}
