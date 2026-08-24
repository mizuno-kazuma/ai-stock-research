# AI Stock Research UI — Implementation Plan

## Context

Build a complete UI prototype for an AI-driven research and trading decision support tool focused on Japanese (TSE) and US markets. The app has 10 screens defined in spec files under `src/imports/`. The current project is a blank Vite + React + Tailwind CSS v4 shell.

**Aesthetic stance: data-dense terminal** — Bloomberg Terminal lineage. True dark canvas (`#0a0d12`), small tabular fonts, maximum information density, functional color coding. JetBrains Mono for data, Inter for UI text, Noto Sans JP for Japanese.

---

## Architecture

### Dependencies to install

```
pnpm add react-router-dom recharts
```

### File structure

```
src/
  App.tsx                  ← router + shell
  index.css                ← fonts + Tailwind + CSS tokens
  data/
    sample.ts              ← all mock data
  components/
    AppShell.tsx           ← sidebar + header + main layout
    Sidebar.tsx
    charts/
      SparklineChart.tsx
      PriceChart.tsx
      FanChart.tsx
  pages/
    DashboardPage.tsx
    RecommendationsPage.tsx
    StockDetailPage.tsx
    ScreenerPage.tsx
    FilingsHubPage.tsx
    FxMacroPage.tsx
    ModelLabPage.tsx
    AgentConsolePage.tsx
    PortfolioPage.tsx
    SettingsPage.tsx
```

---

## Aesthetic tokens (index.css)

**Fonts (Google Fonts @import first in index.css):**
- `Inter` (UI text, weights 400/500/600)
- `JetBrains Mono` (tickers, numbers, status labels, mono data)
- `Noto Sans JP` (Japanese text, weights 400/500)

**CSS custom properties on `:root`:**
```css
--bg: #0a0d12;           /* true dark canvas */
--bg-surface: #111520;   /* card/panel */
--bg-elevated: #161b28;  /* hover / selected row */
--fg: #e2e8f0;           /* primary text */
--fg-secondary: #8b96a8; /* labels, captions */
--fg-tertiary: #556070;  /* timestamps, meta */
--accent: #3b82f6;       /* interactive blue */
--accent-hover: #60a5fa;
--border: rgba(255,255,255,0.07);
--border-strong: rgba(255,255,255,0.14);
--up-jp: #ef4444;        /* JP red = up */
--down-jp: #3b82f6;      /* JP blue = down */
--up-us: #22c55e;        /* US green = up */
--down-us: #ef4444;      /* US red = down */
--status-success: #22c55e;
--status-warning: #f59e0b;
--status-danger: #ef4444;
--status-info: #3b82f6;
--status-neutral: #6b7280;
--font-ui: 'Inter', sans-serif;
--font-data: 'JetBrains Mono', monospace;
--font-ja: 'Noto Sans JP', sans-serif;
--radius: 4px;
```

---

## Mock data (src/data/sample.ts)

Single TypeScript file with realistic mock objects for all pages:
- Dashboard: jobs[], metrics{}, recommendations[], alerts[], filings[], watchlist[], fx{}, model_health{}
- Recommendations: cards[] (4 approved, 1 revised, 1 rejected)
- Stock detail: toyota 7203, apple AAPL
- Screener: 12 result rows
- Filings: 14 entries
- FX/Macro: usdjpy forecast, macro series
- Model lab: ic_series[], backtests[], weights{}
- Agent: jobs[], llm_cost{}, critic_stats{}, memory[]
- Portfolio: positions[], trades[]
- Settings: settings{}

All numbers, names, dates match the spec examples exactly (7203 トヨタ自動車, 3,125円, etc.).

---

## Component plan

### AppShell (all pages share this)

- **Sidebar** (desktop 240px, icon-only at 768px):
  - Logo + app name (AIリサーチ)
  - Nav items: ダッシュボード / 推奨銘柄 / スクリーナー / 決算資料 / 為替・マクロ / モデルラボ / エージェント / ポートフォリオ / 設定
  - Each nav item: icon + Japanese label + English label (tiny)
  - Active state: accent left border + bg-elevated
- **Top bar** (64px):
  - Market switch (日本株 / 米国株)
  - Data freshness indicator
  - Alert bell (badge)
  - As-of date

### Page-by-page plan

#### 1. Dashboard (`/`)
- `JobStatusStrip`: 6 pill cards (colored by status: 成功=green, 部分=amber, 失敗=red), horizontal row
- `MetricCardGrid`: 4 metric cards (TOPIX, USD/JPY, portfolio value, daily P/L) with DirectionValue
- `RecommendationHighlights`: 3 compact cards (ticker, badge row, expected return, bull + bear)
- `AlertFeed`: scrollable list with severity dot (color-coded), title, timestamp
- `FilingsToday`: 6 rows with time, ticker, doc type, title
- `WatchlistTable`: dense DataTable 8 rows
- `FxSnapshotCard`: sparkline + forecast value
- `ModelHealthPanel`: 4 metric rows

#### 2. Recommendations (`/recommendations`)
- Left `FilterRail` (240px sticky): market, horizon, action, conviction, critic verdict, sector toggles
- Right `RecommendationList`: full-width cards
- Each card: ticker header row, badge row (action/horizon/conviction/score), ForecastValue block, ReasonCodeChipRow, ThesisSection (green-tinted left border), **BearCaseSection** (amber left border, always expanded), InvalidationSection, CitationList, CardActions
- Bear case must never be collapsed — implement exactly per spec

#### 3. Stock Detail (`/stocks/JP/7203` and `/stocks/US/AAPL`)
- Sticky `StockHeader` (96px): ticker badge, name, sector, price, change, score badge
- `TabBar`: 価格 / ファクター / 財務 / 開示資料 / 推奨履歴 / 保有履歴
- Price section: range selector chips + `PriceChart` (Recharts LineChart, 360px)
- Key metrics: 2-column definition list (14 rows)
- Factor table: z-score + sector percentile + raw value columns
- Financials: horizontal scroll table (5 fiscal periods)
- Filings: filter chips + list
- Recommendation history: sortable table with 的中/外れ badges
- Position panel: summary + trade history

#### 4. Screener (`/screener`)
- Left `FilterBuilder` (240px sticky): preset chips (8 presets), filter rows with field/operator/value, universe section
- Right `ResultsPanel`: summary bar (match count) + dense DataTable (16 columns, toggleable)
- Distribution strip: 4 mini histograms (placeholder SVG bars)
- Preset chips: value_trap_warning renders in amber

#### 5. Filings Hub (`/filings`)
- Left `FilterRail` (240px): scope toggle, market, doc type checkboxes, ticker search, summary toggle
- Center `FilingFeed` (columns 4-8): grouped by date, `FilingListItem` rows with doc type badge + tone badge
- Right `DetailPane` (columns 9-12): summary header, key points list, risk factors, citations, open button
- Empty detail state: "左の一覧から資料を選択してください"

#### 6. FX & Macro (`/macro`)
- **`BaselineVerdictPanel`** (full width, first, always): verdict headline in Japanese, DM stat row, RMSE comparison — rendered before any forecast number
- `FanChart` (Recharts AreaChart with bands, 400px)
- `ForecastTable`: 3 horizon rows
- `ModelComparisonTable`: ARIMAX / VECM / random walk
- `RateDifferentialChart` (Recharts LineChart)
- `VolatilityPanel`: 6 metric rows
- `MacroSeriesGrid`: 6 cards with sparkline
- `FxSensitivityTable`: held/watched tickers

#### 7. Model Lab (`/model-lab`)
- 4 tabs: モデルの状態 / 学習履歴 / バックテスト / ファクター重み
- Health tab: 4 metric cards + IC time series (Recharts BarChart) + quintile chart (BarChart) + feature importance (horizontal bars) + leakage check list
- Calibration note (IC ~0.03 is realistic) rendered as visible text beside the IC cards
- Backtests: cost assumptions row FIRST before any return figures
- Weights tab: diff table + approve/reject buttons

#### 8. Agent Console (`/agent`)
- 4 tabs: ジョブ / コスト / レビュー / 教訓
- Jobs tab: scheduler status bar + today's pipeline strip (6 cards with arrows) + job run list/detail + manual run panel
- Cost tab: 3 metric cards + gauge + **KillSwitchControl** (prominent toggle) + stacked bar chart + call table
- Critic tab: rejection reason breakdown (horizontal bars) + rejected recommendation list
- Memory tab: filter bar + memory items with active toggle + effectiveness panel

#### 9. Portfolio (`/portfolio`)
- 3 tabs: 保有 / 売買日誌 / 分析
- Positions tab: summary bar (4 metrics) + performance chart (Recharts LineChart) + allocation donuts (Recharts PieChart) + positions table (13 columns)
- Journal tab: new entry button + trade list grouped by month (each entry shows emotion tag color-coded) + stats panel
- Analysis tab: recommendation quality vs execution quality side-by-side + emotion tag breakdown chart + holding period panel

#### 10. Settings (`/settings`)
- Left sticky nav (6 sections)
- Center content (max-width 720px)
- Right preview pane (live preview of direction color convention)
- Direction color control: 2 option cards with REAL example rows (not swatches)
- Cost section: cap inputs with current spend shown beside them
- Data section: J-Quants plan toggle + data source status table

---

## Charts implementation

Use `recharts`. Key charts:
- `SparklineChart`: `<LineChart>` tiny, no axes, 60px tall
- `PriceChart`: `<ComposedChart>` with candlestick approximation (bar + line) + volume subchart
- `FanChart`: `<AreaChart>` with two area bands (80%, 95%) + median line + baseline flat line
- `IcTimeSeriesChart`: `<ComposedChart>` with bar (daily IC) + line (rolling mean) + zero reference line
- `QuintileChart`: `<BarChart>` 5 bars, colored by value (+/-)
- `EquityCurveChart`: `<LineChart>` portfolio vs benchmark

---

## Routing (react-router-dom v6)

```tsx
<Routes>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/recommendations" element={<RecommendationsPage />} />
  <Route path="/stocks/:market/:ticker" element={<StockDetailPage />} />
  <Route path="/screener" element={<ScreenerPage />} />
  <Route path="/filings" element={<FilingsHubPage />} />
  <Route path="/macro" element={<FxMacroPage />} />
  <Route path="/model-lab" element={<ModelLabPage />} />
  <Route path="/agent" element={<AgentConsolePage />} />
  <Route path="/portfolio" element={<PortfolioPage />} />
  <Route path="/settings" element={<SettingsPage />} />
</Routes>
```

---

## Critical product requirements (from spec)

1. **Bear case always visible** — never collapsed on RecommendationCard (amber left border)
2. **BaselineVerdictPanel before forecast** on FX page — loading order enforced
3. **Direction colors**: JP (red=up/blue=down) vs US (green=up/red=down) — implement as CSS var toggle, default JP
4. **Backtest cost assumptions rendered before return figures** — JSX order enforced
5. **Leakage check list** — shown with pass/fail markers, dangerous if any fail
6. **Model IC calibration note** — visible text (not tooltip): "Rank IC 0.03 前後はこの種のモデルとして現実的な水準です"
7. **Kill switch** — reachable from Agent Console and Settings
8. **Reference price disclaimer** — "参考価格は yfinance の15分遅延値" on every table that shows prices

---

## Implementation order

1. `pnpm add react-router-dom recharts`
2. `src/index.css` — fonts + CSS tokens
3. `src/data/sample.ts` — all mock data
4. `src/components/AppShell.tsx` + `Sidebar.tsx`
5. `src/App.tsx` — Router + routes
6. Pages in order: Dashboard → Recommendations → StockDetail → Screener → FilingsHub → FxMacro → ModelLab → AgentConsole → Portfolio → Settings

---

## Verification

- Navigate all 10 routes in browser preview
- Confirm sidebar nav links work
- Confirm bear case is visible (not collapsed) on recommendation cards
- Confirm BaselineVerdictPanel renders before FanChart on `/macro`
- Confirm direction color preview works in Settings
- Confirm `/stocks/JP/7203` and `/stocks/US/AAPL` both render
- Check that Recharts charts render without console errors
- Verify Japanese text renders correctly (Noto Sans JP loaded)
