import { useState } from "react";
import AppShell from "../components/AppShell";
import { portfolioData } from "../data/sample";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";

const emotionMap: Record<string, { label: string; color: string }> = {
  confident:  { label: "自信あり", color: "var(--status-success)" },
  neutral:    { label: "平常",     color: "var(--accent)" },
  fomo:       { label: "乗り遅れ懸念", color: "var(--status-danger)" },
  fearful:    { label: "不安",     color: "var(--status-warning)" },
  disciplined:{ label: "規律",     color: "var(--status-success)" },
};

const perfData = Array.from({ length: 60 }, (_, i) => ({
  d: i,
  portfolio: 100 + i * 0.15 + Math.sin(i * 0.3) * 2.5,
  benchmark: 100 + i * 0.08 + Math.sin(i * 0.25) * 1.8,
}));

const PIE_COLORS = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316"];

export default function PortfolioPage() {
  const [tab, setTab] = useState("positions");
  const d = portfolioData;

  const allocationData = d.positions.map(p => ({
    name: p.ticker,
    value: parseFloat(p.value.replace(/[¥,$,円,\s]/g, "").replace(/,/g, "")) || 0,
  }));

  return (
    <AppShell>
      <div style={{ overflowY: "auto", height: "100%", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px" }}>ポートフォリオ</h1>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>個人ポートフォリオ · 2026年8月22日 時点</div>
        </div>

        {/* Summary bar */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {[
            { label: "評価総額", value: d.totalValue, color: "var(--fg)" },
            { label: "含み損益 (累計)", value: d.unrealized, color: "var(--status-success)" },
            { label: "確定損益 (今年)", value: d.realizedYTD, color: "var(--status-success)" },
            { label: "現金",   value: d.cash, color: "var(--fg)" },
          ].map(m => (
            <div key={m.label} className="metric-card">
              <div className="metric-label">{m.label}</div>
              <div className="metric-value" style={{ fontFamily: "var(--font-data)", color: m.color, fontSize: 14 }}>{m.value}</div>
            </div>
          ))}
        </div>

        <div className="tab-bar">
          {[["positions","保有"],["journal","売買日誌"],["analysis","分析"]].map(([v,l]) => (
            <button key={v} className={`tab-item ${tab === v ? "active" : ""}`} onClick={() => setTab(v)}>{l}</button>
          ))}
        </div>

        {tab === "positions" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card">
              <div className="section-header">パフォーマンス推移 (過去60営業日)</div>
              <div style={{ padding: "16px 16px 8px" }}>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={perfData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="d" tick={false} />
                    <YAxis domain={[95, 115]} tick={{ fontSize: 9, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={36} />
                    <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 11 }} />
                    <Line type="monotone" dataKey="portfolio" stroke="var(--accent)" strokeWidth={2} dot={false} name="ポートフォリオ" />
                    <Line type="monotone" dataKey="benchmark" stroke="var(--fg-tertiary)" strokeWidth={1.5} dot={false} strokeDasharray="4 4" name="TOPIX" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 16 }}>
              <div className="card">
                <div className="section-header">配分</div>
                <div style={{ padding: "8px" }}>
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie data={allocationData} cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2} dataKey="value">
                        {allocationData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                      </Pie>
                      <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 10 }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="card">
                <div className="section-header">保有銘柄一覧</div>
                <div style={{ overflowX: "auto" }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>銘柄</th>
                        <th>参考価格</th>
                        <th>株数</th>
                        <th>平均取得</th>
                        <th>評価額</th>
                        <th>含損益</th>
                        <th>スコア</th>
                        <th>見通し</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.positions.map(p => {
                        const isProfit = p.unrealized.startsWith("+");
                        return (
                          <tr key={p.ticker}>
                            <td>
                              <div style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11 }}>{p.ticker}</div>
                              <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{p.name}</div>
                            </td>
                            <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.refPrice}</td>
                            <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.qty}</td>
                            <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.avgCost}</td>
                            <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.value}</td>
                            <td>
                              <span className={isProfit ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.unrealized}</span>
                            </td>
                            <td>
                              <span className={`score-badge ${p.score >= 70 ? "score-high" : p.score >= 50 ? "score-mid" : "score-low"}`}>{p.score}</span>
                            </td>
                            <td style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{p.view || "—"}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div style={{ padding: "6px 16px", fontSize: 10, color: "var(--fg-tertiary)", borderTop: "1px solid var(--border)" }}>
                  参考価格は yfinance の15分遅延値です。
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === "journal" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button className="btn btn-primary">+ 売買記録を追加</button>
            </div>
            {d.trades.map((t) => {
              const emo = emotionMap[t.emotion] || { label: t.emotionLabel, color: "var(--fg-secondary)" };
              return (
                <div key={t.id} className="card">
                  <div style={{ padding: "12px 16px", display: "flex", gap: 14, alignItems: "flex-start" }}>
                    <div style={{ width: 4, flexShrink: 0, alignSelf: "stretch", borderRadius: 2, background: emo.color }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", gap: 8, marginBottom: 4, flexWrap: "wrap", alignItems: "center" }}>
                        <span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 13 }}>{t.ticker}</span>
                        <span className={`badge ${t.side === "買い" ? "badge-success" : "badge-danger"}`}>{t.side}</span>
                        <span className="badge badge-neutral" style={{ borderColor: emo.color, color: emo.color }}>{emo.label}</span>
                        <span style={{ fontFamily: "var(--font-data)", fontSize: 11, color: "var(--fg-tertiary)" }}>{t.date} {t.time}</span>
                        {!t.linked && <span className="badge badge-warning">推奨外</span>}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--fg)", lineHeight: 1.6, marginBottom: 4 }}>{t.thesis}</div>
                      {t.exitPlan && (
                        <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginBottom: 4 }}>撤退計画: {t.exitPlan}</div>
                      )}
                      <div style={{ display: "flex", gap: 16, fontSize: 11, color: "var(--fg-tertiary)" }}>
                        <span>数量: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)" }}>{t.qty}</span></span>
                        <span>価格: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)" }}>{t.price}</span></span>
                        <span>手数料: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)" }}>{t.fee}</span></span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tab === "analysis" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div className="card">
                <div className="section-header">感情タグ別 損益</div>
                <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    { emotion: "自信あり", trades: 12, avgPl: "+2.4%", totalPl: "+186,400円", color: "var(--status-success)" },
                    { emotion: "平常",     trades: 8,  avgPl: "+1.8%", totalPl: "+98,200円",  color: "var(--accent)" },
                    { emotion: "乗り遅れ懸念", trades: 4, avgPl: "-1.2%", totalPl: "-38,600円", color: "var(--status-danger)" },
                    { emotion: "不安",     trades: 3,  avgPl: "-0.8%", totalPl: "-18,900円",  color: "var(--status-warning)" },
                  ].map(e => (
                    <div key={e.emotion} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ width: 8, height: 8, borderRadius: "50%", background: e.color, flexShrink: 0 }} />
                      <span style={{ width: 96, fontSize: 11, color: "var(--fg-secondary)" }}>{e.emotion}</span>
                      <span style={{ fontSize: 11, color: "var(--fg-tertiary)", width: 32 }}>{e.trades}件</span>
                      <span style={{ fontFamily: "var(--font-data)", fontSize: 11, color: e.avgPl.startsWith("+") ? "var(--status-success)" : "var(--status-danger)" }}>{e.avgPl}</span>
                      <span style={{ fontFamily: "var(--font-data)", fontSize: 11, color: e.totalPl.startsWith("+") ? "var(--status-success)" : "var(--status-danger)", marginLeft: "auto" }}>{e.totalPl}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="card">
                <div className="section-header">保有期間分析</div>
                <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                  {[
                    { label: "平均保有期間", value: "18.4日" },
                    { label: "利確の平均保有", value: "22.1日" },
                    { label: "損切の平均保有", value: "8.6日" },
                    { label: "損切率", value: "28.5%" },
                    { label: "プロフィットファクター", value: "1.62" },
                    { label: "最大連敗", value: "3連敗" },
                  ].map(m => (
                    <div key={m.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                      <span style={{ color: "var(--fg-secondary)" }}>{m.label}</span>
                      <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{m.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
