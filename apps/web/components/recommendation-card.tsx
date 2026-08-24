"use client";

/**
 * 推奨カード。docs/ui/screens/02-recommendations.md と components.md §4.1 に対応。
 *
 * 仕様上の必須要件をこのコンポーネントで構造的に担保している:
 * - 弱気論拠は強気論拠と同じ字送り・同じ余白で常に表示する。折りたたみ制御を持たない。
 * - 期待収益率は必ず信頼区間つき（ForecastValue が区間を必須にしている）。
 * - 的中率は必ず母数つき（RateWithN）。
 * - 参考価格には遅延と「約定価格ではない」旨を添える。
 * - 売買の指示や執行の導線は置かない。行動ラベルは「注目 / 積み増し検討 / 縮小検討 / 回避」。
 */

import Link from "next/link";
import { ExternalLink, FileText } from "lucide-react";
import {
  formatDateIso,
  formatJpy,
  formatNumeric,
  formatPct,
  formatUsd,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import type { Citation, FactorDetail, RecommendationCard as RecCard } from "../lib/api-types";
import {
  ACTION_LABEL_JA,
  ACTION_TONE,
  CITATION_STATUS_LABEL_JA,
  CITATION_STATUS_STYLE,
  CRITIC_VERDICT_LABEL_JA,
  CRITIC_VERDICT_TONE,
  HORIZON_LABEL_JA,
  MARKET_LABEL_JA,
  reasonCodeLabel,
  reasonCodeTone,
} from "../lib/labels";
import { Badge, Card, Chip } from "./ui";
import { ConvictionBadge, DirectionValue, ForecastValue, NullableText, ScoreBadge, ZValue } from "./values";
import { FreshnessBadge } from "./states";

const price = (value: number | null | undefined, currency: string | null | undefined) =>
  currency === "JPY" ? formatJpy(value) : formatUsd(value);

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <p className="text-body-sm text-fg-tertiary">
        引用はありません。論拠は定量指標のみに基づいています。
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {citations.map((c, i) => {
        const status = c.verification ?? "unverified";
        return (
          <li key={`${c.doc_id}-${c.page}-${i}`} className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-caption text-fg-tertiary num">{formatDateIso(c.filed_at ?? null)}</span>
              {c.title ? (
                <Link
                  href={`/filings?doc=${c.doc_id}#page=${c.page}`}
                  className="text-body-sm text-accent inline-flex items-center gap-1"
                >
                  <FileText size={12} aria-hidden="true" />
                  {c.title}
                </Link>
              ) : null}
              <span className="text-caption text-fg-tertiary num">p.{c.page}</span>
              <Badge tone={CITATION_STATUS_STYLE[status] ?? "neutral"}>
                {CITATION_STATUS_LABEL_JA[status] ?? status}
              </Badge>
            </div>
            <blockquote className="quote-block mt-1 prose-block">{c.quote}</blockquote>
          </li>
        );
      })}
    </ul>
  );
}

export function FactorTable({ factors }: { factors: FactorDetail[] }) {
  if (factors.length === 0) {
    return <p className="text-body-sm text-fg-tertiary">この銘柄のファクター内訳はまだ計算されていません。</p>;
  }
  return (
    <table className="data-table data-table--dense">
      <caption className="visually-hidden">ファクター別のスコア内訳</caption>
      <thead>
        <tr>
          <th scope="col">ファクター</th>
          <th scope="col" className="is-numeric">
            z値
          </th>
          <th scope="col" className="is-numeric">
            順位
          </th>
          <th scope="col" className="is-numeric">
            実数
          </th>
        </tr>
      </thead>
      <tbody>
        {factors.map((f) => (
          <tr key={f.key}>
            <td>{f.label_ja}</td>
            <td className="is-numeric">
              <ZValue value={f.z} />
            </td>
            <td className="is-numeric">
              <NullableText value={f.percentile_ja} />
            </td>
            <td className="is-numeric">
              <NullableText value={f.raw_ja} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export interface RecommendationCardProps {
  rec: RecCard;
  /** 一覧では compact。compact でも弱気論拠のプレビュー行は必ず出す */
  variant?: "full" | "compact";
}

export function RecommendationCard({ rec, variant = "full" }: RecommendationCardProps) {
  const compact = variant === "compact";
  const stockHref = `/stocks/${rec.market}/${rec.ticker}`;

  return (
    <Card as="article" className="p-4 tablet:p-5 min-w-0">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={stockHref} className="text-h3 text-fg-primary hover:text-accent">
              <span className="num mr-2 text-fg-secondary">{rec.ticker}</span>
              {rec.name_local}
            </Link>
            <Badge tone="neutral">{MARKET_LABEL_JA[rec.market]}</Badge>
          </div>
          <p className="text-caption text-fg-tertiary mt-0.5">
            {rec.sector_name} · {HORIZON_LABEL_JA[rec.horizon]} · 生成日 {formatDateIso(rec.as_of)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={ACTION_TONE[rec.action]}>{ACTION_LABEL_JA[rec.action]}</Badge>
          <ConvictionBadge conviction={rec.conviction} />
          {rec.critic_verdict ? (
            <Badge tone={CRITIC_VERDICT_TONE[rec.critic_verdict]}>
              レビュー: {CRITIC_VERDICT_LABEL_JA[rec.critic_verdict]}
            </Badge>
          ) : null}
        </div>
      </header>

      {/* スコアと期待収益 */}
      <div className="mt-4 grid gap-4 tablet:grid-cols-3">
        <div>
          <p className="text-caption text-fg-tertiary">定量スコア</p>
          <div className="mt-1 flex items-center gap-2">
            <ScoreBadge score={rec.quant_score} size="lg" />
            <span className="text-caption text-fg-tertiary">
              {rec.quant_rank != null ? `${rec.quant_rank}位` : NULL_PLACEHOLDER} ·{" "}
              {rec.quant_percentile != null ? `上位 ${formatPct(1 - rec.quant_percentile, { precision: 0 })}` : NULL_PLACEHOLDER}
            </span>
          </div>
          <p className="text-caption text-fg-tertiary mt-1">
            定性調整{" "}
            <DirectionValue value={rec.qual_score != null ? rec.qual_score / 100 : null} format="percent" precision={1} />
            {rec.qual_doc_count != null ? `（資料 ${rec.qual_doc_count}件）` : null}
          </p>
        </div>

        <div className="tablet:col-span-2">
          <p className="text-caption text-fg-tertiary">期待収益率（{HORIZON_LABEL_JA[rec.horizon]}）</p>
          <ForecastValue
            point={rec.expected_ret}
            lo={rec.expected_ret_lo}
            hi={rec.expected_ret_hi}
            ciLevel={rec.ci_level ?? 80}
            hitRate={rec.hit_rate_prior}
            nSamples={rec.n_prior_samples}
            className="mt-1"
          />
        </div>
      </div>

      {/* 理由コード */}
      <div className="mt-4 flex flex-wrap gap-1.5">
        {rec.reason_codes.map((code) => (
          <Chip key={code} tone={reasonCodeTone(code)}>
            {reasonCodeLabel(code)}
          </Chip>
        ))}
      </div>

      {/* 論拠。強気と弱気を同じ見た目で並べる（弱気を目立たなくしない） */}
      <div className="mt-4 space-y-2">
        <section>
          <h3 className="text-h4 text-fg-primary">強気の論拠</h3>
          <p className="argument-panel argument-panel--thesis mt-1">{rec.thesis_ja}</p>
        </section>
        <section>
          <h3 className="text-h4 text-fg-primary">弱気の論拠</h3>
          <p className="argument-panel argument-panel--bear mt-1">{rec.bear_case_ja}</p>
        </section>
        <section>
          <h3 className="text-h4 text-fg-primary">無効化条件</h3>
          <p className="argument-panel argument-panel--invalidation mt-1">{rec.invalidation_ja}</p>
        </section>
      </div>

      {/* 参考価格。遅延と用途の注意を必ず添える */}
      <div className="mt-4 card-inset p-3">
        <div className="grid grid-cols-2 gap-3 tablet:grid-cols-4">
          <div>
            <p className="text-caption text-fg-tertiary">参考価格</p>
            <p className="num text-metric-sm">{price(rec.entry_ref_price, rec.currency)}</p>
          </div>
          <div>
            <p className="text-caption text-fg-tertiary">参考目標値</p>
            <p className="num text-metric-sm">
              <NullableText value={rec.target_ref_price !== null ? price(rec.target_ref_price, rec.currency) : null} />
            </p>
          </div>
          <div>
            <p className="text-caption text-fg-tertiary">参考撤退値</p>
            <p className="num text-metric-sm">
              <NullableText value={rec.stop_ref_price != null ? price(rec.stop_ref_price, rec.currency) : null} />
            </p>
          </div>
          <div>
            <p className="text-caption text-fg-tertiary">参考比率の目安</p>
            <p className="num text-metric-sm">
              <NullableText
                value={rec.suggested_size_pct !== null ? formatPct(rec.suggested_size_pct, { precision: 1 }) : null}
                reasonJa="確信度が低いため比率の目安は提示していません"
              />
            </p>
          </div>
        </div>
        <p className="text-caption text-fg-tertiary mt-2">
          {rec.entry_ref_note_ja}（出所 {rec.entry_ref_source}）· これらは判断の目安で、約定価格や執行の指示ではありません
        </p>
      </div>

      {!compact ? (
        <>
          <div className="mt-4 grid gap-4 desktop:grid-cols-2">
            <section>
              <h3 className="text-h4 text-fg-primary mb-2">ファクター内訳</h3>
              <FactorTable factors={rec.factor_details ?? []} />
            </section>
            <section>
              <h3 className="text-h4 text-fg-primary mb-2">引用（原文）</h3>
              <CitationList citations={rec.citations} />
            </section>
          </div>

          {rec.critic_notes_ja ? (
            <section className="mt-4">
              <h3 className="text-h4 text-fg-primary">レビューの指摘</h3>
              <p className="argument-panel mt-1">{rec.critic_notes_ja}</p>
            </section>
          ) : null}
        </>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Link href={`/recommendations?rec=${rec.rec_id}`} className="btn btn-outline">
            詳細と引用を見る
          </Link>
          <Link href={stockHref} className="btn btn-ghost">
            銘柄詳細
            <ExternalLink size={13} aria-hidden="true" />
          </Link>
        </div>
      )}

      <footer className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-divider pt-3">
        <span className="text-caption text-fg-tertiary">使用データ:</span>
        {rec.data_freshness?.map((f) => (
          <FreshnessBadge key={f.source} item={f} />
        ))}
        {(rec.flags?.length ?? 0) > 0 ? (
          <span className="text-caption text-status-warning">
            注意: {rec.flags?.map((f) => FLAG_LABEL_JA[f] ?? f).join(" / ")}
          </span>
        ) : null}
      </footer>
    </Card>
  );
}

const FLAG_LABEL_JA: Record<string, string> = {
  low_sample: "実績サンプルが少ない",
  citation_unverified: "引用が原文で確認できていない",
  stale_data: "古いデータを含む",
};

/** 一覧の1行に収める最小形。弱気論拠のプレビューを必ず含める */
export function RecommendationRowSummary({ rec }: { rec: RecCard }) {
  return (
    <div className="min-w-0">
      <p className="text-body text-fg-primary truncate">
        <span className="num mr-2 text-fg-secondary">{rec.ticker}</span>
        {rec.name_local}
      </p>
      <p className="text-caption text-fg-tertiary line-clamp-2">
        弱気論拠: {rec.bear_case_ja}
      </p>
      <p className="text-caption num mt-0.5">
        <span className="text-fg-tertiary">期待収益 </span>
        {formatNumeric(rec.expected_ret, "percent", { sign: true, precision: 1 })}{" "}
        <span className="text-fg-tertiary">
          [{formatNumeric(rec.expected_ret_lo, "percent", { sign: true, precision: 1 })},{" "}
          {formatNumeric(rec.expected_ret_hi, "percent", { sign: true, precision: 1 })}]
        </span>
      </p>
    </div>
  );
}
