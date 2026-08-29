"use client";

/**
 * 表示設定（方向色・テーマ・既定市場・密度）を保持する。
 *
 * 方向色は `<html data-direction-colors>` を切り替えるだけで全画面に反映される。
 * トークン側（styles/tokens.css）で `--dir-up` / `--dir-down` を入れ替えているため、
 * コンポーネントは「上か下か」だけを知っていればよく、赤か緑かを知る必要がない。
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { DirectionColors, Market, ThemeMode } from "../lib/api-types";
import { resolveMarket } from "../lib/market";

export type Density = "standard" | "dense";

export interface Prefs {
  directionColors: DirectionColors;
  theme: ThemeMode;
  market: Market;
  density: Density;
}

const DEFAULT_PREFS: Prefs = {
  directionColors: "jp",
  theme: "dark",
  market: "JP",
  density: "standard",
};

const STORAGE_KEY = "ai-stock.prefs.v1";

interface PrefsContextValue extends Prefs {
  setPrefs: (patch: Partial<Prefs>) => void;
}

const PrefsContext = createContext<PrefsContextValue | null>(null);

function readStored(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      ...DEFAULT_PREFS,
      ...parsed,
      market: resolveMarket(parsed.market),
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  // 初期値はサーバと同じ既定値にする。localStorage の反映は mount 後（ハイドレーション不整合を避ける）
  const [prefs, setPrefsState] = useState<Prefs>(DEFAULT_PREFS);

  useEffect(() => {
    setPrefsState(readStored());
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.directionColors = prefs.directionColors;
    root.dataset.theme = prefs.theme;
    root.dataset.density = prefs.density;
    root.style.colorScheme = prefs.theme;
  }, [prefs]);

  const setPrefs = useCallback((patch: Partial<Prefs>) => {
    setPrefsState((prev) => {
      const next = {
        ...prev,
        ...patch,
        market: resolveMarket(patch.market ?? prev.market),
      };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // プライベートブラウジングなどで書けない場合は、セッション内だけ反映する
      }
      return next;
    });
  }, []);

  const value = useMemo<PrefsContextValue>(() => ({ ...prefs, setPrefs }), [prefs, setPrefs]);

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): PrefsContextValue {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs は PrefsProvider の内側で使ってください");
  return ctx;
}
