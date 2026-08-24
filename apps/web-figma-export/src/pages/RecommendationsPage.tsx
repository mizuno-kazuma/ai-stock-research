import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { recommendations } from "../data/sample";

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 50 ? "score-mid" : "score-low";
  return <span className={`score-badge ${cls}`}>{score.toFixed(1)}</span>;
}

function CriticBadge({ verdict, label }: { verdict: string; label: string }) {
  const cls = verdict === "approved" ? "badge-success" : verdict === "revised" ? "badge-warning" : "badge-danger";
  return <span className={`badge ${cls}`}>{label}</span>;
}

export default function RecommendationsPage() {
  const navigate = useNavigate();
  const [horizon, setHorizon] = useState("all");
  const [conviction, setConviction] = useState("all");
  const [criticFilter, setCriticFilter] = useState<string[]>(["approved", "revised"]);
  const [expandedBear] = useState<Set<string>>(new Set());

  const filtered = recommendations.filter(r => {
    if (conviction !== "all" && r.conviction !== conviction) return false;
    if (!criticFilter.includes(r.criticVerdict)) return false;
    return true;
  });

  const toggleCritic = (v: string) => {
    setCriticFilter(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v]);
  };

  return (
    <AppShell>
      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        {/* Filter rail */}
        <aside style={{
          width: 220, flexShrink: 0,
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border)",
          padding: "16px 14px",
          overflowY: "auto",
          display: "flex", flexDirection: "column", gap: 20,
        }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>予測期間</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {[["all","すべて"],["H5","5営業日"],["H20","20営業日"]].map(([v,l]) => (
                <button key={v} className={`chip ${horizon === v ? "active" : ""}`}
                  style={{ justifyContent: "flex-start", borderRadius: 3 }}
                  onClick={() => setHorizon(v)}>{l}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>確信度</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {[["all","すべて"],["high","高"],["medium","中"],["low","低"]].map(([v,l]) => (
                <button key={v} className={`chip ${conviction === v ? "active" : ""}`}
                  style={{ justifyContent: "flex-start", borderRadius: 3 }}
                  onClick={() => setConviction(v)}>{l}</button>
              ))}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>レビュー結果</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {[["approved","承認"],["revised","修正"],["rejected","却下"]].map(([v,l]) => (
                <label key={v} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 12, color: "var(--fg-secondary)" }}>
                  <input type="checkbox" checked={criticFilter.includes(v)}
                    onChange={() => toggleCritic(v)}
                    style={{ accentColor: "var(--accent)" }} />
                  {l}
                </label>
              ))}
            </div>
            <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 8, lineHeight: 1.5 }}>
              Criticが却下した推奨も学習のため保存されています。
            </div>
          </div>
          <button className="btn btn-ghost" style={{ fontSize: 11, justifyContent: "center" }}
            onClick={() => { setHorizon("all"); setConviction("all"); setCriticFilter(["approved","revised"]); }}>
            条件をリセット
          </button>
        </aside>

        {/* Main */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>推奨銘柄</h1>
              <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginTop: 2 }}>
                {filtered.length}件（承認 {filtered.filter(r=>r.criticVerdict==="approved").length} / 修正 {filtered.filter(r=>r.criticVerdict==="revised").length}）
              </div>
            </div>
          </div>

          {/* Disclaimer */}
          <div style={{
            padding: "8px 12px", background: "var(--status-neutral-bg)",
            border: "1px solid var(--border)", borderRadius: "var(--radius)",
            fontSize: 11, color: "var(--fg-tertiary)", lineHeight: 1.5,
          }}>
            本画面は投資判断の材料を提示するものです。売買の指示ではありません。予測には必ず不確実性があります。
          </div>

          {/* Recommendation cards */}
          {filtered.map((rec) => (
            <div key={rec.id} className="card">
              {/* Card header */}
              <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span
                      style={{ fontFamily: "var(--font-data)", fontWeight: 800, color: "var(--accent)", fontSize: 16, cursor: "pointer" }}
                      onClick={() => navigate(`/stocks/${rec.market}/${rec.ticker}`)}>
                      {rec.ticker}
                    </span>
                    <span style={{ fontSize: 15, fontWeight: 600, color: "var(--fg)" }}>{rec.name}</span>
                    <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>{rec.sector}</span>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>定量 <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)", fontWeight: 600 }}>{rec.quantScore}</span></span>
                    {rec.qualDelta !== undefined && (
                      <span style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>定性 <span className={rec.qualDelta >= 0 ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{rec.qualDelta >= 0 ? "+" : ""}{rec.qualDelta}</span></span>
                    )}
                    <ScoreBadge score={rec.quantScore} />
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                  <span className="badge badge-info">{rec.actionLabel}</span>
                  <span className="badge badge-neutral">{rec.horizonLabel}</span>
                  <span className="badge badge-neutral">{rec.convictionLabel}</span>
                  <CriticBadge verdict={rec.criticVerdict} label={rec.criticLabel} />
                </div>
              </div>

              <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
                {/* Forecast */}
                <div style={{ background: "var(--bg-elevated)", borderRadius: "var(--radius)", padding: "10px 14px" }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
                    期待超過リターン ({rec.horizonLabel})
                  </div>
                  <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "baseline" }}>
                    <span className={rec.expectedReturn.startsWith("+") ? "dir-up" : "dir-down"}
                      style={{ fontFamily: "var(--font-data)", fontSize: 18, fontWeight: 700 }}>
                      {rec.expectedReturn}
                    </span>
                    <span style={{ fontFamily: "var(--font-data)", fontSize: 12, color: "var(--fg-secondary)" }}>{rec.interval}</span>
                    <span style={{ fontSize: 11, color: "var(--fg-secondary)" }}>的中率 <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{rec.hitRate}</span> (n={rec.hitN})</span>
                  </div>
                </div>

                {/* Reason codes */}
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {rec.reasonCodes.map((c) => (
                    <span key={c.label} className={`chip ${c.tone}`}>{c.label}</span>
                  ))}
                </div>

                {/* Thesis */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>強気論拠</div>
                  <div className="thesis-panel" style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>{rec.thesis}</div>
                </div>

                {/* Bear case — ALWAYS VISIBLE */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--status-warning)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>弱気論拠</div>
                  <div className="bear-case-panel" style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>{rec.bearCase}</div>
                </div>

                {/* Invalidation */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6 }}>この見立てを捨てる条件</div>
                  <div className="invalidation-panel" style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6 }}>{rec.invalidation}</div>
                </div>

                {/* Factor scores */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>ファクター内訳</div>
                  <div style={{ overflowX: "auto" }}>
                    <table className="data-table">
                      <thead>
                        <tr><th>ファクター</th><th>z-score</th><th>セクター内順位</th><th>実数値</th></tr>
                      </thead>
                      <tbody>
                        {rec.factors.map((f) => (
                          <tr key={f.name}>
                            <td>{f.name}</td>
                            <td>
                              <span className={f.score > 0 ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)" }}>
                                {f.score > 0 ? "+" : ""}{f.score.toFixed(2)}
                              </span>
                            </td>
                            <td style={{ color: "var(--fg-secondary)" }}>{f.pct}</td>
                            <td style={{ color: "var(--fg-secondary)", fontFamily: "var(--font-data)", fontSize: 11 }}>{f.raw}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 6 }}>セクター内で中央値・MADを用いて標準化したz-scoreです。</div>
                </div>

                {/* Citations */}
                {rec.citations.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
                      根拠資料 ({rec.citations.length}件)
                    </div>
                    {rec.citations.map((c, i) => (
                      <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                        <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginBottom: 4 }}>
                          {c.date} · {c.docType} · {c.title} · {c.page}
                          <span className="badge badge-success" style={{ marginLeft: 8 }}>検証済み</span>
                        </div>
                        <div style={{ fontSize: 11, color: "var(--fg)", padding: "6px 10px", background: "var(--bg-elevated)", borderRadius: "var(--radius)", fontStyle: "italic" }}>
                          「{c.quote}」
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Reference price */}
                <div style={{
                  display: "flex", gap: 16, padding: "8px 12px",
                  background: "var(--bg-elevated)", borderRadius: "var(--radius)",
                  fontSize: 11, flexWrap: "wrap",
                }}>
                  <div>
                    <span style={{ color: "var(--fg-tertiary)" }}>参考価格 </span>
                    <span style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{rec.refPrice}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--fg-tertiary)" }}>参考目標 </span>
                    <span className="dir-up" style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{rec.refTarget}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--fg-tertiary)" }}>撤退目安 </span>
                    <span className="dir-down" style={{ fontFamily: "var(--font-data)", fontWeight: 600 }}>{rec.refStop}</span>
                  </div>
                  <div style={{ color: "var(--fg-tertiary)", fontSize: 10 }}>約定価格には使用できません</div>
                </div>

                {/* Critic note */}
                {rec.criticNote && (
                  <div style={{
                    padding: "8px 12px", border: "1px solid var(--border)", borderRadius: "var(--radius)",
                    background: rec.criticVerdict === "rejected" ? "var(--status-danger-bg)" : "var(--status-warning-bg)",
                  }}>
                    <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4,
                      color: rec.criticVerdict === "rejected" ? "var(--status-danger)" : "var(--status-warning)" }}>
                      レビュー結果
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{rec.criticNote}</div>
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 4 }}>
                  <button className="btn btn-secondary">ウォッチリストに追加</button>
                  <button className="btn btn-secondary">売買記録を作成</button>
                  <button className="btn btn-primary" onClick={() => navigate(`/stocks/${rec.market}/${rec.ticker}`)}>銘柄詳細へ</button>
                  <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <button className="btn btn-ghost" style={{ fontSize: 11 }}>参考になった</button>
                    <button className="btn btn-ghost" style={{ fontSize: 11 }}>参考にならなかった</button>
                  </div>
                </div>
              </div>
            </div>
          ))}

          {filtered.length === 0 && (
            <div style={{ textAlign: "center", padding: 40, color: "var(--fg-secondary)" }}>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>条件に一致する推奨がありません</div>
              <div style={{ fontSize: 12 }}>絞り込み条件を変更してください。</div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
