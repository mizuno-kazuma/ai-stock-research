"use client";

/**
 * 推奨銘柄（docs/ui/screens/02-recommendations.md）。
 *
 * 母集団は当日の推奨カードではなく、スコア済みユニバース。絞り込みは全銘柄に効く。
 * カードがない行でも会社名とスコアは出す。
 */

import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import Link from "next/link";

import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import { RecommendationFeedRow } from "../../components/recommendation-card";
import { QuerySection, SkeletonCards } from "../../components/states";
import { Badge, Chip, SectionCard, SegmentedControl } from "../../components/ui";
import {
  ACTION_LABEL_JA,
  CONVICTION_LABEL_JA,
  CRITIC_VERDICT_LABEL_JA,
  DISPLAY_TIER_LABEL_JA,
} from "../../lib/labels";
import type { Conviction, CriticVerdict, Horizon, RecAction } from "../../lib/api-types";
import { useRecommendations } from "../../lib/queries";

const ACTIONS: RecAction[] = ["watch", "accumulate", "reduce", "avoid"];
const CONVICTIONS: Conviction[] = ["high", "medium", "low"];
const VERDICTS: CriticVerdict[] = ["approved", "revised", "rejected"];
const SCORE_FLOORS = [null, 60, 70, 80] as const;

export default function RecommendationsPage() {
  const prefs = usePrefs();
  const qc = useQueryClient();
  const [horizon, setHorizon] = useState<Horizon>("H20");
  const [action, setAction] = useState<RecAction | null>(null);
  const [conviction, setConviction] = useState<Conviction | null>(null);
  const [verdicts, setVerdicts] = useState<CriticVerdict[]>([]);
  const [sector, setSector] = useState<string | null>(null);
  const [minScore, setMinScore] = useState<number | null>(null);
  const [predSign, setPredSign] = useState<"positive" | "negative" | null>(null);
  const [hasCard, setHasCard] = useState<boolean | null>(null);

  const params = useMemo(
    () => ({
      market: prefs.market,
      horizon,
      ...(action ? { action } : {}),
      ...(conviction ? { conviction } : {}),
      ...(verdicts.length ? { critic_verdict: verdicts.join(",") } : {}),
      ...(sector ? { sector } : {}),
      ...(minScore != null ? { min_score: minScore } : {}),
      ...(predSign ? { pred_sign: predSign } : {}),
      ...(hasCard == null ? {} : { has_card: hasCard }),
      include_rejected: true,
      limit: 50,
    }),
    [prefs.market, horizon, action, conviction, verdicts, sector, minScore, predSign, hasCard],
  );

  const query = useRecommendations(params);
  const meta = query.data?.meta;
  const data = query.data?.data;

  const toggleVerdict = (v: CriticVerdict) =>
    setVerdicts((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));

  const sectors = useMemo(() => {
    const names = new Set<string>();
    if (sector) names.add(sector);
    for (const row of data?.items ?? []) {
      if (row.sector_name) names.add(row.sector_name);
    }
    return [...names].sort((a, b) => a.localeCompare(b, "ja"));
  }, [data?.items, sector]);

  const resetFilters = () => {
    setAction(null);
    setConviction(null);
    setVerdicts([]);
    setSector(null);
    setMinScore(null);
    setPredSign(null);
    setHasCard(null);
  };

  return (
    <>
      <PageHeader
        title="推奨銘柄"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={query.isFetching && !query.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["recommendations"] })}
        description="スコア済みの全銘柄から絞り込みます。推奨カードがある銘柄はレビュー結果も併記します。"
        actions={
          <SegmentedControl
            label="予測期間"
            value={horizon}
            onChange={setHorizon}
            options={[
              { value: "H5", label: "5営業日" },
              { value: "H20", label: "20営業日" },
            ]}
          />
        }
      />

      <SectionCard title="絞り込み" bodyClassName="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">セクター</span>
          <Chip selected={sector === null} onClick={() => setSector(null)}>
            すべて
          </Chip>
          {sectors.map((name) => (
            <Chip key={name} selected={sector === name} onClick={() => setSector(name)}>
              {name}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">スコア</span>
          {SCORE_FLOORS.map((n) => (
            <Chip key={String(n)} selected={minScore === n} onClick={() => setMinScore(n)}>
              {n == null ? "すべて" : `${n}以上`}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">予測符号</span>
          <Chip selected={predSign === null} onClick={() => setPredSign(null)}>
            すべて
          </Chip>
          <Chip selected={predSign === "positive"} onClick={() => setPredSign("positive")}>
            超過リターン正
          </Chip>
          <Chip selected={predSign === "negative"} onClick={() => setPredSign("negative")}>
            超過リターン負
          </Chip>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">カード</span>
          <Chip selected={hasCard === null} onClick={() => setHasCard(null)}>
            すべて
          </Chip>
          <Chip selected={hasCard === true} onClick={() => setHasCard(true)}>
            推奨カードあり
          </Chip>
          <Chip selected={hasCard === false} onClick={() => setHasCard(false)}>
            定量のみ
          </Chip>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">行動</span>
          <Chip selected={action === null} onClick={() => setAction(null)}>
            すべて
          </Chip>
          {ACTIONS.map((a) => (
            <Chip key={a} selected={action === a} onClick={() => setAction(a)}>
              {ACTION_LABEL_JA[a]}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">確信度</span>
          <Chip selected={conviction === null} onClick={() => setConviction(null)}>
            すべて
          </Chip>
          {CONVICTIONS.map((c) => (
            <Chip key={c} selected={conviction === c} onClick={() => setConviction(c)}>
              {CONVICTION_LABEL_JA[c]}
            </Chip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-fg-tertiary w-20">レビュー</span>
          {VERDICTS.map((v) => (
            <Chip key={v} selected={verdicts.includes(v)} onClick={() => toggleVerdict(v)}>
              {CRITIC_VERDICT_LABEL_JA[v]}
            </Chip>
          ))}
          <span className="text-caption text-fg-tertiary">
            未選択ならレビュー前・却下・定量のみも表示します
          </span>
        </div>
        <button type="button" className="btn btn-ghost" onClick={resetFilters}>
          条件をリセット
        </button>
      </SectionCard>

      <div className="mt-4">
        <QuerySection
          label="銘柄一覧"
          query={query}
          section="recommendations"
          skeleton={<SkeletonCards count={3} />}
          emptyWhen={(payload) => payload.items.length === 0}
          empty={{
            title: "条件に一致する銘柄がありません",
            description: "絞り込みを緩めるか、条件をリセットしてください。スコアが未計算の日はバッチ完了を待ってください。",
            action: (
              <button type="button" className="btn btn-secondary" onClick={resetFilters}>
                条件をリセット
              </button>
            ),
          }}
        >
          {(payload) => {
            const items = payload.items;
            return (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-body-sm text-fg-secondary num">
                    {payload.total}件 / {payload.universe_size}銘柄
                  </span>
                  {(["core", "fill", "score_only"] as const).map((tier) => {
                    const n = items.filter((r) => r.display_tier === tier).length;
                    if (n === 0) return null;
                    return (
                      <Badge key={tier} tone="neutral">
                        {DISPLAY_TIER_LABEL_JA[tier]} {n}
                      </Badge>
                    );
                  })}
                </div>
                {items.map((item) => (
                  <RecommendationFeedRow
                    key={item.rec_id ?? `${item.market}:${item.ticker}`}
                    item={item}
                  />
                ))}
                <p className="text-caption text-fg-tertiary">
                  <Link href="/screener" className="text-accent">
                    条件を細かく組み立てる場合はスクリーナーへ
                  </Link>
                </p>
              </div>
            );
          }}
        </QuerySection>
      </div>
    </>
  );
}
