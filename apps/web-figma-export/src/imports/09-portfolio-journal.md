# 09. Portfolio and Trade Journal

## Purpose

Positions, realized and unrealized performance, and the trade journal. Orders are placed manually at
the brokerage, so every trade here is entered by hand or imported from a CSV. That constraint turns
out to be an advantage: the entry form can ask for the thesis and the emotional state at the time of
the trade, which no broker-integrated tool captures.

The analytical purpose of this screen is to separate two things that are usually conflated:

- **Recommendation quality** — were the tool's recommendations any good, measured over all
  recommendations regardless of whether the user acted on them.
- **Execution quality** — were the user's actual trades any good, including the discretionary ones
  the tool never suggested, the timing relative to the reference price, and the holding period
  versus the plan.

Keeping those separate is what makes the journal useful. A tool with mediocre recommendations and a
user who trades on impulse will produce bad results, and the user needs to know which of the two to
fix. The `emotion_tag` breakdown is often the single most actionable number on the screen.

All valuations use delayed reference prices and say so. Nothing here is a brokerage statement.

## Route

`/portfolio`

| Param | Values | Default |
| --- | --- | --- |
| `tab` | `positions`, `journal`, `analysis` | `positions` |
| `range` | `3m`, `6m`, `1y`, `3y`, `max` | `1y` |
| `market` | `JP`, `US`, `all` | `all` |
| `trade_id` | id | none, opens the entry in a sheet |
| `ticker` | ticker | none, filters the journal |

Unlike other screens, the default market scope is `all`, because a portfolio spans both markets.

## Layout

### Desktop (>= 1280px)

12-column grid, tabbed.

Tab `positions`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-12 | `PortfolioSummaryBar`: total value, unrealized, realized YTD, cash, currency split |
| 2 | 1-8 | `PerformanceChart`: portfolio value vs benchmark, 320px |
| 2 | 9-12 | `AllocationPanel`: sector and market donuts, top-5 concentration |
| 3 | 1-12 | `PositionsTable` |
| 4 | 1-6 | `RiskPanel`: concentration, FX exposure, earnings proximity |
| 4 | 7-12 | `UpcomingEventsPanel`: earnings dates for held tickers |

Tab `journal`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-12 | `JournalToolbar`: new entry, import CSV, filters, search |
| 2 | 1-8 | `TradeJournalList` (grouped by month) |
| 2 | 9-12 | `JournalStatsPanel`: entries, tagged rate, linked-to-recommendation rate |

Tab `analysis`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-6 | `RecommendationQualityPanel` |
| 1 | 7-12 | `ExecutionQualityPanel` |
| 2 | 1-6 | `EmotionTagBreakdownChart` |
| 2 | 7-12 | `HoldingPeriodPanel`: planned vs actual |
| 3 | 1-6 | `SlippagePanel` |
| 3 | 7-12 | `DiscretionaryVsRecommendedPanel` |
| 4 | 1-12 | `LessonsPanel`: plain-language observations with sample sizes |

### Tablet (768px - 1279px)

8-column grid. Summary bar wraps to two rows. Charts full width. `PositionsTable` keeps 8 of its
columns; the rest move behind the column picker. Analysis panels stack in pairs.

### Mobile (< 768px)

Single column. Full functionality including trade entry, because recording a trade right after
placing it at the broker is a phone task.

- `PortfolioSummaryBar` becomes a 2 x 2 metric grid with the total value as a display-size number.
- `PerformanceChart` 200px, no crosshair.
- `PositionsTable` converts to `PositionCardList`: ticker + name, market value, unrealized with
  direction color and sign, weight, and an expand affordance for the rest.
- `TradeJournalList` as cards. A floating action button opens the entry sheet.
- The entry sheet is a full-height bottom sheet with the numeric keypad triggered by
  `inputMode="decimal"`.
- Analysis tab renders as stacked cards; the emotion-tag chart becomes a horizontal bar list.

## Component tree

```
PortfolioJournalPage
├── AppShell
│   └── MainContent
│       ├── OfflineBanner                        (queued entries indicator)
│       ├── WarningBanner[]
│       ├── PageHeader
│       │   ├── PageTitle                        "ポートフォリオ"
│       │   ├── MarketScopeToggle                すべて / 日本株 / 米国株
│       │   └── AsOfLabel
│       ├── TabBar                               保有 / 売買日誌 / 分析
│       ├── TabPanel "保有"
│       │   ├── PortfolioSummaryBar
│       │   │   ├── MetricCard                   評価額
│       │   │   ├── MetricCard                   評価損益
│       │   │   ├── MetricCard                   実現損益（年初来）
│       │   │   ├── MetricCard                   現金
│       │   │   └── CurrencySplitRow
│       │   ├── SectionCard "推移"
│       │   │   ├── RangeSelector
│       │   │   ├── PerformanceChart
│       │   │   └── ChartCaption
│       │   ├── SectionCard "構成"
│       │   │   ├── SectorDonut
│       │   │   ├── MarketDonut
│       │   │   └── ConcentrationRow
│       │   ├── SectionCard "保有銘柄"
│       │   │   └── PositionsTable
│       │   ├── SectionCard "リスク"
│       │   │   └── RiskPanel
│       │   └── SectionCard "予定"
│       │       └── UpcomingEventsPanel
│       ├── TabPanel "売買日誌"
│       │   ├── JournalToolbar
│       │   │   ├── NewEntryButton
│       │   │   ├── ImportCsvButton
│       │   │   ├── SideFilterChips               買い / 売り
│       │   │   ├── LinkedFilterChips             推奨連動 / 裁量
│       │   │   ├── EmotionFilterChips
│       │   │   └── SearchInput
│       │   ├── TradeJournalList
│       │   │   └── MonthGroup > TradeJournalEntry[]
│       │   └── JournalStatsPanel
│       ├── TabPanel "分析"
│       │   ├── RecommendationQualityPanel
│       │   ├── ExecutionQualityPanel
│       │   ├── EmotionTagBreakdownChart
│       │   ├── HoldingPeriodPanel
│       │   ├── SlippagePanel
│       │   ├── DiscretionaryVsRecommendedPanel
│       │   └── LessonsPanel
│       └── TradeEntrySheet
│           ├── BearCaseRecallPanel               when linked to a recommendation
│           ├── TickerCombobox
│           ├── SideToggle
│           ├── QuantityInput
│           ├── PriceInput
│           ├── FeeInput
│           ├── ExecutedAtInput
│           ├── BrokerSelect
│           ├── AccountTypeSelect
│           ├── LinkedRecommendationSelect
│           ├── ThesisTextarea
│           ├── EmotionTagSelect                  required
│           ├── ExitPlanTextarea
│           └── SaveButton
```

## Content spec

### Portfolio summary

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Total value | Market value | 評価額 | 8,472,150円 |
| Unrealized | Unrealized P/L | 評価損益 | +495,120円 (+6.2%) |
| Realized YTD | Realized P/L (YTD) | 実現損益（年初来） | +182,400円 |
| Cash | Cash | 現金 | 1,240,000円 |
| Currency split | Currency | 通貨構成 | 円 78% / 米ドル 22%（1ドル152.34円で換算） |
| Positions count | Positions | 保有銘柄数 | 7銘柄 |
| Caption | | | 評価額は参考価格（15分遅延）ベースです。証券会社の残高とは一致しません。 |

### Performance chart

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Performance | 推移 | 推移 |
| Portfolio | Portfolio | ポートフォリオ | +6.2% |
| Benchmark | Benchmark | ベンチマーク | TOPIX +4.1% |
| Excess | Excess | 超過 | +2.1% |
| Caption | | | 手動入力された売買記録から算出しています。入力漏れがある場合は数値が正しくありません。 |
| Cash flow markers | Deposits and withdrawals | 入出金 | |

The caption naming the data-entry dependency is necessary. A portfolio chart built from a hand-kept
journal is only as good as the journal.

### Positions table

| Column | label_en | label_ja | Format |
| --- | --- | --- | --- |
| 1 | Ticker / Name | 銘柄 | `7203 トヨタ自動車` |
| 2 | Market | 市場 | `日本株` |
| 3 | Quantity | 数量 | `300株` |
| 4 | Average cost | 平均取得単価 | `2,948円` |
| 5 | Reference price | 参考価格 | `3,125円` |
| 6 | Market value | 評価額 | `937,500円` |
| 7 | Unrealized | 評価損益 | `DirectionValue` `+53,100円 (+6.0%)` |
| 8 | Weight | 比率 | `11.1%` |
| 9 | Score | 総合スコア | `ScoreBadge` `78.4` |
| 10 | Current view | 現在の見立て | `注目` / `縮小検討` / `—` |
| 11 | Holding days | 保有日数 | `42営業日` |
| 12 | Earnings | 決算 | `3営業日後` |
| 13 | Actions | 操作 | detail link, new entry |

The `現在の見立て` column is where the tool contradicts the user's position if it should. When the
current recommendation for a held ticker is `縮小検討` or `回避`, the cell renders in
`--status-warning` with the reason available in a popover. Do not soften this.

Caption: `評価額と評価損益は参考価格ベースです。`

### Risk panel

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Top concentration | Largest position | 最大保有比率 | 18.4% (6758 ソニーグループ) |
| Top 3 | Top 3 concentration | 上位3銘柄の比率 | 44.2% |
| Sector concentration | Largest sector | 最大セクター比率 | 32.1%（電気機器・3銘柄） |
| FX exposure | USD exposure | 米ドル建て比率 | 22.4% |
| FX sensitivity | Weighted FX sensitivity | 加重為替感応度 | +0.28 |
| High vol share | High volatility share | 高ボラ銘柄の比率 | 12.8%（実現ボラ30%超） |
| Earnings soon | Positions reporting soon | 決算が近い銘柄 | 2銘柄（3営業日以内） |
| Warnings | | | セクター集中が30%を超えています。 |

These are observations with thresholds, not instructions. Each warning states the threshold it
crossed so the user can judge whether the threshold is right for them.

### Trade journal entry (display)

```
2026年8月22日 09:15    買い    7203 トヨタ自動車    100株 @ 3,125円    手数料 275円
推奨連動 (2026-08-22 生成 · 注目 · 確信度 中)          心理状態: 自信あり

判断メモ
上方修正と割安さを評価。北米の競争環境は懸念だが為替の追い風が上回ると判断した。

撤退計画
3,420円で半分、2,890円割れで全部撤退。

参考価格との差: +12bp（記録時の参考価格 3,121円）
証券会社: 楽天証券 · 口座: 特定
```

| Field | label_en | label_ja |
| --- | --- | --- |
| Side buy | Buy | 買い |
| Side sell | Sell | 売り |
| Linked | Linked to recommendation | 推奨連動 |
| Discretionary | Discretionary | 裁量 |
| Emotion | Emotional state | 心理状態 |
| Thesis | Rationale | 判断メモ |
| Exit plan | Exit plan | 撤退計画 |
| Slippage | Difference from reference | 参考価格との差 |
| Broker | Broker | 証券会社 |
| Account | Account type | 口座 |

Emotion tags:

| Value | label_en | label_ja |
| --- | --- | --- |
| `confident` | Confident | 自信あり |
| `fomo` | Fear of missing out | 乗り遅れ懸念 |
| `fearful` | Fearful | 不安 |
| `neutral` | Neutral | 平常 |

### Trade entry sheet

| Field | label_en | label_ja | Validation |
| --- | --- | --- | --- |
| Ticker | Ticker | 銘柄 | required, must exist in the master |
| Side | Side | 売買 | required |
| Quantity | Quantity | 数量 | required, positive integer. JP equities validate against the trading unit (100株単位) with the message `この銘柄の売買単位は100株です` |
| Price | Execution price | 約定価格 | required, positive. Warns when more than 10% away from the reference price: `参考価格 3,125円 から 12.4% 離れています。入力を確認してください。` |
| Fee | Fee | 手数料 | optional, defaults 0 |
| Executed at | Executed at | 約定日時 | required, cannot be in the future, warns when outside market hours |
| Broker | Broker | 証券会社 | optional, remembered from the last entry |
| Account | Account type | 口座区分 | 特定 / 一般 / NISA |
| Linked recommendation | Linked recommendation | 関連する推奨 | optional; auto-selected when arriving from a recommendation |
| Thesis | Rationale | 判断メモ | required, minimum 10 characters |
| Emotion | Emotional state | 心理状態 | **required** |
| Exit plan | Exit plan | 撤退計画 | required for buys, minimum 5 characters |

Two required fields are unusual and both are intentional. The emotion tag is required because it is
the input to the most useful analysis on this screen and it cannot be reconstructed later. The exit
plan is required on buys because writing it before the position exists is the only time it is honest.

Bear-case recall panel, shown when the entry is linked to a recommendation:

```
この推奨の弱気論拠（記録時点）
上方修正の主因は為替効果で、数量ベースの改善は前年同期比+1.2%にとどまる。
円高に転じた場合、上方修正分の大半が消える構造にある。

この内容を読んだうえで記録しますか。
```

This is not a confirmation dialog and does not block saving. It is a panel above the form. The point
is that the bear case is on screen at the moment of recording, which is the last moment it can still
influence anything.

### Analysis tab

Recommendation quality panel:

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Recommendation quality | 推奨の質 | 推奨の質 |
| Count | Recommendations | 推奨件数 | 214件 |
| Hit rate | Hit rate | 的中率 | 54.2% (n=214) |
| Avg excess | Average excess return | 平均超過リターン | +0.81% |
| By conviction | By conviction | 確信度別 | 高 61% (n=42) / 中 56% (n=98) / 低 51% (n=74) |
| Monotonicity | Conviction monotonicity | 確信度の単調性 | 単調性あり |
| Note | | | 確信度が高いほど的中率が高く、確信度の付け方は妥当です。 |
| Note (broken) | | | 確信度と的中率の関係が単調ではありません。確信度の付け方に問題があります。 |
| Scope note | | | この指標は利用者が売買したかどうかに関係なく、全推奨を対象に算出しています。 |

Execution quality panel:

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Execution quality | 実行の質 | 実行の質 |
| Trades | Trades | 売買件数 | 42件（推奨連動 31件 / 裁量 11件） |
| Hit rate linked | Hit rate (from recommendations) | 的中率（推奨連動） | 58.1% (n=31) |
| Hit rate discretionary | Hit rate (discretionary) | 的中率（裁量） | 36.4% (n=11) |
| Slippage | Average difference from reference | 参考価格との平均乖離 | +18.4bp |
| Holding | Average holding period | 平均保有日数 | 24.1営業日（計画 20.0営業日） |
| Plan adherence | Exit plan adherence | 撤退計画の遵守率 | 62% (n=26) |
| Note | | | 裁量売買の的中率が推奨連動を大きく下回っています。 |

Emotion tag breakdown:

```
心理状態別の的中率
自信あり     61%  (n=18)
平常         55%  (n=11)
不安         44%  (n=9)
乗り遅れ懸念 29%  (n=7)

観察: 「乗り遅れ懸念」で記録した売買の的中率が29% (n=7) と最も低いです。
ただしサンプルが7件と少ないため、断定はできません。件数が20件を超えた時点で
再評価してください。
```

The sample-size caveat is mandatory. This analysis is the most tempting place to over-read a small
sample, and the note is what keeps it honest.

Holding period panel:

| Element | label_ja | Example |
| --- | --- | --- |
| 計画保有日数の中央値 | | 20営業日 |
| 実際の保有日数の中央値 | | 24営業日 |
| 計画より早く手放した割合 | | 31% (n=13) |
| 計画より長く持ち続けた割合 | | 48% (n=20) |
| 観察 | | 損失が出ている銘柄の保有日数の中央値は38営業日で、利益が出ている銘柄の19営業日より長いです。損切りが遅れる傾向があります。 |

Slippage panel:

| Element | label_ja | Example |
| --- | --- | --- |
| 参考価格との平均乖離 | | +18.4bp |
| 買いの平均乖離 | | +24.1bp |
| 売りの平均乖離 | | -11.8bp |
| 注記 | | 参考価格は15分遅延値のため、この乖離はスリッページそのものではなく、記録時点との時間差を含みます。 |

Lessons panel: plain-language observations, each with its sample size and a link to the underlying
trades. Observations below n=10 are shown but marked `参考`.

### Journal stats panel

| Element | label_ja | Example |
| --- | --- | --- |
| 記録件数 | | 42件 |
| 判断メモ記入率 | | 100% |
| 心理状態タグ付与率 | | 100% |
| 撤退計画記入率 | | 88% (22 / 25件の買い) |
| 推奨連動率 | | 74% (31 / 42件) |

## States

### Loading

Summary bar skeletons at final size. The positions table skeletons the number of rows from the last
known position count.

### Empty

| Case | label_ja |
| --- | --- |
| No positions | 保有銘柄がありません。売買を記録すると保有状況が表示されます。[売買記録を作成] |
| No trades | 売買記録がありません。手動で記録するか、証券会社のCSVを取り込んでください。[記録を作成] [CSVを取り込む] |
| No analysis data | 分析には最低10件の売買記録が必要です。現在 4件です。 |
| No recommendation outcomes | 推奨の実績がまだ確定していません。20営業日ホライズンの実績は生成から20営業日後に確定します。 |
| No upcoming earnings | 保有銘柄で決算発表が近いものはありません。 |

The analysis tab's threshold message is important: showing a hit rate computed from 4 trades would be
worse than showing nothing.

### Partial data

| Failing part | Behavior |
| --- | --- |
| Reference prices unavailable | Market value and unrealized columns render `—` with the caption `参考価格を取得できませんでした。取得価額のみ表示しています。` Quantities and average costs still render because they come from the journal |
| Benchmark data unavailable | Performance chart draws the portfolio line only, with `ベンチマークを取得できませんでした` |
| Scores unavailable | Score and 現在の見立て columns render `—` |
| FX rate unavailable | USD positions show `為替レートが取得できないため円換算できません` and the total is shown in each currency separately rather than combined |
| Recommendation outcomes partially pending | Analysis panels show the confirmed subset with `判定前 18件を除く` stated explicitly |
| Earnings calendar unavailable | 決算 column renders `—` |

The FX case matters: a combined total computed with a stale rate is worse than two separate
currency totals.

### Error

```
ポートフォリオを読み込めませんでした
GET /api/v1/portfolio → 500
[再試行]
```

Save failure on the entry sheet keeps every field's value and shows an inline error:

```
記録を保存できませんでした
POST /api/v1/trades → 500
入力内容は保持されています。もう一度お試しください。
[再試行]  [下書きとして保存]
```

Losing a hand-typed thesis and exit plan to a failed request would be unacceptable, so the form
never clears on error and offers a local draft.

### Offline

- Positions and journal render from cache with the timestamp.
- **Trade entry works offline.** Saving queues the entry via Background Sync, the list shows it with
  a `送信待ち` badge, and the summary numbers include it locally with the note
  `未送信の記録1件を含みます`.
- On iOS, where Background Sync is unavailable, the entry is stored locally and the banner reads
  `未送信の記録が1件あります。オンラインになったら画面を開いて送信してください。` with a manual
  `送信` action.
- CSV import is disabled offline.

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Tab | Click | Switches panel, updates `?tab=` |
| Market scope toggle | Click | Filters positions and journal; the analysis tab recomputes |
| Range selector | Click | Refetches performance |
| Performance chart hover | Hover | Readout with date, portfolio value, benchmark, and any cash flow on that date |
| Cash flow marker | Click | Popover with the deposit or withdrawal amount |
| Sector donut segment | Click | Filters the positions table to that sector |
| Position row | Click | Navigates to `/stocks/{market}/{ticker}` |
| Position 現在の見立て cell | Click | Popover with the current recommendation summary including its bear case, and a link to the card |
| Position new-entry action | Click | Opens the entry sheet prefilled with that ticker and `sell` preselected when a position exists |
| New entry | Click | Opens the entry sheet |
| Ticker combobox | Type | Async search via `GET /api/v1/stocks/search` |
| Linked recommendation select | Open | Lists recent recommendations for that ticker; selecting one shows the bear-case recall panel |
| Quantity / price inputs | Blur | Validates unit size and reference-price deviation, shows inline warnings without blocking |
| Save entry | Click | `POST /api/v1/trades`, non-optimistic: the row appears only after the server confirms, because a silently lost trade record is worse than a slow one |
| Import CSV | Click | Opens a dialog with the expected column format, a file picker, an encoding note (`Shift_JIS のファイルも読み込めます`), and a preview of the first 5 parsed rows before committing |
| Journal entry | Click | Opens the entry in a sheet for viewing and editing |
| Journal entry edit | Click | Same form, prefilled; saving records an edit timestamp |
| Journal entry delete | Click | Confirm dialog naming the ticker and date |
| Filter chips | Click | Filters the journal client-side |
| Search | Type | Searches the thesis and exit-plan text, debounced 300ms |
| Emotion bar | Click | Filters the journal to that tag |
| Lessons panel observation | Click | Filters the journal to the trades behind that observation |
| Slippage note | Click | Popover explaining that the reference price is delayed and what that means for the number |
| Queued entry `送信` | Click | Retries the queued write |
| `n` | Keyboard | New entry |
| `Escape` in sheet | Keyboard | Closes; if fields are dirty, asks `入力内容を破棄しますか` |

## Data source

| Section | Endpoint |
| --- | --- |
| Summary and positions | `GET /api/v1/portfolio`, `GET /api/v1/portfolio/positions` |
| Performance | `GET /api/v1/portfolio/performance?range=1y` |
| Journal | `GET /api/v1/trades?limit=100&offset=0` |
| Create, edit, delete | `POST /api/v1/trades`, `PATCH /api/v1/trades/{id}`, `DELETE /api/v1/trades/{id}` |
| CSV import | `POST /api/v1/trades/import` |
| Analysis | `GET /api/v1/trades/analysis` |
| Current view per holding | `GET /api/v1/recommendations?tickers=...` |
| Earnings dates | Included in the positions response as `next_earnings_date` |
| Ticker search | `GET /api/v1/stocks/search?q=...` |

Populate from `sample-data.json` keys `portfolio`, `positions` (7 positions including one US ticker
and one where the current view is `縮小検討`), `trades` (12 entries covering all four emotion tags,
one discretionary trade, one queued offline entry), and `trade_analysis`.
