import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { filings, filingSummary } from "../data/sample";

const docTypeColors: Record<string, string> = {
  "業績予想の修正": "badge-warning",
  "決算短信": "badge-info",
  "10-Q": "badge-neutral",
  "10-K": "badge-neutral",
  "自己株式の取得": "badge-info",
  "有価証券報告書": "badge-neutral",
};

const toneColors: Record<string, string> = {
  "前向き": "badge-success",
  "中立": "badge-neutral",
  "慎重": "badge-warning",
  "弱気": "badge-danger",
};

export default function FilingsHubPage() {
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scope, setScope] = useState("all");
  const [sort, setSort] = useState("info_value");

  const selected = filings.find(f => f.id === selectedId);
  const grouped: Record<string, typeof filings> = {};
  filings.forEach(f => {
    if (!grouped[f.date]) grouped[f.date] = [];
    grouped[f.date].push(f);
  });
  const dates = Object.keys(grouped).sort().reverse();

  return (
    <AppShell>
      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        {/* Filter rail */}
        <aside style={{
          width: 220, flexShrink: 0,
          background: "var(--bg-surface)", borderRight: "1px solid var(--border)",
          padding: "14px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 16,
        }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>スコープ</div>
            {[["all","すべて"],["watchlist","ウォッチリスト"],["holdings","保有銘柄"],["recommended","推奨銘柄"]].map(([v,l]) => (
              <button key={v} className={`chip ${scope === v ? "active" : ""}`}
                style={{ display: "block", width: "100%", marginBottom: 4, borderRadius: 3, textAlign: "left" }}
                onClick={() => setScope(v)}>{l}</button>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>書類種別</div>
            {["業績予想の修正","決算短信","有価証券報告書","自己株式の取得","10-Q","10-K","その他"].map((t) => (
              <label key={t} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 11, color: "var(--fg-secondary)", marginBottom: 4 }}>
                <input type="checkbox" defaultChecked style={{ accentColor: "var(--accent)" }} />{t}
              </label>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>その他</div>
            <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 11, color: "var(--fg-secondary)" }}>
              <input type="checkbox" style={{ accentColor: "var(--accent)" }} />要約があるものだけ
            </label>
          </div>
        </aside>

        {/* Feed */}
        <div style={{ width: 340, flexShrink: 0, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Header */}
          <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
              <h1 style={{ fontSize: 15, fontWeight: 700, margin: 0 }}>決算資料</h1>
              <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>48件（要約あり 31件）</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {[["info_value","情報価値順"],["filed_at","開示時刻順"]].map(([v,l]) => (
                <button key={v} className={`chip ${sort === v ? "active" : ""}`}
                  style={{ borderRadius: 3, fontSize: 11 }}
                  onClick={() => setSort(v)}>{l}</button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {dates.map(date => (
              <div key={date}>
                <div style={{
                  padding: "6px 14px", fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)",
                  background: "var(--bg)", borderBottom: "1px solid var(--border)",
                  position: "sticky", top: 0, zIndex: 1, letterSpacing: "0.06em",
                  display: "flex", justifyContent: "space-between",
                }}>
                  <span>{date.replace(/-/g, "年").replace(/(\d{2})$/, "$1日")} {date === "2026-08-22" ? "(金)" : "(木)"}</span>
                  <span>{grouped[date].length}件</span>
                </div>
                {grouped[date].map((f) => (
                  <div key={f.id}
                    style={{
                      padding: "8px 14px",
                      borderBottom: "1px solid var(--border)",
                      cursor: "pointer",
                      background: selectedId === f.id ? "var(--bg-elevated)" : "transparent",
                      borderLeft: selectedId === f.id ? "2px solid var(--accent)" : "2px solid transparent",
                    }}
                    onClick={() => setSelectedId(f.id)}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      <span style={{ fontFamily: "var(--font-data)", fontSize: 10, color: "var(--fg-tertiary)", width: 36 }}>{f.time}</span>
                      <span
                        style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11, cursor: "pointer" }}
                        onClick={(e) => { e.stopPropagation(); navigate(`/stocks/JP/${f.ticker}`); }}>
                        {f.ticker}
                      </span>
                      <span style={{ fontSize: 10, color: "var(--fg-secondary)" }}>{f.name}</span>
                    </div>
                    <div style={{ display: "flex", gap: 4, marginBottom: 4 }}>
                      <span className={`badge ${docTypeColors[f.docType] || "badge-neutral"}`}>{f.docType}</span>
                      <span className={`badge ${toneColors[f.tone] || "badge-neutral"}`}>{f.tone}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg)", lineHeight: 1.4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                      {f.title}
                    </div>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginTop: 3 }}>
                      {f.hasSummary ? "要約あり" : "要約なし（生成 推定 $0.008）"}
                      {f.localCopy && " · ローカル保存済み"}
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>

        {/* Detail pane */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          {!selected ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--fg-tertiary)", fontSize: 13 }}>
              左の一覧から資料を選択してください。
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              {/* Detail header */}
              <div>
                <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                  <span className={`badge ${docTypeColors[selected.docType] || "badge-neutral"}`}>{selected.docType}</span>
                  <span className={`badge ${toneColors[selected.tone] || "badge-neutral"}`}>{selected.tone}</span>
                </div>
                <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 4px" }}>{selected.title}</h2>
                <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>
                  <span style={{ fontFamily: "var(--font-data)", fontWeight: 600, color: "var(--accent)" }}>{selected.ticker}</span>
                  <span style={{ marginLeft: 6 }}>{selected.name}</span>
                  <span style={{ marginLeft: 12 }}>{selected.date} {selected.time} (JST)</span>
                  <span style={{ marginLeft: 12 }}>EDINET</span>
                </div>
              </div>

              {/* Actions */}
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-primary">資料を開く</button>
                <button className="btn btn-secondary">提供元サイトで開く</button>
                <button className="btn btn-ghost">リンクをコピー</button>
              </div>

              {/* Summary */}
              {selected.hasSummary && (
                <div className="card">
                  <div className="section-header">要約</div>
                  <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>
                      {filingSummary.model} · {filingSummary.generatedAt} · {filingSummary.cost} · プロンプト {filingSummary.promptVersion}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--fg)", lineHeight: 1.5 }}>
                      {filingSummary.headline}
                    </div>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>要点</div>
                      {filingSummary.keyPoints.map((p, i) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6, marginBottom: 4 }}>・{p}</div>
                      ))}
                    </div>
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 600, color: "var(--status-warning)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>開示されたリスク</div>
                      {filingSummary.risks.map((r, i) => (
                        <div key={i} style={{ fontSize: 12, color: "var(--fg-secondary)", lineHeight: 1.6, marginBottom: 4 }}>・{r}</div>
                      ))}
                    </div>
                    <div style={{ padding: "8px 12px", background: "var(--bg-elevated)", borderRadius: "var(--radius)" }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-secondary)", marginBottom: 4 }}>開示トーン: <span style={{ color: "var(--status-warning)" }}>{filingSummary.tone}</span></div>
                      <div style={{ fontSize: 11, color: "var(--fg-secondary)", lineHeight: 1.5 }}>{filingSummary.toneExplanation}</div>
                    </div>
                  </div>
                </div>
              )}

              {!selected.hasSummary && (
                <div className="card">
                  <div className="section-header">要約を生成</div>
                  <div style={{ padding: 14 }}>
                    <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginBottom: 8 }}>
                      推定コスト: $0.008（入力 42,800トークン / 出力 1,200トークン）
                    </div>
                    <div style={{ fontSize: 11, color: "var(--fg-tertiary)", marginBottom: 12 }}>
                      本日のLLM利用額: $0.48 / $1.50
                    </div>
                    <button className="btn btn-primary">生成する</button>
                  </div>
                </div>
              )}

              {/* Related */}
              <div className="card">
                <div className="section-header">関連</div>
                <div style={{ padding: 12 }}>
                  <div style={{ fontSize: 11, color: "var(--fg-secondary)", marginBottom: 6, cursor: "pointer" }}
                    onClick={() => navigate(`/stocks/JP/${selected.ticker}`)}>
                    → {selected.ticker} {selected.name} の銘柄詳細
                  </div>
                  <div style={{ fontSize: 11, color: "var(--fg-secondary)", cursor: "pointer" }}
                    onClick={() => navigate("/recommendations")}>
                    → 関連する推奨を見る
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
