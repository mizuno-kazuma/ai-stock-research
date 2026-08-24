import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Phase A では WSL2 上の standalone サーバとして起動する（docs/01-architecture.md §3）
  output: "standalone",
  transpilePackages: ["@ai-stock/ui"],
  eslint: {
    dirs: ["app", "components", "lib"],
  },
  async headers() {
    return [
      {
        // Service Worker は毎回ネットワークから取り直す。
        // 古い SW が居座るとオフライン表示の鮮度ロジックまで古いままになる。
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.webmanifest",
        headers: [{ key: "Cache-Control", value: "public, max-age=3600" }],
      },
    ];
  },
};

export default nextConfig;
