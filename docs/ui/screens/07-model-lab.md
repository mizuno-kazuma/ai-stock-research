# 07. Model Lab

## Purpose

The screen where the user inspects whether the analytical engine is actually working. It shows Rank
IC over time, feature importance, the walk-forward validation structure, backtest results with
Deflated Sharpe Ratio, and the factor weight sets awaiting approval.

The screen has a specific job that no other screen has: making it easy to conclude that the model is
not good enough. Rank IC around 0.03 is a realistic outcome for this kind of setup, and the UI must
present that plainly rather than dressing it up. Every backtest displays its fee, slippage and
turnover assumptions permanently next to its results, and every Sharpe ratio is accompanied by the
deflated value and the number of trials that produced it. A backtest whose cost assumptions are
hidden is worthless, so the UI makes hiding them impossible.

This screen also holds the approval gate for factor weight changes proposed by the Evaluator. Weight
updates never apply automatically.

## Route

`/model-lab`

| Param | Values | Default |
| --- | --- | --- |
| `tab` | `health`, `runs`, `backtests`, `weights` | `health` |
| `market` | `JP`, `US` | global market setting |
| `horizon` | `H5`, `H20` | `H20` |
| `run_id` | model run id | none |
| `backtest_id` | backtest id | none |
| `range` | `3m`, `6m`, `1y`, `2y`, `max` | `1y` |

## Layout

### Desktop (>= 1280px)

12-column grid, tabbed. Tabs switch content here (unlike the stock detail page) because the sections
are independent workflows rather than one document.

Tab `health`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-3 / 4-6 / 7-9 / 10-12 | 4 `MetricCard`: Rank IC (20d), Rank IC (3m), coverage, degradation status |
| 2 | 1-8 | `IcTimeSeriesChart`, 320px, with a zero line and a rolling mean |
| 2 | 9-12 | `QuintileMonotonicityChart` (bar chart, 5 bars) |
| 3 | 1-6 | `FeatureImportancePanel` (top 20, horizontal bars) |
| 3 | 7-12 | `FeatureCorrelationHeatmap` |
| 4 | 1-12 | `ValidationStructurePanel`: walk-forward split visualization |

Tab `runs`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-4 | `ModelRunList` (sticky, scrollable) |
| 1 | 5-12 | `ModelRunDetail` |

Tab `backtests`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-12 | `NewBacktestButton` + `BacktestList` (table) |
| 2 | 1-12 | `BacktestResultCard` for the selected backtest, full width |
| 3 | 1-8 | `EquityCurveChart` |
| 3 | 9-12 | `BacktestStatsPanel` |

Tab `weights`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-6 | `ActiveWeightsPanel` |
| 1 | 7-12 | `ProposedWeightsPanel` with the approval control |
| 2 | 1-12 | `WeightHistoryChart` |

### Tablet (768px - 1279px)

8-column grid. Metric cards 2 x 2. All charts full width. `ModelRunList` becomes a select control
above the detail. Backtest tab keeps the list as a table with fewer columns.

### Mobile (< 768px)

Single column. This screen is explicitly desktop-oriented; mobile shows a reduced, read-only view.

- Tabs become a horizontally scrolling chip row.
- `health`: metric cards 2 x 2, IC chart 200px, quintile chart 200px, feature importance top 10 only,
  correlation heatmap replaced by a note `相関ヒートマップはデスクトップで表示されます`.
- `runs`: list only, tapping opens the detail as a full-height sheet.
- `backtests`: list as cards; results as a stacked card. The new-backtest form is **not available on
  mobile**, replaced by `バックテストの実行はデスクトップから行ってください`. This is deliberate:
  the form requires deliberate entry of cost parameters and is not suited to a phone.
- `weights`: read-only. The approval control is desktop-only, with the note
  `重みの承認はデスクトップから行ってください`.

## Component tree

```
ModelLabPage
├── AppShell
│   └── MainContent
│       ├── WarningBanner[]
│       ├── PageHeader
│       │   ├── PageTitle                        "モデルラボ"
│       │   ├── MarketToggleGroup
│       │   ├── HorizonToggleGroup
│       │   └── AsOfLabel
│       ├── TabBar                               モデルの状態 / 学習履歴 / バックテスト / ファクター重み
│       ├── TabPanel "モデルの状態"
│       │   ├── MetricCardGrid
│       │   │   ├── MetricCard                   Rank IC (20営業日)
│       │   │   ├── MetricCard                   Rank IC (3ヶ月)
│       │   │   ├── MetricCard                   カバー率
│       │   │   └── MetricCard                   劣化検出
│       │   ├── SectionCard "Rank ICの推移"
│       │   │   ├── IcTimeSeriesChart
│       │   │   │   ├── DailyIcBars
│       │   │   │   ├── Rolling20dMeanLine
│       │   │   │   ├── ZeroLine                 emphasized
│       │   │   │   └── RetrainMarkers
│       │   │   └── ChartCaption
│       │   ├── SectionCard "分位別リターン"
│       │   │   ├── QuintileMonotonicityChart
│       │   │   └── MonotonicityVerdictRow
│       │   ├── SectionCard "特徴量の重要度"
│       │   │   ├── FeatureImportancePanel
│       │   │   └── ImportanceCaution
│       │   ├── SectionCard "特徴量の相関"
│       │   │   └── FeatureCorrelationHeatmap
│       │   └── SectionCard "検証構造"
│       │       ├── ValidationStructurePanel
│       │       └── LeakageCheckList
│       ├── TabPanel "学習履歴"
│       │   ├── ModelRunList
│       │   └── ModelRunDetail
│       │       ├── RunMetaTable
│       │       ├── HyperparameterTable
│       │       ├── TrialCountRow                critical for DSR
│       │       ├── FoldMetricsTable
│       │       └── FeatureListTable
│       ├── TabPanel "バックテスト"
│       │   ├── NewBacktestButton
│       │   ├── BacktestList
│       │   ├── BacktestResultCard
│       │   │   ├── CostAssumptionRow            always visible
│       │   │   ├── ReturnStatsRow
│       │   │   ├── SharpeRow
│       │   │   ├── DeflatedSharpeRow
│       │   │   ├── SignificanceVerdictRow
│       │   │   └── TurnoverRow
│       │   ├── EquityCurveChart
│       │   └── BacktestStatsPanel
│       ├── TabPanel "ファクター重み"
│       │   ├── ActiveWeightsPanel
│       │   ├── ProposedWeightsPanel
│       │   │   ├── WeightDiffTable
│       │   │   ├── FitMetaRow
│       │   │   ├── ApproveButton
│       │   │   └── RejectButton
│       │   └── WeightHistoryChart
│       └── NewBacktestDialog
│           ├── StrategyNameInput
│           ├── PeriodRangeInput
│           ├── RebalanceFreqSelect
│           ├── NPositionsInput
│           ├── SignalSourceSelect
│           ├── FeeBpsInput                      required, no default
│           ├── SlippageBpsInput                 required, no default
│           ├── MaxTurnoverPctInput              required, no default
│           ├── UniverseFilterFields
│           ├── TrialCountDisclosureRow
│           └── SubmitButton
```

## Content spec

### Health metric cards

| Card | label_en | label_ja | Value example | Sub-line example |
| --- | --- | --- | --- | --- |
| Rank IC 20d | Rank IC (20 days) | Rank IC (直近20営業日) | 0.031 | n=20日 · 平均対比 +0.003 |
| Rank IC 3m | Rank IC (3 months) | Rank IC (直近3ヶ月) | 0.028 | n=62日 · t値 1.84 |
| Coverage | Coverage | カバー率 | 92.4% | 1,842 / 1,994銘柄 |
| Degradation | Degradation | 劣化検出 | 検出なし | 直近20日平均が3ヶ月平均の-50%を下回った場合に検出 |

A calibration note is attached to the Rank IC cards, permanently:

```
Rank IC 0.03 前後はこの種のモデルとして現実的な水準です。0.10 を超える値が継続する場合は、
リーク（未来情報の混入）を疑って検証してください。
```

This note is not a tooltip. It is visible text. An implausibly good number should make the user
suspicious, and the UI should teach that.

### IC time series

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Rank IC over time | Rank ICの推移 | Rank ICの推移 |
| Daily bars | Daily Rank IC | 日次 Rank IC | |
| Rolling mean | 20-day rolling mean | 20営業日移動平均 | 0.031 |
| Zero line | Zero | ゼロ | |
| Retrain marker | Retrained | 再学習 | 2026年7月1日 再学習 (特徴量 v3) |
| Caption | | | Rank IC は各日のクロスセクションにおける予測値と実現超過リターンのSpearman順位相関です。0が「予測力なし」を意味します。 |
| Summary | | | 期間中の平均 0.029、標準偏差 0.081、プラスの日 54% (n=248) |

The zero line is drawn at 1.5px in `--fg-secondary`, more prominent than other gridlines, because the
distance from zero is the whole point.

### Quintile monotonicity

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Returns by quintile | 分位別リターン | 分位別リターン (20営業日) |
| Q1 label | Q1 (lowest) | 第1分位（最下位） | -0.42% |
| Q2 | Q2 | 第2分位 | -0.08% |
| Q3 | Q3 | 第3分位 | +0.21% |
| Q4 | Q4 | 第4分位 | +0.44% |
| Q5 label | Q5 (highest) | 第5分位（最上位） | +0.91% |
| Spread | Q5 - Q1 spread | 第5分位 - 第1分位 | +1.33% |
| Verdict monotonic | Monotonic | 単調性あり | 分位が上がるほどリターンが高く、単調性が確認できます |
| Verdict not monotonic | Not monotonic | 単調性なし | 分位とリターンの関係が単調ではありません。スコアの序列に意味がない可能性があります |
| Caption | | | セクター中立化した超過リターンの平均。手数料・スリッページは含みません。 |

The caption explicitly states costs are excluded, because quintile spreads look far better before
costs than after them.

### Feature importance

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Feature importance | 特徴量の重要度 | 特徴量の重要度（上位20） |
| Metric select | Metric | 指標 | Gain / Split / Permutation |
| Row | | | `rev_guidance_op_3m` 予想改定（営業利益・3ヶ月） 0.142 |
| Caution | | | 重要度は「予測に寄与した度合い」であり、因果関係を示すものではありません。相関の高い特徴量の間では重要度が分散します。 |

Example top rows:

```
rev_guidance_op_3m     予想改定（営業利益・3ヶ月）      0.142
mom_12m_ex1m           12ヶ月モメンタム（直近1ヶ月除外） 0.118
earnings_yield         益回り                            0.096
roic                   ROIC                              0.081
accruals_ratio         利益の質                          0.074
realized_vol_60d       実現ボラティリティ (60営業日)     0.068
adv_20d_log            平均売買代金（対数）              0.061
fx_sensitivity         為替感応度                        0.054
```

### Validation structure

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Validation structure | 検証構造 | 検証構造 |
| Method | Method | 手法 | Purged Walk-Forward CV |
| Folds | Folds | 分割数 | 8 |
| Train window | Train window | 学習期間 | 252営業日（拡張型） |
| Test window | Test window | 検証期間 | 42営業日 |
| Purge | Purge | パージ | 20営業日（予測ホライズンと同じ） |
| Embargo | Embargo | エンバーゴ | 5営業日 |
| Caption | | | 学習期間と検証期間の間に、予測ホライズン分のパージとエンバーゴを設けています。KFoldやシャッフルを伴う分割は使用していません。 |

The split visualization renders 8 horizontal rows, each showing train (accent), purge (warning),
embargo (warning, hatched), and test (success) segments on a shared time axis. This makes leakage
structurally visible: if train and test ever touch, it shows.

Leakage check list, each item rendered with a pass or fail marker:

| Check | label_ja | State |
| --- | --- | --- |
| `T-LEAK-01` | 禁止された交差検証手法を使用していない | 合格 |
| `T-LEAK-02` | 参考現在値（prices_live）をモデルに渡していない | 合格 |
| `T-LEAK-03` | 学習期間と検証期間が重複していない | 合格 |
| `T-LEAK-04` | 合成ランダムデータでRank ICがゼロ近傍 | 合格 (IC=0.004, n=248) |
| `T-LEAK-05` | バックテストのエントリーが翌営業日始値 | 合格 |
| `T-PIT-01` | 財務データは開示日基準で参照 | 合格 |

Caption: `これらはCIで自動実行されているテストの直近結果です。1件でも失敗している場合、
スコアと推奨は信用できません。`

If any check fails, a page-level `--status-danger` banner appears:
`リーク検出テストが失敗しています。本日のスコアと推奨は信用できません。`

### Model run detail

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Run id | Run ID | 実行ID | `mr_20260801_h20_jp_003` |
| Kind | Model kind | 種別 | ランキング（LightGBM） |
| Trained at | Trained at | 学習日時 | 2026年8月1日 03:12 |
| Period | Training period | 学習期間 | 2024年8月1日 - 2026年7月31日 |
| Samples | Samples | サンプル数 | 892,140 (銘柄 x 営業日) |
| Features | Features | 特徴量数 | 42 (v3) |
| Objective | Objective | 目的関数 | regression + quantile (0.1 / 0.5 / 0.9) |
| Trials | Hyperparameter trials | 探索試行回数 | 120 |
| Trials note | | | この値はDeflated Sharpe Ratioの計算に使用されます。試行回数を記録しないバックテストは信用できません。 |
| Fold metrics | Per-fold Rank IC | 分割別 Rank IC | 0.021 / 0.038 / 0.019 / 0.044 / 0.026 / 0.031 / 0.012 / 0.035 |
| Fold spread | Fold dispersion | 分割間のばらつき | 標準偏差 0.010 |
| Status | Status | 状態 | 稼働中 / 保管 |

### Backtest result card

Cost assumptions render first, before any return figure. This ordering is mandatory.

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Cost row | Cost assumptions | コスト前提 | 手数料 5.0bp · スリッページ 10.0bp · 回転率上限 30%/月 |
| Period | Period | 期間 | 2024年8月1日 - 2026年8月1日 (24ヶ月) |
| Rebalance | Rebalance | リバランス | 月次 · 20銘柄等ウェイト |
| Total return | Total return | 累積リターン | +18.4% |
| Annualized | Annualized | 年率リターン | +8.8% |
| Benchmark | Benchmark | ベンチマーク | TOPIX +6.2% (年率) |
| Excess | Excess return | 超過リターン | +2.6% (年率) |
| Volatility | Volatility | ボラティリティ | 14.2% (年率) |
| Sharpe | Sharpe ratio | シャープレシオ | 0.62 |
| DSR | Deflated Sharpe Ratio | Deflated Sharpe Ratio | 0.18 |
| DSR inputs | | | 試行回数 120 · 検証期間 24ヶ月 · 歪度 -0.31 · 尖度 4.2 |
| Significance | Significance | 有意性 | 統計的に有意とは言えません (DSR p=0.24) |
| Max drawdown | Max drawdown | 最大ドローダウン | -12.8% (2025年3月 - 2025年6月) |
| Turnover | Realized turnover | 実現回転率 | 24.2%/月（上限 30%） |
| Cost drag | Cost drag | コストの影響 | -1.8%/年（コスト前 年率 +10.6%） |
| Hit rate | Monthly hit rate | 月次勝率 | 58% (n=24) |

The significance verdict is generated server-side and rendered verbatim. When DSR indicates
significance:

```
有意性: Deflated Sharpe Ratio 0.71 (p=0.018)。120回の試行を考慮しても有意です。
```

When it does not:

```
有意性: 統計的に有意とは言えません (DSR 0.18, p=0.24)。
シャープレシオ 0.62 は120回のパラメータ探索の結果であり、偶然の可能性を排除できません。
```

The cost-drag row is important: it shows what the strategy looked like before costs, next to what it
looks like after, which is where most naive backtests fall apart.

### New backtest dialog

| Field | label_en | label_ja | Validation |
| --- | --- | --- | --- |
| Strategy name | Strategy name | 戦略名 | required, 1-64 chars |
| Period | Period | 期間 | required, minimum 12 months, must end at least 20 business days before today |
| Rebalance | Rebalance frequency | リバランス頻度 | 週次 / 月次 / 四半期 |
| Positions | Number of positions | 銘柄数 | 5-100 |
| Signal source | Signal | シグナル | 定量スコア / モデル予測 / 総合スコア + 重みセット指定 |
| Fee | Fee (bp) | 手数料 (bp) | **required, no default value** |
| Slippage | Slippage (bp) | スリッページ (bp) | **required, no default value** |
| Max turnover | Max turnover (%/period) | 回転率上限 (%/期間) | **required, no default value** |
| Min ADV | Minimum daily value | 平均売買代金の下限 | optional |
| Min market cap | Minimum market cap | 時価総額の下限 | optional |
| Trial disclosure | | | この実行は探索試行回数に加算され、Deflated Sharpe Ratioの計算に反映されます。現在の累積試行回数: 120 |

The three cost fields render with empty values and placeholder guidance rather than pre-filled
numbers:

| Field | Placeholder |
| --- | --- |
| 手数料 (bp) | 例: 5.0（楽天証券の現物取引を想定） |
| スリッページ (bp) | 例: 10.0（流動性の高い大型株の想定） |
| 回転率上限 (%/期間) | 例: 30.0 |

Submit is disabled until all three are filled. Attempting to submit without them shows
`手数料・スリッページ・回転率上限は必須です。これらを省略したバックテストは実運用の成績を
大きく過大評価します。`

### Factor weights

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Active heading | Active weights | 稼働中の重み | 稼働中の重み (ws_20260701_a) |
| Proposed heading | Proposed weights | 提案された重み | 提案された重み (ws_20260801_b) |
| Column: group | Factor group | ファクターグループ | バリュエーション |
| Column: active | Active | 現在 | 0.22 |
| Column: proposed | Proposed | 提案 | 0.26 |
| Column: change | Change | 変化 | +0.04 |
| Fit meta | Fit basis | 推定の根拠 | Ridge回帰（非負制約）· 対象 214件の推奨実績 · 期間 2026年2月 - 2026年8月 · 現行重みと50%ブレンド |
| Approve | Approve | 承認して適用 | |
| Reject | Reject | 却下 | |
| Approval note | | | 重みの変更は承認するまで適用されません。承認後の最初の推奨生成から反映されます。 |
| No proposal | | | 現在、提案されている重みの変更はありません。 |
| Insufficient samples | | | 実績サンプルが不足しているため（46件、最低100件必要）、重みの再推定は行われていません。 |

## States

### Loading

Metric cards skeleton, charts skeleton at exact final heights. The leakage check list renders last
because it depends on the CI results endpoint.

### Empty

| Case | label_ja |
| --- | --- |
| No model trained yet | モデルがまだ学習されていません。Analystジョブの初回実行後に表示されます。 |
| No IC history | Rank ICの履歴がまだありません。運用開始から20営業日経過後に表示されます。 |
| No backtests | バックテストの実行履歴がありません。[バックテストを実行] |
| No weight proposal | 提案されている重みの変更はありません。 |
| No feature importance | 特徴量の重要度は学習済みモデルが必要です。 |

### Not-ready

```
本日のRank ICはまだ算出されていません。20営業日ホライズンの実績確定には
20営業日を要するため、直近20営業日分のICは順次確定します。
```

This explains a genuinely confusing property of the metric rather than showing a blank.

### Partial data

| Failing part | Behavior |
| --- | --- |
| Evaluator did not run | IC cards show the previous day's values with `実績評価が未実行のため前営業日の値を表示しています` |
| CI results unavailable | Leakage check list shows `テスト結果を取得できませんでした` in `--status-warning` with a note that the checks could not be confirmed, which is treated as a warning rather than a pass |
| Backtest still running | That row shows a progress state with elapsed time and an estimated completion; the result card shows `実行中（経過 3分12秒 / 推定 8分）` |
| Backtest failed | Row shows `失敗` with the error message and a `再実行` action |
| Permutation importance unavailable | The metric select disables that option with `Permutation importanceは計算に時間がかかるため、週次でのみ算出しています` |
| Correlation heatmap partial | Missing pairs render as blank cells with a legend note |

### Error

```
モデル情報を読み込めませんでした
GET /api/v1/models/health → 500
[再試行]
```

Backtest submission error:

```
バックテストを開始できませんでした
POST /api/v1/backtests → 422
回転率上限が指定されていません。
[入力に戻る]
```

### Offline

Cached health metrics and the last backtest results render read-only. The new-backtest button is
disabled with `オフラインでは実行できません`. Weight approval is disabled.

### Degraded

If the model is flagged as degraded:

```
モデルの成績低下を検出しました。直近20営業日の Rank IC は 0.004 で、
3ヶ月平均 0.028 を大きく下回っています。本日の推奨は確信度を一段引き下げて生成されています。
```

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Tab | Click | Switches panel, updates `?tab=` |
| Market / horizon toggle | Click | Refetches all panels for that combination |
| IC chart hover | Hover | Readout with date, daily IC, rolling mean, and the number of stocks in the cross-section |
| Retrain marker | Click | Navigates to the `runs` tab with that run selected |
| Rank IC calibration note | Click | Popover with a longer explanation and a link to the leakage checks |
| Quintile bar | Click | Opens the constituent list for that quintile on the selected date |
| Feature importance metric select | Change | Refetches importance with that metric |
| Feature importance row | Click | Popover with the feature definition, its formula summary, and the `as_of` rule that governs it |
| Correlation heatmap cell | Hover | Shows the pair and the coefficient |
| Validation split row | Click | Popover with the exact train / purge / embargo / test date ranges for that fold |
| Leakage check row | Click | Popover with the test's purpose and the last run timestamp |
| Model run list row | Click | Loads the detail, updates `?run_id=` |
| Trial count row | Click | Popover explaining how trial count enters the DSR calculation |
| New backtest | Click | Opens the dialog (desktop only) |
| Backtest submit | Click | `POST /api/v1/backtests`, returns 202, the row appears with a running state, progress arrives over SSE |
| Backtest row | Click | Loads the result card, updates `?backtest_id=` |
| Backtest cost row | Click | Popover explaining each cost component and its typical range |
| Equity curve hover | Hover | Readout with date, portfolio value, benchmark, drawdown |
| Backtest trades link | Click | Opens the trade list for that backtest in a sheet |
| DSR row | Click | Popover explaining Deflated Sharpe Ratio in Japanese: why the number of trials matters and what deflation does |
| Approve weights | Click | Confirm dialog showing the diff again and the note that it applies from the next generation, then `POST /api/v1/factor-weights/{id}/activate` |
| Reject weights | Click | Confirm dialog with an optional reason, then marks the proposal rejected |
| Weight history chart | Hover | Readout with the weight set id and activation date |
| `1`-`4` | Keyboard | Switch tabs |

## Data source

| Section | Endpoint |
| --- | --- |
| Health metrics | `GET /api/v1/models/health` |
| IC time series | `GET /api/v1/models/runs/{run_id}/ic-timeseries` |
| Feature importance | `GET /api/v1/models/runs/{run_id}/feature-importance?metric=gain` |
| Model runs | `GET /api/v1/models/runs?kind=ranker&limit=20`, `GET /api/v1/models/runs/{run_id}` |
| Backtest list | `GET /api/v1/backtests?limit=20` |
| Backtest detail | `GET /api/v1/backtests/{backtest_id}` |
| Equity curve | `GET /api/v1/backtests/{backtest_id}/equity-curve` |
| Backtest trades | `GET /api/v1/backtests/{backtest_id}/trades?limit=200` |
| Run backtest | `POST /api/v1/backtests` (202 + `job_run_id`) |
| Backtest progress | `GET /api/v1/agent/events` (SSE) |
| Weights | `GET /api/v1/factor-weights?market=JP&horizon=H20` |
| Approve weights | `POST /api/v1/factor-weights/{weight_set_id}/activate` |
| Leakage checks | `GET /api/v1/system/health` field `test_results` |

Populate from `sample-data.json` keys `model_health`, `model_runs`, `backtests` (one significant, one
not significant, one failed, one running), and `factor_weights` (with a pending proposal).
