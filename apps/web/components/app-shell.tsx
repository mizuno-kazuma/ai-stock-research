"use client";

/**
 * 画面の外枠。components.md §1.1 の階層に対応する。
 *   KillSwitchBanner → AppHeader → Sidebar / BottomNav → main
 *
 * Header と左ペインはビューポートに固定し、スクロールは main だけにする。
 *
 * レスポンシブ（interaction-patterns.md §2.2）:
 *   1280px 以上 … サイドバー（240px、ラベルあり）
 *   768-1279px  … アイコンレール（64px）
 *   768px 未満  … ボトムナビ（5項目、safe-area 対応）
 */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, CloudOff, Keyboard, Moon, RefreshCw, Search, Sun, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { formatDateTimeJst } from "@ai-stock/ui";

import { BOTTOM_NAV_ITEMS, SIDEBAR_ITEMS, routeTitle } from "./nav-items";
import { DataFreshnessIndicator } from "./freshness";
import { usePrefs } from "./prefs";
import { Badge, Button, SegmentedControl, cx } from "./ui";
import { useAlerts, useSettingsQuery, useStockSearch } from "../lib/queries";
import { uniqueByIssuer } from "../lib/tickers";
import { ALERT_CATEGORY_LABEL_JA } from "../lib/labels";
import { ScoreBadge } from "./values";

/* ------------------------------ オフライン ---------------------------- */

export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

function OfflineBanner({ lastSyncedAt }: { lastSyncedAt: string | null }) {
  return (
    <div className="app-banner flex items-center gap-2 bg-status-warning-bg px-4 py-1.5 text-caption text-status-warning" role="status">
      <CloudOff size={14} aria-hidden="true" />
      オフラインです。表示はキャッシュです
      {lastSyncedAt ? <span className="num">（取得時刻 {formatDateTimeJst(lastSyncedAt)}）</span> : null}
    </div>
  );
}

function KillSwitchBanner() {
  const settings = useSettingsQuery();
  if (!settings.data?.data["llm.kill_switch"]) return null;
  return (
    <div className="app-banner bg-status-danger-bg px-4 py-1.5 text-caption text-status-danger" role="alert">
      LLMの停止スイッチが有効です。要約と論拠の生成は行われません（設定 &gt; コストで解除できます）
    </div>
  );
}

/* -------------------------------- 検索 ------------------------------- */

function SearchSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useStockSearch(q);
  const router = useRouter();

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else setQ("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const hits = uniqueByIssuer(results.data?.data ?? []);

  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="sheet-panel p-4" role="dialog" aria-modal="true" aria-label="銘柄検索">
        <div className="flex items-center gap-2">
          <Search size={16} aria-hidden="true" className="text-fg-tertiary" />
          <input
            ref={inputRef}
            className="input"
            placeholder="銘柄コード・企業名で検索"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hits[0]) {
                router.push(`/stocks/${hits[0].market}/${hits[0].ticker}`);
                onClose();
              }
            }}
            aria-label="銘柄コード・企業名で検索"
          />
          <Button variant="ghost" onClick={onClose} ariaLabel="検索を閉じる">
            <X size={16} aria-hidden="true" />
          </Button>
        </div>

        <ul className="mt-3 max-h-80 overflow-auto">
          {results.isPending ? (
            <li className="text-body-sm text-fg-tertiary px-2 py-3">検索中…</li>
          ) : hits.length === 0 ? (
            <li className="text-body-sm text-fg-tertiary px-2 py-3">
              一致する銘柄がありません。銘柄コード（例 7203）または企業名で試してください。
            </li>
          ) : (
            hits.map((hit, index) => (
              <li key={`${hit.market}-${hit.ticker}-${index}`}>
                <Link
                  href={`/stocks/${hit.market}/${hit.ticker}`}
                  onClick={onClose}
                  className="flex items-center justify-between gap-3 rounded-md px-2 py-2 hover:bg-hover"
                >
                  <span className="min-w-0">
                    <span className="num text-body-sm text-fg-secondary mr-2">{hit.ticker}</span>
                    <span className="text-body text-fg-primary">{hit.name_local}</span>
                    <span className="block text-caption text-fg-tertiary truncate">{hit.sector_name}</span>
                  </span>
                  <ScoreBadge score={hit.quant_score} size="sm" />
                </Link>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  );
}

/* ----------------------------- 通知ベル ------------------------------ */

function AlertBell() {
  const alerts = useAlerts();
  const [open, setOpen] = useState(false);
  const items = alerts.data?.data ?? [];
  const unread = items.filter((a) => !a.is_read);

  return (
    <div className="relative">
      <button
        type="button"
        className="btn btn-ghost"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={`通知 ${unread.length}件`}
      >
        <Bell size={16} aria-hidden="true" />
        <span className="num text-caption" aria-live="polite">
          {unread.length > 0 ? unread.length : ""}
        </span>
      </button>
      {open ? (
        <div className="absolute right-0 mt-1 card p-2 shadow-md popover-panel">
          <p className="section-title">通知</p>
          <ul className="max-h-80 overflow-auto">
            {items.length === 0 ? (
              <li className="px-2 py-3 text-body-sm text-fg-tertiary">通知はありません</li>
            ) : (
              items.map((a) => (
                <li key={a.alert_id} className="border-b border-divider last:border-b-0 px-2 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-body-sm text-fg-primary">{a.title_ja}</span>
                    <Badge tone={a.severity === "error" ? "danger" : a.severity === "warning" ? "warning" : "info"}>
                      {ALERT_CATEGORY_LABEL_JA[a.category]}
                    </Badge>
                  </div>
                  {a.body_ja ? <p className="text-caption text-fg-tertiary mt-0.5">{a.body_ja}</p> : null}
                  <p className="text-micro text-fg-muted mt-0.5 num">{formatDateTimeJst(a.created_at)}</p>
                </li>
              ))
            )}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/* --------------------------- ショートカット --------------------------- */

const SHORTCUTS: Array<[string, string]> = [
  ["/", "検索を開く"],
  ["g → d", "ダッシュボード"],
  ["g → r", "推奨銘柄"],
  ["g → s", "スクリーナー"],
  ["g → f", "決算資料"],
  ["g → p", "ポートフォリオ"],
  ["g → a", "エージェント"],
  ["m", "日本株 / 米国株を切替"],
  ["t", "テーマを切替"],
  ["?", "この一覧"],
  ["Escape", "最前面のオーバーレイを閉じる"],
];

function ShortcutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;
  return (
    <>
      <div className="sheet-backdrop" onClick={onClose} aria-hidden="true" />
      <div className="sheet-panel p-4" role="dialog" aria-modal="true" aria-label="キーボードショートカット">
        <div className="flex items-center justify-between">
          <h2 className="text-h3">キーボードショートカット</h2>
          <Button variant="ghost" onClick={onClose} ariaLabel="閉じる">
            <X size={16} aria-hidden="true" />
          </Button>
        </div>
        <dl className="mt-3 grid gap-2">
          {SHORTCUTS.map(([key, desc]) => (
            <div key={key} className="flex items-center justify-between gap-4">
              <dt className="num text-body-sm text-fg-secondary">{key}</dt>
              <dd className="text-body-sm text-fg-primary">{desc}</dd>
            </div>
          ))}
        </dl>
      </div>
    </>
  );
}

/* ------------------------------ AppShell ----------------------------- */

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const prefs = usePrefs();
  const online = useOnlineStatus();
  const qc = useQueryClient();
  const [searchOpen, setSearchOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);

  const refreshAll = useCallback(() => {
    void qc.invalidateQueries();
    setLastRefreshed(new Date().toISOString());
  }, [qc]);

  // g → x の連続入力。テキスト入力中は無効にする
  useEffect(() => {
    let pendingG = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const isTyping = (target: EventTarget | null) => {
      const el = target as HTMLElement | null;
      if (!el) return false;
      const tag = el.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTyping(e.target)) return;

      if (pendingG) {
        pendingG = false;
        const routes: Record<string, string> = {
          d: "/",
          r: "/recommendations",
          s: "/screener",
          f: "/filings",
          p: "/portfolio",
          a: "/agent",
        };
        const next = routes[e.key];
        if (next) {
          e.preventDefault();
          router.push(next);
          return;
        }
      }

      switch (e.key) {
        case "/":
          e.preventDefault();
          setSearchOpen(true);
          break;
        case "g":
          pendingG = true;
          clearTimeout(timer);
          timer = setTimeout(() => {
            pendingG = false;
          }, 1200);
          break;
        case "m":
          prefs.setPrefs({ market: prefs.market === "JP" ? "US" : "JP" });
          break;
        case "t":
          prefs.setPrefs({ theme: prefs.theme === "dark" ? "light" : "dark" });
          break;
        case "?":
          setShortcutsOpen(true);
          break;
        case "Escape":
          setSearchOpen(false);
          setShortcutsOpen(false);
          break;
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      clearTimeout(timer);
    };
  }, [prefs, router]);

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        メインコンテンツへスキップ
      </a>

      {!online ? <OfflineBanner lastSyncedAt={lastRefreshed} /> : null}
      <KillSwitchBanner />

      <header className="app-header flex items-center gap-3 border-b border-divider bg-surface px-3">
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="text-h4 text-fg-primary">AIリサーチ</span>
        </Link>

        <div className="hidden tablet:block">
          <SegmentedControl
            label="市場を選択"
            value={prefs.market}
            onChange={(market) => prefs.setPrefs({ market })}
            options={[
              { value: "JP", label: "日本株" },
              { value: "US", label: "米国株" },
            ]}
          />
        </div>

        <button
          type="button"
          className="btn btn-outline flex-1 justify-start desktop:max-w-sm"
          onClick={() => setSearchOpen(true)}
        >
          <Search size={14} aria-hidden="true" />
          <span className="text-fg-tertiary">銘柄コード・企業名で検索</span>
          <span className="hidden desktop:inline text-micro text-fg-muted ml-auto">/</span>
        </button>

        <div className="ml-auto flex items-center gap-1">
          <DataFreshnessIndicator />
          <Button variant="ghost" onClick={refreshAll} ariaLabel="すべて再取得" title="すべて再取得">
            <RefreshCw size={16} aria-hidden="true" />
          </Button>
          <AlertBell />
          <Button
            variant="ghost"
            onClick={() => prefs.setPrefs({ theme: prefs.theme === "dark" ? "light" : "dark" })}
            ariaLabel="テーマを切り替え"
            className="hidden tablet:inline-flex"
          >
            {prefs.theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
          </Button>
          <Button
            variant="ghost"
            onClick={() => setShortcutsOpen(true)}
            ariaLabel="キーボードショートカット"
            className="hidden desktop:inline-flex"
          >
            <Keyboard size={16} aria-hidden="true" />
          </Button>
        </div>
      </header>

      <div className="app-shell-body">
        {/* 768px 以上でサイドバー。1280px 未満はアイコンだけのレール */}
        <nav
          className="hidden tablet:flex app-nav-rail shrink-0 flex-col gap-1 border-r border-divider bg-surface p-2"
          aria-label="メインナビゲーション"
        >
          {SIDEBAR_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                title={item.labelJa}
                className={cx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-body-sm tap-target justify-center desktop:justify-start",
                  active
                    ? "bg-accent-bg text-accent border-l-2 border-accent"
                    : "text-fg-secondary hover:bg-hover hover:text-fg-primary",
                )}
              >
                <Icon size={18} aria-hidden="true" />
                <span className="hidden desktop:inline">{item.labelJa}</span>
              </Link>
            );
          })}
        </nav>

        <main id="main" className="app-content min-w-0 flex-1 px-4 py-4 tablet:px-6 tablet:py-6">
          <div className="app-content-inner">
          {/* 遷移先の画面名を読み上げる（interaction-patterns.md §4.3） */}
          <p className="visually-hidden" aria-live="polite">
            {routeTitle(pathname)}
          </p>
          {children}
          {/* ボトムナビに隠れないようにモバイルだけ下余白を足す */}
          <div className="h-16 tablet:hidden" aria-hidden="true" />
          </div>
        </main>
      </div>

      <nav
        className="app-bottom-nav tablet:hidden fixed bottom-0 left-0 right-0 flex items-stretch justify-around border-t border-divider bg-surface"
        aria-label="モバイルナビゲーション"
      >
        {BOTTOM_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "tap-target flex flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-micro",
                active ? "text-accent" : "text-fg-tertiary",
              )}
            >
              <Icon size={20} aria-hidden="true" />
              {item.labelJa}
            </Link>
          );
        })}
      </nav>

      <SearchSheet open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ShortcutDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
