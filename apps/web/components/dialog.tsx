"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";

import { Button, cx } from "./ui";

/** 768px 未満はボトムシート、以上は中央ダイアログ（tokens.css の sheet-*）。 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  label,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  label?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="sheet-panel p-4" role="dialog" aria-modal="true" aria-label={label ?? title}>
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-h3 text-fg-primary">{title}</h2>
          <Button variant="ghost" onClick={onClose} ariaLabel="閉じる">
            <X size={16} aria-hidden="true" />
          </Button>
        </div>
        <div className="mt-3 max-h-[70vh] overflow-auto">{children}</div>
        {footer ? <div className="mt-4 flex flex-wrap justify-end gap-2">{footer}</div> : null}
      </div>
    </>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  children,
  confirmLabel,
  danger,
  disabled,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            キャンセル
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={disabled}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-body-sm text-fg-secondary prose-block">{children}</div>
    </Dialog>
  );
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx("block space-y-1", className)}>
      <span className="text-caption text-fg-tertiary">{label}</span>
      {children}
      {hint ? <span className="block text-caption text-fg-muted">{hint}</span> : null}
    </label>
  );
}
