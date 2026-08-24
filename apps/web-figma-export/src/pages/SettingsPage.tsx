import { useState } from "react";
import AppShell from "../components/AppShell";
import { settingsData } from "../data/sample";

const sections = [
  { id: "display",       label: "表示設定" },
  { id: "cost",          label: "コスト上限" },
  { id: "data",          label: "データソース" },
  { id: "analysis",      label: "分析設定" },
  { id: "notifications", label: "通知" },
  { id: "system",        label: "システム" },
];

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState("display");
  const [convention, setConvention] = useState<"jp" | "us">(
    settingsData.display.directionColors as "jp" | "us"
  );
  const d = settingsData;

  return (
    <AppShell>
      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        {/* Left nav */}
        <aside style={{
          width: 200, flexShrink: 0,
          background: "var(--bg-surface)", borderRight: "1px solid var(--border)",
          padding: "16px 0", display: "flex", flexDirection: "column",
        }}>
          {sections.map(s => (
            <button key={s.id}
              onClick={() => setActiveSection(s.id)}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "9px 16px", fontSize: 13, cursor: "pointer",
                background: activeSection === s.id ? "var(--bg-elevated)" : "transparent",
                borderLeft: activeSection === s.id ? "2px solid var(--accent)" : "2px solid transparent",
                color: activeSection === s.id ? "var(--fg)" : "var(--fg-secondary)",
                border: "none",
                fontFamily: "var(--font-ui)",
              } as React.CSSProperties}>
              {s.label}
            </button>
          ))}
        </aside>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px" }}>
          <div style={{ maxWidth: 720, display: "flex", flexDirection: "column", gap: 24 }}>

            {activeSection === "display" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>表示設定</h2>

                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>方向色の規則</div>
                  <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginBottom: 16 }}>
                    日本株モード（赤=上昇・青=下落）または米国株モード（緑=上昇・赤=下落）を選択してください。
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {[
                      {
                        id: "jp", title: "日本株モード",
                        rows: [
                          { ticker: "7203 トヨタ", val: "3,125 +1.2%", up: true },
                          { ticker: "6758 ソニー", val: "12,840 −0.8%", up: false },
                        ],
                        upColor: "#ef4444", downColor: "#60a5fa",
                      },
                      {
                        id: "us", title: "米国株モード",
                        rows: [
                          { ticker: "AAPL", val: "$214.32 +1.2%", up: true },
                          { ticker: "NVDA", val: "$118.50 −0.8%", up: false },
                        ],
                        upColor: "#22c55e", downColor: "#ef4444",
                      },
                    ].map(opt => (
                      <div key={opt.id}
                        onClick={() => setConvention(opt.id as "jp" | "us")}
                        style={{
                          padding: 14, borderRadius: "var(--radius)", cursor: "pointer",
                          border: `2px solid ${convention === opt.id ? "var(--accent)" : "var(--border)"}`,
                          background: convention === opt.id ? "rgba(59,130,246,0.06)" : "var(--bg-elevated)",
                        }}>
                        <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{opt.title}</div>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font-data)" }}>
                          <tbody>
                            {opt.rows.map(r => (
                              <tr key={r.ticker}>
                                <td style={{ padding: "2px 4px", color: "var(--fg-secondary)" }}>{r.ticker}</td>
                                <td style={{ padding: "2px 4px", color: r.up ? opt.upColor : opt.downColor, fontWeight: 600 }}>{r.val}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="card" style={{ padding: 20 }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>表示テーマ</label>
                      <select className="input" style={{ width: 200 }} defaultValue={d.display.theme}>
                        <option value="dark">ダーク（固定）</option>
                      </select>
                    </div>
                    <div>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>デフォルト市場</label>
                      <select className="input" style={{ width: 200 }} defaultValue={d.display.defaultMarket}>
                        <option value="jp">日本株</option>
                        <option value="us">米国株</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "cost" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>コスト上限</h2>
                <div style={{ padding: "8px 12px", background: "var(--status-info-bg)", border: "1px solid var(--status-info)", borderRadius: "var(--radius)", fontSize: 11, color: "var(--fg-secondary)", marginBottom: 16, lineHeight: 1.5 }}>
                  上限に達するとパイプラインが自動停止します。緊急停止はエージェントコンソールからも操作できます。
                </div>
                <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  {[
                    { label: "1日あたりのLLM上限 (USD)", cap: d.cost.dailyCap },
                    { label: "1ヶ月あたりのLLM上限 (USD)", cap: d.cost.monthlyCap },
                  ].map(c => (
                    <div key={c.label}>
                      <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>{c.label}</label>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontFamily: "var(--font-data)", fontSize: 12 }}>$</span>
                        <input className="input" type="number" defaultValue={c.cap} style={{ width: 120 }} />
                      </div>
                    </div>
                  ))}
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 4 }}>通知閾値 (%)</label>
                    <input className="input" type="number" defaultValue={d.cost.alertThreshold} style={{ width: 120 }} />
                  </div>
                  <button className="btn btn-primary" style={{ alignSelf: "flex-start" }}>保存</button>
                </div>
              </div>
            )}

            {activeSection === "data" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>データソース</h2>
                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 12 }}>J-Quants プラン</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {["free","light","standard","premium"].map(plan => (
                      <button key={plan} className={`chip ${d.data.jquantsPlan === plan ? "active" : ""}`}>
                        {plan === "free" ? "無料" : plan === "light" ? "ライト" : plan === "standard" ? "スタンダード" : "プレミアム"}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="card">
                  <div className="section-header">データソース一覧</div>
                  <div style={{ overflowX: "auto" }}>
                    <table className="data-table">
                      <thead>
                        <tr><th>ソース</th><th>ステータス</th><th>最終取得</th><th>APIキー</th></tr>
                      </thead>
                      <tbody>
                        {d.system.dataSources.map(s => (
                          <tr key={s.id}>
                            <td style={{ fontWeight: 600 }}>{s.label}</td>
                            <td>
                              <span className={`badge ${s.status === "正常" ? "badge-success" : s.status === "無効" ? "badge-neutral" : "badge-warning"}`}>
                                {s.status}
                              </span>
                            </td>
                            <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{s.latest}</td>
                            <td style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{s.apiKey}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}

            {activeSection === "analysis" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>分析設定</h2>
                <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>デフォルト予測期間</label>
                    <select className="input" style={{ width: 200 }} defaultValue={d.analysis.defaultHorizon}>
                      <option value="H5">5営業日</option>
                      <option value="H20">20営業日</option>
                      <option value="H60">60営業日</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>1セクターあたりの最大推奨数</label>
                    <input className="input" type="number" defaultValue={d.analysis.maxPerSector} style={{ width: 120 }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>ウェイト変更の承認方法</label>
                    <select className="input" style={{ width: 200 }} defaultValue={d.analysis.weightApproval}>
                      <option value="manual">手動承認</option>
                      <option value="auto">自動承認</option>
                    </select>
                  </div>
                  <button className="btn btn-primary" style={{ alignSelf: "flex-start" }}>保存</button>
                </div>
              </div>
            )}

            {activeSection === "notifications" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>通知</h2>
                <div className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
                  {[
                    { label: "パイプライン失敗時に通知",         val: d.notifications.batchFailure },
                    { label: "データが古くなったとき",           val: d.notifications.dataStale },
                    { label: "コスト閾値到達時",                 val: d.notifications.costThreshold },
                    { label: "保有銘柄の決算資料が開示されたとき", val: d.notifications.filingForHoldings },
                    { label: "決算発表が5営業日以内に迫ったとき",  val: d.notifications.earningsApproaching },
                    { label: "推奨の見通しが変更されたとき",      val: d.notifications.viewChanged },
                    { label: "Webプッシュ通知を受け取る",        val: d.notifications.webPush },
                  ].map((n, i) => (
                    <label key={i} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 12 }}>
                      <input type="checkbox" defaultChecked={n.val} style={{ accentColor: "var(--accent)" }} />
                      {n.label}
                    </label>
                  ))}
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 600, display: "block", marginBottom: 6 }}>通知を止める時間帯</label>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                      <input className="input" defaultValue={d.notifications.quietFrom} style={{ width: 80 }} />
                      <span style={{ color: "var(--fg-tertiary)" }}>〜</span>
                      <input className="input" defaultValue={d.notifications.quietTo} style={{ width: 80 }} />
                    </div>
                  </div>
                  <button className="btn btn-primary" style={{ alignSelf: "flex-start" }}>保存</button>
                </div>
              </div>
            )}

            {activeSection === "system" && (
              <div>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 20px" }}>システム</h2>
                <div className="card" style={{ padding: 20, marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>緊急停止スイッチ</div>
                  <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginBottom: 12, lineHeight: 1.5 }}>
                    すべてのLLM呼び出しとパイプライン実行を即座に停止します。エージェントコンソールのコストタブからも操作できます。
                  </div>
                  <button className="btn btn-danger">停止する (Kill Switch)</button>
                </div>
                <div className="card">
                  <div className="section-header">バージョン情報</div>
                  <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    {[
                      { label: "アプリバージョン", value: `v${d.system.version}` },
                      { label: "コミット",         value: d.system.commit },
                      { label: "Python",           value: d.system.python },
                      { label: "Node.js",          value: d.system.node },
                      { label: "OS",               value: d.system.wsl },
                      { label: "最終バックアップ", value: d.system.lastBackup },
                      { label: "DBサイズ",         value: d.system.dbSizes },
                    ].map(i => (
                      <div key={i.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, gap: 16 }}>
                        <span style={{ color: "var(--fg-secondary)", flexShrink: 0 }}>{i.label}</span>
                        <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)", textAlign: "right" }}>{i.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </AppShell>
  );
}
