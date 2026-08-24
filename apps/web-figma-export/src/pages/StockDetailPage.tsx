import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { stockDetail7203 } from "../data/sample";
import { ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from "recharts";

const priceData = Array.from({ length: 60 }, (_, i) => ({
  day: i + 1,
  price: 2900 + Math.sin(i * 0.15) * 180 + i * 3.8 + (Math.random() - 0.5) * 60,
  vol: Math.floor(Math.random() * 5000000 + 3000000),
}));

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 50 ? "score-mid" : "score-low";
  return <span className={`score-badge ${cls}`}>{score.toFixed(1)}</span>;
}

const tabs = ["価格", "ファクター", "財務", "開示資料", "推奨履歴", "保有・売買履歴"];

export default function StockDetailPage() {
  const { market, ticker } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("価格");
  const [range, setRange] = useState("1Y");
  const stock = stockDetail7203;

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
        {/* Sticky stock header */}
        <div style={{
          background: "var(--bg-surface)", borderBottom: "1px solid var(--border)",
          padding: "12px 24px", position: "sticky", top: 0, zIndex: 10,
        }}>
          {/* Breadcrumb */}
          <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 6, display: "flex", gap: 6 }}>
            <span style={{ cursor: "pointer" }} onClick={() => navigate("/screener")}>日本株</span>
            <span>›</span>
            <span style={{ cursor: "pointer" }}>輸送用機器</span>
            <span>›</span>
            <span style={{ color: "var(--fg-secondary)" }}>{ticker}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{
                fontFamily: "var(--font-data)", fontSize: 20, fontWeight: 800,
                color: "var(--accent)", background: "rgba(59,130,246,0.1)",
                padding: "2px 10px", borderRadius: "var(--radius)",
              }}>{ticker}</span>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "var(--fg)" }}>{stock.name}</div>
                <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>{stock.exchange} · {stock.sector}</div>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontFamily: "var(--font-data)", fontSize: 22, fontWeight: 700, color: "var(--fg)" }}>{stock.price}</div>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", alignItems: "center" }}>
                  <span className="dir-up" style={{ fontFamily: "var(--font-data)", fontSize: 13 }}>{stock.change}</span>
                  <span className="dir-up" style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>({stock.changeAbs})</span>
                </div>
                <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{stock.priceSource}</div>
              </div>
              <ScoreBadge score={stock.score} />
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-secondary" style={{ fontSize: 11 }}>ウォッチリスト追加</button>
                <button className="btn btn-primary" style={{ fontSize: 11 }}>売買記録を作成</button>
              </div>
            </div>
          </div>
        </div>

        {/* Tab bar */}
        <div className="tab-bar" style={{ padding: "0 24px", flexShrink: 0 }}>
          {tabs.map((t) => (
            <div key={t} className={`tab-item ${activeTab === t ? "active" : ""}`} onClick={() => setActiveTab(t)}>{t}</div>
          ))}
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
          {activeTab === "価格" && (
            <>
              {/* Chart section */}
              <div className="card">
                <div className="section-header">
                  価格チャート
                  <div style={{ display: "flex", gap: 4 }}>
                    {["1M","3M","6M","1Y","3Y","MAX"].map(r => (
                      <button key={r} className={`chip ${range === r ? "active" : ""}`}
                        style={{ borderRadius: 3, padding: "1px 7px" }}
                        onClick={() => setRange(r)}>{r}</button>
                    ))}
                  </div>
                </div>
                <div style={{ padding: "12px 16px" }}>
                  <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 8 }}>
                    リサーチ用データ（J-Quants 無料プラン・12週遅延）
                  </div>
                  <ResponsiveContainer width="100%" height={280}>
                    <ComposedChart data={priceData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="day" tick={{ fontSize: 10, fill: "var(--fg-tertiary)" }} />
                      <YAxis domain={["auto","auto"]} tick={{ fontSize: 10, fill: "var(--fg-tertiary)" }} />
                      <Tooltip contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 4, fontSize: 11 }} />
                      <Line type="monotone" dataKey="price" stroke="var(--accent)" strokeWidth={1.5} dot={false} name="価格" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Key metrics */}
              <div className="card">
                <div className="section-header">主要指標</div>
                <div style={{ padding: "8px 0" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
                    {stock.keyMetrics.map((m) => (
                      <div key={m.label} style={{
                        display: "flex", justifyContent: "space-between",
                        padding: "7px 16px", borderBottom: "1px solid var(--border)",
                      }}>
                        <span style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{m.label}</span>
                        <span style={{ fontFamily: "var(--font-data)", fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>{m.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === "ファクター" && (
            <div className="card">
              <div className="section-header">ファクター内訳</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ファクター</th>
                      <th>z-score</th>
                      <th>セクター内順位</th>
                      <th>実数値</th>
                      <th>スコア寄与</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { name: "バリュエーション", score: +1.42, pct: "上位 8% (12 / 148銘柄)", raw: "PER 11.2倍", contrib: "+11.4" },
                      { name: "クオリティ",       score: +0.88, pct: "上位 22%",              raw: "ROIC 12.4%", contrib: "+7.8" },
                      { name: "モメンタム",       score: +1.05, pct: "上位 15%",              raw: "12M +18.4%", contrib: "+9.2" },
                      { name: "成長",             score: +0.31, pct: "上位 38%",              raw: "EPS +8.2%",  contrib: "+2.8" },
                      { name: "予想改定",         score: +1.67, pct: "上位 5%",               raw: "+5.0% 上方修正", contrib: "+14.8" },
                      { name: "ボラティリティ",   score: -0.24, pct: "下位 42%",              raw: "22.4%",     contrib: "-2.1" },
                      { name: "流動性",           score: +0.92, pct: "上位 18%",              raw: "412億円/日", contrib: "+8.2" },
                    ].map((f) => (
                      <tr key={f.name}>
                        <td style={{ fontWeight: 500 }}>{f.name}</td>
                        <td>
                          <span className={f.score > 0 ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>
                            {f.score > 0 ? "+" : ""}{f.score.toFixed(2)}
                          </span>
                        </td>
                        <td style={{ color: "var(--fg-secondary)", fontSize: 11 }}>{f.pct}</td>
                        <td style={{ fontFamily: "var(--font-data)", fontSize: 11, color: "var(--fg-secondary)" }}>{f.raw}</td>
                        <td>
                          <span className={f.contrib.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontWeight: 600, fontSize: 11 }}>
                            {f.contrib}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ padding: "8px 16px", fontSize: 10, color: "var(--fg-tertiary)", borderTop: "1px solid var(--border)" }}>
                z-scoreはセクター内で中央値とMADを用いて標準化し、±3で切り詰めています。特徴量バージョン: v3 (2026年6月1日以降)
              </div>
            </div>
          )}

          {activeTab === "財務" && (
            <div className="card" style={{ overflow: "hidden" }}>
              <div className="section-header">財務サマリー</div>
              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 160 }}>指標</th>
                      {stock.financials.map((p) => (
                        <th key={p.period}>{p.period}<br/><span style={{ fontSize: 9, fontWeight: 400 }}>{p.filedAt} 開示</span></th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      { key: "revenue", label: "売上収益" },
                      { key: "opIncome", label: "営業利益" },
                      { key: "opMargin", label: "営業利益率" },
                      { key: "netIncome", label: "純利益" },
                      { key: "eps", label: "EPS" },
                      { key: "fcf", label: "フリーCF" },
                    ].map((row) => (
                      <tr key={row.key}>
                        <td style={{ fontWeight: 500, color: "var(--fg-secondary)" }}>{row.label}</td>
                        {stock.financials.map((p) => (
                          <td key={p.period} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>
                            {(p as any)[row.key]}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === "推奨履歴" && (
            <div className="card">
              <div className="section-header">推奨履歴</div>
              <div style={{ padding: "8px 16px", fontSize: 11, color: "var(--fg-secondary)", borderBottom: "1px solid var(--border)" }}>
                この銘柄の推奨 {stock.recHistory.length}件　的中率 62% (n=13)　平均超過リターン +1.4%
              </div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>生成日</th><th>区分</th><th>期間</th><th>確信度</th><th>予測</th><th>実績</th><th>判定</th>
                  </tr>
                </thead>
                <tbody>
                  {stock.recHistory.map((r, i) => (
                    <tr key={i}>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.date}</td>
                      <td><span className="badge badge-info">{r.action}</span></td>
                      <td style={{ color: "var(--fg-secondary)", fontSize: 11 }}>{r.horizon}</td>
                      <td style={{ color: "var(--fg-secondary)", fontSize: 11 }}>{r.conviction}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.expected}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>
                        {r.realized === "—" ? <span style={{ color: "var(--fg-tertiary)" }}>—</span> : (
                          <span className={r.realized.startsWith("+") ? "dir-up" : "dir-down"}>{r.realized}</span>
                        )}
                      </td>
                      <td>
                        {r.outcome === "hit" && <span className="badge badge-success">的中</span>}
                        {r.outcome === "miss" && <span className="badge badge-danger">外れ</span>}
                        {r.outcome === "pending" && <span className="badge badge-neutral">判定前（残り{r.pendingDays}営業日）</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "保有・売買履歴" && stock.position && (
            <div className="card">
              <div className="section-header">保有・売買履歴</div>
              <div style={{ padding: 16, display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 12 }}>
                {[
                  { label: "保有数量",     value: stock.position.quantity },
                  { label: "平均取得単価", value: stock.position.avgCost },
                  { label: "取得価額",     value: stock.position.bookValue },
                  { label: "評価額（参考）", value: stock.position.marketValue },
                  { label: "評価損益",     value: stock.position.unrealized },
                  { label: "ポートフォリオ比率", value: stock.position.weight },
                ].map((m) => (
                  <div key={m.label}>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 3 }}>{m.label}</div>
                    <div style={{ fontFamily: "var(--font-data)", fontSize: 14, fontWeight: 600, color: "var(--fg)" }}>{m.value}</div>
                  </div>
                ))}
              </div>
              <div style={{ padding: "4px 16px 12px", fontSize: 10, color: "var(--fg-tertiary)" }}>評価額は参考価格ベースです。</div>
            </div>
          )}

          {activeTab === "開示資料" && (
            <div className="card">
              <div className="section-header">開示資料</div>
              {[
                { date: "2026-08-08", type: "決算短信",     title: "2027年3月期 第1四半期決算短信〔IFRS〕(連結)", hasSummary: true },
                { date: "2026-06-24", type: "有価証券報告書", title: "第122期 有価証券報告書",                    hasSummary: true },
                { date: "2026-05-14", type: "業績予想の修正", title: "2027年3月期 通期業績予想の修正に関するお知らせ", hasSummary: false },
                { date: "2026-05-08", type: "決算短信",     title: "2026年3月期 決算短信〔IFRS〕(連結)",          hasSummary: true },
              ].map((f, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 12,
                  padding: "9px 16px", borderBottom: "1px solid var(--border)", cursor: "pointer",
                }}>
                  <span style={{ fontFamily: "var(--font-data)", fontSize: 11, color: "var(--fg-tertiary)", width: 80, flexShrink: 0 }}>{f.date}</span>
                  <span className={`badge ${f.type === "業績予想の修正" ? "badge-warning" : "badge-info"}`}>{f.type}</span>
                  <span style={{ flex: 1, fontSize: 12, color: "var(--fg)" }}>{f.title}</span>
                  {f.hasSummary
                    ? <button className="btn btn-ghost" style={{ fontSize: 11 }}>要約を見る</button>
                    : <button className="btn btn-ghost" style={{ fontSize: 11 }}>要約を生成</button>}
                  <button className="btn btn-secondary" style={{ fontSize: 11 }}>開く</button>
                </div>
              ))}
            </div>
          )}

          {/* Peer comparison — always shown */}
          <div className="card">
            <div className="section-header">同業比較</div>
            <div style={{ overflowX: "auto" }}>
              <table className="data-table">
                <thead>
                  <tr><th>銘柄</th><th>総合スコア</th><th>PER</th><th>PBR</th><th>ROIC</th><th>20営業日リターン</th><th>為替感応度</th></tr>
                </thead>
                <tbody>
                  {stock.peers.map((p) => (
                    <tr key={p.ticker} onClick={() => navigate(`/stocks/JP/${p.ticker}`)}>
                      <td><span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11 }}>{p.ticker}</span> <span style={{ color: "var(--fg-secondary)", fontSize: 11 }}>{p.name}</span></td>
                      <td><span className={`score-badge ${p.score >= 70 ? "score-high" : p.score >= 50 ? "score-mid" : "score-low"}`}>{p.score}</span></td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.per}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.pbr}</td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.roic}</td>
                      <td><span className={p.ret20.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{p.ret20}</span></td>
                      <td style={{ fontFamily: "var(--font-data)", fontSize: 11, color: "var(--fg-secondary)" }}>{p.fxSens}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ padding: "6px 16px", fontSize: 10, color: "var(--fg-tertiary)", borderTop: "1px solid var(--border)" }}>
              同一セクター内で時価総額が近い上位5銘柄を表示しています。
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
