# 01. Dashboard

## Purpose

The single screen the user opens first, in the morning before the Tokyo open and in the evening
after the US close. It answers four questions in one view: did the overnight batch finish, what
changed in the market and in FX, which recommendations are new today, and does the portfolio need
attention. Everything on this screen is a summary that links to a deeper screen. Nothing on this
screen is the only place a piece of information exists.

The screen must remain useful when the batch failed. A failed Collector run is itself the most
important information on the page, so job status is rendered above the market summary, not below it.

## Route

`/`

Query parameters:

| Param | Values | Default | Note |
| --- | --- | --- | --- |
| `market` | `JP`, `US` | `JP` before 15:00 JST, `US` after | Global market context, persisted in settings |
| `as_of` | ISO date | latest available | Allows reviewing a past day |

## Layout

### Desktop (>= 1280px)

12-column grid, `--space-6` gutter, `--content-max-width` 1600px, page padding `--space-8`.

| Row | Columns | Content |
| --- | --- | --- |
| 0 | 1-12 | `WarningBanner` (only when `warnings[]` is non-empty) |
| 1 | 1-12 | `PageHeader` with date, market switch, freshness summary |
| 2 | 1-12 | `JobStatusStrip` (single row, 6 job pills, height 72px) |
| 3 | 1-3 / 4-6 / 7-9 / 10-12 | 4 `MetricCard`: market index, USDJPY, portfolio value, today's P/L |
| 4 | 1-8 | `RecommendationHighlights` (3 `RecommendationCard` variant `compact`, stacked) |
| 4 | 9-12 | `AlertFeed` (scrollable, max height 420px) |
| 5 | 1-6 | `FilingsToday` (up to 6 `FilingListItem`) |
| 5 | 7-12 | `WatchlistTable` (`DataTable` dense, up to 8 rows) |
| 6 | 1-6 | `FxSnapshotCard` (`SparklineChart` + `ForecastValue`) |
| 6 | 7-12 | `ModelHealthPanel` (compact variant) |

### Tablet (768px - 1279px)

8-column grid, `--space-5` gutter. Sidebar collapses to icon rail (`--sidebar-width-collapsed`).

- Row 3 metric cards become 2 x 2 (columns 1-4 / 5-8).
- Row 4 becomes full width stacked: `RecommendationHighlights` then `AlertFeed`.
- Rows 5 and 6 become single column, full width, in the order: `FilingsToday`,
  `WatchlistTable`, `FxSnapshotCard`, `ModelHealthPanel`.

### Mobile (< 768px)

Single column, page padding `--space-4`, `BottomNav` fixed, safe-area inset respected.

Vertical order, which differs deliberately from desktop because thumb reach matters more than
information density:

1. `OfflineBanner` / `KillSwitchBanner` (when applicable)
2. `FreshnessSummaryRow` (compact, tappable, opens a sheet with per-source detail)
3. `JobStatusStrip` (horizontal scroll, 6 pills, snap scrolling)
4. Metric cards as a 2 x 2 grid, `--space-3` gap
5. `RecommendationHighlights`, 2 cards, "すべての推奨を見る" link
6. `AlertFeed`, 3 items, "すべて見る" link
7. `FilingsToday`, 3 items, "すべて見る" link
8. `WatchlistTable` converted to `WatchlistCardList` (see `components.md` §5, mobile table rule)
9. `FxSnapshotCard`
10. `ModelHealthPanel` collapsed into a single-line summary that expands on tap

## Component tree

```
DashboardPage
├── AppShell
│   ├── AppHeader
│   │   ├── MarketSwitch                      market=JP|US
│   │   ├── DataFreshnessIndicator            aggregate status
│   │   ├── AsOfDatePicker
│   │   └── AlertBell                         unread count badge
│   ├── Sidebar (desktop) / BottomNav (mobile)
│   └── MainContent
│       ├── WarningBanner[]                   from response.warnings
│       ├── PageHeader
│       │   ├── PageTitle                     "ダッシュボード"
│       │   ├── AsOfLabel                     "2026年8月22日 (金) 時点"
│       │   └── RefreshButton
│       ├── JobStatusStrip
│       │   └── JobPill x6                    collector / analyst / researcher / strategist / critic / evaluator
│       ├── MetricCardGrid
│       │   ├── MetricCard                    市場指数 (TOPIX or S&P 500)
│       │   ├── MetricCard                    USD/JPY
│       │   ├── MetricCard                    ポートフォリオ評価額
│       │   └── MetricCard                    当日損益
│       ├── SectionCard "本日の注目"
│       │   ├── SectionHeader + LinkToAll
│       │   └── RecommendationCard[compact] x3
│       ├── SectionCard "アラート"
│       │   ├── SectionHeader + MarkAllReadButton
│       │   └── AlertRow[]
│       │       ├── SeverityDot
│       │       ├── AlertTitle
│       │       ├── AlertTimestamp
│       │       └── AlertLink
│       ├── SectionCard "本日の開示"
│       │   ├── SectionHeader + LinkToAll
│       │   └── FilingListItem[]
│       ├── SectionCard "ウォッチリスト"
│       │   ├── SectionHeader + LinkToAll
│       │   └── DataTable
│       │       └── columns: 銘柄 / 参考価格 / 前日比 / スコア / 決算 / 開示
│       ├── SectionCard "為替"
│       │   ├── SparklineChart                USDJPY 60 business days
│       │   ├── DirectionValue                現在値と前日比
│       │   └── ForecastValue                 5営業日先の予測 + CI + baseline verdict
│       └── SectionCard "モデルの状態"
│           └── ModelHealthPanel[compact]
```

## Content spec

### Page header

| Element | label_en | label_ja | Example rendering |
| --- | --- | --- | --- |
| Title | Dashboard | ダッシュボード | ダッシュボード |
| As-of | As of | 時点 | 2026年8月22日 (金) 時点 |
| Market switch JP | Japan | 日本株 | 日本株 |
| Market switch US | United States | 米国株 | 米国株 |
| Refresh | Refresh | 更新 | 更新 |

### Job status strip

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Collector | Collector | データ収集 | データ収集 · 成功 · 06:12 · 6分52秒 |
| Analyst | Analyst | 分析 | 分析 · 成功 · 06:19 · 4分08秒 |
| Researcher | Researcher | 資料読解 | 資料読解 · 部分 · 06:31 · 3件スキップ |
| Strategist | Strategist | 推奨生成 | 推奨生成 · 成功 · 06:38 · 12件生成 |
| Critic | Critic | レビュー | レビュー · 成功 · 06:44 · 2件却下 |
| Evaluator | Evaluator | 実績評価 | 実績評価 · 成功 · 06:47 · 教訓1件追加 |
| Strip caption | Last full run | 直近の実行 | 直近の実行: 2026年8月22日 06:47 (JST) |

Status labels come from `components.md` §4.5. A `partial` job renders the count of skipped steps
inline, because "partial" without a count is not actionable.

### Metric cards

| Card | label_en | label_ja | Value example | Sub-line example |
| --- | --- | --- | --- | --- |
| Index (JP) | TOPIX | TOPIX | 2,847.32 | +0.84% (+23.71) · 2026-08-21 終値 |
| Index (US) | S&P 500 | S&P 500 | 5,612.48 | -0.32% (-18.04) · 2026-08-21 終値 |
| FX | USD/JPY | ドル円 | 152.34円 | +0.41% (+0.62円) · 18:35 時点 |
| Portfolio | Portfolio value | ポートフォリオ評価額 | 8,472,150円 | 取得価額比 +6.2% (+495,120円) |
| Daily P/L | Today's P/L | 当日損益 | +38,420円 | +0.46% · 参考価格ベース |

Every metric card carries a freshness caption in `--text-caption` / `--fg-tertiary`. The portfolio
cards add "参考価格ベース" because positions are marked with delayed reference prices, never with
execution prices.

### Recommendation highlights

Section heading: label_en `Today's highlights`, label_ja `本日の注目`.
Link to all: label_en `View all recommendations`, label_ja `すべての推奨を見る`.

Compact card example content:

```
7203  トヨタ自動車          輸送用機器
注目  20営業日  確信度 中
期待超過リターン +2.4% [-3.1%, +7.9%]  類似条件の的中率 58% (n=34)
[セクター内で割安] [会社予想の上方修正] [12ヶ月モメンタム強い] [為替が追い風]
強気論拠: 北米向け出荷が想定を上回り、通期の営業利益予想が5%上方修正された。
弱気論拠: 上方修正の主因は為替で、数量ベースの改善は限定的。円高に転じると前提が崩れる。
```

The bear-case preview line is present on the compact variant. A compact card that shows only the
thesis is a defect.

### Alert feed

| Element | label_en | label_ja |
| --- | --- | --- |
| Section title | Alerts | アラート |
| Mark all read | Mark all as read | すべて既読にする |
| Empty | No new alerts | 新しいアラートはありません |

Example rows:

```
warning  J-Quantsの価格データが5営業日更新されていません        08-22 06:12
info     6758 ソニーグループが業績予想の修正を開示しました      08-22 15:04
warning  LLMの日次予算の80%（$1.20 / $1.50）に達しました        08-22 06:31
info     7203 トヨタ自動車の決算発表が3営業日後です              08-22 06:47
danger   TDnetの取得が3日連続で失敗しています                    08-22 06:14
```

Alert categories are limited to system health, filing events, and cost. There are no
price-threshold alerts (see `SKILL.md` §10).

### Filings today

Section title: label_en `Today's filings`, label_ja `本日の開示`.

```
15:04  6758  ソニーグループ    業績予想の修正   2027年3月期 通期業績予想の修正に関するお知らせ   PDF
15:00  7203  トヨタ自動車      決算短信         2027年3月期 第1四半期決算短信                    PDF
09:30  AAPL  Apple Inc.        10-Q             Quarterly report for the period ended 2026-06-27  HTML
08:45  9432  日本電信電話      自己株式の取得   自己株式取得に係る事項の決定に関するお知らせ     PDF
```

Filing titles render in their original language, unmodified.

### Watchlist table

| Column | label_en | label_ja | Format |
| --- | --- | --- | --- |
| 1 | Ticker / Name | 銘柄 | `7203 トヨタ自動車` |
| 2 | Reference price | 参考価格 | `3,125円` |
| 3 | Change | 前日比 | `DirectionValue` `+1.24%` |
| 4 | Score | スコア | `ScoreBadge` `78.4` |
| 5 | Earnings | 決算 | `3営業日後` or `—` |
| 6 | Filings | 開示 | count badge `2` or `—` |

Table caption: `参考価格は yfinance の15分遅延値です。約定価格には使用できません。`

### FX snapshot

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | FX | 為替 | 為替 |
| Current | Current | 現在値 | 152.34円 (+0.41%) |
| Forecast | 5-day forecast | 5営業日先の予測 | 152.80円 [150.10円, 155.50円] |
| Baseline verdict | Baseline comparison | ベースライン比較 | ランダムウォークに対する優位性は確認できません (DM検定 p=0.31) |
| Hit rate | Directional hit rate | 方向的中率 | 51% (n=248) |

The baseline verdict string comes from the API field `verdict_ja` and is rendered verbatim. The UI
does not compute or soften it.

### Model health (compact)

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | Model status | モデルの状態 | モデルの状態 |
| Rank IC | Rank IC (20 days) | Rank IC (直近20営業日) | 0.031 (n=20日) |
| Trend | Trend | 傾向 | 直近3ヶ月平均 0.028 と同水準 |
| Coverage | Coverage | 対象銘柄カバー率 | 92.4% (1,842 / 1,994銘柄) |
| Warning | Degradation detected | 成績低下の検出 | 検出なし |

## States

### Loading

- `JobStatusStrip`: 6 skeleton pills at final size, no spinner.
- Metric cards: skeleton value bar 120 x 28px plus skeleton caption 180 x 12px.
- Recommendation cards: 3 skeleton cards at 220px height each.
- Tables: skeleton rows equal to the previous row count, minimum 5.
- Load order per `states.md` §2.2: job strip and freshness first, then metric cards, then
  recommendations, then the lower sections.

### Loading-refresh

Existing content stays visible at full opacity. The refresh button shows a spinner and the
`DataFreshnessIndicator` shows a subtle pulse. Never blank a populated dashboard.

### Empty

Occurs only on the first run before any batch has completed.

| Element | label_ja |
| --- | --- |
| Title | まだデータがありません |
| Body | 初回のデータ収集がまだ完了していません。エージェントコンソールから収集ジョブを実行してください。 |
| Action | エージェントコンソールを開く → `/agent` |

Section-level empties:

| Section | label_ja |
| --- | --- |
| Recommendations | 本日の推奨はありません。条件を満たす銘柄が見つからなかったか、Criticが全件を却下しました。 |
| Alerts | 新しいアラートはありません |
| Filings | 本日の開示はありません |
| Watchlist | ウォッチリストが空です。銘柄詳細から追加してください。 |

### Not-ready

Requested `as_of` has no generated data.

```
2026年8月23日のデータはまだ生成されていません。
最新の利用可能日は 2026年8月22日です。            [2026年8月22日を表示]
```

### Partial data

The most common non-nominal state and the one that must be handled well.

| Failing part | Dashboard behavior |
| --- | --- |
| Researcher hit the LLM cost cap | Recommendation cards render with `qualScore` shown as `—` and a section note: `LLMの日次予算に達したため、定性評価は含まれていません。定量スコアのみで生成されています。` |
| TDnet fetch failed | `FilingsToday` shows EDINET-sourced items and a footer note: `TDnetの取得に失敗しました。適時開示は反映されていません。` with a retry link |
| yfinance failed | Reference prices render as `—` and the watchlist caption becomes an error: `参考価格を取得できませんでした。表示されている価格はありません。` Treated as an error, not a soft warning, because a stale "current" price is dangerous |
| FRED failed | `FxSnapshotCard` renders the last known value with a `stale` marker and the forecast section shows `為替予測を更新できませんでした（最終更新 2026年8月20日）` |
| Evaluator did not run | `ModelHealthPanel` shows the previous day's values with a caption `実績評価が未実行のため、前営業日の値を表示しています` |

Each partial section renders a `--status-warning` left border 2px and a warning-tinted caption. The
rest of the page renders normally.

### Error

Page-level error only when `GET /api/v1/dashboard` itself fails.

| Element | label_ja |
| --- | --- |
| Title | ダッシュボードを読み込めませんでした |
| Body | APIサーバーに接続できません。WSL2上のサービスが起動しているか確認してください。 |
| Detail (collapsed) | `GET /api/v1/dashboard` → `ECONNREFUSED 127.0.0.1:8000` |
| Action | 再試行 |
| Secondary | 診断手順を表示（`docs/15-windows-runtime.md` §7 のチェックリストを要約表示） |

### Stale

When `latest_as_of` is more than one business day behind `expected_as_of`, the freshness indicator
turns `--status-warning` and a persistent row appears under the page header:

```
価格データが2営業日更新されていません（最終 2026年8月20日）。表示中のスコアはこの日付時点のものです。
```

### Offline

`OfflineBanner` pinned at `--z-banner`:

```
オフラインです。2026年8月22日 06:47 に取得したデータを表示しています。
```

Cached dashboard renders read-only. The refresh button is disabled. Trade-journal entry remains
available because it queues via Background Sync.

### Degraded

When the LLM kill switch is on, `KillSwitchBanner` renders above everything:

```
LLMの停止スイッチが有効です。定性分析と要約は生成されません。   [設定を開く]
```

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Market switch | Click / tap | Updates global `market`, refetches all sections, syncs to URL and settings |
| As-of date picker | Select date | Refetches with `as_of`; dates without data are disabled in the picker |
| Refresh button | Click | Invalidates all dashboard queries; content stays visible during refetch |
| `DataFreshnessIndicator` | Click / tap | Opens a popover (desktop) or sheet (mobile) listing each source with `latest_as_of`, expected date, and status |
| Job pill | Click | Navigates to `/agent?job_run_id=<id>` |
| Job pill (failed) | Click on retry icon | `POST /api/v1/agent/jobs/{job_name}/run`, optimistic status change to `running` |
| Metric card (FX) | Click | Navigates to `/macro` |
| Metric card (portfolio) | Click | Navigates to `/portfolio` |
| Recommendation card body | Click | Navigates to `/recommendations?rec_id=<id>` with the card expanded |
| Recommendation card ticker | Click | Navigates to `/stocks/JP/7203` (stops propagation, per `interaction-patterns.md` §3.1) |
| Bear-case affordance (compact) | Click | Expands in place, does not navigate |
| Alert row | Click | Navigates to the alert's target and marks it read |
| Mark all read | Click | `POST /api/v1/alerts/read-all`, optimistic |
| Filing row | Click | Opens the PDF in a new tab via `GET /api/v1/documents/{doc_id}/file?disposition=inline` |
| Filing row summary icon | Click | Opens the cached LLM summary in a sheet; if absent, shows the estimated cost and a generate button |
| Watchlist row | Click | Navigates to `/stocks/{market}/{ticker}` |
| Watchlist row score | Click | Navigates to `/stocks/{market}/{ticker}#factors` |
| "すべて見る" links | Click | Navigate to `/recommendations`, `/filings`, `/portfolio` respectively |
| Pull down (mobile) | Gesture | Refetches the dashboard, threshold 64px |
| `g` then `d` | Keyboard | Navigates to the dashboard from anywhere |
| `r` | Keyboard | Refresh |

## Data source

| Section | Endpoint |
| --- | --- |
| Whole page | `GET /api/v1/dashboard?market=JP&as_of=2026-08-22` (single aggregate call) |
| Freshness detail | `GET /api/v1/system/freshness` |
| Job strip detail | `GET /api/v1/agent/jobs?limit=6` |
| Live job progress | `GET /api/v1/agent/events` (SSE), fallback to 15s polling |
| Alerts | `GET /api/v1/alerts?is_read=false&limit=50` |

Refetch intervals per `interaction-patterns.md` §6.1: dashboard aggregate 5 minutes while the tab is
focused, alerts 60 seconds, job status via SSE.

Populate every field from `sample-data.json` (`dashboard`, `recommendations`, `watchlist`,
`filings`, `alerts`, `jobs`, `fx`, `model_health`).
