/**
 * 汎用プリミティブ。色・寸法はすべて styles/tokens.css の合成クラス経由。
 * ここにも app/ 配下にも 16 進カラーや任意値クラス（ブラケット記法）は書かない。
 */

import type { ReactNode } from "react";

import type { StatusTone } from "../lib/labels";

export const cx = (...parts: Array<string | false | null | undefined>): string =>
  parts.filter(Boolean).join(" ");

const TONE_BADGE: Record<StatusTone, string> = {
  info: "badge-info",
  success: "badge-success",
  warning: "badge-warning",
  danger: "badge-danger",
  neutral: "badge-neutral",
  accent: "badge-accent",
};

export function Badge({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: StatusTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span className={cx("badge", TONE_BADGE[tone], className)} title={title}>
      {children}
    </span>
  );
}

export function Chip({
  children,
  tone,
  selected,
  onClick,
  title,
}: {
  children: ReactNode;
  tone?: "positive" | "negative" | "warning" | "neutral";
  selected?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  const toneClass =
    tone === "positive"
      ? "chip-positive"
      : tone === "negative"
        ? "chip-negative"
        : tone === "warning"
          ? "chip-warning"
          : undefined;

  if (!onClick) {
    return (
      <span className={cx("chip", toneClass)} title={title} data-selected={selected}>
        {children}
      </span>
    );
  }
  return (
    <button
      type="button"
      className={cx("chip", toneClass)}
      onClick={onClick}
      aria-pressed={selected}
      title={title}
    >
      {children}
    </button>
  );
}

export function Card({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article" | "li";
}) {
  return <Tag className={cx("card", className)}>{children}</Tag>;
}

/** 見出し + 右肩の操作 + 本文。ページ内のセクションはすべてこれで囲む */
export function SectionCard({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <Card className={className}>
      <div className="section-title" id={id}>
        <div className="min-w-0">
          <h2 className="text-h4 text-fg-primary truncate">{title}</h2>
          {subtitle ? <p className="text-caption text-fg-tertiary mt-0.5">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2 shrink-0">{actions}</div> : null}
      </div>
      <div className={cx("p-5", bodyClassName)}>{children}</div>
    </Card>
  );
}

export function Notice({
  tone = "neutral",
  icon,
  children,
  className,
  role,
}: {
  tone?: "info" | "warning" | "danger" | "neutral";
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  role?: "status" | "alert";
}) {
  const toneClass =
    tone === "info"
      ? "notice-info"
      : tone === "warning"
        ? "notice-warning"
        : tone === "danger"
          ? "notice-danger"
          : "notice-neutral";
  return (
    <div className={cx("notice", toneClass, className)} role={role}>
      {icon ? <span className="shrink-0 mt-0.5">{icon}</span> : null}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Button({
  variant = "secondary",
  children,
  onClick,
  disabled,
  type = "button",
  className,
  ariaLabel,
  title,
}: {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
  ariaLabel?: string;
  title?: string;
}) {
  return (
    <button
      type={type}
      className={cx("btn", `btn-${variant}`, className)}
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      title={title}
    >
      {children}
    </button>
  );
}

/** 単一選択のセグメント。市場切替・期間切替に使う */
export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className="chip"
          aria-pressed={opt.value === value}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string; badge?: ReactNode }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="tab-bar" role="tablist" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="tab"
          className="tab-item"
          aria-selected={opt.value === value}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
          {opt.badge != null ? <span className="ml-1.5 text-micro text-fg-tertiary">{opt.badge}</span> : null}
        </button>
      ))}
    </div>
  );
}

/** 説明つきのラベル。用語のツールチップは title 属性で十分（キーボードでも読める） */
export function LabelWithHint({ label, hint }: { label: ReactNode; hint?: string | null }) {
  if (!hint) return <>{label}</>;
  return (
    <span title={hint} className="underline decoration-dotted decoration-1 underline-offset-2">
      {label}
    </span>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-start justify-between gap-4 py-2 cursor-pointer">
      <span className="min-w-0">
        <span className="block text-body text-fg-primary">{label}</span>
        {description ? <span className="block text-caption text-fg-tertiary">{description}</span> : null}
      </span>
      <input
        type="checkbox"
        className="tap-target accent-accent"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}

export function ProgressBar({
  ratio,
  tone = "accent",
  label,
}: {
  ratio: number;
  tone?: "accent" | "success" | "warning" | "danger";
  label: string;
}) {
  const pct = Math.max(0, Math.min(1, ratio));
  const fillTone =
    tone === "success"
      ? "progress-fill--success"
      : tone === "warning"
        ? "progress-fill--warning"
        : tone === "danger"
          ? "progress-fill--danger"
          : undefined;
  return (
    <div
      className="progress-track"
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {/* 幅だけはインラインで持つ（可変値なのでクラスにできない） */}
      <div className={cx("progress-fill", fillTone)} style={{ width: `${pct * 100}%` }} />
    </div>
  );
}
