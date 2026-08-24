"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { PrefsProvider } from "../components/prefs";

/**
 * 自動再取得はしない（interaction-patterns.md §5.1）。
 * 数字が勝手に変わると判断を誤るため、更新はヘッダの更新ボタンか画面内の再試行に限る。
 * ただしオフラインから復帰したときだけは、古い表示を残さないように再取得する。
 */
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        gcTime: 30 * 60_000,
        refetchOnWindowFocus: false,
        refetchOnMount: false,
        refetchOnReconnect: true,
        retry: false,
      },
      mutations: { retry: false },
    },
  });
}

function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    const register = () => {
      void navigator.serviceWorker.register("/sw.js", { scope: "/" });
    };
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
  }, []);
  return null;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <PrefsProvider>
        <ServiceWorkerRegistrar />
        {children}
      </PrefsProvider>
    </QueryClientProvider>
  );
}
