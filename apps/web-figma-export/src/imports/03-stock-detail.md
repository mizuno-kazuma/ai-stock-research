# 03. Stock Detail

## Purpose

Everything known about one security in one place: price history, factor scores and where they sit
within the sector, financial history on a point-in-time basis, the filing list with one-click PDF
access, the recommendation history for this ticker with realized outcomes, and the user's own
position and past trades in it.

The screen has two jobs that pull in opposite directions. It must be comprehensive, because this is
where the user does the actual homework before a manual order. It must also not imply certainty, so
every model output on this page carries an interval and a sample size, and the recommendation
history shows misses as prominently as hits.

The financial statement section is point-in-time by construction: figures are keyed by `filed_at`,
not by fiscal period end, and restatements are visible rather than silently overwritten.

## Route

`/stocks/[market]/[ticker]`

Examples: `/stocks/JP/7203`, `/stocks/US/AAPL`.

| Param | Values | Default |
| --- | --- | --- |
| `market` (path) | `JP`, `US` | required |
| `ticker` (path) | `7203`, `AAPL` | required, string type, never numeric |
| `range` | `1m`, `3m`, `6m`, `1y`, `3y`, `5y`, `max` | `1y` |
| `series` | `research`, `live` | `research` |
| `tab` | `overview`, `factors`, `financials`, `filings`, `recommendations`, `journal` | `overview` |
| `as_of` | ISO date | latest available |

Anchors: `#factors`, `#financials`, `#filings` scroll to and activate the corresponding tab.

## Layout

### Desktop (>= 1280px)

12-column grid. Sticky ticker header below the app header.

| Row | Columns | Content |
| --- | --- | --- |
| 0 | 1-12 | `WarningBanner[]` |
| 1 | 1-12 | `StockHeader` (sticky, 96px): ticker, name, sector, reference price, change, score, action buttons |
| 2 | 1-12 | `TabBar` (underline variant, sticky beneath the header) |
| 3 | 1-8 | `PriceChart` with range selector and series toggle, 360px tall |
| 3 | 9-12 | `KeyMetricsPanel` (2-column definition list) |
| 4 | 1-5 | `FactorRadar` + sector percentile bars |
| 4 | 6-12 | `FactorScoreTable` with sector median comparison |
| 5 | 1-12 | `FinancialsTable` (horizontal scroll, sticky first column) |
| 6 | 1-7 | `FilingsList` (grouped by fiscal period, accordion) |
| 6 | 8-12 | `RecommendationHistoryPanel` |
| 7 | 1-6 | `PositionPanel` (only when a position or past trade exists) |
| 7 | 7-12 | `PeerComparisonTable` |

Tabs do not hide sections on desktop; they scroll to them. The full page is one document so the user
can scan.

### Tablet (768px - 1279px)

8-column grid. `PriceChart` full width at 300px tall, `KeyMetricsPanel` below it as a 3-column
definition grid. `FactorRadar` and `FactorScoreTable` stack. All other sections full width.

### Mobile (< 768px)

Single column. Tabs become real tabs that switch content, because the full document is too long to
scroll on a phone.

- `StockHeader` compresses to 72px: ticker + name on line 1, price + change + score on line 2.
- `TabBar` is horizontally scrollable, snap-aligned.
- `PriceChart` 240px tall, range selector as a chip row above it, no crosshair (tap shows a value
  callout instead).
- `FactorRadar` is dropped; only `FactorScoreTable` renders, as stacked rows.
- `FinancialsTable` converts to per-period cards: one card per fiscal period with the metrics as
  rows.
- `PeerComparisonTable` converts to a card list.
- The action buttons move into a sticky bottom bar above `BottomNav`, 56px tall.

## Component tree

```
StockDetailPage
├── AppShell
│   └── MainContent
│       ├── WarningBanner[]
│       ├── Breadcrumb                          日本株 > 輸送用機器 > 7203
│       ├── StockHeader (sticky)
│       │   ├── TickerBadge                     7203
│       │   ├── CompanyName                     トヨタ自動車
│       │   ├── MarketBadge + SectorLink
│       │   ├── ReferencePriceBlock
│       │   │   ├── DirectionValue              3,125円 +1.24%
│       │   │   └── PriceSourceCaption          yfinance · 15分遅延 · 15:10
│       │   ├── ScoreBadge                      78.4
│       │   ├── ConvictionBadge                 (if a live recommendation exists)
│       │   └── HeaderActions
│       │       ├── AddToWatchlistButton
│       │       ├── CreateTradeEntryButton
│       │       └── OpenFilingsButton
│       ├── TabBar
│       ├── Section "価格" #price
│       │   ├── RangeSelector                   1M 3M 6M 1Y 3Y 5Y MAX
│       │   ├── SeriesToggle                    リサーチ用 / 参考現在値
│       │   ├── PriceChart
│       │   │   ├── CandlestickOrLine
│       │   │   ├── VolumeSubchart
│       │   │   ├── MA20 / MA60 / MA200 overlays
│       │   │   ├── EarningsMarkers
│       │   │   └── RecommendationMarkers       past recommendation dates
│       │   └── ChartCaption                    source + delay disclosure
│       ├── Section "主要指標"
│       │   └── KeyMetricsPanel
│       ├── Section "ファクター" #factors
│       │   ├── FactorRadar
│       │   ├── SectorPercentileBars
│       │   └── FactorScoreTable
│       ├── Section "財務" #financials
│       │   ├── PeriodBasisToggle               会計期間基準 / 開示日基準
│       │   ├── FinancialsTable
│       │   └── RestatementNote
│       ├── Section "開示資料" #filings
│       │   ├── FilingTypeFilterChips
│       │   └── FilingListItem[]
│       ├── Section "推奨履歴"
│       │   └── RecommendationHistoryPanel
│       │       ├── SummaryRow                  的中率 62% (n=13)
│       │       └── RecommendationHistoryRow[]
│       ├── Section "保有・売買履歴"
│       │   └── PositionPanel
│       │       ├── PositionSummary
│       │       └── TradeJournalEntry[compact][]
│       └── Section "同業比較"
│           └── PeerComparisonTable
```

## Content spec

### Stock header

| Element | label_en | label_ja | Example (JP) | Example (US) |
| --- | --- | --- | --- | --- |
| Ticker | Ticker | 銘柄コード | 7203 | AAPL |
| Name | Name | 銘柄名 | トヨタ自動車 | Apple Inc. |
| Market | Market | 市場 | 東証プライム | NASDAQ |
| Sector | Sector | セクター | 輸送用機器 | Information Technology |
| Price | Reference price | 参考価格 | 3,125円 | $189.42 |
| Change | Change | 前日比 | +1.24% (+38円) | -0.83% (-$1.58) |
| Score | Composite score | 総合スコア | 78.4 | 71.2 |
| Price caption | | | yfinance · 15分遅延 · 2026年8月22日 15:10 取得 | yfinance · 15分遅延 · 2026年8月22日 05:10 取得 |

### Series toggle (important)

| Option | label_en | label_ja | Caption |
| --- | --- | --- | --- |
| `research` | Research series | リサーチ用データ | J-Quants（無料プラン・12週遅延）。分析とバックテストに使用している系列です。 |
| `live` | Reference current | 参考現在値 | yfinance の15分遅延値。表示専用で、分析には使用していません。 |

Switching series changes the chart caption and, when `live` is selected, adds a persistent inline
note: `この系列はモデルの学習・検証には一切使用されていません。`

This separation is a hard product requirement, not a UI nicety. The two series must never be drawn
as one continuous line without a visible seam. When both are shown, the delayed research series is
solid and the live segment is drawn with a distinct dashed stroke plus a vertical divider labeled
`ここから参考現在値`.

### Key metrics panel

| Metric | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Market cap | Market cap | 時価総額 | 42兆1,800億円 |
| PER | P/E (trailing) | PER（実績） | 11.2倍 |
| PER (forward) | P/E (company forecast) | PER（会社予想） | 10.4倍 |
| PBR | P/B | PBR | 1.18倍 |
| EV/EBITDA | EV/EBITDA | EV/EBITDA | 8.4倍 |
| Dividend yield | Dividend yield | 配当利回り | 2.84% |
| ROE | ROE | ROE | 11.6% |
| ROIC | ROIC | ROIC | 12.4% |
| Equity ratio | Equity ratio | 自己資本比率 | 38.2% |
| Realized vol | Realized volatility (60d) | 実現ボラティリティ (60営業日) | 22.4% |
| GARCH vol | GARCH(1,1) forecast vol | GARCH予測ボラティリティ | 21.8% |
| ADV | Average daily value (20d) | 平均売買代金 (20営業日) | 412億円 |
| Beta | Beta vs TOPIX | ベータ（TOPIX比） | 1.04 |
| FX sensitivity | FX sensitivity | 為替感応度 | +0.42 (1円円安あたり) |
| Next earnings | Next earnings | 次回決算 | 2026年11月6日（予定・3営業日後） |
| As-of | Valuation as of | 指標の基準日 | 2026年8月22日（財務は2026年8月8日開示分） |

A negative PER renders `—` with the caption `赤字のため算出していません`, never a negative number
and never `0`.

### Factor section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Factors | ファクター | ファクター |
| Column: factor | Factor | ファクター | バリュエーション |
| Column: z-score | z-score | z-score | +1.42 |
| Column: sector percentile | Sector percentile | セクター内順位 | 上位 8% (12 / 148銘柄) |
| Column: raw value | Raw value | 実数値 | PER 11.2倍 |
| Column: sector median | Sector median | セクター中央値 | PER 15.8倍 |
| Column: contribution | Contribution to score | スコア寄与 | +11.4 |
| Caption | | | z-scoreはセクター内で中央値とMADを用いて標準化し、±3で切り詰めています。 |
| Version caption | | | 特徴量バージョン: v3 (2026年6月1日以降) |

### Financials table

Columns are fiscal periods, most recent first. Rows are metrics. The `PeriodBasisToggle` switches
between `会計期間基準` (grouped by fiscal period end) and `開示日基準` (ordered by `filed_at`, which
is what the model uses).

| Row | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Revenue | Revenue | 売上収益 | 12兆3,400億円 |
| Operating income | Operating income | 営業利益 | 1兆2,040億円 |
| Operating margin | Operating margin | 営業利益率 | 9.8% |
| Net income | Net income | 純利益 | 8,920億円 |
| EPS | EPS | EPS | 279.4円 |
| Free cash flow | Free cash flow | フリーCF | 6,140億円 |
| Accruals ratio | Accruals ratio | 会計上の利益の質 | -0.021 |
| Net debt / EBITDA | Net debt / EBITDA | 純有利子負債 / EBITDA | 0.42倍 |
| YoY revenue | Revenue YoY | 売上前年比 | +6.4% |
| YoY operating income | Operating income YoY | 営業利益前年比 | +18.2% |
| Filed at | Filed | 開示日 | 2026-08-08 |
| Source doc | Source | 出典 | 決算短信 → 開く |

Column header example: `2027/3期 1Q (2026-08-08 開示)`.

Restatement note: `2026年5月14日開示分は2026年8月8日に修正再表示されています。モデルは各時点で
入手可能だった数値のみを使用しています。`

### Filings list

| Element | label_en | label_ja |
| --- | --- | --- |
| Heading | Filings | 開示資料 |
| Filter chips | | すべて / 決算短信 / 有価証券報告書 / 四半期報告書 / 業績予想の修正 / その他 |
| Summary present | View summary | 要約を見る |
| Summary absent | Generate summary | 要約を生成（推定 $0.012） |
| Open | Open | 開く |
| Local copy | Local copy | ローカル保存済み |
| Official site | Official site | 提供元サイトで開く |

Example rows:

```
2026-08-08  決算短信            2027年3月期 第1四半期決算短信〔IFRS〕(連結)        要約あり  開く
2026-06-24  有価証券報告書      第122期 有価証券報告書                              要約あり  開く
2026-05-14  業績予想の修正      2027年3月期 通期業績予想の修正に関するお知らせ      要約なし  開く
2026-05-08  決算短信            2026年3月期 決算短信〔IFRS〕(連結)                  要約あり  開く
```

### Recommendation history

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Recommendation history | 推奨履歴 | 推奨履歴 |
| Summary | | | この銘柄の推奨 13件。的中率 62% (n=13)、平均超過リターン +1.4% |
| Column: date | Date | 生成日 | 2026-07-18 |
| Column: action | Action | 区分 | 注目 |
| Column: horizon | Horizon | 期間 | 20営業日 |
| Column: conviction | Conviction | 確信度 | 中 |
| Column: expected | Expected | 予測 | +2.1% [-3.4%, +7.6%] |
| Column: realized | Realized | 実績 | +3.8% |
| Column: outcome | Outcome | 判定 | 的中 |
| Outcome hit | Hit | 的中 | |
| Outcome miss | Miss | 外れ | |
| Outcome pending | Pending | 判定前 | 判定前（残り8営業日） |

Misses render in the direction-down color with the same weight as hits. Sorting defaults to newest
first and must not default to hits first.

### Position panel

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Your position | 保有・売買履歴 | 保有・売買履歴 |
| Quantity | Quantity | 保有数量 | 300株 |
| Average cost | Average cost | 平均取得単価 | 2,948円 |
| Book value | Book value | 取得価額 | 884,400円 |
| Market value | Market value | 評価額（参考） | 937,500円 |
| Unrealized | Unrealized P/L | 評価損益 | +53,100円 (+6.0%) |
| Weight | Portfolio weight | ポートフォリオ比率 | 11.1% |
| Note | | | 評価額は参考価格ベースです。 |
| Past trades | Past trades | 過去の売買 | 4件 |

### Peer comparison

| Column | label_ja | Example |
| --- | --- | --- |
| 銘柄 | | 7267 本田技研工業 |
| 総合スコア | | 71.8 |
| PER | | 8.9倍 |
| PBR | | 0.72倍 |
| ROIC | | 9.1% |
| 20営業日リターン | | +4.2% |
| 為替感応度 | | +0.38 |

Caption: `同一セクター内で時価総額が近い上位5銘柄を表示しています。`

## States

### Loading

- `StockHeader` renders the ticker and name immediately from the route if available in cache,
  skeletons the price.
- `PriceChart` shows a skeleton at the exact final height (360px desktop / 240px mobile) so nothing
  shifts.
- Sections load progressively: header, chart, key metrics, factors, financials, filings, history.

### Empty

| Case | label_ja |
| --- | --- |
| Ticker not found | 銘柄コード 9999 は見つかりませんでした。銘柄マスタに存在しないか、上場廃止の可能性があります。 [銘柄を検索] |
| No filings | この銘柄の開示資料はまだ取得されていません。 |
| No recommendation history | この銘柄はまだ推奨対象になっていません。 |
| No position | この銘柄の保有・売買記録はありません。 [売買記録を作成] |
| No peers | セクター情報が不足しているため同業比較を表示できません。 |

### Not-ready

Scores for the requested `as_of` are not generated:
`2026年8月23日のスコアはまだ生成されていません。価格と開示資料のみ表示しています。`

### Partial data

| Failing part | Behavior |
| --- | --- |
| J-Quants gap (structural) | Research price series ends 12 weeks back. The chart shows a shaded region labeled `無料プランの遅延期間（12週）` and the live series continues past it, visually distinct |
| Financials missing | The financials section renders the periods it has and a row-level note `2026年3月期のXBRL取得に失敗しました` with a retry link |
| Factor scores unavailable | Factor table renders `—` per missing factor, plus `一部のファクターは入力データが不足しているため算出されていません` |
| Filing PDF not downloaded | Row shows `提供元サイトで開く` instead of the local link, plus `ローカル保存に失敗しました` |
| Summary generation blocked by cost cap | `要約を生成` button is disabled with the caption `LLMの日次予算に達しています。明日以降に生成できます。` |
| Peer scores missing | Peer rows render with `—` in the score column |

### Error

Section-scoped errors with inline retry. Page-level error only if `GET /api/v1/stocks/...` fails:

```
銘柄情報を読み込めませんでした
GET /api/v1/stocks/JP/7203 → 500
[再試行]
```

### Stale

If this ticker's price data is older than the market's expected `as_of`, the header price shows a
`stale` marker and the caption becomes
`この銘柄の価格は2026年8月18日から更新されていません。`

### Offline

Chart and metrics render from cache with the offline banner. `開く` on filings is disabled unless
the PDF is in the cache; cached PDFs remain openable and are marked `ローカル保存済み`.

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Breadcrumb sector | Click | `/screener?sector=輸送用機器` |
| Range selector | Click | Refetches prices for the range; chart keeps the previous data during the fetch |
| Series toggle | Click | Switches between research and live series and updates the caption |
| Chart crosshair | Hover (desktop) | Shows date, OHLC, volume in a floating readout |
| Chart tap (mobile) | Tap | Shows a value callout, does not follow the finger |
| Earnings marker | Click | Opens a popover with the earnings date and links to that period's filings |
| Recommendation marker | Click | Opens the recommendation card in a sheet |
| MA overlay legend | Click | Toggles that overlay |
| Chart accessibility toggle | Click | Replaces the chart with an equivalent data table |
| Tab | Click | Desktop scrolls to the section; mobile switches content. Both update `?tab=` |
| Factor row | Click | Opens a popover with the definition, formula summary, and sector distribution histogram |
| Factor row "この条件で探す" | Click | `/screener` with that factor prefilled |
| Period basis toggle | Click | Re-sorts the financials columns; shows the restatement note when the basis differs |
| Financials source link | Click | Opens the filing PDF at the relevant page |
| Filing filter chip | Click | Filters the list client-side |
| Filing row | Click | Opens the PDF inline in a new tab |
| Filing "要約を見る" | Click | Opens the cached summary in a sheet with citations |
| Filing "要約を生成" | Click | Shows a confirm dialog with the estimated cost, then `POST /api/v1/documents/{doc_id}/summary` |
| Recommendation history row | Click | Opens that recommendation card in a sheet, including its bear case as written at the time |
| Add to watchlist | Click | `POST /api/v1/watchlist`, optimistic |
| Record a trade | Click | Opens the trade-entry sheet prefilled with this ticker and reference price |
| Peer row | Click | Navigates to that peer's detail page |
| `w` | Keyboard | Toggle watchlist |
| `f` | Keyboard | Jump to the filings section |
| `[` / `]` | Keyboard | Previous / next ticker within the list the user arrived from |

## Data source

| Section | Endpoint |
| --- | --- |
| Header, key metrics | `GET /api/v1/stocks/{market}/{ticker}` |
| Price chart | `GET /api/v1/stocks/{market}/{ticker}/prices?range=1y&series=research` and `?series=live` |
| Factors | `GET /api/v1/stocks/{market}/{ticker}/features?as_of=2026-08-22` |
| Score decomposition | `GET /api/v1/scores?market=JP&as_of=2026-08-22&ticker=7203` |
| Financials | `GET /api/v1/stocks/{market}/{ticker}/financials?periods=8` |
| Filings | `GET /api/v1/stocks/{market}/{ticker}/documents?limit=20` |
| Recommendation history | `GET /api/v1/stocks/{market}/{ticker}/recommendations` |
| Peers | `GET /api/v1/stocks/{market}/{ticker}/peers` |
| Position and trades | `GET /api/v1/portfolio/positions` filtered client-side, `GET /api/v1/trades?ticker=7203` |

Populate from `sample-data.json` keys `stock_detail` (7203 and AAPL are both fully specified),
`prices`, `financials`, `filings`, `factors`, `peers`.
