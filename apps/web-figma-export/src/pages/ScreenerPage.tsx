import { useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { screenerResults } from "../data/sample";

const presets = [
  { id: "value_quality",       label: "割安クオリティ",     desc: "セクター内で割安かつROICが高い銘柄" },
  { id: "revision_momentum",   label: "上方修正モメンタム", desc: "会社予想が上方修正され、モメンタムも強い銘柄" },
  { id: "weak_yen",            label: "円安メリット",       desc: "円安局面で恩恵を受けやすい銘柄" },
  { id: "strong_yen",          label: "円高メリット",       desc: "円高局面で恩恵を受けやすい銘柄" },
  { id: "low_vol_dividend",    label: "低ボラ配当",         desc: "ボラティリティが低く配当利回りが高い銘柄" },
  { id: "pre_earnings",        label: "決算前チェック",     desc: "5営業日以内に決算発表がある保有・ウォッチ銘柄" },
  { id: "high_growth",         label: "高成長",             desc: "売上・EPSがともに15%以上成長" },
  { id: "value_trap_warning",  label: "バリュートラップ注意", desc: "割安だがクオリティが低く、利益の質にも懸念がある銘柄", warn: true },
];

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 70 ? "score-high" : score >= 50 ? "score-mid" : "score-low";
  return <span className={`score-badge ${cls}`}>{score.toFixed(1)}</span>;
}

type Filter = { field: string; operator: string; value: string };

export default function ScreenerPage() {
  const navigate = useNavigate();
  const [activePreset, setActivePreset] = useState<string | null>("value_quality");
  const [filters, setFilters] = useState<Filter[]>([
    { field: "PER（会社予想）", operator: "以下", value: "12.0" },
    { field: "ROIC",            operator: "以上", value: "10.0" },
    { field: "利益の質",        operator: "以上", value: "-0.05" },
    { field: "平均売買代金(20日)", operator: "以上", value: "1.0" },
  ]);
  const [sortCol, setSortCol] = useState("score");
  const [sortDir, setSortDir] = useState<"asc"|"desc">("desc");

  const addFilter = () => setFilters(f => [...f, { field: "総合スコア", operator: "以上", value: "" }]);
  const removeFilter = (i: number) => setFilters(f => f.filter((_, j) => j !== i));

  const sorted = [...screenerResults].sort((a, b) => {
    if (sortDir === "desc") return b.score - a.score;
    return a.score - b.score;
  });

  return (
    <AppShell>
      <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
        {/* Filter builder */}
        <aside style={{
          width: 240, flexShrink: 0,
          background: "var(--bg-surface)",
          borderRight: "1px solid var(--border)",
          overflowY: "auto",
          display: "flex", flexDirection: "column",
        }}>
          <div style={{ padding: "14px 14px 0" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 10 }}>
              条件 (AND)
            </div>
            {filters.map((f, i) => (
              <div key={i} style={{
                display: "flex", alignItems: "center", gap: 4,
                padding: "6px 8px", marginBottom: 4,
                background: "var(--bg-elevated)", borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg)", marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.field}</div>
                  <div style={{ fontSize: 10, color: "var(--fg-tertiary)" }}>{f.operator} {f.value}</div>
                </div>
                <button onClick={() => removeFilter(i)} style={{ background: "none", border: "none", color: "var(--fg-tertiary)", cursor: "pointer", padding: 2, fontSize: 12 }}>×</button>
              </div>
            ))}
            <button className="btn btn-ghost" style={{ fontSize: 11, width: "100%", justifyContent: "center", marginBottom: 12 }} onClick={addFilter}>
              + 条件を追加
            </button>
          </div>

          <div style={{ padding: "0 14px", borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-tertiary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>ユニバース</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { label: "時価総額の下限", value: "300億円" },
                { label: "平均売買代金の下限", value: "1.0億円" },
              ].map((u) => (
                <div key={u.label} style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                  <span style={{ color: "var(--fg-secondary)" }}>{u.label}</span>
                  <span style={{ fontFamily: "var(--font-data)", color: "var(--fg)" }}>{u.value}</span>
                </div>
              ))}
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 11, color: "var(--fg-secondary)" }}>
                <input type="checkbox" defaultChecked style={{ accentColor: "var(--accent)" }} />
                流動性の低い銘柄を除外
              </label>
            </div>
          </div>

          <div style={{ padding: "12px 14px", marginTop: "auto" }}>
            <div style={{ fontSize: 10, color: "var(--fg-tertiary)", marginBottom: 8 }}>
              5件の条件 (AND)。1,994銘柄のうち142銘柄が該当。
            </div>
            <button className="btn btn-ghost" style={{ width: "100%", justifyContent: "center", fontSize: 11 }}>条件をリセット</button>
          </div>
        </aside>

        {/* Results */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {/* Page header */}
          <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", background: "var(--bg-surface)", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <div>
                <h1 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>スクリーナー</h1>
                <div style={{ fontSize: 11, color: "var(--fg-tertiary)" }}>142件 / 1,994銘柄 · 2026年8月22日 時点</div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-secondary" style={{ fontSize: 11 }}>この条件を保存</button>
                <button className="btn btn-secondary" style={{ fontSize: 11 }}>CSVで書き出し</button>
              </div>
            </div>
            {/* Preset chips */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {presets.map((p) => (
                <button
                  key={p.id}
                  className={`chip ${activePreset === p.id ? "active" : ""} ${p.warn ? "warning" : ""}`}
                  onClick={() => setActivePreset(p.id)}
                  title={p.desc}
                >{p.label}</button>
              ))}
            </div>
          </div>

          {/* Results summary */}
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "7px 20px", borderBottom: "1px solid var(--border)",
            background: "var(--bg-surface)", flexShrink: 0,
            fontSize: 11, color: "var(--fg-secondary)",
          }}>
            <span>上位 {sorted.length}件を表示（100件上限）</span>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ color: "var(--fg-tertiary)" }}>並び替え:</span>
              <select className="input" style={{ width: "auto", padding: "3px 24px 3px 8px" }}
                value={sortCol} onChange={e => setSortCol(e.target.value)}>
                <option value="score">総合スコア（降順）</option>
                <option value="per">PER（昇順）</option>
                <option value="mom">モメンタム（降順）</option>
              </select>
            </div>
          </div>

          {/* Table */}
          <div style={{ flex: 1, overflowY: "auto", overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 2 }}>銘柄コード</th>
                  <th style={{ position: "sticky", left: 80, background: "var(--bg-surface)", zIndex: 2 }}>銘柄名</th>
                  <th>セクター</th>
                  <th onClick={() => setSortDir(d => d === "desc" ? "asc" : "desc")} style={{ cursor: "pointer" }}>
                    総合スコア {sortCol === "score" ? (sortDir === "desc" ? "▼" : "▲") : ""}
                  </th>
                  <th>参考価格</th>
                  <th>前日比</th>
                  <th>PER（会社予想）</th>
                  <th>ROIC</th>
                  <th>12Mモメンタム</th>
                  <th>主な理由</th>
                  <th>決算まで</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.ticker} onClick={() => navigate(`/stocks/JP/${r.ticker}`)}>
                    <td style={{ position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 1 }}>
                      <span style={{ fontFamily: "var(--font-data)", fontWeight: 700, color: "var(--accent)", fontSize: 11 }}>{r.ticker}</span>
                    </td>
                    <td style={{ position: "sticky", left: 80, background: "var(--bg-surface)", zIndex: 1 }}>
                      <span style={{ fontSize: 11 }}>{r.name}</span>
                    </td>
                    <td style={{ fontSize: 10, color: "var(--fg-secondary)" }}>{r.sector}</td>
                    <td><ScoreBadge score={r.score} /></td>
                    <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.price}</td>
                    <td>
                      <span className={r.change.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.change}</span>
                    </td>
                    <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.per}</td>
                    <td style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.roic}</td>
                    <td>
                      <span className={r.mom12.startsWith("+") ? "dir-up" : "dir-down"} style={{ fontFamily: "var(--font-data)", fontSize: 11 }}>{r.mom12}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        {r.chips.slice(0, 2).map((c) => (
                          <span key={c} className="chip positive" style={{ fontSize: 10, padding: "1px 6px" }}>{c}</span>
                        ))}
                      </div>
                    </td>
                    <td style={{ fontSize: 11, color: "var(--fg-secondary)" }}>{r.days}</td>
                    <td onClick={e => e.stopPropagation()}>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button className="btn btn-ghost" style={{ fontSize: 10, padding: "3px 8px" }}>+ウォッチ</button>
                        <button className="btn btn-secondary" style={{ fontSize: 10, padding: "3px 8px" }}
                          onClick={() => navigate(`/stocks/JP/${r.ticker}`)}>詳細</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "6px 20px", fontSize: 10, color: "var(--fg-tertiary)", borderTop: "1px solid var(--border)", background: "var(--bg-surface)", flexShrink: 0 }}>
            参考価格は yfinance の15分遅延値です。スコアと財務指標は 2026年8月22日 時点、財務は各銘柄の直近開示日基準です。
          </div>
        </div>
      </div>
    </AppShell>
  );
}
