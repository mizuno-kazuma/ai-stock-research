import type { NextConfig } from "next";

/** Next.js から見た FastAPI。ブラウザには出さない。 */
const API_INTERNAL_ORIGIN = (
  process.env.API_INTERNAL_ORIGIN ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Phase A では WSL2 上の standalone サーバとして起動する（docs/01-architecture.md §3）
  output: "standalone",
  transpilePackages: ["@ai-stock/ui"],
  // Tailscale Serve / MagicDNS から dev の /_next を読めるようにする
  allowedDevOrigins: ["*.ts.net", "desktop-5vdan61", "100.72.249.69"],
  eslint: {
    dirs: ["app", "components", "lib"],
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_INTERNAL_ORIGIN}/api/v1/:path*`,
      },
    ];
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
