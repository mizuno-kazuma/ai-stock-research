# 06. FX and Macro

## Purpose

The USD/JPY forecast and the macro context around it. Exchange rate expectations drive a large part
of Japanese equity earnings, so this screen exists both as a standalone view and as the source of the
`為替が追い風` / `為替が逆風` reason codes on recommendation cards.

This is the screen where statistical honesty is most likely to be tested, because a currency forecast
looks authoritative and almost never beats a random walk. The design therefore inverts the usual
emphasis: the baseline comparison verdict is rendered *above* the forecast, in plain Japanese, in
full sentences. If the Diebold-Mariano test does not reject the null, the screen says so before it
shows a single predicted number. A user must not be able to read the forecast without first reading
whether the model has demonstrated any edge at all.

## Route

`/macro`

| Param | Values | Default |
| --- | --- | --- |
| `pair` | `USDJPY` | `USDJPY` (single pair in Phase A) |
| `range` | `6m`, `1y`, `3y`, `5y`, `10y` | `1y` |
| `horizon` | `H5`, `H20`, `H60` | `H20` |
| `series` | comma-separated FRED ids | `DGS10,DGS2,DEXJPUS,CPIAUCSL` |
| `as_of` | ISO date | latest available |

## Layout

### Desktop (>= 1280px)

12-column grid.

| Row | Columns | Content |
| --- | --- | --- |
| 0 | 1-12 | `WarningBanner[]` |
| 1 | 1-12 | `PageHeader`: title, pair, current level, as-of |
| 2 | 1-12 | `BaselineVerdictPanel` (full width, prominent, always first) |
| 3 | 1-8 | `FanChart`: history + forecast fan with 80% and 95% bands, 400px tall |
| 3 | 9-12 | `ForecastTable`: per-horizon point, interval, hit rate, model used |
| 4 | 1-6 | `ModelComparisonTable`: each model versus random walk |
| 4 | 7-12 | `RateDifferentialChart`: US-JP 10y and 2y spread overlaid on USDJPY |
| 5 | 1-4 | `VolatilityPanel`: GARCH forecast, realized vol, implied comparison note |
| 5 | 5-12 | `MacroSeriesGrid`: 6 `MacroSeriesCard`, 2 rows x 3 |
| 6 | 1-12 | `FxSensitivityTable`: which held and watched tickers are most FX sensitive |

### Tablet (768px - 1279px)

8-column grid. `BaselineVerdictPanel` full width. `FanChart` full width at 320px with the
`ForecastTable` below it. `ModelComparisonTable` and `RateDifferentialChart` stack full width.
`MacroSeriesGrid` becomes 2 columns.

### Mobile (< 768px)

Single column.

- `BaselineVerdictPanel` renders first and is not collapsible.
- `FanChart` 220px tall, no crosshair, tap shows a callout. The forecast fan is drawn but the
  gridline density is halved.
- `ForecastTable` becomes stacked rows, one horizon per card.
- `ModelComparisonTable` converts to a card list, one card per model.
- `RateDifferentialChart` 180px tall, single spread series (10y only) with a toggle for 2y.
- `MacroSeriesGrid` single column; each card 120px tall with a sparkline.
- `FxSensitivityTable` converts to a card list, limited to the top 8 tickers with a "すべて見る"
  link to `/screener?sort=fx_sensitivity`.

## Component tree

```
FxMacroPage
├── AppShell
│   └── MainContent
│       ├── WarningBanner[]
│       ├── PageHeader
│       │   ├── PageTitle                       "為替・マクロ"
│       │   ├── PairLabel                       USD/JPY
│       │   ├── CurrentLevelBlock
│       │   │   ├── DirectionValue              152.34円 +0.41%
│       │   │   └── SourceCaption               FRED DEXJPUS · 2026-08-21 / 参考現在値 18:35
│       │   └── AsOfLabel
│       ├── BaselineVerdictPanel
│       │   ├── VerdictHeadline                 from API verdict_ja, rendered verbatim
│       │   ├── DieboldMarianoRow               DM統計量 / p値 / サンプル数
│       │   ├── BaselineRmseRow                 ランダムウォークのRMSE
│       │   ├── ModelRmseRow                    モデルのRMSE
│       │   └── InterpretationNote
│       ├── SectionCard "予測"
│       │   ├── HorizonToggleGroup              5営業日 / 20営業日 / 60営業日
│       │   ├── FanChart
│       │   │   ├── HistoryLine
│       │   │   ├── ForecastMedianLine          dashed
│       │   │   ├── Band80
│       │   │   ├── Band95
│       │   │   ├── RandomWalkReferenceLine     flat line at the last observed level
│       │   │   └── ForecastStartDivider
│       │   ├── ChartCaption
│       │   └── ForecastTable
│       │       └── ForecastRow[]               per horizon
│       ├── SectionCard "モデル比較"
│       │   └── ModelComparisonTable
│       ├── SectionCard "日米金利差"
│       │   ├── RateDifferentialChart
│       │   └── CorrelationNote
│       ├── SectionCard "ボラティリティ"
│       │   └── VolatilityPanel
│       ├── SectionCard "マクロ指標"
│       │   └── MacroSeriesGrid
│       │       └── MacroSeriesCard x6
│       └── SectionCard "為替感応度の高い銘柄"
│           └── FxSensitivityTable
```

## Content spec

### Page header

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | FX and macro | 為替・マクロ | 為替・マクロ |
| Pair | Pair | 通貨ペア | USD/JPY |
| Current | Current | 現在値 | 152.34円 |
| Change | Change | 前日比 | +0.41% (+0.62円) |
| Official source | Official close | 公式終値 | FRED DEXJPUS · 2026年8月21日 |
| Reference source | Reference current | 参考現在値 | yfinance · 2026年8月22日 18:35 |

The two sources are labeled separately and never merged into one number, mirroring the research /
live price separation used for equities.

### Baseline verdict panel (the most important block on the screen)

Rendered above the forecast, full width, `--status-*-bg` background matched to the verdict.

Verdict when no edge is demonstrated (the expected default):

| Element | label_en | label_ja |
| --- | --- | --- |
| Headline | No demonstrated edge over the baseline | ランダムウォークに対する優位性は確認できていません |
| Body | | 過去248営業日の予測を検証した結果、ARIMAXモデルの予測精度はランダムウォーク（前日値をそのまま予測とする手法）と統計的に区別できませんでした。以下の予測値は参考情報として扱ってください。 |
| DM row | Diebold-Mariano test | Diebold-Mariano検定 | DM統計量 -1.02 · p値 0.31 · n=248 (HAC分散、ラグ5) |
| Baseline RMSE | Baseline RMSE | ベースラインのRMSE | 1.842円 |
| Model RMSE | Model RMSE | モデルのRMSE | 1.826円 |
| Interpretation | | | RMSEの差は0.9%で、統計的に有意ではありません。 |

Verdict when an edge is demonstrated:

| Element | label_ja |
| --- | --- |
| Headline | ランダムウォークに対する優位性が確認できました |
| Body | 過去248営業日の検証で、VECMモデルの予測精度がランダムウォークを有意に上回りました（p=0.012）。ただし優位性の幅は小さく、取引コストを考慮すると実用上の意味は限定的な可能性があります。 |
| DM row | DM統計量 2.51 · p値 0.012 · n=248 (HAC分散、ラグ5) |

Verdict when there is not enough history:

| Element | label_ja |
| --- | --- |
| Headline | 優位性の判定にはサンプルが不足しています |
| Body | 検証サンプルが62営業日しかありません。判定には最低120営業日を必要とします。予測値は表示しますが、精度は未検証です。 |

The `verdict_ja` string is produced by the API. The UI renders it verbatim and does not paraphrase,
shorten, or soften it. This is deliberate: it removes the possibility of a presentation-layer bug
turning "no edge" into an optimistic headline.

### Fan chart

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Chart title | USD/JPY forecast | ドル円の予測 | ドル円の予測 (20営業日) |
| Median | Median forecast | 中央予測 | 152.80円 |
| Band 80 | 80% interval | 80%区間 | [150.90円, 154.70円] |
| Band 95 | 95% interval | 95%区間 | [149.40円, 156.30円] |
| Baseline line | Random walk baseline | ランダムウォーク | 152.34円（現在値を維持） |
| Divider | Forecast starts here | ここから予測 | ここから予測 |
| Caption | | | 実績は FRED DEXJPUS の日次終値。予測はARIMAX(1,0,1) + 日米金利差を外生変数とし、GARCH(1,1)で分散を推定した分位予測です。区間は予測区間であり、信頼区間ではありません。 |

The random-walk reference line is drawn in `--chart-baseline` and is always visible in the forecast
region. Seeing the flat baseline next to the model's fan makes the practical size of the claimed
edge obvious at a glance.

### Forecast table

| Column | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Horizon | Horizon | 期間 | 20営業日 |
| Point | Median | 中央予測 | 152.80円 |
| Change | Implied change | 想定変化 | +0.30% (+0.46円) |
| Interval 80 | 80% interval | 80%区間 | [150.90円, 154.70円] |
| Interval 95 | 95% interval | 95%区間 | [149.40円, 156.30円] |
| Direction hit rate | Directional hit rate | 方向的中率 | 51% (n=248) |
| Model | Model | モデル | ARIMAX(1,0,1) |
| Baseline verdict | vs baseline | ベースライン比較 | 優位性なし (p=0.31) |

A directional hit rate near 50% is displayed as-is, without any framing that makes it sound better
than a coin flip.

### Model comparison table

| Column | label_ja | Example rows |
| --- | --- | --- |
| モデル | | ランダムウォーク / ARIMAX(1,0,1) / VECM(2) / GARCH平均回帰 |
| RMSE | | 1.842 / 1.826 / 1.871 / 1.858 |
| MAE | | 1.402 / 1.388 / 1.421 / 1.412 |
| 方向的中率 | | 50% (n=248) / 51% (n=248) / 49% (n=248) / 50% (n=248) |
| DM検定 p値 | | — / 0.31 / 0.72 / 0.58 |
| 判定 | | ベースライン / 優位性なし / 優位性なし / 優位性なし |

Caption: `すべてのモデルは Purged Walk-Forward で検証しています。学習期間と検証期間の間に5営業日の
embargoを設けています。`

Row-level highlight: only a model with `p < 0.05` gets an `--status-success` marker. Everything else
is neutral. There is no "best model" badge based on RMSE alone, because ranking by an insignificant
difference is exactly the error this panel exists to prevent.

### Rate differential

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | US-JP rate differential | 日米金利差 | 日米金利差 |
| 10y spread | 10-year spread | 10年金利差 | 3.42% (米 4.18% - 日 0.76%) |
| 2y spread | 2-year spread | 2年金利差 | 3.88% (米 4.42% - 日 0.54%) |
| Correlation | Correlation with USDJPY | ドル円との相関 | 0.72（過去1年、日次変化率） |
| Note | | | 相関は因果を意味しません。金利差はモデルの外生変数として使用していますが、単独の売買根拠にはなりません。 |
| Source | Source | 出典 | FRED: DGS10, DGS2, IRLTLT01JPM156N |

### Volatility panel

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Volatility | ボラティリティ | ボラティリティ |
| Realized | Realized (20d, annualized) | 実現ボラ (20営業日・年率) | 8.42% |
| Realized 60 | Realized (60d, annualized) | 実現ボラ (60営業日・年率) | 9.18% |
| GARCH | GARCH(1,1) forecast (20d) | GARCH予測 (20営業日) | 8.94% |
| Persistence | Persistence (alpha + beta) | 持続性 (α+β) | 0.962 |
| Convergence | Model convergence | モデルの収束 | 収束（定常条件を満たす） |
| Regime | Volatility regime | ボラティリティ局面 | 低ボラ局面（過去3年の下位30%） |
| Regime note | | | 局面判定は注意喚起のためのもので、予測には使用していません。 |

When GARCH fails to converge or `alpha + beta >= 1`:

```
GARCHモデルが収束しなかったため、実現ボラティリティ (EWMA, λ=0.94) を代替値として使用しています。
```

### Macro series grid

Six cards, each with a sparkline, latest value, change, and vintage information.

| Series | label_en | label_ja | FRED id | Example |
| --- | --- | --- | --- | --- |
| 1 | US 10-year Treasury | 米10年国債利回り | `DGS10` | 4.18% (前月比 -0.12pt) |
| 2 | US 2-year Treasury | 米2年国債利回り | `DGS2` | 4.42% (前月比 -0.08pt) |
| 3 | US CPI (YoY) | 米CPI（前年同月比） | `CPIAUCSL` | 2.8% (2026年7月分) |
| 4 | US unemployment | 米失業率 | `UNRATE` | 4.2% (2026年7月分) |
| 5 | JP 10-year JGB | 日10年国債利回り | `IRLTLT01JPM156N` | 0.76% (2026年7月分) |
| 6 | USD/JPY | ドル円 | `DEXJPUS` | 152.34円 |

Each card carries a vintage caption because macro data is revised:

```
2026年7月分 · 2026年8月13日 公表 · 改定あり（速報 2.9% → 確報 2.8%）
```

Caption for the whole grid: `マクロ統計は改定されるため、モデルは各時点で公表されていた値
（vintage）のみを使用しています。表示値は最新の確報値です。`

### FX sensitivity table

| Column | label_ja | Example |
| --- | --- | --- |
| 銘柄 | | 7203 トヨタ自動車 |
| 保有・登録 | | 保有 / ウォッチ / 推奨 |
| 為替感応度 | | +0.42 |
| 円安1円あたりの営業利益影響 | | +450億円（会社開示ベース） |
| 20営業日リターン | | +6.2% |
| 相関 | | 0.68（過去1年） |
| 判定 | | 円安メリット |

Caption: `感応度はドル円の変化率に対する株価変化率の回帰係数です。会社開示の為替感応度が
入手できる場合はその値も併記しています。`

## States

### Loading

- `BaselineVerdictPanel` shows a skeleton at its final height (140px) so the forecast never briefly
  appears above it.
- `FanChart` skeleton at exact final height.
- Macro cards render as 6 skeletons.
- Loading order: verdict panel, then fan chart, then everything else. The forecast numbers must
  never render before the verdict.

### Empty

| Case | label_ja |
| --- | --- |
| No FX history yet | 為替データがまだ取得されていません。データ収集ジョブを実行してください。 |
| No forecast yet | 為替予測はまだ生成されていません。Analystジョブの完了後に表示されます。 |
| No macro series | マクロ指標が取得されていません。FRED APIキーが設定されているか確認してください。 |
| No FX-sensitive tickers | 保有・ウォッチ銘柄がないため、感応度の一覧を表示できません。 |

### Not-ready

```
2026年8月23日の予測はまだ生成されていません。
最新の予測は 2026年8月22日 時点のものです。   [2026年8月22日を表示]
```

### Partial data

| Failing part | Behavior |
| --- | --- |
| FRED fetch failed | Page-level warning: `FREDからのデータ取得に失敗しました。表示中の値は2026年8月20日時点です。` The forecast section shows the last generated forecast with a `stale` marker |
| Rate series missing | `RateDifferentialChart` renders `—` and the forecast table notes `金利差を外生変数として使用できなかったため、ARIMAモデル（外生変数なし）の予測を表示しています` |
| GARCH did not converge | Volatility panel shows the EWMA fallback with the explanation above |
| Insufficient validation history | Verdict panel shows the "not enough samples" variant; the forecast is still rendered but the forecast table's baseline column shows `検証不足` |
| Macro series partially missing | Missing cards render `—` with `この系列は取得できませんでした` and a retry link; the rest render normally |
| Company FX sensitivity unavailable | That column renders `—`; the regression-based sensitivity still renders |

### Error

```
為替データを読み込めませんでした
GET /api/v1/fx/USDJPY → 500
[再試行]
```

If the forecast fails but history succeeds, render the history chart and show a section-level error
in the forecast area only. Historical FX data is useful on its own.

### Stale

```
為替データが3営業日更新されていません（最終 2026年8月19日）。
予測は古いデータに基づくため、参考程度に扱ってください。
```

### Offline

History and the last generated forecast render from cache. The verdict panel renders from cache and
is explicitly timestamped: `2026年8月22日 06:19 に生成された判定です。`

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Range selector | Click | Refetches history for the range; the forecast region is unaffected |
| Horizon toggle | Click | Switches the fan chart's forecast horizon and highlights the matching forecast-table row |
| Fan chart hover (desktop) | Hover | Readout with date, actual or median, and both intervals |
| Fan chart tap (mobile) | Tap | Value callout at the tapped date |
| Baseline line legend | Click | Toggles the random-walk reference line. Cannot be hidden permanently; it re-enables on reload |
| DM test row | Click | Popover explaining the test in Japanese: what the null hypothesis is, why HAC variance is used, and what the p-value does and does not mean |
| Model comparison row | Click | Expands to show the model's coefficients, the training window, and the walk-forward split count |
| Rate differential legend | Click | Toggles 10y / 2y series |
| Correlation value | Click | Popover with the rolling correlation chart over the selected range |
| Macro card | Click | Expands to a full chart in a sheet with the revision history table |
| Macro card vintage caption | Click | Popover listing the revision sequence with dates |
| FX sensitivity row | Click | Navigates to `/stocks/{market}/{ticker}` |
| FX sensitivity "すべて見る" | Click | `/screener?sort=fx_sensitivity&dir=desc` |
| Chart accessibility toggle | Click | Replaces each chart with an equivalent data table |
| `1` / `2` / `3` | Keyboard | Switch horizon to H5 / H20 / H60 |

## Data source

| Section | Endpoint |
| --- | --- |
| Current, forecast, verdict, model comparison | `GET /api/v1/fx/USDJPY?as_of=2026-08-22` |
| History | `GET /api/v1/fx/USDJPY/history?range=1y` |
| Macro series | `GET /api/v1/macro/series?ids=DGS10,DGS2,CPIAUCSL,UNRATE,IRLTLT01JPM156N,DEXJPUS&range=5y` |
| Rate differential | `GET /api/v1/macro/rate-differential?range=5y` |
| FX sensitivity | `GET /api/v1/screener` with `sort=fx_sensitivity` restricted to watchlist and holdings |

The `verdict_ja`, `dm_stat`, `dm_pvalue`, `n_validation`, `baseline_rmse`, and `model_rmse` fields
are all required in the FX response. If any of them is null, the UI renders the "not enough samples"
variant rather than hiding the panel.

Populate from `sample-data.json` keys `fx` (including a full model comparison array where no model
beats the baseline) and `macro_series`.
