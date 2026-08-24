import React, { useState } from "react";
import AppShell from "../components/AppShell";
import { agentData } from "../data/sample";

export default function AgentConsolePage() {
  const [tab, setTab] = useState("jobs");
  const [killActive, setKillActive] = useState(agentData.cost.killSwitch);
  const d = agentData;

  return (
    <AppShell>
      <div style={{ overflowY: "auto", height: "100%", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 4px" }}>エージェントコンソール</h1>
          <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
            スケジューラ: <span style={{ color: d.schedulerAlive ? "var(--status-success)" : "var(--status-danger)", fontWeight: 600 }}>{d.schedulerAlive ? "稼働中" : "停止"}</span>
            <span style={{ marginLeft: 12 }}>次回実行: {d.nextRun}</span>
            <span style={{ marginLeft: 12 }}>稼働時間: {d.uptime}</span>
          </div>
        </div>

        <div className="tab-bar">
          {[["jobs","ジョブ"],["cost","コスト"],["critic","レビュー"],["memory","教訓"]].map(([v,l]) => (
            <button key={v} className={`tab-item ${tab === v ? "active" : ""}`} onClick={() => setTab(v)}>{l}</button>
          ))}
        </div>

        {tab === "jobs" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card">
              <div className="section-header">本日のパイプライン</div>
              <div style={{ padding: "16px", display: "flex", alignItems: "center", gap: 4, overflowX: "auto" }}>
                {d.jobs.map((job, i) => (
                  <React.Fragment key={job.name}>
                    <div className="job-pill" style={{
                      background: job.status === "success" ? "rgba(34,197,94,0.1)" : job.status === "partial" ? "rgba(245,158,11,0.1)" : "rgba(239,68,68,0.1)",
                      borderColor: job.status === "success" ? "var(--status-success)" : job.status === "partial" ? "var(--status-warning)" : "var(--status-danger)",
                      flexShrink: 0,
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: job.status === "success" ? "var(--status-success)" : job.status === "partial" ? "var(--status-warning)" : "var(--status-danger)" }} />
                        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>{job.name}</span>
                      </div>
                      <div style={{ fontSize: 10, color: "var(--fg-tertiary)", fontFamily: "var(--font-data)" }}>{job.time} · {job.duration}</div>
                    </div>
                    {i < d.jobs.length - 1 && (
                      <span style={{ color: "var(--fg-tertiary)", fontSize: 14, flexShrink: 0 }}>→</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="section-header">実行ログ</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr><th>ジョブ</th><th>ステータス</th><th>開始</th><th>所要時間</th><th>出力</th><th>詳細</th></tr>
                  </thead>
                  <tbody>
                    {d.jobs.map(job => (
                      <tr key={job.name}>
                        <td style={{ fontWeight: 600 }}>{job.name}</td>
                        <td>
                          <span className={`badge ${job.status === "success" ? "badge-success" : job.status === "partial" ? "badge-warning" : "badge-danger"}`}>
                            {job.status === "success" ? "成功" : job.status === "partial" ? "部分成功" : "失敗"}
                          </span>
                        </td>
                        <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{job.time}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{job.duration}</td>
                        <td style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{job.output}</td>
                        <td><button className="btn btn-ghost" style={{ fontSize: 10, padding: "3px 8px" }}>ログ表示</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="section-header">手動実行</div>
              <div style={{ padding: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {d.jobs.map(job => (
                  <button key={job.name} className="btn btn-secondary" style={{ fontSize: 11 }}>
                    {job.name}
                  </button>
                ))}
                <button className="btn btn-primary" style={{ fontSize: 11 }}>パイプライン全体を実行</button>
              </div>
            </div>
          </div>
        )}

        {tab === "cost" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              {[
                { label: "本日のLLMコスト", value: d.cost.today, cap: `上限 ${d.cost.todayCap}`, pct: d.cost.todayPct },
                { label: "今月のLLMコスト", value: d.cost.month, cap: `上限 ${d.cost.monthCap}`, pct: d.cost.monthPct },
                { label: "今月の予測額", value: d.cost.projection, cap: "月末予測", pct: null },
              ].map(m => (
                <div key={m.label} className="metric-card">
                  <div className="metric-label">{m.label}</div>
                  <div className="metric-value" style={{ fontFamily: "var(--font-data)" }}>{m.value}</div>
                  <div className="metric-sub">{m.cap}</div>
                  {m.pct !== null && (
                    <div style={{ marginTop: 8, height: 4, background: "var(--bg-elevated)", borderRadius: 2, overflow: "hidden" }}>
                      <div style={{
                        width: `${Math.min(m.pct, 100)}%`,
                        height: "100%",
                        background: m.pct > 80 ? "var(--status-danger)" : m.pct > 60 ? "var(--status-warning)" : "var(--status-success)",
                        borderRadius: 2,
                      }} />
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Kill switch */}
            <div className={`kill-switch-banner ${killActive ? "active" : ""}`}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>緊急停止スイッチ (Kill Switch)</div>
                  <div style={{ fontSize: 12, opacity: 0.85, lineHeight: 1.5 }}>
                    {killActive
                      ? "LLM呼び出しを停止中です。パイプラインは無効化されています。"
                      : "有効にするとすべてのLLM呼び出しとパイプラインを即座に停止します。"}
                  </div>
                </div>
                <button
                  className={`btn ${killActive ? "btn-success" : "btn-danger"}`}
                  style={{ flexShrink: 0, padding: "10px 20px", fontSize: 13, fontWeight: 700 }}
                  onClick={() => setKillActive(k => !k)}>
                  {killActive ? "再開する" : "停止する"}
                </button>
              </div>
            </div>

            <div className="card">
              <div className="section-header">コスト内訳</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr><th>用途</th><th>金額</th><th>割合</th><th>キャッシュヒット</th></tr>
                  </thead>
                  <tbody>
                    {d.cost.breakdown.map((b) => (
                      <tr key={b.purpose}>
                        <td>{b.purpose}</td>
                        <td style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{b.amount}</td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ width: 60, height: 4, background: "var(--bg-elevated)", borderRadius: 2, overflow: "hidden" }}>
                              <div style={{ width: `${b.pct}%`, height: "100%", background: "var(--accent)", borderRadius: 2 }} />
                            </div>
                            <span style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{b.pct}%</span>
                          </div>
                        </td>
                        <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{b.cacheHit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <div className="section-header">LLM呼び出し明細（本日）</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr><th>時刻</th><th>用途</th><th>モデル</th><th>入力Tok</th><th>出力Tok</th><th>コスト</th><th>ステータス</th></tr>
                  </thead>
                  <tbody>
                    {d.cost.calls.map((c, i) => (
                      <tr key={i}>
                        <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{c.time}</td>
                        <td>{c.purpose}</td>
                        <td style={{ fontFamily: "var(--font-data)", fontSize: 10 }}>{c.model}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{c.input.toLocaleString()}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{c.output.toLocaleString()}</td>
                        <td style={{ fontFamily: "var(--font-data)" }}>{c.cost}</td>
                        <td><span className="badge badge-success">{c.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {tab === "critic" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              {[
                { label: "却下率", value: d.criticStats.rejectionRate, sub: d.criticStats.rejectionN },
                { label: "修正率", value: d.criticStats.revisionRate, sub: d.criticStats.revisionN },
                { label: "主な却下理由", value: "—", sub: d.criticStats.topReason },
              ].map(m => (
                <div key={m.label} className="metric-card">
                  <div className="metric-label">{m.label}</div>
                  <div className="metric-value" style={{ fontFamily: "var(--font-data)" }}>{m.value}</div>
                  <div className="metric-sub">{m.sub}</div>
                </div>
              ))}
            </div>
            <div className="card">
              <div className="section-header">却下理由の内訳</div>
              <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                {d.criticStats.reasons.map(r => {
                  const total = d.criticStats.reasons.reduce((s, x) => s + x.count, 0);
                  const pct = Math.round(r.count / total * 100);
                  return (
                    <div key={r.code} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ width: 220, fontSize: 11, color: "var(--fg-secondary)", flexShrink: 0 }}>{r.label}</div>
                      <div style={{ flex: 1, height: 8, background: "var(--bg-elevated)", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ width: `${pct}%`, height: "100%", background: "var(--status-danger)", borderRadius: 2 }} />
                      </div>
                      <div style={{ width: 36, fontFamily: "var(--font-data)", fontSize: 11, textAlign: "right", color: "var(--fg-secondary)" }}>{r.count}件</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {tab === "memory" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" placeholder="教訓を検索..." style={{ flex: 1 }} />
              <select className="input" style={{ width: "auto" }}>
                <option>すべての種別</option>
                <option>偏り</option>
                <option>パターン</option>
                <option>注意点</option>
              </select>
            </div>
            {d.memory.map(m => (
              <div key={m.id} className="card" style={{ opacity: m.active ? 1 : 0.5 }}>
                <div style={{ padding: "12px 16px", display: "flex", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", gap: 6, marginBottom: 6, flexWrap: "wrap", alignItems: "center" }}>
                      <span className="badge badge-neutral">{m.category}</span>
                      <span style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{m.scope}</span>
                      <span className={`badge ${m.active ? "badge-success" : "badge-neutral"}`}>{m.active ? "有効" : "無効"}</span>
                      {m.harmful && <span className="badge badge-danger">有害・無効化済み</span>}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--fg)", lineHeight: 1.6, marginBottom: 6 }}>{m.text}</div>
                    <div style={{ fontSize: 11, color: "var(--fg-tertiary)", lineHeight: 1.5 }}>
                      <div>証拠: {m.evidence}</div>
                      <div>有効性: {m.effect}</div>
                      <div>更新: {m.updatedAt} · {m.usage}</div>
                    </div>
                  </div>
                  <button className={`btn ${m.active ? "btn-ghost" : "btn-secondary"}`} style={{ fontSize: 11, flexShrink: 0 }}>
                    {m.active ? "無効化" : "有効化"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
