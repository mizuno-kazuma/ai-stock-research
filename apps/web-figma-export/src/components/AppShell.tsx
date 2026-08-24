import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

const navItems = [
  { path: "/",           icon: "⊞", label: "ダッシュボード",  en: "Dashboard" },
  { path: "/recommendations", icon: "★", label: "推奨銘柄",   en: "Recommendations" },
  { path: "/screener",   icon: "⊟", label: "スクリーナー",    en: "Screener" },
  { path: "/filings",    icon: "□", label: "決算資料",        en: "Filings" },
  { path: "/macro",      icon: "~", label: "為替・マクロ",     en: "FX & Macro" },
  { path: "/model-lab",  icon: "◈", label: "モデルラボ",      en: "Model Lab" },
  { path: "/agent",      icon: "▶", label: "エージェント",     en: "Agent" },
  { path: "/portfolio",  icon: "◎", label: "ポートフォリオ",   en: "Portfolio" },
  { path: "/settings",   icon: "⚙", label: "設定",            en: "Settings" },
];

interface AppShellProps {
  children: React.ReactNode;
  convention?: "jp" | "us";
}

export default function AppShell({ children, convention = "jp" }: AppShellProps) {
  const location = useLocation();
  const [market, setMarket] = useState<"JP" | "US">("JP");

  return (
    <div
      style={{ display: "flex", height: "100vh", overflow: "hidden" }}
      data-convention={convention}
    >
      {/* Sidebar */}
      <nav style={{
        width: "var(--sidebar-width)",
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        overflow: "hidden",
      }}>
        {/* Logo */}
        <div style={{
          padding: "16px 16px 14px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: 4,
            background: "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 700, color: "#fff", flexShrink: 0,
          }}>AI</div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--fg)", lineHeight: 1.2 }}>AIリサーチ</div>
            <div style={{ fontSize: 9, color: "var(--fg-tertiary)", lineHeight: 1.2 }}>RESEARCH TERMINAL</div>
          </div>
        </div>

        {/* Nav items */}
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
          {navItems.map((item) => {
            const active = item.path === "/"
              ? location.pathname === "/"
              : location.pathname.startsWith(item.path);
            return (
              <Link key={item.path} to={item.path} style={{ textDecoration: "none" }}>
                <div style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "7px 14px",
                  margin: "1px 6px",
                  borderRadius: "var(--radius)",
                  background: active ? "rgba(59,130,246,0.12)" : "transparent",
                  borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                  cursor: "pointer",
                  transition: "background 0.1s",
                }}>
                  <span style={{
                    fontSize: 13,
                    color: active ? "var(--accent)" : "var(--fg-tertiary)",
                    width: 16,
                    textAlign: "center",
                    flexShrink: 0,
                  }}>{item.icon}</span>
                  <div>
                    <div style={{
                      fontSize: 12,
                      fontWeight: active ? 600 : 400,
                      color: active ? "var(--fg)" : "var(--fg-secondary)",
                      lineHeight: 1.3,
                    }}>{item.label}</div>
                    <div style={{ fontSize: 9, color: "var(--fg-tertiary)", lineHeight: 1.2 }}>{item.en}</div>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>

        {/* Bottom info */}
        <div style={{
          padding: "10px 14px",
          borderTop: "1px solid var(--border)",
          fontSize: 10,
          color: "var(--fg-tertiary)",
        }}>
          <div>v0.9.2 · 2026-08-22</div>
          <div style={{ marginTop: 2, color: "var(--status-success)", display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--status-success)", display: "inline-block" }} />
            スケジューラ稼働中
          </div>
        </div>
      </nav>

      {/* Main area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
        {/* Top bar */}
        <header style={{
          height: "var(--header-height)",
          background: "var(--bg-surface)",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          flexShrink: 0,
          gap: 16,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Market switch */}
            <div style={{
              display: "flex",
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-strong)",
              borderRadius: "var(--radius)",
              overflow: "hidden",
            }}>
              {(["JP", "US"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMarket(m)}
                  style={{
                    padding: "4px 14px",
                    fontSize: 11,
                    fontWeight: 600,
                    border: "none",
                    cursor: "pointer",
                    background: market === m ? "var(--accent)" : "transparent",
                    color: market === m ? "#fff" : "var(--fg-secondary)",
                    transition: "background 0.15s",
                  }}
                >
                  {m === "JP" ? "日本株" : "米国株"}
                </button>
              ))}
            </div>
            <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
              2026年8月22日 (金) 時点
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* Freshness */}
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, color: "var(--status-success)" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--status-success)", display: "inline-block" }} />
              データ最新
            </div>
            {/* Alert bell */}
            <div style={{ position: "relative", cursor: "pointer" }}>
              <span style={{ fontSize: 16, color: "var(--fg-secondary)" }}>🔔</span>
              <span style={{
                position: "absolute", top: -4, right: -4,
                width: 14, height: 14, borderRadius: "50%",
                background: "var(--status-danger)",
                color: "#fff", fontSize: 9, fontWeight: 700,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>3</span>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main style={{ flex: 1, overflowY: "auto", overflowX: "hidden" }}>
          {children}
        </main>
      </div>
    </div>
  );
}
