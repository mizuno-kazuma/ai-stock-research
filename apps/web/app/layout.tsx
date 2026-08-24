import type { Metadata, Viewport } from "next";

import "./globals.css";
import { AppShell } from "../components/app-shell";
import { THEME_COLOR_DARK, THEME_COLOR_LIGHT } from "../lib/brand";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "AIリサーチ", template: "%s | AIリサーチ" },
  description:
    "日本株・米国株のリサーチ支援。定量スコア、開示資料の要約、為替予測を1つの画面で確認する。投資判断は利用者が行う。",
  manifest: "/manifest.webmanifest",
  applicationName: "AIリサーチ",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "AIリサーチ" },
  formatDetection: { telephone: false },
  icons: {
    icon: [{ url: "/icons/icon-192.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/icon-192.svg" }],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // ノッチ端末で safe-area-inset を使うために必須
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: THEME_COLOR_DARK },
    { media: "(prefers-color-scheme: light)", color: THEME_COLOR_LIGHT },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja" data-theme="dark" data-direction-colors="jp" data-density="standard">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
