# States

State definitions for every component and screen. All user-visible copy is Japanese.

## 1. State taxonomy

| State | When | Key rule |
| --- | --- | --- |
| `loading` | Data request in flight, no cached data | Skeleton matched to final dimensions |
| `loading-refresh` | Data request in flight, cached data present | Show cached data with a subtle progress indicator. Never blank it out |
| `empty` | Request succeeded, zero results | Explain why it is empty and what to do next |
| `not-ready` | Data for the requested date has not been generated yet | Offer the latest available date |
| `partial` | Some sections loaded, others failed | Render what works, mark what failed. Never blank the page |
| `error` | Request failed | Explain, offer retry, keep other sections alive |
| `stale` | Data is older than expected | Show the data with an explicit staleness note |
| `offline` | No network connection | Show cached data with an explicit offline banner |
| `degraded` | A subsystem is disabled (LLM kill switch, TDnet disabled) | Show a persistent notice; the rest of the app works |
| `truncated` | Result set exceeded the display limit | Show the limit and suggest narrowing the filter |

**The most important rule in this document: `partial` is a normal state, not an error.** One data
source failing must never blank the whole screen. This product runs on free-tier data sources that
fail regularly.

## 2. Loading

### 2.1 Skeleton rules

Skeletons match the final content dimensions so there is no layout shift when data arrives.

| Component | Skeleton |
| --- | --- |
| `MetricCard` | Label bar 80x12, value bar 120x28, sub bar 60x12 |
| `RecommendationCard` (compact) | Header 200x16, 3 chips 72x20, 2 text lines full-width x14 |
| `RecommendationCard` (full) | Full structural skeleton with all section headings visible as real text |
| `DataTable` | Header row real, 8 body rows of shimmer bars matching column widths |
| `PriceChart` | Rectangle at final chart height with a centered pulsing axis line |
| `FanChart` | Same as PriceChart |
| `FilingListItem` | Date 80x12, badge 64x18, title 320x14, summary 2 lines |
| `JobTimeline` | 6 circles with connecting lines, labels as shimmer bars |

Shimmer: `--bg-hover` to `--bg-surface-raised`, 1.4s linear infinite. Disabled when
`prefers-reduced-motion` is set; in that case use a static `--bg-hover` fill.

### 2.2 Progressive loading order

For the dashboard and stock detail screens, sections load independently so the fastest data appears
first.

| Priority | Content | Reason |
| --- | --- | --- |
| 1 | Header, freshness indicator, navigation | Always available from cache |
| 2 | Cached metrics (previous load) | Instant perceived response |
| 3 | Price and score data | Small payload |
| 4 | Recommendations | Medium payload |
| 5 | Charts | Larger payload |
| 6 | LLM summaries | Slowest, may be absent |

### 2.3 Long-running operations

Backtests and manual job runs return `202 Accepted` and progress via SSE.

```
バックテストを実行中です
████████████░░░░░░░░  62%   2024-08-01 〜 2025-11-30 を処理済み
推定残り時間: 約45秒

この画面を離れても処理は継続します
                                                        [中止]
```

The note that the user may leave the screen matters; otherwise people wait unnecessarily.

## 3. Empty

Empty states explain the cause and the next action. Never a bare "No data".

| Screen / component | Cause | Title (ja) | Body (ja) | Action |
| --- | --- | --- | --- | --- |
| Recommendations | No recommendation met the criteria today | 本日の推奨はありません | 定量スコアとMLモデルの条件を満たす銘柄が本日はありませんでした。スクリーナーで条件を緩めて探すこともできます。 | スクリーナーを開く |
| Recommendations | Operation just started, no history yet | 実績データの蓄積中です | 推奨の開始から12営業日です。過去実績が20件を超えるまで、確信度は「低」に固定されます。 | — |
| Screener results | Filter too narrow | 条件に一致する銘柄がありません | 条件を緩めるか、プリセットから選び直してください。 | 条件をリセット |
| Filings hub | No filings in range | この期間の開示はありません | 期間を広げるか、フィルタを解除してください。 | 期間を1週間に変更 |
| Watchlist | Nothing added | ウォッチリストが空です | 銘柄詳細やスクリーナーから銘柄を追加できます。 | スクリーナーを開く |
| Portfolio | No positions | 保有銘柄がありません | 売買記録を追加すると、保有状況と評価損益が表示されます。 | 売買記録を追加 |
| Trade journal | No trades | 売買記録がありません | 手動で入力するか、証券会社のCSVを取り込めます。 | 記録を追加 / CSVを取り込む |
| Agent memory | No lessons yet | 蓄積された教訓はまだありません | 推奨の実績が20件以上溜まると、Evaluatorが教訓を抽出します。 | — |
| Backtest list | None run | バックテストの実行履歴がありません | 戦略とコスト前提を指定して実行できます。 | 新規実行 |
| Alerts | None | 未読の通知はありません | — | — |
| Stock filings | Ticker has no filings on record | この銘柄の開示資料は取得できていません | EDINETまたはEDGARで直接検索できます。 | 公式サイトで探す |
| Document summary | Not yet summarized | 要約はまだありません | この資料をLLMで要約できます（推定コスト $0.04）。 | 要約を生成 |
| Recommendation outcomes | Horizon not reached | 実績はまだ確定していません | H20の評価は 2026-09-19 に確定します。 | — |

Visual treatment: centered in the container, icon at 40px in `--fg-muted`, title in `--text-h4`,
body in `--text-body-sm` / `--fg-secondary` at max `48ch`, action as a `secondary` button. Vertical
padding `--space-12` on desktop, `--space-8` on mobile.

## 4. Not ready

Distinct from empty. The user requested a date for which the batch has not run.

```
2026-08-23 のデータはまだ生成されていません

日次バッチは平日 18:30（日本株）と 06:30（米国株）に実行されます。
最新の利用可能日は 2026-08-22 です。

              [2026-08-22 を表示]     [バッチを手動実行]
```

Uses HTTP 409 with `latest_available_as_of` in the body (see `../09-api-spec.md` §1.1). The primary
action navigates to the latest available date rather than leaving the user stuck.

## 5. Partial data (the most important state)

### 5.1 Principle

When some sections load and others fail, render what works. Mark the failures explicitly and
locally, at the section where the failure occurred, so the user knows exactly which part of the
screen is unreliable.

### 5.2 Section-level failure

```
┌─────────────────────────────────────────────────┐
│ 定性分析                                        │
│                                                 │
│  ⚠ 本日のLLM予算に達したため、定性分析は        │
│    停止しています                               │
│                                                 │
│  定量スコアのみで推奨を生成しています。         │
│  設定から上限を変更できます。                   │
│                              [設定を開く]       │
└─────────────────────────────────────────────────┘
```

Section-level failures render inside the section's own card, with the card border in
`--status-warning-bg` and the icon in `--status-warning`. The rest of the page is unaffected.

### 5.3 Common partial-data cases

| Failed part | Message (ja) | Severity | Rest of screen |
| --- | --- | --- | --- |
| LLM cost cap reached | 本日のLLM予算に達したため、定性分析は停止しています | warning | Fully functional with quant scores only |
| LLM kill switch on | 定性分析を手動で停止しています | info | Same |
| TDnet fetch failed | TDnetからの取得に失敗しています（3日連続）。適時開示の一部が欠けている可能性があります | warning | Filings from EDINET still shown |
| TDnet disabled by setting | TDnetの取得は無効に設定されています | info | Same |
| EDINET fetch failed | EDINETからの取得に失敗しています（最終取得 2026-08-19） | warning | Prices and scores unaffected |
| yfinance failed | 現在値を取得できませんでした。表示している価格はリサーチ用データ（12週前）です | **error** | Explicitly flag every price as research-date |
| Model not trained | 予測モデルが未学習のため、期待リターンは表示できません | warning | Quant score shown, ML prediction shows `—` |
| GARCH did not converge | 一部銘柄でGARCH推定が収束せず、実現ボラティリティで代替しています | info | Values shown with a substitution note |
| FX exogenous data missing | 金利データが欠損しているため、ARIMAXモデルは実行できていません。ランダムウォークのみ表示しています | warning | Baseline forecast shown |
| Financials missing | 財務データが未取得のため、バリュエーション指標は表示できません | warning | Price-based metrics shown |
| Feature count insufficient | 特徴量の欠損が多いため、この銘柄はスコアリング対象外です | info | Prices and filings shown |
| Some tickers failed | 4,012銘柄のうち 38銘柄でデータ取得に失敗しました | info | Details behind a link |

The `yfinance failed` case is classified as `error` rather than `warning` because the consequence is
that every displayed "current" price is actually 12 weeks old. That must be unmissable.

### 5.4 Null values within a loaded section

Individual missing values render as `—` in `--fg-muted`, not as `0` and not as a blank cell. Hovering
shows the reason.

| Reason | Tooltip (ja) |
| --- | --- |
| Loss-making company | 純利益が負のため算出できません |
| Insufficient history | 履歴が不足しているため算出できません（上場から 142日） |
| Financials not filed | 直近の財務データが未提出です |
| Excluded by quality check | 品質チェックで除外されました |
| Model produced no value | モデルが値を出力しませんでした |

## 6. Error

### 6.1 Section-level error

```
┌─────────────────────────────────────────────────┐
│ 推奨銘柄                                        │
│                                                 │
│  ⚠ 読み込みに失敗しました                       │
│                                                 │
│  ネットワークエラーが発生しました。             │
│                                    [再試行]     │
│                                                 │
│  詳細: fetch failed (ECONNREFUSED)  [コピー]    │
└─────────────────────────────────────────────────┘
```

Technical detail is collapsed behind a disclosure and copyable. The user is the developer of this
tool, so the technical detail is useful rather than noise.

### 6.2 Page-level error

Only when the page cannot render at all (for example the API is entirely unreachable).

```
              サーバーに接続できません

  APIサーバーが応答していません。以下を確認してください。

  ・WSL2 で ai-stock-api サービスが起動しているか
    systemctl status ai-stock-api
  ・ポート 8000 が listen しているか
    ss -tlnp | grep 8000
  ・Hyper-V ファイアウォールの受信が許可されているか

                        [再試行]

  詳細な切り分け手順: docs/15-windows-runtime.md §2.6
```

Because this is a self-hosted single-user tool, the error state can point at concrete diagnostic
commands. This is more useful than a generic "something went wrong".

### 6.3 Error copy by cause

| Cause | Title (ja) | Body (ja) | Action |
| --- | --- | --- | --- |
| API unreachable | サーバーに接続できません | (see above) | 再試行 |
| 500 | サーバーエラーが発生しました | エージェントのログを確認してください: `journalctl -u ai-stock-agent -n 100` | 再試行 |
| 404 (ticker) | 銘柄が見つかりません | 銘柄コード「9999」は登録されていません。銘柄マスタが最新か確認してください。 | 検索に戻る |
| 422 | 入力内容に誤りがあります | (field-level messages) | — |
| 429 (cost cap) | LLM予算の上限に達しています | 本日の使用額 $1.02 が上限 $1.00 に達しました。上限は設定から変更できます。翌日0時に自動でリセットされます。 | 設定を開く |
| 503 (upstream) | 外部データソースが応答していません | J-Quants APIが応答していません。しばらく待ってから再試行してください。 | 再試行 |
| PDF fetch failed | 資料を取得できませんでした | ローカルに保存されていないため、公式サイトで確認してください。 | 公式サイトで開く |
| Timeout | 処理がタイムアウトしました | 条件を絞ると処理が速くなります。 | 条件を絞る |

**A PDF fetch failure always offers the official-site link.** Losing access to the underlying
document is worse than losing the summary.

## 7. Stale data

Distinct from an error. The data loaded successfully but is older than expected.

### 7.1 Structural delay (J-Quants free plan)

This is expected, not a failure. It is displayed as a persistent condition rather than a warning.

In the header freshness popover:

```
J-Quants（リサーチ用株価）   2026-05-31   12週遅延（無料プラン）
```

On any chart using research prices:

```
出所: J-Quants（リサーチ用・12週遅延、最新 2026-05-31）
```

On any price presented as current:

```
3,125円  参考値（yfinance、約15-20分遅延）
```

**Never present a research-source price as a current price.** If the current-price source fails,
the fallback display is explicit:

```
3,010円  ⚠ 2026-05-31 時点の価格です（現在値の取得に失敗）
```

### 7.2 Unexpected staleness

```
⚠ EDINETのデータが 4営業日 遅れています（最終取得 2026-08-19）
   直近の開示が反映されていない可能性があります
                                            [エージェント画面で確認]
```

Threshold: more than 3 business days behind the expected date (see `../11-security-ops.md` §5.1).

## 8. Offline

### 8.1 Offline banner

Sits at `--z-banner`, above modals.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 オフライン  2026-08-22 18:35 に取得したデータを表示しています
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Background `--status-warning-bg`, text `--status-warning`, full width, 32px height, not dismissible
while offline.

**The timestamp of the cached data is mandatory.** Showing yesterday's prices without saying they
are yesterday's is the failure mode this banner exists to prevent.

### 8.2 Offline availability

| Content | Offline |
| --- | --- |
| Last-loaded dashboard | Available from cache, labeled with its timestamp |
| Last-loaded recommendations | Available from cache |
| Previously opened PDFs | Available (cached immutable) |
| New PDFs | Unavailable, with a note |
| Screener | Unavailable, with a note |
| Trade journal entry | **Available.** Queued and synced on reconnect |
| Settings changes | Queued and synced on reconnect |
| LLM on-demand summary | Unavailable |

### 8.3 Queued writes

```
オフラインのため保存を保留しています（2件）
オンライン復帰時に自動で送信されます
```

After reconnecting:

```
保留していた2件を保存しました
```

## 9. Degraded

A subsystem is intentionally or automatically disabled while the app keeps working.

### 9.1 LLM kill switch banner

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 LLM停止中  定性分析は行われません          [設定を開く]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Shown when `settings["llm.kill_switch"]` is true or a cost cap is exceeded. Sits at `--z-banner`.

### 9.2 Degraded conditions

| Condition | Banner / notice | User impact |
| --- | --- | --- |
| LLM kill switch on | Persistent banner | No qualitative scores or summaries |
| Daily cost cap exceeded | Persistent banner with reset time | Same, auto-recovers next day |
| Monthly cost cap exceeded | Persistent banner, manual release required | Same |
| TDnet disabled | Notice on the filings screen only | Timely disclosures may be missing |
| Model not trained | Notice on model lab and recommendations | No ML predictions |
| Agent process down | Banner: エージェントが停止しています | No new data until restarted |
| Disk space low | Banner: ディスク残量が 18GB です | Backups may fail |

## 10. Truncated

```
500件で表示を打ち切りました（条件に一致: 1,284件）
条件を絞ると全件を確認できます
```

Rendered as a table footer in `--status-warning` on `--bg-surface-sunken`.

## 11. Validation

### 11.1 Form field errors

Rendered below the field in `--status-danger` at `--text-caption`, with the field border switched to
`--status-danger`.

| Field | Rule | Message (ja) |
| --- | --- | --- |
| Trade quantity | Positive number | 数量は0より大きい値を入力してください |
| Trade quantity (JP) | Multiple of the lot size | 単元株数（100株）の倍数で入力してください |
| Trade price | Positive number | 価格は0より大きい値を入力してください |
| Trade price | Within 50% of the reference price | 参考価格（3,125円）から大きく離れています。桁を確認してください |
| Trade date | Not in the future | 未来の日付は指定できません |
| Trade date | Business day | 2026-08-23 は非営業日です |
| Emotion tag | Required | 心理状態を選択してください |
| Daily cost cap | 0.01 - 100 | $0.01 から $100.00 の範囲で入力してください |
| Backtest period | At least 1 year | バックテスト期間は1年以上にしてください |
| Backtest fee_bps | Required | 手数料を入力してください（0を指定する場合も明示的に入力が必要です） |
| Backtest slippage_bps | Required | スリッページを入力してください |
| Backtest max_turnover | Required | 売買回転率の上限を入力してください |

**The backtest cost fields have no default value in the form.** The user must type a number, even if
it is zero. This mirrors the API contract (`../04-analysis-engine.md` §4.1) and exists to prevent
accidentally running a zero-cost backtest.

The price-vs-reference check catches digit-entry errors, which is the most common and most costly
input mistake in a trade log.

### 11.2 Confirmation dialogs

| Action | Title (ja) | Body (ja) | Confirm label |
| --- | --- | --- | --- |
| Delete trade | 売買記録を削除しますか | この操作は取り消せません。保有数量が再計算されます。 | 削除する |
| Deactivate a lesson | この教訓を無効化しますか | 以降の推奨生成でこの教訓は使われなくなります。後から再度有効化できます。 | 無効化する |
| Activate proposed weights | ファクター重みを切り替えますか | 現行の重みと入れ替わります。切り替え後30日間、新旧両方でスコアを計算して比較します。 | 切り替える |
| Bulk re-summarize | 一括で再要約しますか | 対象1,240件。推定コスト $48.8。日次上限を一時的に超過します。 | 実行する |
| Enable TDnet | TDnetの取得を有効にしますか | TDnetは公開APIではありません。利用規約を確認の上、低頻度での取得に留めてください。 | 有効にする |
| Turn off kill switch | LLMを再開しますか | 今月の使用額は $19.20 / $20.00 です。 | 再開する |

The bulk re-summarize dialog shows the estimated cost before the action. Estimating cost after the
fact is not useful.

## 12. Success feedback

Toasts, auto-dismiss after 4 seconds, bottom-right on desktop and top on mobile.

| Action | Message (ja) |
| --- | --- |
| Trade saved | 売買記録を保存しました |
| Added to watchlist | ウォッチリストに追加しました（トヨタ自動車） |
| Filter saved | フィルタ条件を保存しました |
| Settings saved | 設定を保存しました |
| Job started | collector_jp を実行しました |
| Backtest finished | バックテストが完了しました  [結果を見る] |
| Summary generated | 要約を生成しました（コスト $0.04） |
| Weights switched | ファクター重みを切り替えました |
| CSV imported | 42件の売買記録を取り込みました（3件はスキップ） |

The summary-generated toast includes the actual cost. Showing the cost of each on-demand LLM call
builds an accurate intuition for the budget.

## 13. State priority

When multiple states apply simultaneously, render in this order of precedence.

| Priority | State | Reason |
| --- | --- | --- |
| 1 | `offline` | The user must know nothing is live |
| 2 | `degraded` (kill switch, cap) | Affects the whole app's output |
| 3 | `error` (page level) | Nothing can be rendered |
| 4 | `not-ready` | The requested date does not exist |
| 5 | `partial` | Some content is available |
| 6 | `stale` | Content is available but old |
| 7 | `truncated` | Content is available but cut off |
| 8 | `empty` | Content is available and genuinely zero |
| 9 | `loading` | |

`offline` and `degraded` banners coexist and stack, offline on top.
