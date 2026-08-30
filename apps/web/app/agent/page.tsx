"use client";

/**
 * エージェント（docs/ui/screens/08-agent-console.md）。
 *
 * 6ジョブの成否・LLMコスト・Criticの却下・注入される教訓を一箇所で見る。
 * キルスイッチは1操作で届く位置に置く。
 */

import { Suspense, useEffect, useRef, useState, type RefObject } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  formatDateTimeJst,
  formatDuration,
  formatRateWithN,
  formatUsd,
  formatUsdPrecise,
  NULL_PLACEHOLDER,
} from "@ai-stock/ui";

import { useOnlineStatus } from "../../components/app-shell";
import { HorizontalBarChart, TimeSeriesChart } from "../../components/charts";
import { ConfirmDialog, Field } from "../../components/dialog";
import { JobStatusStrip } from "../../components/jobs";
import { PageHeader } from "../../components/page-header";
import {
  LoadingRegion,
  QuerySection,
  Skeleton,
  SkeletonCards,
  SkeletonTable,
} from "../../components/states";
import { DataTable, type Column } from "../../components/table";
import { Badge, Button, Chip, Notice, ProgressBar, SectionCard, Tabs, Toggle } from "../../components/ui";
import { MetricCard, NullableText, RateWithN } from "../../components/values";
import type { AgentJob, AgentMemory, JobName, LlmCall } from "../../lib/api-types";
import {
  JOB_NAME_LABEL_JA,
  JOB_STATUS_LABEL_JA,
  JOB_STATUS_TONE,
  MEMORY_CATEGORY_LABEL_JA,
  MEMORY_CATEGORY_STYLE,
} from "../../lib/labels";
import {
  useAgentCost,
  useAgentJobEvents,
  useAgentJobs,
  useAgentMemory,
  useCancelJob,
  useClearJobHistory,
  useCriticStats,
  useRecommendations,
  useRunJob,
  useSettingsQuery,
  useSystemHealth,
  useToggleMemory,
  useUpdateSettings,
} from "../../lib/queries";
import { useOptionalQueryParam, useQueryParamState } from "../../lib/use-tab";

const TABS = ["jobs", "cost", "critic", "memory"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL: Record<Tab, string> = {
  jobs: "ジョブ",
  cost: "コスト",
  critic: "レビュー",
  memory: "教訓",
};

const JOB_OPTIONS: Array<{ value: JobName; label: string }> = (
  Object.keys(JOB_NAME_LABEL_JA) as JobName[]
).map((value) => ({ value, label: JOB_NAME_LABEL_JA[value] }));

function todayJst(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Tokyo" });
}

const callColumns: Array<Column<LlmCall>> = [
  {
    key: "time",
    header: "時刻",
    primary: true,
    render: (r) => <span className="num">{formatDateTimeJst(r.called_at)}</span>,
    sortValue: (r) => r.called_at,
  },
  { key: "purpose", header: "目的", render: (r) => r.purpose_ja },
  { key: "model", header: "モデル", render: (r) => <span className="num">{r.model}</span> },
  {
    key: "in",
    header: "入力トークン",
    numeric: true,
    hideOnCard: true,
    render: (r) => <span className="num">{r.input_tokens.toLocaleString("ja-JP")}</span>,
    sortValue: (r) => r.input_tokens,
  },
  {
    key: "out",
    header: "出力トークン",
    numeric: true,
    hideOnCard: true,
    render: (r) => <span className="num">{r.output_tokens.toLocaleString("ja-JP")}</span>,
    sortValue: (r) => r.output_tokens,
  },
  {
    key: "cost",
    header: "コスト",
    numeric: true,
    render: (r) => <span className="num">{formatUsdPrecise(r.cost_usd)}</span>,
    sortValue: (r) => r.cost_usd,
  },
  {
    key: "cache",
    header: "キャッシュ",
    render: (r) => (r.cache_hit ? "ヒット" : "ミス"),
  },
  {
    key: "dur",
    header: "所要",
    numeric: true,
    render: (r) => <span className="num">{r.duration_sec.toFixed(1)}秒</span>,
  },
  {
    key: "status",
    header: "結果",
    render: (r) => <Badge tone={r.status === "success" ? "success" : "danger"}>{r.status === "success" ? "成功" : "失敗"}</Badge>,
  },
];

function JobsTab({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const online = useOnlineStatus();
  const healthQ = useSystemHealth();
  const jobsQ = useAgentJobs();
  const runJob = useRunJob();
  const cancelJob = useCancelJob();
  const clearHistory = useClearJobHistory();
  const [jobName, setJobName] = useState<JobName>("collector");
  const [targetDate, setTargetDate] = useState(todayJst);
  const [force, setForce] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  return (
    <div className="space-y-4">
      <QuerySection label="スケジューラ" query={healthQ} skeleton={<Skeleton className="h-16 w-full" />}>
        {(h) => (
          <SectionCard title="スケジューラ">
            <div className="flex flex-wrap items-center gap-3 text-body-sm">
              <Badge tone={h.scheduler_alive ? "success" : "danger"}>
                {h.scheduler_alive ? "スケジューラ稼働中" : "スケジューラ停止中"}
              </Badge>
              <span>次回: {h.next_run ? formatDateTimeJst(h.next_run) : NULL_PLACEHOLDER}</span>
              <span className="num">プロセス稼働時間 {formatDuration(h.uptime_sec)}</span>
              <span>最終再起動 {h.last_reboot_ja ?? NULL_PLACEHOLDER}</span>
            </div>
            {h.resume_note_ja ? <p className="text-caption text-fg-secondary mt-2">{h.resume_note_ja}</p> : null}
          </SectionCard>
        )}
      </QuerySection>

      <QuerySection
        label="ジョブ"
        query={jobsQ}
        skeleton={<SkeletonCards count={6} className="grid-cols-2 desktop:grid-cols-6" />}
        emptyWhen={(d) => d.length === 0}
        empty={{
          title: "ジョブの実行履歴がありません",
          description: "手動実行するか、スケジュールされた時刻を待ってください。",
        }}
      >
        {(jobs) => {
          const selected = jobs.find((j) => String(j.job_run_id) === selectedId) ?? jobs[0];
          return (
            <>
              <SectionCard title="本日のパイプライン">
                <JobStatusStrip jobs={jobs} lastRun={jobs[jobs.length - 1]?.started_at ?? null} />
              </SectionCard>
              <div className="grid gap-4 desktop:grid-cols-12 desktop:items-start">
                <SectionCard
                  title="実行履歴"
                  className="desktop:col-span-5 desktop:sticky desktop:top-4 desktop:self-start"
                  bodyClassName="max-h-96 overflow-y-auto overscroll-contain"
                  actions={
                    <Button
                      variant="ghost"
                      disabled={!online || clearHistory.isPending || jobs.every((j) => j.status === "running")}
                      onClick={() => setConfirmClear(true)}
                    >
                      クリア
                    </Button>
                  }
                >
                  <ul className="space-y-2" aria-label="実行履歴">
                    {jobs.map((job) => (
                      <li key={job.job_run_id}>
                        <button
                          type="button"
                          className="w-full text-left card-inset p-3 tap-target"
                          aria-current={selected && String(selected.job_run_id) === String(job.job_run_id) ? "true" : undefined}
                          onClick={() => onSelect(String(job.job_run_id))}
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span>{job.label_ja}</span>
                            <Badge tone={JOB_STATUS_TONE[job.status]}>{JOB_STATUS_LABEL_JA[job.status]}</Badge>
                          </span>
                          <span className="block text-caption text-fg-tertiary num mt-1">
                            {formatDateTimeJst(job.started_at)} · {formatDuration(job.duration_sec)}
                          </span>
                          {job.output_ja ? <span className="block text-caption text-fg-secondary mt-0.5">{job.output_ja}</span> : null}
                          {job.status === "failed" && job.error_message && job.error_message !== job.output_ja ? (
                            <span className="block text-caption text-status-danger mt-0.5">{job.error_message}</span>
                          ) : null}
                          {job.failed_steps.length > 0 ? (
                            <span className="block text-caption text-status-warning mt-0.5">
                              部分 · {job.failed_steps.join(" / ")}
                            </span>
                          ) : null}
                        </button>
                      </li>
                    ))}
                  </ul>
                </SectionCard>
                <SectionCard title="実行の詳細" className="desktop:col-span-7">
                  {selected ? <JobDetail job={selected} online={online} onCancel={() => cancelJob.mutate(selected.job_run_id)} /> : null}
                </SectionCard>
              </div>
            </>
          );
        }}
      </QuerySection>

      <SectionCard title="手動実行">
        <div className="grid gap-3 tablet:grid-cols-2 desktop:grid-cols-4">
          <Field label="ジョブ">
            <select className="input" value={jobName} onChange={(e) => setJobName(e.target.value as JobName)}>
              {JOB_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="対象日">
            <input className="input" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
          </Field>
          <Toggle
            checked={force}
            onChange={setForce}
            label="完了済みでも再実行"
            description="通常は冪等なため、同じ対象日で再実行しても結果は変わりません。強制再実行はLLMコストが再発生する場合があります。"
            disabled={!online}
          />
        </div>
        <Button variant="primary" className="mt-3" disabled={!online} onClick={() => setConfirmRun(true)}>
          実行
        </Button>
        {!online ? <p className="text-caption text-status-warning mt-2">オフラインでは操作できません</p> : null}
      </SectionCard>

      <ConfirmDialog
        open={confirmRun}
        onClose={() => setConfirmRun(false)}
        title="ジョブを実行しますか"
        confirmLabel="実行"
        onConfirm={() => {
          runJob.mutate({ jobName, asOf: targetDate });
          setConfirmRun(false);
        }}
      >
        {JOB_NAME_LABEL_JA[jobName]} を {targetDate} に対して実行します。
        {force ? "強制再実行のため、LLMコストが再発生する場合があります。" : null}
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="実行履歴を削除しますか"
        confirmLabel="削除する"
        danger
        disabled={!online || clearHistory.isPending}
        onConfirm={() => {
          clearHistory.mutate();
          setConfirmClear(false);
        }}
      >
        完了したジョブの実行履歴を削除します。実行中のジョブは残ります。この操作は取り消せません。
      </ConfirmDialog>
    </div>
  );
}

function JobDetail({ job, online, onCancel }: { job: AgentJob; online: boolean; onCancel: () => void }) {
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="text-caption text-fg-tertiary">実行ID</dt>
          <dd className="num">{job.job_run_id}</dd>
        </div>
        <div>
          <dt className="text-caption text-fg-tertiary">ジョブ</dt>
          <dd>{job.label_ja}</dd>
        </div>
        <div>
          <dt className="text-caption text-fg-tertiary">状態</dt>
          <dd>
            <Badge tone={JOB_STATUS_TONE[job.status]}>{JOB_STATUS_LABEL_JA[job.status]}</Badge>
          </dd>
        </div>
        <div>
          <dt className="text-caption text-fg-tertiary">所要時間</dt>
          <dd>{formatDuration(job.duration_sec)}</dd>
        </div>
      </dl>
      {job.output_ja && job.output_ja !== job.error_message ? (
        <p className="text-body-sm text-fg-secondary">{job.output_ja}</p>
      ) : null}
      {job.error_message ? (
        <Notice tone={job.status === "failed" ? "danger" : "warning"}>
          失敗の原因: {job.error_message}
        </Notice>
      ) : null}
      {job.failed_steps.length > 0 ? (
        <Notice tone="warning">
          失敗したステップ: {job.failed_steps.join(" / ")}。再実行はチェックポイントから再開します。
        </Notice>
      ) : null}
      {job.status === "running" && job.progress && job.progress.total > 0 ? (
        <ProgressBar
          ratio={job.progress.completed / job.progress.total}
          label={`${job.progress.completed} / ${job.progress.total}`}
        />
      ) : null}
      {job.status === "running" ? (
        <Button variant="danger" disabled={!online} onClick={onCancel}>
          中止
        </Button>
      ) : (
        <p className="text-caption text-fg-tertiary">起動要因: スケジュール</p>
      )}
    </div>
  );
}

function CostTab({ killRef }: { killRef: RefObject<HTMLButtonElement | null> }) {
  const online = useOnlineStatus();
  const costQ = useAgentCost();
  const settingsQ = useSettingsQuery();
  const update = useUpdateSettings();
  const [confirmKill, setConfirmKill] = useState<"on" | "off" | null>(null);
  const kill = settingsQ.data?.data["llm.kill_switch"] ?? costQ.data?.data.kill_switch ?? false;

  return (
    <QuerySection
      label="コスト"
      query={costQ}
      skeleton={<SkeletonCards count={3} className="tablet:grid-cols-3" />}
      emptyWhen={(d) => d.calls.length === 0 && d.spent_today_usd === 0}
      empty={{
        title: "LLMの呼び出し履歴がありません",
        description: "資料読解や推奨生成が走るとここに記録されます。",
      }}
    >
      {(cost) => {
        const ratio = cost.daily_cap_usd > 0 ? cost.spent_today_usd / cost.daily_cap_usd : 0;
        const gaugeTone = ratio >= 1 ? "danger" : ratio >= 0.8 ? "warning" : "accent";
        return (
          <div className="space-y-4">
            <div className="grid gap-3 tablet:grid-cols-2 desktop:grid-cols-3">
              <MetricCard
                label="本日"
                value={`${formatUsd(cost.spent_today_usd)} / ${formatUsd(cost.daily_cap_usd)}`}
                sub={`${Math.round(ratio * 100)}%`}
              />
              <MetricCard
                label="当月"
                value={`${formatUsd(cost.spent_month_usd)} / ${formatUsd(cost.monthly_cap_usd)}`}
                sub={
                  cost.monthly_cap_usd > 0
                    ? `${Math.round((cost.spent_month_usd / cost.monthly_cap_usd) * 100)}%`
                    : undefined
                }
              />
              <MetricCard
                label="当月見込み"
                value={<NullableText value={cost.projected_month_usd !== null ? formatUsd(cost.projected_month_usd) : null} />}
                sub="直近7日の平均から算出"
              />
            </div>

            <SectionCard title="日次上限">
              <p className="text-caption text-fg-tertiary mb-2">日次上限 {formatUsd(cost.daily_cap_usd)}</p>
              <ProgressBar ratio={ratio} tone={gaugeTone} label="日次上限の使用率" />
              {ratio >= 1 ? (
                <Notice tone="danger" className="mt-2">
                  日次上限に達したため、LLM呼び出しを停止しています
                </Notice>
              ) : ratio >= 0.8 ? (
                <Notice tone="warning" className="mt-2">
                  日次上限の80%に達しました
                </Notice>
              ) : null}
              <div className="mt-4">
                <p className="text-body text-fg-primary">LLMの停止スイッチ</p>
                <p className="text-caption text-fg-tertiary">
                  有効にすると、定性分析・要約・推奨の論拠生成が停止します。定量スコアと推奨の生成は継続され、論拠は定量的な要因のみで構成されます。
                </p>
                <button
                  ref={killRef}
                  type="button"
                  className="btn btn-outline mt-2"
                  disabled={!online}
                  onClick={() => setConfirmKill(kill ? "off" : "on")}
                >
                  {kill ? "有効（LLM呼び出しを全面停止）" : "無効（通常動作）"}
                </button>
                {!online ? <p className="text-caption text-status-warning mt-2">オフラインでは操作できません</p> : null}
              </div>
            </SectionCard>

            <div className="grid gap-4 desktop:grid-cols-12">
              <SectionCard title="用途別" className="desktop:col-span-4">
                <ul className="space-y-2">
                  {cost.breakdown.map((row) => (
                    <li key={row.purpose_ja} className="flex justify-between gap-3 text-body-sm">
                      <span>
                        {row.purpose_ja}
                        {row.cache_hit_ja ? (
                          <span className="block text-caption text-fg-muted">キャッシュヒット {row.cache_hit_ja}</span>
                        ) : null}
                      </span>
                      <span className="num">
                        {formatUsd(row.usd)} · {formatPctSafe(row.share_pct)}
                      </span>
                    </li>
                  ))}
                </ul>
              </SectionCard>
              <SectionCard title="直近の呼び出し" className="desktop:col-span-8">
                <DataTable columns={callColumns} rows={cost.calls} getKey={(r) => r.called_at + r.model} caption="LLM呼び出し" />
              </SectionCard>
            </div>
            <ConfirmDialog
              open={confirmKill === "on"}
              onClose={() => setConfirmKill(null)}
              title="LLMを停止しますか"
              confirmLabel="停止する"
              danger
              onConfirm={() => {
                update.mutate({ "llm.kill_switch": true });
                setConfirmKill(null);
              }}
            >
              要約・定性評価・論拠生成が止まります。定量スコアによる推奨は継続します。
            </ConfirmDialog>
            <ConfirmDialog
              open={confirmKill === "off"}
              onClose={() => setConfirmKill(null)}
              title="停止を解除しますか"
              confirmLabel="解除する"
              onConfirm={() => {
                update.mutate({ "llm.kill_switch": false });
                setConfirmKill(null);
              }}
            >
              本日の残予算は {formatUsd(Math.max(0, cost.daily_cap_usd - cost.spent_today_usd))} です。
            </ConfirmDialog>
          </div>
        );
      }}
    </QuerySection>
  );
}

function formatPctSafe(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function CriticTab() {
  const statsQ = useCriticStats();
  const rejectedQ = useRecommendations({ critic_verdict: "rejected" });

  return (
    <div className="space-y-4">
      <QuerySection label="レビュー指標" query={statsQ} skeleton={<SkeletonCards count={3} className="tablet:grid-cols-3" />}>
        {(s) => (
          <>
            <div className="grid gap-3 tablet:grid-cols-3">
              <MetricCard
                label="却下率"
                value={<RateWithN rate={s.rejection_rate} n={s.n_total} />}
                sub={`${s.n_rejected}件 / ${s.n_total}件（直近${s.days}日）`}
              />
              <MetricCard
                label="修正率"
                value={<RateWithN rate={s.revision_rate} n={s.n_total} />}
                sub={`${s.n_revised}件 / ${s.n_total}件`}
              />
              <MetricCard
                label="最多の却下理由"
                value={s.reasons[0]?.label_ja ?? NULL_PLACEHOLDER}
                sub={s.reasons[0] ? `${s.reasons[0].count}件` : undefined}
              />
            </div>
            <p className="text-caption text-fg-secondary">
              却下率が0%に近い場合、Criticが機能していない可能性があります。30%を大きく超える場合はStrategistのプロンプトを見直してください。
            </p>
            <div className="grid gap-4 desktop:grid-cols-2">
              <SectionCard title="却下理由">
                <HorizontalBarChart
                  data={s.reasons.map((r) => ({ label: r.label_ja, value: r.count }))}
                  valueFormatter={(v) => `${v}件`}
                />
              </SectionCard>
              <SectionCard title="却下の傾向">
                <TimeSeriesChart
                  data={s.reasons.map((r, i) => ({ date: r.code, rate: r.count / Math.max(s.n_total, 1), i }))}
                  series={[{ dataKey: "rate", label: "件数シェア" }]}
                  xKey="date"
                  yTickFormatter={(v) => formatPctSafe(v)}
                />
              </SectionCard>
            </div>
          </>
        )}
      </QuerySection>
      <SectionCard title="却下された推奨">
        <QuerySection
          label="却下一覧"
          query={rejectedQ}
          section="recommendations"
          skeleton={<SkeletonTable rows={4} cols={3} />}
          emptyWhen={(d) => d.items.length === 0}
          empty={{
            title: "Criticの却下はありません",
            description: "却下率が0%が続く場合は検証が機能しているか確認してください。",
          }}
        >
          {(data) => (
            <ul className="space-y-3">
              {data.items.map((rec) => (
                <li key={rec.rec_id} className="card-inset p-3">
                  <p className="text-body-sm">
                    <span className="num mr-2">{rec.ticker}</span>
                    {rec.name_local}
                    <Badge tone="danger" className="ml-2">
                      却下
                    </Badge>
                  </p>
                  <p className="text-caption text-fg-secondary mt-1">{rec.critic_notes_ja ?? rec.bear_case_ja}</p>
                </li>
              ))}
            </ul>
          )}
        </QuerySection>
      </SectionCard>
    </div>
  );
}

function MemoryTab() {
  const online = useOnlineStatus();
  const query = useAgentMemory();
  const toggle = useToggleMemory();
  const [scope, setScope] = useState("all");
  const [active, setActive] = useState<"true" | "false" | "all">("true");
  const [q, setQ] = useState("");

  return (
    <QuerySection
      label="教訓"
      query={query}
      skeleton={<SkeletonCards count={3} />}
      emptyWhen={(d) => d.length === 0}
      empty={{
        title: "教訓はまだ蓄積されていません",
        description: "推奨の実績が確定し始めると生成されます（最短で運用開始から20営業日後）。",
      }}
    >
      {(items) => {
        const filtered = items.filter((m) => {
          if (scope !== "all" && m.scope !== scope) return false;
          if (active === "true" && !m.is_active) return false;
          if (active === "false" && m.is_active) return false;
          if (q && !m.text_ja.includes(q)) return false;
          return true;
        });
        const harmful = items.filter(
          (m) => m.hit_rate_after !== null && m.hit_rate_before !== null && m.hit_rate_after < m.hit_rate_before,
        );
        const activeCount = items.filter((m) => m.is_active).length;
        return (
          <div className="space-y-4">
            <p className="text-body-sm text-fg-secondary">
              ここに登録された教訓は、推奨生成時のプロンプトに注入されます。誤った教訓は出力を継続的に悪化させるため、定期的に見直してください。
            </p>
            <p className="text-caption text-fg-tertiary">
              教訓（有効 {activeCount}件 / 全 {items.length}件）
            </p>
            <div className="flex flex-wrap gap-2">
              {["all", "global", "market", "sector", "ticker"].map((s) => (
                <Chip key={s} selected={scope === s} onClick={() => setScope(s)}>
                  {s === "all" ? "すべて" : s === "global" ? "全体" : s === "market" ? "市場" : s === "sector" ? "セクター" : "銘柄"}
                </Chip>
              ))}
              <Chip selected={active === "true"} onClick={() => setActive("true")}>
                有効
              </Chip>
              <Chip selected={active === "all"} onClick={() => setActive("all")}>
                すべて
              </Chip>
              <input className="input max-w-xs" placeholder="検索" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <ul className="space-y-3">
              {filtered.map((m) => (
                <MemoryItem key={m.memory_id} memory={m} online={online} onToggle={() => toggle.mutate({ memoryId: m.memory_id, isActive: !m.is_active })} />
              ))}
            </ul>
            <SectionCard title="教訓の有効性">
              <p className="text-body-sm text-fg-secondary">
                使用された推奨と未使用の的中率を、各教訓の母数つきで比較しています。サンプルが少ない場合は率を出しません。
              </p>
              {harmful.length > 0 ? (
                <div className="mt-3 space-y-2">
                  <p className="text-h4">有害な可能性のある教訓</p>
                  {harmful.map((m) => (
                    <Notice key={m.memory_id} tone="warning">
                      「{m.text_ja.slice(0, 24)}…」を使用した推奨の的中率は {formatRateWithN(m.hit_rate_after, m.n_after)}{" "}
                      で、未使用時の {formatRateWithN(m.hit_rate_before, m.n_before)} を下回っています。無効化を検討してください。
                      <Button
                        variant="secondary"
                        className="mt-2"
                        disabled={!online || !m.is_active}
                        onClick={() => toggle.mutate({ memoryId: m.memory_id, isActive: false })}
                      >
                        無効にする
                      </Button>
                    </Notice>
                  ))}
                </div>
              ) : null}
            </SectionCard>
            <p className="text-caption text-fg-tertiary desktop:hidden">教訓の編集はデスクトップから行ってください</p>
          </div>
        );
      }}
    </QuerySection>
  );
}

function MemoryItem({
  memory,
  online,
  onToggle,
}: {
  memory: AgentMemory;
  online: boolean;
  onToggle: () => void;
}) {
  const effect =
    memory.n_after !== null && memory.n_after < 10
      ? `効果の測定にはサンプルが不足しています (n=${memory.n_after})`
      : `効果: この教訓を使用した推奨の的中率 ${formatRateWithN(memory.hit_rate_after, memory.n_after)} / 未使用 ${formatRateWithN(memory.hit_rate_before, memory.n_before)}`;
  return (
    <li className="card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Badge tone={MEMORY_CATEGORY_STYLE[memory.category]}>{MEMORY_CATEGORY_LABEL_JA[memory.category]}</Badge>
        <span className="text-caption text-fg-tertiary">適用範囲: {memory.scope}</span>
        <Toggle checked={memory.is_active} onChange={() => onToggle()} label="有効" disabled={!online} />
      </div>
      <p className="text-body-sm text-fg-primary mt-2 prose-block">{memory.text_ja}</p>
      <p className="text-caption text-fg-secondary mt-2">根拠: {memory.evidence_ja}</p>
      <p className="text-caption text-fg-tertiary">使用回数: 直近30日で {memory.usage_count_30d}回のプロンプトに注入</p>
      <p className="text-caption text-fg-tertiary">{effect}</p>
      <p className="text-micro text-fg-muted num mt-1">更新: {formatDateTimeJst(memory.updated_at)}</p>
    </li>
  );
}

function AgentInner() {
  const qc = useQueryClient();
  useAgentJobEvents();
  const [tab, setTab] = useQueryParamState<Tab>("tab", TABS, "jobs");
  const [jobId, setJobId] = useOptionalQueryParam("job_run_id");
  const healthQ = useSystemHealth();
  const killRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT")) return;
      if (e.key === "k") {
        e.preventDefault();
        killRef.current?.focus();
        setTab("cost");
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setTab]);

  return (
    <>
      <PageHeader
        title="エージェント"
        asOf={healthQ.data?.meta.as_of}
        computedAt={healthQ.data?.meta.computed_at}
        refreshing={healthQ.isFetching && !healthQ.isPending}
        onRefresh={() => void qc.invalidateQueries({ queryKey: ["agent"] })}
      />
      <Tabs
        label="エージェントのタブ"
        value={tab}
        onChange={setTab}
        options={TABS.map((t) => ({ value: t, label: TAB_LABEL[t] }))}
      />
      <div className="mt-4">
        {tab === "jobs" ? <JobsTab selectedId={jobId} onSelect={setJobId} /> : null}
        {tab === "cost" ? <CostTab killRef={killRef} /> : null}
        {tab === "critic" ? <CriticTab /> : null}
        {tab === "memory" ? <MemoryTab /> : null}
      </div>
    </>
  );
}

export default function AgentPage() {
  return (
    <Suspense
      fallback={
        <LoadingRegion label="エージェント">
          <Skeleton className="h-10 w-40" />
          <SkeletonCards count={6} className="mt-4" />
        </LoadingRegion>
      }
    >
      <AgentInner />
    </Suspense>
  );
}
