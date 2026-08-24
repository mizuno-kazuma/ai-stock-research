import { useState } from "react";
import AppShell from "../components/AppShell";
import { fxData } from "../data/sample";
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";

const fanData = [
  { date: "8/22", actual: 152.34 },
  { date: "8/23", actual: null, p80l: 151.2, p80h: 153.5, p95l: 150.4, p95h: 154.6, median: 152.4 },
  { date: "8/26", actual: null, p80l: 150.8, p80h: 154.2, p95l: 149.6, p95h: 155.8, median: 152.5 },
  { date: "8/29", actual: null, p80l: 150.1, p80h: 154.9, p95l: 148.8, p95h: 156.6, median: 152.6 },
  { date: "9/5",  actual: null, p80l: 149.4, p80h: 155.8, p95l: 147.8, p95h: 157.8, median: 152.7 },
];

const rateDiffData = Array.from({ length: 60 }, (_, i) => ({
  date: `${i + 1}`,
  diff: 5.0 - i * 0.02 + Math.sin(i * 0.3) * 0.4,
  usdjpy: 148 + i * 0.08 + Math.sin(i * 0.2) * 1.5,
}));

export default function FxMacroPage() {
  const [tab, setTab] = useState("forecast");

  return (
    <AppShell>
      <div style={{ overflowY: "auto", height: "100%", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px" }}>為替・マクロ</h1>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>USD/JPY モデル予測 · 2026年8月22日 時点</div>
        </div>

        {/* BaselineVerdictPanel — MUST render first, before any forecast content */}
        <div className={`baseline-verdict ${fxData.hasEdge ? "edge" : "no-edge"}`}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: 280 }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6, opacity: 0.7 }}>
                ベースライン評価
              </div>
              <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.4, marginBottom: 8 }}>
                {fxData.verdictHeadline}
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
                {fxData.verdictBody}
              </div>
            </div>
            <div style={{ display: "flex", flex: "none", flexDirection: "column", gap: 8, minWidth: 260 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--fg-tertiary)" }}>Diebold-Mariano 統計量</span>
                <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>
                  {fxData.dmStat} (p={fxData.dmPvalue})
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--fg-tertiary)" }}>モデル RMSE (5日)</span>
                <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{fxData.modelRmse}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "var(--fg-tertiary)" }}>ランダムウォーク RMSE</span>
                <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{fxData.baselineRmse}</span>
              </div>
              <div style={{ fontSize: 10, color: "var(--fg-tertiary)", lineHeight: 1.5 }}>{fxData.rmseNote}</div>
            </div>
          </div>
        </div>

        <div className="tab-bar">
          {[["forecast","予測・シナリオ"],["models","モデル比較"],["macro","マクロ指標"],["sensitivity","感応度分析"]].map(([v,l]) => (
            <button key={v} className={`tab-item ${tab === v ? "active" : ""}`} onClick={() => setTab(v)}>{l}</button>
          ))}
        </div>

        {tab === "forecast" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card">
              <div className="section-header">USD/JPY 確率的予測ファン (5日先まで)</div>
              <div style={{ padding: "16px 16px 8px" }}>
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={fanData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} />
                    <YAxis domain={[147, 158]} tick={{ fontSize: 10, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={40} />
                    <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 11, fontFamily: "var(--font-data)" }} />
                    <Area type="monotone" dataKey="p95h" stroke="none" fill="rgba(59,130,246,0.08)" />
                    <Area type="monotone" dataKey="p95l" stroke="none" fill="var(--bg)" />
                    <Area type="monotone" dataKey="p80h" stroke="none" fill="rgba(59,130,246,0.18)" />
                    <Area type="monotone" dataKey="p80l" stroke="none" fill="var(--bg)" />
                    <Line type="monotone" dataKey="median" stroke="var(--accent)" strokeWidth={2} dot={false} strokeDasharray="6 3" />
                    <Line type="monotone" dataKey="actual" stroke="var(--fg)" strokeWidth={2} dot={{ r: 3, fill: "var(--fg)" }} connectNulls={false} />
                    <ReferenceLine y={152.34} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
                  </AreaChart>
                </ResponsiveContainer>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 8 }}>
                  青色帯: 80% / 95% 予測区間。実線: 実績値。破線: 予測中央値。
                </div>
              </div>
            </div>

            <div className="card">
              <div className="section-header">予測サマリー（ホライズン別）</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>予測期間</th>
                      <th>点推定値</th>
                      <th>80%区間</th>
                      <th>95%区間</th>
                      <th>的中率</th>
                      <th>評価</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fxData.forecasts.map((h) => (
                      <tr key={h.horizon}>
                        <td style={{ fontWeight: 600 }}>{h.horizon}</td>
                        <td style={{ fontFamily: "var(--font-data)", fontWeight: 700 }}>{h.point}</td>
                        <td style={{ fontFamily: "var(--font-data)", color: "var(--fg-secondary)" }}>{h.band80}</td>
                        <td style={{ fontFamily: "var(--font-data)", color: "var(--fg-secondary)" }}>{h.band95}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{h.hitRate} (n={h.hitN})</td>
                        <td><span className="badge badge-neutral">{h.verdict}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="section-header">日米金利差 vs USD/JPY (過去60営業日)</div>
              <div style={{ padding: "16px 16px 8px" }}>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={rateDiffData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" tick={false} />
                    <YAxis yAxisId="left" domain={[4, 6]} tick={{ fontSize: 10, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={32} />
                    <YAxis yAxisId="right" orientation="right" domain={[145, 158]} tick={{ fontSize: 10, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={40} />
                    <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 11 }} />
                    <Line yAxisId="left" type="monotone" dataKey="diff" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="日米金利差 (%)" />
                    <Line yAxisId="right" type="monotone" dataKey="usdjpy" stroke="var(--accent)" strokeWidth={1.5} dot={false} name="USD/JPY" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}

        {tab === "models" && (
          <div className="card">
            <div className="section-header">モデル比較</div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>モデル</th>
                    <th>RMSE (5日)</th>
                    <th>MAE</th>
                    <th>方向的中率</th>
                    <th>DM p値</th>
                    <th>評価</th>
                  </tr>
                </thead>
                <tbody>
                  {fxData.modelComparison.map((m) => (
                    <tr key={m.model}>
                      <td style={{ fontWeight: 600 }}>{m.model}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{m.rmse}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{m.mae}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{m.hitRate}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{m.dmPvalue}</td>
                      <td><span className="badge badge-neutral">{m.verdict}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "macro" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {fxData.macroSeries.map((s) => (
              <div key={s.id} className="card">
                <div style={{ padding: "12px 14px 10px" }}>
                  <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 4 }}>FRED · {s.vintage}</div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{s.labelJa}</div>
                  <div style={{ fontFamily: "var(--font-data)", fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{s.value}</div>
                  <div style={{ fontSize: 11, color: s.change.startsWith("+") ? "var(--up-jp)" : "var(--down-jp)" }}>{s.change}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "sensitivity" && (
          <div className="card">
            <div className="section-header">保有・ウォッチ銘柄の為替感応度</div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>銘柄</th>
                    <th>為替感応度 (β)</th>
                    <th>円安+5円の営業利益影響</th>
                    <th>20日リターン相関</th>
                    <th>感応度の種別</th>
                  </tr>
                </thead>
                <tbody>
                  {fxData.fxSensitivity.map((s) => (
                    <tr key={s.ticker}>
                      <td>
                        <span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11 }}>{s.ticker}</span>
                        <span style={{ fontSize: 11, color: "var(--fg-secondary)", marginLeft: 8 }}>{s.name}</span>
                        <span className={`badge badge-neutral`} style={{ marginLeft: 6 }}>{s.type}</span>
                      </td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{s.sensitivity}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{s.opImpact}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{s.corr}</td>
                      <td><span className={`badge ${s.verdict.includes("円安") ? "badge-info" : "badge-warning"}`}>{s.verdict}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
