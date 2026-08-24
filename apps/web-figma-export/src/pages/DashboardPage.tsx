import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { jobs, metrics, recommendations, alerts, filingsToday, watchlist, fxSnapshot, modelHealth } from "../data/sample";
import { LineChart, Line, ResponsiveContainer } from "recharts";

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 50 ? "score-mid" : "score-low";
  return <span className={`score-badge ${cls}`}>{score.toFixed(1)}</span>;
}

function DirectionValue({ value, change, up }: { value: string; change: string; up: boolean }) {
  return (
    <span className={up ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>
      {change.startsWith("+") ? "" : ""}{change}
    </span>
  );
}

function JobStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = { success: "badge-success", partial: "badge-warning", failed: "badge-danger", running: "badge-info" };
  const labelMap: Record<string, string> = { success: "成功", partial: "部分", failed: "失敗", running: "実行中" };
  return <span className={`badge ${map[status] || "badge-neutral"}`}>{labelMap[status] || status}</span>;
}

function DocTypeBadge({ type }: { type: string }) {
  const map: Record<string, string> = {
    "業績予想の修正": "badge-warning",
    "決算短信": "badge-info",
    "10-Q": "badge-neutral",
    "10-K": "badge-neutral",
    "自己株式の取得": "badge-info",
    "有価証券報告書": "badge-neutral",
  };
  return <span className={`badge ${map[type] || "badge-neutral"}`}>{type}</span>;
}

const sparkData = fxSnapshot.sparkData.map((v, i) => ({ v, i }));

export default function DashboardPage() {
  const navigate = useNavigate();
  const [expandedBear, setExpandedBear] = useState<string | null>(null);
  const displayed = recommendations.filter(r => r.criticVerdict !== "rejected").slice(0, 3);

  return (
    <AppShell>
      <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: "var(--fg)" }}>ダッシュボード</h1>
            <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginTop: 2 }}>2026年8月22日 (金) 時点</div>
          </div>
          <button className="btn btn-secondary">更新</button>
        </div>

        {/* Job status strip */}
        <div className="card" style={{ padding: "10px 14px" }}>
          <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
            直近の実行: 2026年8月22日 06:47 (JST)
          </div>
          <div style={{ display: "flex", gap: 8, overflowX: "auto" }}>
            {jobs.map((job) => (
              <div key={job.nameEn} className="job-pill" style={{ cursor: "pointer" }}
                onClick={() => navigate("/agent")}>
                <span className="job-pill-name">{job.nameEn}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <JobStatusBadge status={job.status} />
                  <span className="job-pill-meta">{job.time}</span>
                </div>
                <span className="job-pill-meta">{job.duration}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Metric cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
          {[
            { ...metrics.topix,    clickPath: undefined },
            { ...metrics.usdjpy,   clickPath: "/macro" },
            { ...metrics.portfolio, clickPath: "/portfolio" },
            { ...metrics.pnl,      clickPath: "/portfolio" },
          ].map((m) => (
            <div key={m.label} className="metric-card"
              onClick={() => m.clickPath && navigate(m.clickPath)}
              style={{ cursor: m.clickPath ? "pointer" : "default" }}>
              <div className="metric-label">{m.label}</div>
              <div className="metric-value">{m.value}</div>
              <div className="metric-sub">
                <span className={m.change.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)" }}>
                  {m.change}
                </span>
                {m.changeAbs && <span style={{ color: "var(--fg-tertiary)", marginLeft: 4, fontFamily: "var(--font-data)", fontSize: 10 }}>({m.changeAbs})</span>}
                <div style={{ color: "var(--fg-tertiary)", fontSize: 10, marginTop: 2 }}>{m.asOf}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Row: recommendations + alerts */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
          {/* Recommendation highlights */}
          <div className="card">
            <div className="section-header">
              本日の注目
              <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => navigate("/recommendations")}>
                すべての推奨を見る →
              </button>
            </div>
            <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
              {displayed.map((rec) => (
                <div key={rec.id}
                  style={{
                    padding: 12,
                    background: "var(--bg-elevated)",
                    borderRadius: "var(--radius)",
                    border: "1px solid var(--border)",
                    cursor: "pointer",
                  }}
                  onClick={() => navigate(`/stocks/${rec.market}/${rec.ticker}`)}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 13 }}>{rec.ticker}</span>
                      <span style={{ fontSize: 12, color: "var(--fg)" }}>{rec.name}</span>
                      <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{rec.sector}</span>
                    </div>
                    <ScoreBadge score={rec.quantScore} />
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                    <span className="badge badge-info">{rec.actionLabel}</span>
                    <span className="badge badge-neutral">{rec.horizonLabel}</span>
                    <span className="badge badge-neutral">{rec.convictionLabel}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginBottom: 4, fontFamily: "var(--font-data)" }}>
                    期待超過リターン <span className="dir-up">{rec.expectedReturn}</span> {rec.interval}　的中率 {rec.hitRate} (n={rec.hitN})
                  </div>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 6 }}>
                    {rec.reasonCodes.slice(0, 3).map((c) => (
                      <span key={c.label} className={`chip ${c.tone}`}>{c.label}</span>
                    ))}
                  </div>
                  {/* Bear case always visible */}
                  <div className="bear-case-panel" style={{ marginTop: 4 }}>
                    <div style={{ fontSize: 10, fontWeight: 600, color: "var(--status-warning)", marginBottom: 3, textTransform: "uppercase", letterSpacing: "0.06em" }}>弱気論拠</div>
                    <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.5 }}>
                      {rec.bearCase.length > 120 ? rec.bearCase.slice(0, 120) + "…" : rec.bearCase}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Alert feed */}
          <div className="card" style={{ display: "flex", flexDirection: "column" }}>
            <div className="section-header">
              アラート
              <button className="btn btn-ghost" style={{ fontSize: 11 }}>すべて既読にする</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto" }}>
              {alerts.map((a) => (
                <div key={a.id} style={{
                  display: "flex", alignItems: "flex-start", gap: 8,
                  padding: "8px 12px",
                  borderBottom: "1px solid var(--border)",
                  cursor: "pointer",
                }}>
                  <span style={{
                    width: 7, height: 7, borderRadius: "50%", flexShrink: 0, marginTop: 4,
                    background: a.severity === "danger" ? "var(--status-danger)" : a.severity === "warning" ? "var(--status-warning)" : "var(--status-info)",
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, color: "var(--fg)", lineHeight: 1.4 }}>{a.title}</div>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-data)", marginTop: 2 }}>{a.time}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Row: filings + watchlist */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* Filings today */}
          <div className="card">
            <div className="section-header">
              本日の開示
              <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => navigate("/filings")}>すべて見る →</button>
            </div>
            <div>
              {filingsToday.slice(0, 5).map((f, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "flex-start", gap: 10,
                  padding: "8px 12px",
                  borderBottom: "1px solid var(--border)",
                  cursor: "pointer",
                }}>
                  <span style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-data)", width: 36, flexShrink: 0, paddingTop: 2 }}>{f.time}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                      <span style={{ fontFamily: "var(--font-data)", fontSize: 11, fontWeight: 600, color: "var(--accent)" }}>{f.ticker}</span>
                      <span style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{f.name}</span>
                      <DocTypeBadge type={f.docType} />
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg)", lineHeight: 1.4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.title}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Watchlist table */}
          <div className="card" style={{ overflow: "hidden" }}>
            <div className="section-header">
              ウォッチリスト
              <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => navigate("/screener")}>すべて見る →</button>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>銘柄</th>
                    <th>参考価格</th>
                    <th>前日比</th>
                    <th>スコア</th>
                    <th>決算</th>
                    <th>開示</th>
                  </tr>
                </thead>
                <tbody>
                  {watchlist.map((w) => (
                    <tr key={w.ticker} onClick={() => navigate(`/stocks/JP/${w.ticker}`)}>
                      <td>
                        <span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11 }}>{w.ticker}</span>
                        <span style={{ marginLeft: 6, fontSize: 11, color: "var(--fg-secondary)" }}>{w.name}</span>
                      </td>
                      <td><span style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{w.price}</span></td>
                      <td>
                        <span className={w.change.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>
                          {w.change}
                        </span>
                      </td>
                      <td><ScoreBadge score={w.score} /></td>
                      <td><span style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{w.earnings}</span></td>
                      <td>
                        {w.filings > 0
                          ? <span className="badge badge-info">{w.filings}</span>
                          : <span style={{ color: "var(--fg-tertiary)" }}>—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "6px 12px", fontSize: 10, color: "var(--fg-tertiary)", borderTop: "1px solid var(--border)" }}>
              参考価格は yfinance の15分遅延値です。約定価格には使用できません。
            </div>
          </div>
        </div>

        {/* Row: FX + Model health */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* FX snapshot */}
          <div className="card" onClick={() => navigate("/macro")} style={{ cursor: "pointer" }}>
            <div className="section-header">為替</div>
            <div style={{ padding: 14 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10, marginBottom: 8 }}>
                <span style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-data)", color: "var(--fg)" }}>{fxSnapshot.current}</span>
                <span className="dir-up" style={{ fontFamily: "var(--font-data)", fontSize: 13 }}>{fxSnapshot.change}</span>
              </div>
              <div style={{ height: 40, marginBottom: 10 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sparkData}>
                    <Line type="monotone" dataKey="v" stroke="var(--accent)" strokeWidth={1.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div style={{ fontSize: 11, color: "var(--fg-secondary)" }}>
                5営業日先予測: <span style={{ fontFamily: "var(--font-data)" }}>{fxSnapshot.forecast}</span>
                <span style={{ color: "var(--fg-tertiary)", marginLeft: 4 }}>{fxSnapshot.interval}</span>
              </div>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 4, lineHeight: 1.4 }}>{fxSnapshot.verdict}</div>
            </div>
          </div>

          {/* Model health */}
          <div className="card" onClick={() => navigate("/model-lab")} style={{ cursor: "pointer" }}>
            <div className="section-header">モデルの状態</div>
            <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { label: "Rank IC (直近20営業日)", value: modelHealth.rankIC20.toFixed(3), status: "neutral" },
                { label: "傾向", value: modelHealth.trendNote, status: "neutral", small: true },
                { label: "対象銘柄カバー率", value: modelHealth.coverage, sub: modelHealth.coverageDetail },
                { label: "成績低下の検出", value: modelHealth.degradation, status: "success" },
              ].map((m) => (
                <div key={m.label} style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  padding: "6px 0", borderBottom: "1px solid var(--border)",
                }}>
                  <span style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{m.label}</span>
                  <span style={{
                    fontSize: m.small ? 10 : 12,
                    fontFamily: !m.small ? "var(--font-data)" : undefined,
                    color: m.status === "success" ? "var(--status-success)" : "var(--fg)",
                    fontWeight: 600,
                    textAlign: "right",
                    maxWidth: "55%",
                  }}>{m.value}</span>
                </div>
              ))}
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", lineHeight: 1.5 }}>
                Rank IC 0.03 前後はこの種のモデルとして現実的な水準です。
              </div>
            </div>
          </div>
        </div>

      </div>
    </AppShell>
  );
}
