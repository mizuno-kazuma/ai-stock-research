# 05. Filings Hub

## Purpose

A cross-ticker feed of regulatory filings and timely disclosures with one-click access to the actual
document. The product requirement it satisfies is blunt: when the user wants to read Toyota's latest
quarterly report, it must take one tap, not a trip through EDINET's search form.

Secondary purpose is triage. On a busy Japanese earnings day, dozens of filings arrive within
minutes of 15:00 JST. The hub ranks by information value rather than strictly by time, so guidance
revisions surface above routine notices, and shows the cached LLM summary inline so the user can
decide whether the full document is worth opening.

Every summary shown here is cached. Generating a new summary costs money, so the cost is displayed
before the user commits to it, and the same document with the same prompt is never billed twice.

## Route

`/filings`

| Param | Values | Default |
| --- | --- | --- |
| `market` | `JP`, `US`, `all` | global market setting |
| `from` | ISO date | today - 7 days |
| `to` | ISO date | today |
| `doc_type` | comma-separated types | all |
| `ticker` | ticker | none |
| `scope` | `all`, `watchlist`, `holdings`, `recommended` | `all` |
| `has_summary` | `true`, `false`, `all` | `all` |
| `sort` | `info_value`, `filed_at` | `info_value` |
| `doc_id` | document id | none, opens the detail sheet |

## Layout

### Desktop (>= 1280px)

12-column grid, master-detail.

| Region | Columns | Behavior |
| --- | --- | --- |
| `PageHeader` | 1-12 | Title, date range, counts |
| `FilterRail` | 1-3 | Sticky: scope, market, doc type, ticker, summary presence |
| `FilingFeed` | 4-8 | Grouped by date, `FilingListItem` rows, virtualized above 200 items |
| `DetailPane` | 9-12 | Sticky. Shows the selected filing's summary, citations, and open actions. Empty-state prompt when nothing is selected |

Selecting a row fills the detail pane without navigating. The PDF itself always opens in a new tab
rather than an embedded viewer, because native PDF viewers handle Japanese fonts, text search and
page anchors better than anything embedded.

### Tablet (768px - 1279px)

8-column grid. `FilterRail` becomes a sheet. `FilingFeed` spans 1-8. Selecting a row opens the
detail as a right sheet at 480px.

### Mobile (< 768px)

Single column.

- Sticky filter chip row showing the active scope and date range.
- `FilingFeed` rows compress to two lines: line 1 is time + ticker + doc-type badge, line 2 is the
  title truncated to two lines.
- Selecting a row opens a full-height bottom sheet with the summary, citations, and a prominent
  `資料を開く` button at 48px.
- Date group headers are sticky within the scroll.

## Component tree

```
FilingsHubPage
├── AppShell
│   └── MainContent
│       ├── WarningBanner[]                     e.g. TDnet 取得失敗
│       ├── PageHeader
│       │   ├── PageTitle                       "決算資料"
│       │   ├── DateRangePicker                 2026-08-16 〜 2026-08-22
│       │   ├── ResultCount                     "48件（要約あり 31件）"
│       │   └── SortSelect                      情報価値順 / 開示時刻順
│       ├── FilterRail / FilterSheet
│       │   ├── ScopeToggleGroup                すべて / ウォッチリスト / 保有銘柄 / 推奨銘柄
│       │   ├── MarketToggleGroup
│       │   ├── DocTypeCheckboxGroup
│       │   ├── TickerCombobox
│       │   ├── HasSummaryToggle
│       │   └── ResetFiltersButton
│       ├── FilingFeed
│       │   └── DateGroup[]
│       │       ├── DateGroupHeader              "2026年8月22日 (金)  12件"
│       │       └── FilingListItem[]
│       │           ├── FiledAtTime              15:04
│       │           ├── TickerAndName            6758 ソニーグループ
│       │           ├── DocTypeBadge             業績予想の修正
│       │           ├── FilingTitle              original language, unmodified
│       │           ├── SummaryPresenceIndicator 要約あり / 要約なし
│       │           ├── ToneBadge                前向き / 中立 / 慎重 / 弱気
│       │           ├── LocalCopyIndicator       ローカル保存済み
│       │           └── OpenButton
│       └── DetailPane / DetailSheet
│           ├── DetailHeader
│           │   ├── TickerAndName + DocTypeBadge
│           │   ├── FilingTitle
│           │   ├── FiledAtLabel                 2026年8月22日 15:04 (JST)
│           │   └── SourceLabel                  EDINET · docID S100XXXX
│           ├── PrimaryActions
│           │   ├── OpenFilingButton             資料を開く
│           │   ├── OpenOfficialSiteButton       提供元サイトで開く
│           │   └── CopyLinkButton
│           ├── SummarySection
│           │   ├── SummaryMetaRow               モデル / 生成日時 / コスト / プロンプト版
│           │   ├── HeadlineJa
│           │   ├── KeyPointsList
│           │   ├── GuidanceChangeBlock
│           │   ├── RiskFactorsList
│           │   ├── ToneAssessment
│           │   └── CitationList
│           ├── GenerateSummaryPanel             (when no cached summary)
│           │   ├── EstimatedCostRow
│           │   ├── ModelTierSelect
│           │   └── GenerateButton
│           └── RelatedSection
│               ├── SameTickerFilingsList
│               └── RelatedRecommendationLink
```

## Content spec

### Page header and filters

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Title | Filings | 決算資料 | 決算資料 |
| Date range | Period | 期間 | 2026年8月16日 〜 2026年8月22日 |
| Range shortcuts | | | 本日 / 直近3日 / 直近1週間 / 直近1ヶ月 / 期間を指定 |
| Count | Results | 件数 | 48件（要約あり 31件） |
| Sort by value | Information value | 情報価値順 | 情報価値順 |
| Sort by time | Filing time | 開示時刻順 | 開示時刻順 |
| Scope all | All | すべて | すべて |
| Scope watchlist | Watchlist | ウォッチリスト | ウォッチリスト (18銘柄) |
| Scope holdings | Holdings | 保有銘柄 | 保有銘柄 (7銘柄) |
| Scope recommended | Recommended | 推奨銘柄 | 推奨銘柄 (12銘柄) |
| Has summary | With summary only | 要約があるものだけ | 要約があるものだけ |

Information-value ordering is explained in a tooltip: `業績予想の修正・決算短信を上位に、保有・
ウォッチ銘柄を優先して並べています。`

### Document types

| doc_type | label_en | label_ja | Badge color |
| --- | --- | --- | --- |
| `guidance_revision` | Guidance revision | 業績予想の修正 | `--status-warning` |
| `earnings_flash` | Earnings release | 決算短信 | `--status-info` |
| `annual_report` | Annual report | 有価証券報告書 | `--status-neutral` |
| `quarterly_report` | Quarterly report | 四半期報告書 | `--status-neutral` |
| `buyback` | Share buyback | 自己株式の取得 | `--status-info` |
| `stock_split` | Stock split | 株式分割 | `--status-info` |
| `dividend_revision` | Dividend revision | 配当予想の修正 | `--status-info` |
| `extraordinary` | Material event | 重要事実 | `--status-danger` |
| `10-K` | 10-K | 10-K | `--status-neutral` |
| `10-Q` | 10-Q | 10-Q | `--status-neutral` |
| `8-K` | 8-K | 8-K | `--status-info` |
| `other` | Other | その他 | `--status-neutral` |

### Feed rows

```
2026年8月22日 (金)   12件

15:04  6758  ソニーグループ    [業績予想の修正]  [慎重]
       2027年3月期 通期業績予想の修正に関するお知らせ
       要約あり · ローカル保存済み                                      [開く]

15:00  7203  トヨタ自動車      [決算短信]  [前向き]
       2027年3月期 第1四半期決算短信〔IFRS〕(連結)
       要約あり · ローカル保存済み                                      [開く]

08:45  9432  日本電信電話      [自己株式の取得]  [中立]
       自己株式取得に係る事項の決定に関するお知らせ
       要約なし（生成 推定 $0.008）                                     [開く]

2026年8月21日 (木)   9件

05:30  NVDA  NVIDIA Corporation  [10-Q]  [前向き]
       Quarterly report for the quarterly period ended 2026-07-26
       要約あり                                                         [開く]
```

Filing titles are rendered in the original language, character for character. Do not translate, do
not normalize, do not truncate mid-character on Japanese text.

### Detail pane: summary

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Summary heading | Summary | 要約 | 要約 |
| Meta | | | Gemini 3.7 Flash · 2026年8月22日 15:12 生成 · $0.009 · プロンプト v4 |
| Headline | Headline | 見出し | 通期営業利益予想を8%下方修正。ゲーム部門の販売計画未達が主因。 |
| Key points | Key points | 要点 | |
| Guidance change | Guidance change | 業績予想の変更 | 営業利益 1兆3,000億円 → 1兆1,960億円 (-8.0%) |
| Risk factors | Disclosed risks | 開示されたリスク | |
| Tone | Disclosure tone | 開示トーン | 慎重 |
| Citations | Supporting quotes | 引用 | |
| Cache note | | | この要約はキャッシュ済みです。再生成には追加コストがかかります。 |

Example key points and risks:

```
要点
・2027年3月期の通期営業利益予想を1兆3,000億円から1兆1,960億円へ8.0%下方修正 (p.1)
・ゲーム&ネットワークサービス部門のハードウェア販売が計画を12%下回った (p.2)
・音楽・映画部門は計画を上回り、下方修正幅を一部相殺 (p.2)
・配当予想は据え置き、年間75円 (p.3)

開示されたリスク
・北米市場における競合の値引き競争の継続 (p.4)
・半導体調達コストの上昇圧力 (p.4)
・為替前提は1ドル148円、現状の152円との差は下期に織り込み予定 (p.3)

開示トーン: 慎重
下方修正の主因を外部環境ではなく自社の販売計画未達と説明しており、
下期の回復見通しについて具体的な施策が示されていない点を慎重と判定した。
```

### Citations

| Element | label_ja | Example |
| --- | --- | --- |
| Quote | 引用 | 「ゲーム&ネットワークサービス分野において、ハードウェアの販売台数が計画を下回ったことから」 |
| Location | 該当箇所 | p.2 · 業績予想の修正の理由 |
| Verification | 検証 | 検証済み |
| Open at page | 該当ページを開く | 該当ページを開く (p.2) |

### Generate summary panel

Shown when no cached summary exists for the current prompt version.

| Element | label_en | label_ja | Example |
| --- | --- | --- | --- |
| Heading | Generate summary | 要約を生成 | 要約を生成 |
| Estimate | Estimated cost | 推定コスト | 推定 $0.008（入力 42,800トークン / 出力 1,200トークン） |
| Model tier | Model | モデル | Gemini 3.7 Flash（既定） / Claude Sonnet 5（詳細） |
| Tier note | | | PDFをそのまま読み込めるため、通常はFlashで十分です。 |
| Today's spend | Today's LLM spend | 本日のLLM利用額 | $0.42 / $1.50 |
| Button | Generate | 生成する | 生成する |
| Blocked | | | LLMの日次予算に達しているため生成できません。 |
| Kill switch | | | LLMの停止スイッチが有効なため生成できません。[設定を開く] |

### Primary actions

| Element | label_en | label_ja | Note |
| --- | --- | --- | --- |
| Open | Open filing | 資料を開く | Local copy via the API, opens in a new tab |
| Open official | Open on official site | 提供元サイトで開く | EDINET / EDGAR / company IR page |
| Copy link | Copy link | リンクをコピー | Copies the local API URL |
| Open at page | Open at page | 該当ページを開く | Appends `#page=N` |

Local delivery is the primary path, and the official site link is always present as a fallback so
that a download failure never leaves the user unable to reach the document.

### Related section

| Element | label_ja | Example |
| --- | --- | --- |
| Same ticker | この銘柄の他の資料 | 6758 の直近5件 |
| Related recommendation | 関連する推奨 | 2026年8月22日 生成の推奨（縮小検討・確信度 中）を見る |
| Stock detail | 銘柄詳細へ | 6758 ソニーグループ |

## States

### Loading

Feed shows 8 skeleton rows at 76px each with the date group headers already rendered from the
requested range. Detail pane shows its empty prompt, not a skeleton, until a row is selected.

### Empty

| Case | label_ja |
| --- | --- |
| No filings in range | この期間の開示資料はありません。期間を広げてください。 |
| No filings for scope | ウォッチリスト銘柄の開示はこの期間にありません。[すべての銘柄を表示] |
| Nothing selected (detail pane) | 左の一覧から資料を選択してください。 |
| Summary filter empty | 要約がある資料はこの期間にありません。 |

### Partial data

| Failing part | Behavior |
| --- | --- |
| TDnet fetch failed | Page-level `WarningBanner`: `TDnetの取得に失敗しました。適時開示が反映されていません。EDINETの資料のみ表示しています。` with `再試行` |
| TDnet disabled by config | Informational note, not a warning: `適時開示（TDnet）の取得は設定で無効になっています。` with a link to settings |
| PDF download failed | Row shows `ローカル保存に失敗` in `--status-warning` and the open button becomes `提供元サイトで開く` |
| Summary generation failed | Detail shows `要約の生成に失敗しました（引用の検証に失敗したため保存されていません）` with `再生成` |
| Citation not verifiable | That citation renders in `--status-danger` with `原文で確認できません`, and the summary carries a header note that it was not fully verified |
| XBRL parse failed but PDF present | Note: `構造化データの解析に失敗しましたが、PDFは閲覧できます。` |

### Error

```
開示資料を読み込めませんでした
GET /api/v1/documents → 500
[再試行]
```

For a PDF that fails to open:

```
資料を開けませんでした
ローカルに保存されたファイルが見つかりません。
[提供元サイトで開く]  [再ダウンロード]
```

### Stale

If the newest filing in the feed is older than expected for the market's session:

```
本日の開示がまだ取得されていません（最終取得 2026年8月21日 18:30）。
```

### Offline

- Rows render from cache.
- Filings whose PDFs are in the cache remain openable and show `ローカル保存済み`.
- Filings without a cached PDF show a disabled open button with
  `オフラインでは開けません`.
- `要約を生成` is disabled with `オフラインでは生成できません`.

### Degraded

Kill switch on: the generate panel is replaced by
`LLMの停止スイッチが有効です。既存の要約は閲覧できます。` Existing cached summaries stay fully
readable, which is the point of caching them.

## Interactions

| Element | Trigger | Result |
| --- | --- | --- |
| Date range shortcut | Click | Refetches the feed |
| Date range custom | Select | Refetches; the range is capped at 92 days with the note `期間は最大92日です` |
| Scope toggle | Click | Refetches |
| Doc type checkbox | Change | Filters client-side when the full set is loaded, otherwise refetches |
| Ticker combobox | Select | Adds a ticker filter |
| Sort select | Change | Reorders |
| Feed row | Click | Fills the detail pane (desktop) or opens the sheet (mobile); sets `?doc_id=` |
| Feed row ticker | Click | Navigates to `/stocks/{market}/{ticker}` (stops propagation) |
| Open filing | Click | Opens `GET /api/v1/documents/{doc_id}/file?disposition=inline` in a new tab |
| Open at page | Click | Same URL with `#page=N` |
| Open official site | Click | Opens the source URL in a new tab |
| Copy link | Click | Copies the local URL; toast `リンクをコピーしました` |
| Generate summary | Click | Confirm dialog showing the estimated cost, then `POST /api/v1/documents/{doc_id}/summary`; the button shows a progress state with an elapsed-time counter |
| Summary generated | Completion | Toast `要約を生成しました（$0.009）`, panel replaced by the summary |
| Regenerate | Click | Confirm dialog stating that a new charge applies and showing the current prompt version |
| Citation quote | Click | Expands the surrounding chunk via `GET /api/v1/documents/{doc_id}/chunks` |
| Related recommendation | Click | Navigates to `/recommendations?rec_id=` |
| `j` / `k` | Keyboard | Move selection down / up in the feed |
| `Enter` | Keyboard | Opens the selected filing's PDF |
| `s` | Keyboard | Focus the summary section |
| Pull down (mobile) | Gesture | Refetch |

## Data source

| Section | Endpoint |
| --- | --- |
| Feed | `GET /api/v1/documents?market=JP&from=2026-08-16&to=2026-08-22&doc_type=...&scope=watchlist&sort=info_value` |
| Detail | `GET /api/v1/documents/{doc_id}` |
| Cached summary | `GET /api/v1/documents/{doc_id}/summary` |
| Generate summary | `POST /api/v1/documents/{doc_id}/summary` with `{tier: "bulk"}`; returns 429 when the cost cap is hit |
| PDF | `GET /api/v1/documents/{doc_id}/file?disposition=inline` |
| Chunk expansion | `GET /api/v1/documents/{doc_id}/chunks?section=...` |
| Today's LLM spend | `GET /api/v1/agent/cost?period=daily&days=1` |

Populate from `sample-data.json` keys `filings` (14 entries spanning both markets, including one
with no summary, one with a failed local copy, and one US 10-Q) and `filing_summary`.
