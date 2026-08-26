# 08. Agent Console

## Purpose

The operational view of the six-job agent loop: what ran, what it produced, what it cost, what the
Critic threw out, and what the Evaluator learned. It is also the recovery console. When the machine
reboots because of a Windows Update at 03:00, this is where the user confirms that interrupted jobs
resumed from their checkpoints, and manually re-runs anything that did not.

Two parts of this screen are unusual and both matter.

The first is the agent memory list. Those lessons are injected into later prompts, so they directly
change the product's output. They must be reviewable, editable and deactivatable by hand. A lesson
derived from a small or unlucky sample can make the system systematically worse, and the only
practical defence is a human periodically reading the list.

The second is cost. LLM spending is the one part of this system that can run away silently, so the
daily and monthly spend, the cap, and the kill switch are all on this screen, and the kill switch is
reachable in one tap.

## Route

`/agent`

| Param | Values | Default |
| --- | --- | --- |
| `tab` | `jobs`, `cost`, `critic`, `memory` | `jobs` |
| `job_run_id` | integer | none, opens the run detail |
| `days` | 7, 30, 90 | 30 |
| `memory_scope` | `global`, `market`, `sector`, `ticker` | all |
| `memory_active` | `true`, `false`, `all` | `true` |

## Layout

### Desktop (>= 1280px)

12-column grid, tabbed.

Tab `jobs`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-12 | `SchedulerStatusBar`: scheduler alive, next scheduled run, host uptime, last reboot |
| 2 | 1-12 | `TodayPipelineStrip`: 6 job cards in sequence with arrows, showing status and duration |
| 3 | 1-5 | `JobRunList` (sticky, scrollable, grouped by date) |
| 3 | 6-12 | `JobRunDetail`: phases, checkpoint, metrics, logs, artifacts |
| 4 | 1-12 | `ManualRunPanel`: run any job for any date |

Tab `cost`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-4 / 5-8 / 9-12 | 3 `MetricCard`: today, this month, projected month-end |
| 2 | 1-12 | `CostGauge` (daily cap) + `KillSwitchControl` |
| 3 | 1-8 | `CostTimeSeriesChart` (stacked by model tier) |
| 3 | 9-12 | `CostByPurposePanel` |
| 4 | 1-12 | `LlmCallTable` (recent 100 calls) |

Tab `critic`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-4 / 5-8 / 9-12 | 3 `MetricCard`: rejection rate, revision rate, most common reason |
| 2 | 1-6 | `RejectionReasonBreakdown` (horizontal bars) |
| 2 | 7-12 | `RejectionRateTrendChart` |
| 3 | 1-12 | `RejectedRecommendationList` |

Tab `memory`:

| Row | Columns | Content |
| --- | --- | --- |
| 1 | 1-12 | `MemoryFilterBar`: scope, category, active state, search |
| 2 | 1-12 | `AgentMemoryList` |
| 3 | 1-12 | `MemoryEffectivenessPanel`: which lessons were used and how those recommendations performed |

### Tablet (768px - 1279px)

8-column grid. `JobRunList` becomes a select above the detail. Cost metric cards 2 x 2 with the
projection card full width. Charts full width.

### Mobile (< 768px)

Single column, read-mostly, with the two controls that matter kept fully functional: the kill switch
and manual job re-run.

- `SchedulerStatusBar` compresses to one line with a status dot.
- `TodayPipelineStrip` becomes a vertical list of 6 rows.
- `JobRunList` full width; tapping opens the detail as a full-height sheet.
- Cost tab: gauge and kill switch first, then the metric cards 2 x 2, then a simplified 14-day chart.
  `LlmCallTable` converts to a card list limited to 20 entries.
- Critic tab: metric cards, then the reason breakdown, then the rejected list as cards.
- Memory tab: full list as cards with the activate toggle available. Editing lesson text is
  desktop-only, with the note `教訓の編集はデスクトップから行ってください`.

## Component tree

```
AgentConsolePage
├── AppShell
│   └── MainContent
│       ├── KillSwitchBanner                     (when active)
│       ├── WarningBanner[]
│       ├── PageHeader
│       │   ├── PageTitle                        "エージェント"
│       │   └── AsOfLabel
│       ├── TabBar                               ジョブ / コスト / レビュー / 教訓
│       ├── TabPanel "ジョブ"
│       │   ├── SchedulerStatusBar
│       │   │   ├── SchedulerStateDot
│       │   │   ├── NextRunLabel
│       │   │   ├── HostUptimeLabel
│       │   │   └── LastRebootLabel
│       │   ├── TodayPipelineStrip
│       │   │   └── JobCard x6
│       │   │       ├── JobName
│       │   │       ├── StatusBadge
│       │   │       ├── DurationLabel
│       │   │       ├── OutputSummary
│       │   │       └── RerunButton
│       │   ├── JobRunList
│       │   │   └── DateGroup > JobRunRow[]
│       │   ├── JobRunDetail
│       │   │   ├── RunMetaTable
│       │   │   ├── JobTimeline                  phase-by-phase
│       │   │   ├── CheckpointPanel
│       │   │   ├── MetricsTable
│       │   │   ├── FailedStepList
│       │   │   ├── LogViewer
│       │   │   └── ArtifactLinks
│       │   └── ManualRunPanel
│       │       ├── JobSelect
│       │       ├── TargetDateInput
│       │       ├── ForceRerunSwitch
│       │       └── RunButton
│       ├── TabPanel "コスト"
│       │   ├── MetricCardGrid x3
│       │   ├── CostGauge
│       │   ├── KillSwitchControl
│       │   ├── CostTimeSeriesChart
│       │   ├── CostByPurposePanel
│       │   └── LlmCallTable
│       ├── TabPanel "レビュー"
│       │   ├── MetricCardGrid x3
│       │   ├── RejectionReasonBreakdown
│       │   ├── RejectionRateTrendChart
│       │   └── RejectedRecommendationList
│       └── TabPanel "教訓"
│           ├── MemoryFilterBar
│           ├── AgentMemoryList
│           │   └── AgentMemoryItem[]
│           │       ├── CategoryBadge
│           │       ├── ScopeLabel
│           │       ├── LessonText
│           │       ├── EvidenceRow
│           │       ├── UsageRow
│           │       ├── EffectRow
│           │       ├── ActiveToggle
│           │       └── EditButton
│           └── MemoryEffectivenessPanel
```

## Content spec

### Scheduler status bar

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| State running | Scheduler running | スケジューラ稼働中 | スケジューラ稼働中 |
| State stopped | Scheduler stopped | スケジューラ停止中 | スケジューラ停止中 |
| Next run | Next scheduled run | 次回の実行 | 次回: データ収集 2026年8月23日 06:00 (JST) |
| Uptime | Process uptime | プロセス稼働時間 | 2日 14時間 |
| Last reboot | Last host reboot | 最終再起動 | 2026年8月20日 03:14（Windows Update） |
| Resume note | | | 再起動後、中断していた2件のジョブをチェックポイントから自動再開しました。 |

The resume note is what tells the user the reboot-resilience design is working. When jobs did not
resume, the same row becomes a `--status-danger` message with a re-run action:
`再起動後に自動再開できなかったジョブが1件あります。`

### Today's pipeline strip

Six cards in sequence. Each shows name, status, duration, and a one-line output summary.

| Job | label_en | label_ja | Output summary example |
| --- | --- | --- | --- |
| Collector | Collector | データ収集 | 価格 1,994銘柄 · 開示 12件 · 為替 1系列 |
| Analyst | Analyst | 分析 | 特徴量 42項目 x 1,842銘柄 · GARCH 収束 · 為替予測 3モデル |
| Researcher | Researcher | 資料読解 | 資料 8件を要約 · 定性スコア 34銘柄 · $0.18 |
| Strategist | Strategist | 推奨生成 | 候補 34件 → 推奨 12件 · $0.21 |
| Critic | Critic | レビュー | 承認 10件 · 修正 2件 · 却下 2件 · $0.09 |
| Evaluator | Evaluator | 実績評価 | 実績確定 18件 · 教訓 1件追加 · 重み提案 1件 |

Status labels use the shared set: 成功 / 部分 / 失敗 / 実行中 / 中断 / スキップ / 待機.

A `partial` card always names what was skipped:
`部分 · TDnetの取得に失敗（3回試行）`.

### Job run list

The list is sticky on desktop and scrolls internally so the page does not grow with history.

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Run history | 実行履歴 | |
| Clear | Clear | クリア | |
| Clear confirm title | Clear job history? | 実行履歴を削除しますか | |
| Clear confirm body | | 完了したジョブの実行履歴を削除します。実行中のジョブは残ります。この操作は取り消せません。 | |
| Clear confirm | Delete | 削除する | |

### Job run detail

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Run id | Run ID | 実行ID | 1284 |
| Job | Job | ジョブ | データ収集 (collector_jp) |
| Status | Status | 状態 | 部分 |
| Started | Started | 開始 | 2026年8月22日 06:00:04 |
| Finished | Finished | 終了 | 2026年8月22日 06:06:56 |
| Duration | Duration | 所要時間 | 6分52秒 |
| Trigger | Trigger | 起動要因 | スケジュール / 手動 / 自動再開 |
| Attempt | Attempt | 試行 | 1回目 |
| Phase list | Phases | フェーズ | |
| Checkpoint | Checkpoint | チェックポイント | `{"phase": "tdnet", "cursor": "2026-08-22T06:03:11", "completed": 42, "total": 61}` |
| Failed steps | Failed steps | 失敗したステップ | tdnet (3回試行後に中断) |
| Metrics | Metrics | 指標 | |
| Artifacts | Artifacts | 生成物 | 生データ 61ファイル (12.4MB) |

Phase timeline example:

```
prices_jquants     成功    2分14秒   1,994銘柄 / 新規 1,994行
prices_yfinance    成功    1分48秒   1,994銘柄 / 欠損 12銘柄
edinet_list        成功    0分22秒   書類一覧 148件 / 対象 12件
edinet_docs        成功    1分52秒   PDF 12件 (18.2MB)
tdnet              失敗    0分34秒   HTTP 503 (3回試行)
fred               成功    0分08秒   6系列 / 改定 1件
sec_edgar          スキップ  —       市場がJPのためスキップ
```

Metrics table example:

```
rows_upserted           14,208
raw_files_written       61
raw_bytes               12,412,844
rate_limit_waits        18
rate_limit_wait_sec     212
retries                 4
schema_drift_detected   0
data_gaps_found         12
```

`rate_limit_wait_sec` matters on the J-Quants free plan (5 requests per minute), where waiting is
the dominant cost of the job, so it is shown rather than buried.

### Manual run panel

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Manual run | 手動実行 | 手動実行 |
| Job select | Job | ジョブ | データ収集 / 分析 / 資料読解 / 推奨生成 / レビュー / 実績評価 |
| Target date | Target date | 対象日 | 2026-08-22 |
| Force re-run | Force re-run | 完了済みでも再実行 | |
| Force note | | | 通常は冪等なため、同じ対象日で再実行しても結果は変わりません。強制再実行はLLMコストが再発生する場合があります。 |
| Run | Run | 実行 | |
| Running | Running | 実行中 | 実行中（経過 1分12秒） |
| Cancel | Cancel | 中止 | |

### Cost tab

| Card | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Today | Today | 本日 | $0.48 / $1.50 (32%) |
| This month | This month | 当月 | $8.42 / $20.00 (42%) |
| Projection | Projected month-end | 当月見込み | $11.60（直近7日の平均から算出） |

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Gauge label | Daily cap | 日次上限 | 日次上限 $1.50 |
| Gauge warning | Approaching cap | 上限に近づいています | 日次上限の80%に達しました |
| Gauge exceeded | Cap reached | 上限に達しました | 日次上限に達したため、LLM呼び出しを停止しています |
| Kill switch label | LLM kill switch | LLMの停止スイッチ | LLMの停止スイッチ |
| Kill switch off | Off | 無効 | 無効（通常動作） |
| Kill switch on | On | 有効 | 有効（LLM呼び出しを全面停止） |
| Kill switch note | | | 有効にすると、定性分析・要約・推奨の論拠生成が停止します。定量スコアと推奨の生成は継続され、論拠は定量的な要因のみで構成されます。 |

Cost time series: stacked bars by model tier over the selected range.

| Tier | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Bulk | Bulk (Gemini Flash) | 一括処理 (Gemini Flash) | $0.21 |
| Default | Reasoning (Claude Sonnet) | 推論 (Claude Sonnet) | $0.22 |
| Deep | Deep dive (Claude Opus) | 詳細分析 (Claude Opus) | $0.05 |
| Embedding | Embedding | 埋め込み | $0.00 |

Cost by purpose:

```
資料要約           $0.18   38%   キャッシュヒット 24 / 32件
推奨の論拠生成      $0.21   44%
レビュー           $0.09   19%
教訓の抽出         $0.00    0%   （週次のみ）
```

Cache hit rate is displayed because it is the single most effective lever on cost.

LLM call table columns:

| Column | label_ja | Example |
| --- | --- | --- |
| 時刻 | | 06:31:12 |
| 目的 | | 資料要約 |
| モデル | | gemini-3.7-flash |
| 入力トークン | | 42,812 |
| 出力トークン | | 1,204 |
| コスト | | $0.0077 |
| キャッシュ | | ヒット / ミス |
| 所要 | | 4.2秒 |
| 結果 | | 成功 / 失敗（スキーマ検証エラー） |

### Critic tab

| Card | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Rejection rate | Rejection rate | 却下率 | 14.2% (直近30日、42件 / 296件) |
| Revision rate | Revision rate | 修正率 | 21.6% (64件 / 296件) |
| Top reason | Most common reason | 最多の却下理由 | 引用が原文で確認できない (18件) |

Rejection reason breakdown:

| Reason code | label_ja | Example count |
| --- | --- | --- |
| `CITATION_NOT_FOUND` | 引用が原文で確認できない | 18件 |
| `BEAR_CASE_INSUBSTANTIAL` | 弱気論拠が定型的で実質がない | 11件 |
| `STALE_DATA_USED` | 古いデータに基づいている | 6件 |
| `DELAYED_PRICE_MISUSED` | 遅延データを現在値として扱っている | 3件 |
| `CONVICTION_UNSUPPORTED` | 確信度がサンプル数に見合わない | 2件 |
| `INTERVAL_MISSING` | 信頼区間が欠けている | 1件 |
| `PIT_VIOLATION` | 開示日より前の情報を使用している | 1件 |

Caption: `却下率が0%に近い場合、Criticが機能していない可能性があります。30%を大きく超える場合は
Strategistのプロンプトを見直してください。`

That guidance is important. A rejection rate of zero looks like success and is usually a broken
validator.

Rejected recommendation list: each row shows the ticker, the date, the reason code, and a link to
view the rejected card as it was generated, with the Critic's notes.

### Memory tab

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Agent memory | 教訓 | 教訓 (有効 18件 / 全 24件) |
| Filter scope | Scope | 適用範囲 | 全体 / 市場 / セクター / 銘柄 |
| Filter category | Category | 種別 | 教訓 / 偏り / パターン / 注意点 |
| Search | Search | 検索 | |
| Explanation | | | ここに登録された教訓は、推奨生成時のプロンプトに注入されます。誤った教訓は出力を継続的に悪化させるため、定期的に見直してください。 |

Memory item example:

```
[偏り]  適用範囲: 市場 (日本株)                                    有効 [切替]

決算発表の3営業日前に生成した推奨の的中率は42% (n=38) で、それ以外の期間の
57% (n=176) を大きく下回る。決算直前は確信度を一段引き下げるか、推奨を見送る。

根拠: 2026年2月 - 2026年8月の推奨実績 214件を集計
使用回数: 直近30日で 28回のプロンプトに注入
効果: この教訓を使用した推奨の的中率 59% (n=28) / 未使用 54% (n=64)
更新: 2026年8月15日
```

| Field | label_en | label_ja |
| --- | --- | --- |
| Evidence | Evidence | 根拠 |
| Usage | Times injected | 使用回数 |
| Effect | Observed effect | 効果 |
| Updated | Updated | 更新 |
| Active toggle | Active | 有効 |
| Edit | Edit | 編集 |
| Deactivate | Deactivate | 無効にする |

Effectiveness panel:

```
教訓の有効性
使用された推奨 168件のうち的中 96件 (57%)。未使用 128件のうち的中 66件 (52%)。
差は5ポイントですが、サンプル数を考慮すると統計的に有意ではありません (p=0.38)。

有害な可能性のある教訓
「低ボラ銘柄を優先する」を使用した推奨の的中率は 44% (n=32) で、
未使用時の 56% (n=112) を下回っています。無効化を検討してください。   [無効にする]
```

Flagging potentially harmful lessons with their sample sizes is the mechanism that keeps the feedback
loop from drifting. Do not hide it behind a filter.

## States

### Loading

Pipeline strip renders 6 skeleton cards at final size. The scheduler status bar loads first because
it is the single most important fact on the page.

### Empty

| Case | label_ja |
| --- | --- |
| No job history | ジョブの実行履歴がありません。手動実行するか、スケジュールされた時刻を待ってください。 |
| No LLM calls | LLMの呼び出し履歴がありません。 |
| No rejections | Criticの却下はありません。却下率が0%が続く場合は検証が機能しているか確認してください。 |
| No memory | 教訓はまだ蓄積されていません。推奨の実績が確定し始めると生成されます（最短で運用開始から20営業日後）。 |
| No weight proposal | 重みの変更提案はありません。 |

### Partial data

| Failing part | Behavior |
| --- | --- |
| Job partially failed | Detail shows the successful phases normally and the failed phase with its error and retry count; the `再実行` action re-runs from the checkpoint, not from the beginning |
| Log file rotated away | `ログは保持期間（14日）を過ぎたため参照できません` |
| Cost data incomplete | `一部の呼び出しのコストが記録されていません（$0.00と表示）。LiteLLMのコールバックが失敗した可能性があります。` |
| Memory effect unavailable | `効果の測定にはサンプルが不足しています (n=6)` shown instead of a rate |
| SSE disconnected | Falls back to 15-second polling with the note `リアルタイム更新が切断されたため、15秒間隔で更新しています` |

### Error

```
ジョブ情報を読み込めませんでした
GET /api/v1/agent/jobs → ECONNREFUSED
エージェントプロセスが停止している可能性があります。

確認手順:
1. WSL2内で systemctl --user status ai-stock-agent を実行
2. 停止している場合は systemctl --user start ai-stock-agent
3. WSL2が停止している場合は Windows側で wsl -d Ubuntu

[再試行]
```

Embedding the recovery steps here is deliberate. This is exactly the failure the user will hit after
a Windows Update reboot, and the console should tell them what to type.

### Stale

```
スケジューラの最終ハートビートが42分前です。プロセスが応答していない可能性があります。
```

### Offline

Job history and cost data render from cache with timestamps. Manual run, kill switch, and memory
edits are disabled with `オフラインでは操作できません`. The kill switch specifically shows its
current state clearly so the user is not left guessing.

### Degraded

Kill switch on: `KillSwitchBanner` at the top of every screen, and on this screen the cost tab shows
the switch in its active state with the count of LLM calls skipped today.

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Tab | Click | Switches panel, updates `?tab=` |
| Job card | Click | Loads the run detail, updates `?job_run_id=` |
| Job card re-run | Click | Confirm dialog naming the job and date, warning about LLM cost when applicable, then `POST /api/v1/agent/jobs/{job_name}/run` |
| Job run row | Click | Loads that run's detail |
| Phase row | Click | Expands to show that phase's log lines |
| Checkpoint value | Click | Copies the checkpoint JSON; toast `チェックポイントをコピーしました` |
| Failed step retry | Click | Re-runs from the checkpoint; the button shows a running state |
| Cancel running job | Click | Confirm dialog, then `POST /api/v1/agent/jobs/{job_run_id}/cancel` |
| Clear history | Click | Confirm dialog, then `DELETE /api/v1/agent/jobs`. Running jobs are kept. The list becomes the empty state when nothing remains. |
| Manual run | Click | Validates the date, shows the cost estimate for LLM-using jobs, then runs |
| Log viewer | Scroll | Loads older lines on demand; supports text search within the loaded buffer |
| Artifact link | Click | Opens the raw file listing for that run |
| Kill switch | Toggle | Confirm dialog: enabling requires one confirmation, disabling requires a second confirmation naming today's remaining budget. Then `PATCH /api/v1/settings` with `llm.kill_switch` |
| Cost gauge | Click | Opens the cost breakdown for the day |
| Cost cap value | Click | Navigates to `/settings#cost` |
| Cost chart bar | Click | Filters the call table to that day |
| LLM call row | Click | Popover with the prompt name, prompt version, cache key, and the truncated request metadata. The prompt body itself is not shown here |
| Rejection reason bar | Click | Filters the rejected list to that reason |
| Rejected recommendation | Click | Opens the rejected card in a sheet, marked `却下` with the Critic's notes |
| Memory item toggle | Toggle | `PATCH /api/v1/agent/memory/{id}` with `is_active`, optimistic |
| Memory item edit | Click | Opens an editor with the lesson text, scope, and category. Saving records the edit and the previous text |
| Memory item delete | Click | Confirm dialog explaining that deactivation is usually preferable to deletion, then `DELETE` |
| Harmful lesson "無効にする" | Click | Same as toggle, with the sample size restated in the confirmation |
| SSE events | Push | Updates job statuses live and appends log lines to the open run detail |
| `r` | Keyboard | Refresh |
| `k` | Keyboard | Focus the kill switch (does not toggle it) |

## Data source

| Section | Endpoint |
| --- | --- |
| Scheduler status, health | `GET /api/v1/system/health` |
| Job list | `GET /api/v1/agent/jobs?limit=50` |
| Job detail | `GET /api/v1/agent/jobs/{job_run_id}` |
| Manual run | `POST /api/v1/agent/jobs/{job_name}/run` |
| Cancel | `POST /api/v1/agent/jobs/{job_run_id}/cancel` |
| Clear history | `DELETE /api/v1/agent/jobs` |
| Live progress | `GET /api/v1/agent/events` (SSE) |
| Cost | `GET /api/v1/agent/cost?period=daily&days=30` |
| Critic stats | `GET /api/v1/agent/critic-stats?days=30` |
| Rejected recommendations | `GET /api/v1/recommendations?critic_verdict=rejected` |
| Memory | `GET /api/v1/agent/memory?is_active=true`, `PATCH`, `DELETE` |
| Kill switch, caps | `GET /api/v1/settings`, `PATCH /api/v1/settings` |

Populate from `sample-data.json` keys `jobs` (including one partial run with a TDnet failure and one
auto-resumed run after a reboot), `llm_cost`, `critic_stats`, and `agent_memory` (including one
lesson flagged as potentially harmful).
