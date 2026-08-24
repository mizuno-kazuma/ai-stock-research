# 10. Settings

## Purpose

Every user-adjustable behavior in one place, organized by consequence rather than by subsystem. Two
groups matter more than the rest and are placed first.

**Direction colors.** The Japanese convention (red = up, blue = down) and the US convention
(green = up, red = down) are exact opposites. A user who reads the wrong convention for a second
reads the position backwards. This is the first setting on the screen, it has a live preview, and it
is a first-class product setting rather than a theme detail.

**Cost controls.** The daily and monthly LLM caps and the kill switch live here. Changing a cap
changes how much money the system can spend without asking, so the current spend is shown next to
the input and lowering a cap below today's spend is explained rather than silently accepted.

The data-plan section is where the J-Quants free-plan delay is documented in the product itself. The
switch to the paid Light plan must be a configuration change and nothing more, so this screen shows
what changes when it is flipped, and what stays the same.

There is no account section. Phase A is single-user with no authentication.

## Route

`/settings`

| Param | Values | Default |
| --- | --- | --- |
| `section` | `display`, `cost`, `data`, `analysis`, `notifications`, `system` | `display` |

Anchors: `#display`, `#cost`, `#data`, `#analysis`, `#notifications`, `#system`.

## Layout

### Desktop (>= 1280px)

12-column grid, two-pane.

| Region | Columns | Behavior |
| --- | --- | --- |
| `SettingsNav` | 1-3 | Sticky vertical nav with 6 section links and a jump-to-anchor behavior |
| `SettingsContent` | 4-9 | Section cards, single column, max width 720px for readability |
| `PreviewPane` | 10-12 | Sticky live preview showing a sample recommendation row, a price change, and a chart snippet rendered with the current display settings |

The preview pane is what makes the direction-color setting safe to change. The user sees the effect
before leaving the screen.

### Tablet (768px - 1279px)

8-column grid. `SettingsNav` becomes a horizontal tab row. Content spans 1-8. The preview pane moves
inline inside the display section.

### Mobile (< 768px)

Single column.

- Section nav becomes a list of 6 rows that navigate into the section (a drill-down pattern rather
  than anchors, because long scroll settings pages are hard to use on a phone).
- Each section is its own view with a back affordance.
- The display section's preview renders inline directly beneath the direction-color control.
- Destructive and desktop-only controls are noted as such rather than hidden: rebuilding the vector
  store and running a backup are shown with
  `この操作はデスクトップから実行してください`.

## Component tree

```
SettingsPage
├── AppShell
│   └── MainContent
│       ├── PageHeader
│       │   ├── PageTitle                       "設定"
│       │   └── SaveStateIndicator              自動保存の状態
│       ├── SettingsNav
│       │   └── NavItem x6                      表示 / コスト / データ / 分析 / 通知 / システム
│       ├── SettingsContent
│       │   ├── SettingsSection "表示" #display
│       │   │   ├── DirectionColorControl
│       │   │   │   ├── OptionCard "日本式"
│       │   │   │   ├── OptionCard "米国式"
│       │   │   │   └── PreviewRow
│       │   │   ├── ThemeControl                システム / ダーク / ライト
│       │   │   ├── DefaultMarketSelect
│       │   │   ├── NumberFormatControl
│       │   │   ├── DensityControl
│       │   │   └── ReducedMotionNote
│       │   ├── SettingsSection "コスト" #cost
│       │   │   ├── DailyCapInput
│       │   │   ├── MonthlyCapInput
│       │   │   ├── CurrentSpendRow
│       │   │   ├── KillSwitchControl
│       │   │   ├── ModelTierTable
│       │   │   └── CostAlertThresholdInput
│       │   ├── SettingsSection "データ" #data
│       │   │   ├── JQuantsPlanControl
│       │   │   ├── DataSourceStatusTable
│       │   │   ├── TdnetEnableSwitch
│       │   │   ├── CollectionScheduleTable
│       │   │   ├── UniverseControl
│       │   │   └── DataDirectoryRow
│       │   ├── SettingsSection "分析" #analysis
│       │   │   ├── HorizonDefaultSelect
│       │   │   ├── RecommendationCountInput
│       │   │   ├── RiskConstraintFields
│       │   │   ├── QualScoreCapRow             read-only
│       │   │   ├── WeightApprovalModeControl
│       │   │   └── FeatureVersionRow           read-only
│       │   ├── SettingsSection "通知" #notifications
│       │   │   ├── InAppAlertToggles
│       │   │   ├── WebPushControl
│       │   │   ├── WebhookControl
│       │   │   ├── QuietHoursControl
│       │   │   └── NotificationTestButton
│       │   └── SettingsSection "システム" #system
│       │       ├── VersionInfoTable
│       │       ├── HealthSummaryTable
│       │       ├── BackupPanel
│       │       ├── VectorStoreRebuildPanel
│       │       ├── ExportPanel
│       │       └── DiagnosticsPanel
│       └── PreviewPane
│           ├── PreviewRecommendationRow
│           ├── PreviewPriceChange
│           └── PreviewMiniChart
```

## Content spec

### Display section

| Element | label_en | label_ja | Example / options |
| --- | --- | --- | --- |
| Section title | Display | 表示 | 表示 |
| Direction colors | Up and down colors | 上昇・下落の色 | |
| Option JP | Japanese convention | 日本式 | 上昇 = 赤 / 下落 = 青 |
| Option US | US convention | 米国式 | 上昇 = 緑 / 下落 = 赤 |
| Direction note | | | 日本と米国では上昇・下落の色が逆です。取り違えると保有状況を正反対に読み取る危険があるため、必ず自分が慣れている方式を選んでください。 |
| Accessibility note | | | どちらを選んでも、符号（+ / -）と矢印を併記します。色だけで方向を判断する必要はありません。 |
| Theme | Theme | テーマ | システムに合わせる / ダーク / ライト |
| Theme note | | | 既定はダークです。 |
| Default market | Default market | 既定の市場 | 日本株 / 米国株 / 時刻で自動切替 |
| Default market note | | | 「時刻で自動切替」は日本時間15時までを日本株、それ以降を米国株として開きます。 |
| Number format | Large numbers | 大きい数値の表記 | 日本式（1兆2,340億円） / 国際式（12.34兆 / 1.234e12） |
| Density | Density | 情報密度 | 標準 / 高密度 |
| Density note | | | 高密度は表の行の高さを詰めます。モバイルでは常に標準が使われます。 |
| Reduced motion | Reduced motion | アニメーションの抑制 | OSの設定に従います（現在: 抑制なし） |

The direction-color options render as two cards, each showing an actual example rather than a color
swatch:

```
日本式                                    米国式
7203 トヨタ自動車  +1.24%  (赤)           7203 トヨタ自動車  +1.24%  (緑)
6758 ソニーグループ -0.82% (青)           6758 ソニーグループ -0.82% (赤)
```

### Cost section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | Cost | コスト | コスト |
| Daily cap | Daily cap (USD) | 日次上限 (USD) | 1.50 |
| Daily cap note | | | 上限に達するとその日のLLM呼び出しを停止します。定量スコアと推奨の生成は継続します。 |
| Monthly cap | Monthly cap (USD) | 月次上限 (USD) | 20.00 |
| Current spend | Current spend | 現在の利用額 | 本日 $0.48 / 当月 $8.42 |
| Projection | Projection | 当月見込み | $11.60 |
| Alert threshold | Alert at | 警告のしきい値 | 上限の 80% |
| Kill switch | LLM kill switch | LLMの停止スイッチ | 無効 |
| Kill switch note | | | 有効にすると、資料の要約・定性評価・論拠生成をすべて停止します。この状態でも推奨は定量スコアのみで生成されます。 |
| Model tier heading | Model routing | モデルの割り当て | |

Model tier table, read-only on this screen because model identifiers live in `models.yaml`:

| Tier | label_ja | Model | Price (in / out per 1M tokens) | Used for |
| --- | --- | --- | --- | --- |
| bulk | 一括処理 | Gemini 3.7 Flash | $0.75 / $3.75 | 資料の要約、PDFの直接読み込み |
| default | 推論 | Claude Sonnet 5 | $3.00 / $15.00 | 推奨の論拠生成、レビュー |
| deep | 詳細分析 | Claude Opus 5 | $5.00 / $25.00 | 週次の深掘り分析 |
| embedding | 埋め込み | gemini-embedding | $0.15 / — | ベクトル検索用 |

Table caption:

```
モデル名と単価は models.yaml で管理しています。この画面からは変更できません。
表示している単価は 2026年8月 時点の確認値です。価格は改定されるため、
実際の請求額はプロバイダの最新料金表を確認してください。
Gemini 3.7 Flash の上記単価は2026年12月31日までの導入価格で、
2027年1月1日から $1.50 / $7.50 に変更される予定です。
```

Validation for cap inputs:

| Case | Message |
| --- | --- |
| Below today's spend | 本日すでに $0.48 使用しています。上限を $0.30 に設定すると、本日はこれ以上LLMを使用できません。 |
| Zero | $0.00 を設定するとLLMを完全に停止します。停止スイッチと同じ動作になります。 |
| Above 50 | 日次上限 $50.00 は想定利用額（$0.30 - $0.60/日）の80倍以上です。入力を確認してください。 |

### Data section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | Data | データ | データ |
| J-Quants plan | J-Quants plan | J-Quantsのプラン | 無料プラン / Lightプラン |
| Free plan detail | | | 無料プラン: 費用 ¥0 · 過去2年 · **12週間の遅延** · 5リクエスト/分 |
| Light plan detail | | | Lightプラン: 月額 ¥1,650 · 過去5年 · 遅延なし · 60リクエスト/分 |
| Plan change note | | | プランを変更する場合は、J-Quantsのサイトで契約を変更したうえでこの設定を切り替えてください。切り替え後、初回のデータ収集で遅延分のデータが埋まります。 |
| What changes | | | 変更されるもの: 価格データの遅延、取得可能な履歴の長さ、リクエスト間隔。変更されないもの: スキーマ、分析ロジック、参考現在値の取得元（yfinance）。 |
| Plan verify note | | | プランの内容と価格は変更される可能性があります。契約前に公式サイトで確認してください。 |
| Delay explanation | | | 無料プランでは、リサーチ用の価格データが約12週間遅れます。直近の値動きは参考現在値（yfinance・15分遅延）で補っていますが、この系列はモデルの学習・検証には使用していません。 |
| TDnet | Timely disclosure (TDnet) | 適時開示 (TDnet) | 無効 |
| TDnet note | | | TDnetには公開APIがないため、取得は低頻度に制限しています。利用規約を確認したうえで有効にしてください。無効の場合、適時開示は反映されず、EDINETの資料のみを使用します。 |
| Universe | Universe | 対象銘柄 | 全上場 / 時価総額300億円以上 / TOPIX500 / ウォッチリストのみ |
| Universe note | | | 対象を絞るとデータ収集とLLMのコストが下がります。 |
| Data directory | Data directory | データ保存先 | `/home/user/ai-stock/data` (使用 38.2GB / 空き 412GB) |
| Data directory note | | | `/mnt/c/` 配下は入出力が大幅に遅くなるため使用できません。 |

Data source status table:

| Source | label_ja | Status example | Latest data |
| --- | --- | --- | --- |
| `jquants` | J-Quants | 正常 | 2026-05-30（無料プランの遅延による） |
| `yfinance_jp` | yfinance (日本株) | 正常 | 2026-08-22 15:10 |
| `yfinance_us` | yfinance (米国株) | 正常 | 2026-08-22 05:10 |
| `edinet` | EDINET | 正常 | 2026-08-22 15:04 |
| `tdnet` | TDnet | 無効 | — |
| `sec_edgar` | SEC EDGAR | 正常 | 2026-08-21 |
| `fred` | FRED | 正常 | 2026-08-21 |

Each row shows the configured rate limit and the API key state (`設定済み` / `未設定`), never the key
itself. A missing key renders `未設定` in `--status-warning` with a note naming the environment
variable to set, for example `EDINET_API_KEY を .env に設定してください`.

Collection schedule table (read-only, with the note that the scheduler is in-process and therefore
independent of the OS):

| Job | label_ja | Schedule |
| --- | --- | --- |
| collector_jp | 日本株の収集 | 平日 06:00 / 15:30 (JST) |
| collector_us | 米国株の収集 | 平日 06:30 (JST) |
| analyst | 分析 | 平日 06:15 / 16:00 (JST) |
| researcher | 資料読解 | 平日 06:25 (JST) |
| strategist | 推奨生成 | 平日 06:35 (JST) |
| critic | レビュー | 平日 06:42 (JST) |
| evaluator | 実績評価 | 平日 06:47 (JST) |
| weekly_deep | 週次の深掘り | 土曜 09:00 (JST) |

Caption: `スケジュールはアプリ内のスケジューラで管理しています。OSのタスクスケジューラやcronは
使用していません。PCがスリープしていた場合、復帰後にまとめて1回だけ実行されます。`

### Analysis section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | Analysis | 分析 | 分析 |
| Default horizon | Default horizon | 既定の予測期間 | 5営業日 / 20営業日 |
| Recommendation count | Maximum recommendations per day | 1日の推奨件数の上限 | 12 |
| Count note | | | 件数を増やすとLLMコストが比例して増えます。 |
| Max per sector | Maximum per sector | 同一セクターの上限 | 3 |
| Exclude high vol | Exclude high volatility | 高ボラ銘柄を除外 | 実現ボラ 40% 超を除外 |
| Exclude pre-earnings | Exclude pre-earnings | 決算直前を除外 | 3営業日以内を除外 |
| Min ADV | Minimum daily value | 平均売買代金の下限 | 1.0億円 |
| Min market cap | Minimum market cap | 時価総額の下限 | 300億円 |
| Qual cap | Qualitative overlay cap | 定性スコアの調整幅 | ±12点（変更不可） |
| Qual cap note | | | 定性評価が定量スコアの序列を覆さないよう、調整幅を固定しています。 |
| Weight approval | Factor weight updates | ファクター重みの更新 | 承認制（既定） / 自動適用 |
| Weight approval note | | | 自動適用は推奨しません。Evaluatorが提案した重みは、モデルラボで内容を確認してから適用してください。 |
| Feature version | Feature version | 特徴量バージョン | v3 (2026年6月1日以降) |

### Notifications section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | Notifications | 通知 | 通知 |
| In-app alerts | In-app alerts | アプリ内アラート | |
| Alert: batch failure | Batch failure | バッチの失敗 | 有効 |
| Alert: data stale | Stale data | データの陳腐化 | 有効 |
| Alert: cost threshold | Cost threshold | コストのしきい値到達 | 有効 |
| Alert: filing for holdings | Filings for holdings | 保有・ウォッチ銘柄の開示 | 有効 |
| Alert: earnings approaching | Earnings approaching | 決算発表の接近 | 有効（3営業日前） |
| Alert: view changed | Recommendation reversal | 保有銘柄の見立ての変化 | 有効 |
| Web push | Web push | Webプッシュ通知 | 未許可 |
| Web push note (iOS) | | | iOSではホーム画面に追加したPWAでのみプッシュ通知を受け取れます。ホーム画面に追加してから許可してください。 |
| Webhook | Webhook | Webhook通知 | 未設定 |
| Webhook note | | | 確実に通知を受け取りたい場合はWebhookを推奨します。SlackやDiscordのIncoming Webhook URLを設定してください。 |
| Webhook URL | Webhook URL | Webhook URL | `https://hooks.slack.com/services/...`（保存後はマスク表示） |
| Quiet hours | Quiet hours | 通知しない時間帯 | 22:00 - 07:00 |
| Quiet hours note | | | 緊急度の高い通知（バッチの失敗、コスト上限）はこの時間帯でも送信されます。 |
| Test | Send test notification | テスト通知を送信 | |

### System section

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Section title | System | システム | システム |
| App version | Version | バージョン | 0.9.2 (commit `a3f91c2`) |
| Python | Python | Python | 3.12.7 |
| Node | Node.js | Node.js | 22.14.0 |
| WSL | WSL distribution | WSLディストリビューション | Ubuntu 24.04 (WSL2) |
| Networking mode | Networking mode | ネットワークモード | mirrored |
| Tailscale | Tailscale | Tailscale | Windowsホスト側で稼働 (100.x.y.z) |
| Encoding | Python UTF-8 mode | Python UTF-8モード | 有効 (`PYTHONUTF8=1`) |
| Encoding warning | | | 無効の場合、日本語の資料の読み込みで文字化けや例外が発生します。 |
| DB sizes | Storage | ストレージ | DuckDB 24.1GB · Parquet 12.8GB · SQLite 82MB · LanceDB 1.2GB |
| Last backup | Last backup | 最終バックアップ | 2026年8月22日 03:00（成功） |
| Backup target | Backup target | バックアップ先 | `/mnt/d/ai-stock-backup`（Windows側のDドライブ） |
| Run backup | Run backup now | いますぐバックアップ | |
| Rebuild vectors | Rebuild vector store | ベクトルストアを再構築 | 推定 18分 · 推定コスト $0.42 |
| Rebuild note | | | 埋め込みを再生成するためコストが発生します。チャンク分割規則を変更した場合のみ実行してください。 |
| Export | Export data | データを書き出し | 売買記録 / 推奨履歴 / 設定 |
| Diagnostics | Run diagnostics | 診断を実行 | |
| Diagnostics note | | | ネットワーク到達性、文字コード、データ保存先、外部APIの認証を順に確認します。 |

Diagnostics output example:

```
診断結果 (2026年8月22日 18:42)

ネットワーク
  API サーバー                 正常   127.0.0.1:8000
  Windowsホストへの到達         正常   mirrored networking 有効
  Tailscale IP からのアクセス   正常   100.x.y.z:3000
  Hyper-Vファイアウォール       正常   受信許可

実行環境
  PYTHONUTF8                   正常   1
  ロケール                     正常   C.UTF-8
  データ保存先                 正常   /home/user/ai-stock/data（/mnt/c 配下ではありません）
  改行コード設定               正常   .gitattributes に eol=lf

外部API
  J-Quants                     正常   認証成功（無料プラン）
  EDINET                       正常   認証成功
  SEC EDGAR                    正常   User-Agent 設定済み
  FRED                         正常   認証成功
  TDnet                        無効   設定で無効化されています
  LLM (Gemini)                 正常   疎通確認 $0.0001
  LLM (Claude)                 正常   疎通確認 $0.0003
```

## States

### Loading

Each section card renders skeletons for its controls. The display section loads first so the user's
color convention is applied before anything else renders.

### Empty

Settings always have values, so there is no empty state. Unset optional fields show placeholders,
for example the webhook URL field showing `未設定`.

### Partial data

| Failing part | Behavior |
| --- | --- |
| Health endpoint unavailable | System section shows `システム情報を取得できませんでした` for the affected rows and the rest of the settings remain editable |
| Cost endpoint unavailable | Current-spend row shows `—` with `利用額を取得できませんでした`; the cap inputs still work |
| Storage size unavailable | Those rows render `—` |
| Data source status unavailable | The table shows `状態を取得できませんでした` per row while keeping the configured values visible |

### Error

Save failure:

```
設定を保存できませんでした
PATCH /api/v1/settings → 500
変更は適用されていません。
[再試行]
```

The failed control reverts to its previous value and is highlighted so the user is never left
believing a setting took effect when it did not. This matters most for the kill switch and the cost
caps.

Validation error:

```
日次上限は 0 以上 100 以下の数値で入力してください。
```

### Offline

- Read-only display of all current values.
- Client-side-only settings (direction colors, theme, density) apply immediately and persist locally,
  syncing on reconnect.
- Server-side settings are disabled with `オフラインでは変更できません`.
- The kill switch is disabled offline and shows its last known state with the timestamp, because
  showing a stale-but-unlabeled kill-switch state would be misleading.

### Degraded

When the kill switch is on, the cost section shows it in an active, prominent state, and the
notifications section notes that filing-summary notifications will contain no summaries.

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Nav item | Click | Scrolls to the section (desktop) or drills in (mobile), updates `?section=` |
| Direction color card | Click | Applies immediately, updates the preview pane and every open view, persists via `PATCH /api/v1/settings` with `ui.direction_colors` |
| Theme control | Click | Applies immediately |
| Default market | Change | Saves; takes effect on the next navigation |
| Number format | Change | Applies immediately, preview updates |
| Density | Change | Applies immediately |
| Daily / monthly cap | Blur or Enter | Validates, shows a contextual message when the new value is below today's spend, then saves |
| Kill switch | Toggle | Enabling asks one confirmation. Disabling asks a confirmation that restates today's remaining budget. Saves via `PATCH /api/v1/settings` |
| Model tier row | Click | Popover explaining what that tier is used for and where the identifier is configured (`models.yaml`) |
| J-Quants plan | Change | Confirm dialog listing what changes and what does not, then saves. A note states that the next collection run will backfill the delayed window |
| TDnet switch | Toggle | Enabling shows a confirmation restating the terms-of-service caution and the fetch interval |
| Universe select | Change | Confirm dialog showing the estimated change in daily LLM cost and collection duration |
| Data directory row | Click | Popover with the current path, free space, and the reason `/mnt/c/` is rejected |
| Recommendation count | Blur | Validates 1-50; shows the estimated LLM cost change |
| Weight approval mode | Change | Selecting 自動適用 requires a confirmation explaining the risk |
| Alert toggles | Toggle | Saves immediately |
| Web push enable | Click | Requests browser permission; on iOS, first checks whether the app is installed to the home screen and explains if not |
| Webhook URL | Blur | Validates the URL format, saves, then masks the value |
| Test notification | Click | Sends through every enabled channel and reports per-channel results |
| Quiet hours | Change | Saves |
| Run backup | Click | Confirm dialog with the estimated duration, then runs and reports the result |
| Rebuild vector store | Click | Confirm dialog naming the estimated time and cost, requires typing `再構築` to proceed |
| Export | Click | Downloads a zip containing CSV and JSON exports, UTF-8 with BOM for the CSV files |
| Run diagnostics | Click | Runs the checks sequentially with live per-check results, then offers `結果をコピー` |
| Copy diagnostics | Click | Copies the plain-text report for pasting into an issue or a note |

## Data source

| Section | Endpoint |
| --- | --- |
| All settings | `GET /api/v1/settings`, `PATCH /api/v1/settings` |
| Current spend | `GET /api/v1/agent/cost?period=daily&days=1` |
| Data source status | `GET /api/v1/system/freshness` |
| System info, storage, versions | `GET /api/v1/system/health` |
| Diagnostics | `POST /api/v1/system/diagnostics` |
| Backup | `POST /api/v1/system/backup` |
| Vector rebuild | `POST /api/v1/system/vector-rebuild` (202 + `job_run_id`) |
| Export | `GET /api/v1/system/export?kinds=trades,recommendations,settings` |

Settings keys follow the dotted convention used by the API: `ui.direction_colors`, `ui.theme`,
`ui.default_market`, `ui.number_format`, `ui.density`, `llm.daily_cap_usd`,
`llm.monthly_cap_usd`, `llm.kill_switch`, `llm.alert_threshold_pct`, `data.jquants_plan`,
`data.tdnet_enabled`, `data.universe`, `analysis.default_horizon`, `analysis.max_recommendations`,
`analysis.max_per_sector`, `analysis.weight_approval_mode`, `notify.web_push_enabled`,
`notify.webhook_url`, `notify.quiet_hours`.

Populate from `sample-data.json` key `settings`, which contains a complete settings object with the
free J-Quants plan, TDnet disabled, and the kill switch off.
