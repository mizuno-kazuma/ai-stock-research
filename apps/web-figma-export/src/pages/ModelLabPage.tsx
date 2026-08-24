import { useState } from "react";
import AppShell from "../components/AppShell";
import { modelHealthData } from "../data/sample";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ComposedChart, Line, ReferenceLine, Cell,
} from "recharts";

export default function ModelLabPage() {
  const [tab, setTab] = useState("health");

  const d = modelHealthData;
  const icSeriesWithDate = d.icSeries.map((x) => ({ ...x, date: `D${x.day}` }));

  return (
    <AppShell>
      <div style={{ overflowY: "auto", height: "100%", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px" }}>モデルラボ</h1>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>ファクターモデル v2.3 · 最終学習: 2026-08-20 02:14 JST</div>
        </div>

        <div className="tab-bar">
          {[["health","モデルの状態"],["runs","学習履歴"],["backtests","バックテスト"],["weights","ファクター重み"]].map(([v,l]) => (
            <button key={v} className={`tab-item ${tab === v ? "active" : ""}`} onClick={() => setTab(v)}>{l}</button>
          ))}
        </div>

        {tab === "health" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {[
                { label: "Rank IC (60日平均)", value: d.rankIC20.toFixed(3), sub: "p=0.04", status: "success" },
                { label: "IC IR", value: "0.42", sub: "目標 >0.40", status: "success" },
                { label: "カバレッジ", value: d.coverage, sub: d.coverageDetail, status: "success" },
                { label: "IC正値日比率", value: d.positivePct, sub: "直近60日", status: "warning" },
              ].map((m) => (
                <div key={m.label} className="metric-card">
                  <div className="metric-label">{m.label}</div>
                  <div className="metric-value" style={{ color: `var(--status-${m.status})`, fontFamily: "var(--font-data)" }}>{m.value}</div>
                  <div className="metric-sub">{m.sub}</div>
                </div>
              ))}
            </div>

            {/* Calibration note — always visible as text */}
            <div style={{ padding: "8px 14px", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: "var(--radius)", fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>
              Rank IC 0.03 前後はこの種のモデルとして現実的な水準です。IC &gt; 0.10 が続く場合はデータリークを疑ってください。
            </div>

            <div className="card">
              <div className="section-header">IC 時系列 (過去30営業日)</div>
              <div style={{ padding: "16px 16px 8px" }}>
                <ResponsiveContainer width="100%" height={200}>
                  <ComposedChart data={icSeriesWithDate} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" tick={{ fontSize: 9, fill: "var(--fg-tertiary)" }} interval={4} />
                    <YAxis domain={[-0.1, 0.12]} tick={{ fontSize: 9, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={36} />
                    <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 11 }} />
                    <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                    <ReferenceLine y={0.03} stroke="var(--status-success)" strokeDasharray="4 4" strokeOpacity={0.5} />
                    <Bar dataKey="ic" radius={[1,1,0,0]}>
                      {icSeriesWithDate.map((entry, i) => (
                        <Cell key={i} fill={entry.ic >= 0 ? "var(--status-success)" : "var(--status-danger)"} opacity={0.7} />
                      ))}
                    </Bar>
                    <Line type="monotone" dataKey="rolling" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="section-header">クインタイル平均超過収益 (年率換算・直近60日)</div>
              <div style={{ padding: "16px 16px 8px" }}>
                <ResponsiveContainer width="100%" height={160}>
                  <BarChart data={d.quintile} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="q" tick={{ fontSize: 10, fill: "var(--fg-tertiary)" }} />
                    <YAxis tick={{ fontSize: 9, fill: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }} width={36} />
                    <Tooltip contentStyle={{ background: "var(--bg-surface)", border: "1px solid var(--border)", fontSize: 11 }} />
                    <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />
                    <Bar dataKey="ret" radius={[2,2,0,0]}>
                      {d.quintile.map((entry, i) => (
                        <Cell key={i} fill={entry.ret >= 0 ? "var(--status-success)" : "var(--status-danger)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <div className="section-header">フィーチャー重要度 (上位10)</div>
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
                {d.featureImportance.map((f) => (
                  <div key={f.name} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 220, fontSize: 11, color: "var(--fg-secondary)", flexShrink: 0 }}>{f.label}</div>
                    <div style={{ flex: 1, height: 8, background: "var(--bg-elevated)", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{ width: `${f.value * 100 / 0.142}%`, height: "100%", background: "var(--accent)", borderRadius: 2 }} />
                    </div>
                    <div style={{ width: 40, fontFamily: "var(--font-data)", fontSize: 11, textAlign: "right", color: "var(--fg-secondary)" }}>
                      {(f.value * 100).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="section-header">リークチェック</div>
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 6 }}>
                {d.leakageChecks.map((c) => (
                  <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ fontSize: 14, color: c.status === "pass" ? "var(--status-success)" : "var(--status-danger)" }}>
                      {c.status === "pass" ? "✓" : "✗"}
                    </span>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>{c.label}</div>
                      {c.detail && <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>{c.detail}</div>}
                    </div>
                    <span className={`badge ${c.status === "pass" ? "badge-success" : "badge-danger"}`}>
                      {c.status === "pass" ? "合格" : "要確認"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {tab === "runs" && (
          <div className="card">
            <div className="section-header">学習履歴</div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr><th>実行ID</th><th>日時</th><th>ステータス</th><th>Val AUC</th><th>IC (60日)</th><th>時間</th></tr>
                </thead>
                <tbody>
                  {[
                    { id: "run_024", dt: "2026-08-20 02:14", ok: true,  auc: "0.561", ic: "0.031", dur: "48分" },
                    { id: "run_023", dt: "2026-08-13 02:11", ok: true,  auc: "0.558", ic: "0.029", dur: "47分" },
                    { id: "run_022", dt: "2026-08-06 02:09", ok: true,  auc: "0.554", ic: "0.028", dur: "49分" },
                    { id: "run_021", dt: "2026-07-30 02:14", ok: false, auc: "—",     ic: "—",     dur: "12分" },
                    { id: "run_020", dt: "2026-07-23 02:10", ok: true,  auc: "0.551", ic: "0.027", dur: "46分" },
                  ].map(r => (
                    <tr key={r.id}>
                      <td style={{ fontFamily: "var(--font-data)", color: "var(--accent)" }}>{r.id}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.dt}</td>
                      <td><span className={`badge ${r.ok ? "badge-success" : "badge-danger"}`}>{r.ok ? "成功" : "失敗"}</span></td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{r.auc}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{r.ic}</td>
                      <td style={{ fontFamily: "var(--font-data)" }}>{r.dur}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === "backtests" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {/* Cost assumptions MUST come before any return figures */}
            <div style={{ padding: "12px 16px", background: "var(--status-warning-bg)", border: "1px solid var(--status-warning)", borderRadius: "var(--radius)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--status-warning)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                コスト前提（すべてのリターンはこの前提に基づく）
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, fontSize: 11, color: "var(--fg-secondary)" }}>
                <div>往片道手数料: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)", fontWeight: 600 }}>5.0bp</span></div>
                <div>スリッページ: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)", fontWeight: 600 }}>10.0bp</span></div>
                <div>税引前ベース: <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)", fontWeight: 600 }}>はい</span></div>
              </div>
            </div>

            <div className="card">
              <div className="section-header">バックテスト結果</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>戦略名</th>
                      <th>期間</th>
                      <th>年率超過収益</th>
                      <th>シャープ比</th>
                      <th>最大DD</th>
                      <th>回転率/月</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.backtests.map((b) => (
                      <tr key={b.id}>
                        <td style={{ fontWeight: 600 }}>{b.name}</td>
                        <td style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{b.period}</td>
                        <td>
                          <span className={b.annReturn.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontWeight: 700 }}>
                            {b.annReturn}
                          </span>
                        </td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{b.sharpe}</td>
                        <td style={{ fontFamily: "var(--font-data)", color: "var(--status-danger)" }}>{b.maxDD}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{b.turn}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: "6px 16px 10px", fontSize: 10, color: "var(--fg-tertiary)" }}>
                過去のパフォーマンスは将来を保証しません。上記はすべて税引前・コスト控除後の参考値です。
              </div>
            </div>
          </div>
        )}

        {tab === "weights" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ padding: "8px 12px", background: "var(--status-info-bg)", border: "1px solid var(--status-info)", borderRadius: "var(--radius)", fontSize: 11, color: "var(--fg-secondary)" }}>
              ウェイト変更後は次の週次再学習（毎週水曜 02:00 JST）に反映されます。
              <span style={{ marginLeft: 8, color: "var(--fg-tertiary)" }}>{d.weights.fitMeta}</span>
            </div>
            <div className="card">
              <div className="section-header">ファクターウェイト一覧（現行: {d.weights.active} / 提案: {d.weights.proposed}）</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr><th>ファクターグループ</th><th>現行ウェイト</th><th>提案ウェイト</th><th>変化</th><th>操作</th></tr>
                  </thead>
                  <tbody>
                    {d.weights.groups.map((w) => (
                      <tr key={w.name}>
                        <td style={{ fontWeight: 600 }}>{w.name}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{(w.active * 100).toFixed(0)}%</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{(w.proposed * 100).toFixed(0)}%</td>
                        <td>
                          <span style={{ fontFamily: "var(--font-data)", color: w.delta > 0 ? "var(--status-success)" : w.delta < 0 ? "var(--status-warning)" : "var(--fg-tertiary)" }}>
                            {w.delta === 0 ? "変更なし" : `${w.delta > 0 ? "+" : ""}${(w.delta * 100).toFixed(0)}pp`}
                          </span>
                        </td>
                        <td onClick={e => e.stopPropagation()}>
                          {w.delta !== 0 && (
                            <div style={{ display: "flex", gap: 4 }}>
                              <button className="btn btn-success" style={{ fontSize: 10, padding: "3px 8px" }}>承認</button>
                              <button className="btn btn-danger" style={{ fontSize: 10, padding: "3px 8px" }}>却下</button>
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
