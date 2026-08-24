"use client";

/**
 * バッチの実行状況。ダッシュボードとエージェント画面で共用する。
 *
 * 「部分（partial）」はスキップ件数まで出す。件数のない「部分」は行動につながらない。
 */

import { formatDuration, formatTimeJst } from "@ai-stock/ui";

import type { AgentJob } from "../lib/api-types";
import { JOB_STATUS_LABEL_JA, JOB_STATUS_TONE } from "../lib/labels";
import { Badge, ProgressBar, cx } from "./ui";

const BORDER_TONE = {
  success: "border-status-success",
  warning: "border-status-warning",
  danger: "border-status-danger",
  info: "border-status-info",
  neutral: "border-outline",
  accent: "border-accent",
} as const;

export function JobPill({ job }: { job: AgentJob }) {
  const tone = JOB_STATUS_TONE[job.status];
  return (
    <li
      className={cx("card-inset min-w-44 shrink-0 border-l-2 p-3 snap-start", BORDER_TONE[tone])}
      aria-live={job.status === "running" ? "polite" : undefined}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-body-sm text-fg-primary">{job.label_ja}</span>
        <Badge tone={tone}>{JOB_STATUS_LABEL_JA[job.status]}</Badge>
      </div>
      <p className="text-caption text-fg-tertiary mt-1 num">
        {formatTimeJst(job.started_at)} · {formatDuration(job.duration_sec)}
      </p>
      {job.output_summary_ja ? (
        <p className="text-caption text-fg-secondary mt-0.5 truncate">{job.output_summary_ja}</p>
      ) : null}
      {job.failed_steps.length > 0 ? (
        <p className="text-caption text-status-warning mt-0.5">
          失敗した処理: {job.failed_steps.join(" / ")}
        </p>
      ) : null}
      {job.progress ? (
        <div className="mt-2">
          <ProgressBar
            ratio={job.progress.total === 0 ? 0 : job.progress.completed / job.progress.total}
            label={`${job.label_ja}の進捗`}
          />
          <p className="text-micro text-fg-tertiary mt-1 num">
            {job.progress.completed} / {job.progress.total}
            {job.progress.eta_sec !== null ? ` · 残り ${formatDuration(job.progress.eta_sec)}` : null}
          </p>
        </div>
      ) : null}
    </li>
  );
}

export function JobStatusStrip({ jobs, lastRun }: { jobs: AgentJob[]; lastRun: string | null }) {
  return (
    <div>
      <ul className="flex gap-3 overflow-x-auto snap-x pb-1" aria-label="バッチの実行状況">
        {jobs.map((job) => (
          <JobPill key={job.job_run_id} job={job} />
        ))}
      </ul>
      <p className="text-caption text-fg-tertiary mt-1 num">
        直近の実行: {lastRun ? `${formatTimeJst(lastRun)} (JST)` : "記録がありません"}
      </p>
    </div>
  );
}
