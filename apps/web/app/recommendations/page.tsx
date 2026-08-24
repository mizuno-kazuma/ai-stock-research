"use client";

/**
 * 推奨銘柄（docs/ui/screens/02-recommendations.md）。
 *
 * 却下された候補も「なぜ却下したか」とともに見られるようにする。承認だけを見せると
 * ツールが常に自信を持っているように見えてしまう。
 */

import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import Link from "next/link";

import { PageHeader } from "../../components/page-header";
import { usePrefs } from "../../components/prefs";
import { RecommendationCard } from "../../components/recommendation-card";
import { EmptyState, QuerySection, SkeletonCards } from "../../components/states";
import { Badge, Chip, SectionCard, SegmentedControl } from "../../components/ui";
import {
  ACTION_LABEL_JA,
  ACTION_TONE,
  CONVICTION_LABEL_JA,
  CRITIC_VERDICT_LABEL_JA,
} from "../../lib/labels";
import type { Conviction, CriticVerdict, Horizon, RecAction } from "../../lib/api-types";
import { useRecommendations } from "../../lib/queries";

const ACTIONS: RecAction[] = ["watch", "accumulate", "reduce", "avoid"];
const CONVICTIONS: Conviction[] = ["high", "medium", "low"];
const VERDICTS: CriticVerdict[] = ["approved", "revised", "rejected"];

export default function RecommendationsPage() {
  const prefs = usePrefs();
  const qc = useQueryClient();
  const [horizon, setHorizon] = useState<Horizon>("H20");
  const [action, setAction] = useState<RecAction | null>(null);
  const [conviction, setConviction] = useState<Conviction | null>(null);
  const [verdicts, setVerdicts] = useState<CriticVerdict[]>(["approved", "revised"]);

  const params = useMemo(
    () => ({
      market: prefs.market,
      horizon,
      ...(action ? { action } : {}),
      ...(conviction ? { conviction } : {}),
    }),
    [prefs.market, horizon, action, conviction],
  );

  const query = useRecommendations(params);
  const meta = query.data?.meta;

  const toggleVerdict = (v: CriticVerdict) =>
    setVerdicts((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));

  return (
    <>
      <PageHeader
        title="推奨銘柄"
        asOf={meta?.as_of}
        computedAt={meta?.computed_at}
        refreshing={query.isFetching && !query.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["recommendations"] })}
        description="各推奨には弱気の論拠と無効化条件が必ず付いています。判断は利用者が行います。"
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
            却下された候補も理由つきで確認できます
          </span>
        </div>
      </SectionCard>

      <div className="mt-4">
        <QuerySection
          label="推奨一覧"
          query={query}
          section="recommendations"
          skeleton={<SkeletonCards count={3} />}
          emptyWhen={(data) => data.items.length === 0}
          empty={{
            title: "この条件の推奨はありません",
            description:
              "絞り込みを緩めるか、期間を20営業日に変えてみてください。当日のバッチが未完了の場合もあります。",
            action: (
              <Link href="/agent" className="btn btn-secondary">
                バッチの状況を見る
              </Link>
            ),
          }}
        >
          {(data) => {
            const items = data.items.filter(
              (r): r is typeof r & { critic_verdict: CriticVerdict } =>
                r.critic_verdict != null && verdicts.includes(r.critic_verdict),
            );
            if (items.length === 0) {
              return (
                <EmptyState
                  title="表示できる推奨がありません"
                  description="レビュー状態の絞り込みですべて除外されています。「却下」を含めると内容を確認できます。"
                />
              );
            }
            return (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-body-sm text-fg-secondary num">{items.length}件</span>
                  {meta?.excluded_count ? (
                    <Badge tone="neutral">除外 {meta.excluded_count}件</Badge>
                  ) : null}
                  {ACTIONS.map((a) => {
                    const n = items.filter((r) => r.action === a).length;
                    if (n === 0) return null;
                    return (
                      <Badge key={a} tone={ACTION_TONE[a]}>
                        {ACTION_LABEL_JA[a]} {n}
                      </Badge>
                    );
                  })}
                </div>
                {items.map((rec) => (
                  <RecommendationCard key={rec.rec_id} rec={rec} />
                ))}
              </div>
            );
          }}
        </QuerySection>
      </div>
    </>
  );
}
