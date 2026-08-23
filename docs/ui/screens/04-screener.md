# 04. Screener

## Purpose

The tool for answering "which stocks currently satisfy these conditions". It is the most useful part
of the product when the ranking model turns out to have weak predictive power, because filtering on
verifiable fundamentals and disclosed facts is valuable even with zero forecasting edge. The screener
is therefore designed to stand on its own and never to depend on the model being good.

Filters operate on the factor and feature tables, results are ranked by a user-chosen column, and
every row links to the stock detail. Presets encode useful starting points, including deliberately
cautionary ones such as "value trap warning", because a screener that only surfaces reasons to buy
trains bad habits.

## Route

`/screener`

The full filter state is serialized into the URL so a screen is reproducible and bookmarkable.

| Param | Values | Default |
| --- | --- | --- |
| `market` | `JP`, `US` | global market setting |
| `as_of` | ISO date | latest available |
| `preset` | preset id | none |
| `f` | encoded filter array (JSON, URL-safe base64) | none |
| `sort` | column id | `total_score` |
| `dir` | `asc`, `desc` | `desc` |
| `limit` | 50, 100, 200, 500 | 100 |
| `saved` | saved-screen id | none |

Long filter sets are POSTed to `POST /api/v1/screener`; the URL carries the same state so the view
can be restored, and the request body is rebuilt from it.

## Layout

### Desktop (>= 1280px)

12-column grid.

| Row | Columns | Content |
| --- | --- | --- |
| 0 | 1-12 | `WarningBanner[]` |
| 1 | 1-12 | `PageHeader`: title, result count, as-of, save / load controls |
| 2 | 1-12 | `PresetChipRow` (horizontal, wraps to 2 lines maximum) |
| 3 | 1-3 | `FilterBuilder` (sticky, own scroll, max height `calc(100vh - 180px)`) |
| 3 | 4-12 | `ResultsPanel`: summary bar, `DataTable`, pagination |
| 4 | 4-12 | `DistributionStrip` (optional, 4 mini histograms of the active filter fields) |

### Tablet (768px - 1279px)

8-column grid. `FilterBuilder` moves into a right `Sheet` opened by a `絞り込み (3)` button that
shows the active filter count. Results span all 8 columns. `DistributionStrip` drops to 2 histograms.

### Mobile (< 768px)

Single column.

- `PresetChipRow` becomes a horizontally scrolling chip row, snap-aligned.
- `FilterBuilder` opens as a full-height bottom sheet with a sticky footer holding
  `条件をリセット` and `N件を表示`.
- `DataTable` converts to `ScreenerResultCardList`: one card per row showing ticker + name, score
  badge, reference price with change, and the three columns most relevant to the active sort. A
  `詳細` affordance expands the remaining columns in place.
- `DistributionStrip` is not rendered.
- Sorting is exposed as a `並び替え` button opening a sheet, because sortable table headers do not
  work on touch.

## Component tree

```
ScreenerPage
├── AppShell
│   └── MainContent
│       ├── WarningBanner[]
│       ├── PageHeader
│       │   ├── PageTitle                    "スクリーナー"
│       │   ├── ResultCount                  "142件 / 1,994銘柄"
│       │   ├── AsOfLabel                    "2026年8月22日 時点"
│       │   ├── SavedScreenSelect
│       │   ├── SaveScreenButton
│       │   └── ExportCsvButton
│       ├── PresetChipRow
│       │   └── PresetChip x8
│       ├── FilterBuilder
│       │   ├── FilterGroupHeader             "条件 (AND)"
│       │   ├── FilterRow[]
│       │   │   ├── FieldCombobox
│       │   │   ├── OperatorSelect
│       │   │   ├── ValueInput | ValueRangeInput | ValueMultiSelect
│       │   │   ├── UnitLabel
│       │   │   └── RemoveFilterButton
│       │   ├── AddFilterButton
│       │   ├── UniverseSection
│       │   │   ├── MinMarketCapInput
│       │   │   ├── MinAdvInput
│       │   │   ├── ExcludeIlliquidSwitch
│       │   │   └── ExcludePreEarningsSwitch
│       │   ├── ActiveFilterSummary
│       │   └── ResetFiltersButton
│       ├── ResultsPanel
│       │   ├── ResultsSummaryBar
│       │   │   ├── MatchCount
│       │   │   ├── TruncationNotice          (when capped)
│       │   │   ├── ColumnPickerButton
│       │   │   └── SortSelect (mobile)
│       │   ├── DataTable
│       │   │   ├── StickyHeaderRow
│       │   │   └── ResultRow[]
│       │   │       ├── TickerCell
│       │   │       ├── NameCell
│       │   │       ├── SectorCell
│       │   │       ├── ScoreBadgeCell
│       │   │       ├── DirectionValueCell     前日比
│       │   │       ├── MetricCells[]          per active columns
│       │   │       ├── ReasonCodeChipCell     up to 2 chips + overflow count
│       │   │       ├── EarningsProximityCell
│       │   │       └── RowActionsCell         ウォッチ追加 / 詳細
│       │   └── Pagination
│       └── DistributionStrip
│           └── MiniHistogram x4
```

## Content spec

### Page header

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Screener | スクリーナー | スクリーナー |
| Count | Matches | 該当件数 | 142件 / 1,994銘柄 |
| As-of | As of | 時点 | 2026年8月22日 時点 |
| Saved screens | Saved screens | 保存した条件 | 保存した条件 |
| Save | Save this screen | この条件を保存 | この条件を保存 |
| Export | Export CSV | CSVで書き出し | CSVで書き出し |
| Export note | | | 文字コードは Excel 用に UTF-8 (BOM付き) で出力します。 |

### Presets

| Preset id | label_en | label_ja | Description (label_ja) |
| --- | --- | --- | --- |
| `value_quality` | Cheap quality | 割安クオリティ | セクター内で割安かつROICが高い銘柄 |
| `revision_momentum` | Revision momentum | 上方修正モメンタム | 会社予想が上方修正され、モメンタムも強い銘柄 |
| `weak_yen_beneficiary` | Weak-yen beneficiary | 円安メリット | 円安局面で恩恵を受けやすい銘柄 |
| `strong_yen_beneficiary` | Strong-yen beneficiary | 円高メリット | 円高局面で恩恵を受けやすい銘柄 |
| `low_vol_dividend` | Low volatility dividend | 低ボラ配当 | ボラティリティが低く配当利回りが高い銘柄 |
| `pre_earnings` | Pre-earnings check | 決算前チェック | 5営業日以内に決算発表がある保有・ウォッチ銘柄 |
| `high_growth` | High growth | 高成長 | 売上・EPSがともに15%以上成長 |
| `value_trap_warning` | Value trap warning | バリュートラップ注意 | 割安だがクオリティが低く、利益の質にも懸念がある銘柄 |

`value_trap_warning` renders with a `--status-warning` outline. Its results panel gains a persistent
note: `この条件は「安いが買うべきでない可能性がある」銘柄を洗い出すためのものです。`

### Filter fields

| Field id | label_en | label_ja | Unit | Type |
| --- | --- | --- | --- | --- |
| `total_score` | Composite score | 総合スコア | | 0-100 |
| `quant_score` | Quantitative score | 定量スコア | | 0-100 |
| `qual_score` | Qualitative overlay | 定性スコア | | -1.0 to +1.0 |
| `ml_pred` | Model prediction | モデル予測 | % | signed |
| `per_trailing` | P/E (trailing) | PER（実績） | 倍 | number, null when negative |
| `per_forward` | P/E (company forecast) | PER（会社予想） | 倍 | number |
| `pbr` | P/B | PBR | 倍 | number |
| `ev_ebitda` | EV/EBITDA | EV/EBITDA | 倍 | number |
| `earnings_yield` | Earnings yield | 益回り | % | number |
| `dividend_yield` | Dividend yield | 配当利回り | % | number |
| `roe` | ROE | ROE | % | number |
| `roic` | ROIC | ROIC | % | number |
| `equity_ratio` | Equity ratio | 自己資本比率 | % | number |
| `net_debt_ebitda` | Net debt / EBITDA | 純有利子負債 / EBITDA | 倍 | number |
| `accruals_ratio` | Accruals ratio | 利益の質 | | signed |
| `revenue_growth_yoy` | Revenue growth YoY | 売上成長率（前年比） | % | number |
| `eps_growth_yoy` | EPS growth YoY | EPS成長率（前年比） | % | number |
| `guidance_revision` | Guidance revision | 会社予想の改定 | | enum: 上方 / 下方 / 変更なし |
| `mom_12m` | 12-month momentum | 12ヶ月モメンタム | % | number |
| `mom_1m` | 1-month reversal | 1ヶ月リターン | % | number |
| `dist_52w_high` | Distance from 52w high | 52週高値からの乖離 | % | number |
| `above_ma200` | Above 200-day MA | 200日線より上 | | boolean |
| `rsi_14` | RSI(14) | RSI(14) | | 0-100 |
| `realized_vol_60d` | Realized volatility (60d) | 実現ボラティリティ (60営業日) | % | number |
| `garch_vol` | GARCH forecast volatility | GARCH予測ボラティリティ | % | number |
| `beta` | Beta | ベータ | | number |
| `fx_sensitivity` | FX sensitivity | 為替感応度 | | signed |
| `market_cap` | Market cap | 時価総額 | 円 | number |
| `adv_20d` | Average daily value (20d) | 平均売買代金 (20営業日) | 円 | number |
| `sector` | Sector | セクター | | multi-select |
| `days_to_earnings` | Days to earnings | 決算までの営業日数 | 営業日 | integer |
| `has_recent_filing` | Recent filing | 直近の開示あり | | boolean |
| `in_watchlist` | In watchlist | ウォッチリスト登録 | | boolean |
| `has_position` | Held | 保有中 | | boolean |

Operator labels come from `components.md` §4.4.

### Filter row rendering

```
セクター内で割安クオリティ

PER（会社予想）        以下      12.0  倍                     [削除]
ROIC                  以上      10.0  %                      [削除]
利益の質              以上      -0.05                        [削除]
平均売買代金 (20営業日) 以上     1.0   億円                    [削除]
セクター              のいずれか  輸送用機器, 電気機器 (+3)     [削除]

[+ 条件を追加]

ユニバース
  時価総額の下限          300億円
  平均売買代金の下限      1.0億円
  流動性の低い銘柄を除外   有効
  決算発表5営業日前の銘柄を除外  無効
```

Active filter summary example: `5件の条件 (AND)。1,994銘柄のうち142銘柄が該当。`

### Results table columns

Default column set, reorderable and toggleable through the column picker:

| Column | label_en | label_ja | Format | Default |
| --- | --- | --- | --- | --- |
| 1 | Ticker | 銘柄コード | `7203` | on, pinned |
| 2 | Name | 銘柄名 | `トヨタ自動車` | on, pinned |
| 3 | Sector | セクター | `輸送用機器` | on |
| 4 | Composite score | 総合スコア | `ScoreBadge` `78.4` | on |
| 5 | Reference price | 参考価格 | `3,125円` | on |
| 6 | Change | 前日比 | `DirectionValue` `+1.24%` | on |
| 7 | P/E (forecast) | PER（会社予想） | `10.4倍` | on |
| 8 | PBR | PBR | `1.18倍` | off |
| 9 | ROIC | ROIC | `12.4%` | on |
| 10 | Dividend yield | 配当利回り | `2.84%` | off |
| 11 | 12-month momentum | 12ヶ月モメンタム | `+18.4%` | on |
| 12 | Realized volatility | 実現ボラ | `22.4%` | off |
| 13 | Reason codes | 主な理由 | up to 2 chips `+2` | on |
| 14 | Days to earnings | 決算まで | `3営業日` | on |
| 15 | Market cap | 時価総額 | `42兆1,800億円` | off |
| 16 | Actions | 操作 | watchlist toggle, detail link | on, pinned right |

Table caption, always present:

```
参考価格は yfinance の15分遅延値です。スコアと財務指標は 2026年8月22日 時点、
財務は各銘柄の直近開示日基準です。
```

### Results summary bar

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Match count | Matches | 該当 | 142件 |
| Universe | Universe | 対象 | 1,994銘柄中 |
| Truncation | Truncated | 表示上限 | 上位100件を表示しています。条件を絞るか表示件数を増やしてください。 |
| Column picker | Columns | 表示する列 | 表示する列 (9 / 16) |
| Sort (mobile) | Sort | 並び替え | 並び替え: 総合スコア（降順） |

### Distribution strip

Four mini histograms of the fields used in the active filters, each 120 x 56px, showing the full
universe distribution with the filtered region highlighted and the threshold marked.

Caption per histogram example: `PER（会社予想）: 中央値 15.8倍、条件 12.0倍以下は下位27%`.

This exists to make it obvious when a filter is either trivially loose or absurdly tight.

## States

### Loading

- Initial: `FilterBuilder` renders immediately (it depends on no data), results show 10 skeleton
  rows at the final row height.
- Filter change: existing rows stay visible at full opacity, the summary bar shows a small spinner
  next to the match count, and the table gets `aria-busy="true"`. Never blank the table.

### Empty (no filters yet)

| Element | label_ja |
| --- | --- |
| Title | 条件を指定してください |
| Body | 左のパネルで条件を追加するか、上のプリセットから選んでください。 |
| Suggestion | よく使う出発点: 割安クオリティ / 上方修正モメンタム / バリュートラップ注意 |

### Empty (no matches)

| Element | label_ja |
| --- | --- |
| Title | 条件に一致する銘柄がありません |
| Body | 5件の条件すべてを満たす銘柄は見つかりませんでした。 |
| Diagnostic | 最も厳しい条件は「ROIC 10.0%以上」で、単独でも該当は284銘柄です。「PER（会社予想）12.0倍以下」との組み合わせで0件になっています。 |
| Action 1 | 最後に追加した条件を削除 |
| Action 2 | 条件をリセット |

The diagnostic line, computed server-side, is what makes an empty screener result useful instead of
frustrating.

### Not-ready

```
2026年8月23日のスコアはまだ生成されていません。
財務指標のみで絞り込むことは可能です。最新のスコアは 2026年8月22日 時点です。
[2026年8月22日のスコアで実行]
```

### Partial data

| Failing part | Behavior |
| --- | --- |
| `qual_score` unavailable (cost cap) | The qualitative filter field is disabled with the caption `定性スコアは本日生成されていません`, and the column renders `—` |
| Some tickers lack features | Those tickers are excluded from results and a note appears: `62銘柄は入力データが不足しているため対象外です` with a link listing them |
| Live prices unavailable | The 参考価格 and 前日比 columns render `—` with the caption `参考価格を取得できませんでした`. Filtering on other fields still works |
| Earnings calendar unavailable | 決算まで renders `—` and the `pre_earnings` preset is disabled with `決算予定日を取得できていません` |

Partial state never disables the whole screener. Filtering on the fields that do exist must keep
working.

### Error

```
スクリーニングを実行できませんでした
POST /api/v1/screener → 422
条件「PER（会社予想）」に不正な値が含まれています: "abc"
[条件を修正]
```

Validation errors point at the offending filter row and highlight it with `--status-danger`. The
user's filter state is never cleared by an error.

### Truncated

When the match count exceeds `limit`:

```
142件が該当しますが、上位100件を表示しています。
[表示件数を200件にする]  [条件を絞る]
```

### Offline

The screener requires a server round trip and cannot run offline. The page shows:

```
オフラインです
スクリーニングにはサーバーへの接続が必要です。
最後に実行した条件と結果（2026年8月22日 07:02 取得）を表示できます。
[前回の結果を表示]
```

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Preset chip | Click | Replaces the current filter set, runs immediately, sets `?preset=`. A confirm is shown only if the current set has unsaved edits |
| Add filter | Click | Appends an empty filter row with the field combobox focused |
| Field combobox | Type | Fuzzy search over field labels in both Japanese and English |
| Operator select | Change | Swaps the value input type (single / range / multi-select) and preserves the value where compatible |
| Value input | Blur or Enter | Runs the screen. Debounce 400ms while typing; no request per keystroke |
| Remove filter | Click | Removes the row and re-runs |
| Reset filters | Click | Clears to the empty state |
| Universe switches | Toggle | Re-runs |
| Apply (mobile sheet) | Click | Closes the sheet and re-runs; the footer shows the pending match count when a preview is available |
| Column header | Click (desktop) | Sorts; a second click reverses; a third clears back to the default sort |
| Column picker | Click | Popover with checkboxes; selection persists per market in settings |
| Sort sheet (mobile) | Select | Applies sort and closes |
| Result row | Click | Navigates to `/stocks/{market}/{ticker}` |
| Row score badge | Click | Popover with the score decomposition, does not navigate |
| Row reason chip | Click | Popover with the code definition; does not navigate |
| Row watchlist icon | Click | Toggles watchlist membership, optimistic, does not navigate |
| Row overflow `+2` | Click | Popover listing the remaining reason codes |
| Save screen | Click | Dialog asking for a name, then `POST /api/v1/screener/saved` |
| Saved screen select | Change | Loads that filter set and runs it |
| Delete saved screen | Click | Confirm dialog, then `DELETE /api/v1/screener/saved/{id}` |
| Export CSV | Click | Downloads the current result set with UTF-8 BOM; filename `screener_JP_2026-08-22.csv` |
| Histogram threshold | Drag (desktop) | Adjusts that filter's threshold and re-runs on release |
| Pagination | Click | Fetches the next page, keeping filters and sort |
| `/` | Keyboard | Focuses the field combobox of a new filter row |
| `Enter` in filter panel | Keyboard | Runs the screen |
| `Escape` in mobile sheet | Keyboard | Closes without applying |

## Data source

| Section | Endpoint |
| --- | --- |
| Run screen | `POST /api/v1/screener` with `{market, as_of, filters[], universe, sort, dir, limit, offset, columns[]}` |
| Field metadata | `GET /api/v1/screener/fields` (labels, units, types, valid operators) |
| Presets | `GET /api/v1/screener/presets` |
| Saved screens | `GET /api/v1/screener/saved`, `POST`, `DELETE /api/v1/screener/saved/{id}` |
| Distributions | Included in the screener response as `meta.distributions` |
| Watchlist toggle | `POST /api/v1/watchlist`, `DELETE /api/v1/watchlist/{market}/{ticker}` |

The response carries `meta.data_freshness`, `meta.excluded_count`, `meta.total_matched`,
`meta.truncated`, and `warnings[]`, all of which are rendered rather than ignored.

Populate from `sample-data.json` key `screener` (142-row summary metadata plus 12 concrete rows
covering high and low scores, a null PER, and a pre-earnings flag).
