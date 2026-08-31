# Component Inventory

Component specifications with props, variants, and composition rules. Base primitives come from
shadcn/ui; domain components are built on top of them. All visible copy is Japanese, given as
`label_en` / `label_ja` pairs.

## 1. Layout components

### 1.1 AppShell

Wraps every page.

```
AppShell
├── OfflineBanner            (conditional, z-banner)
├── KillSwitchBanner         (conditional, z-banner)
├── AppHeader                (sticky, z-header)
├── Sidebar                  (desktop/tablet only, z-sidebar)
├── main                     (page content)
└── BottomNav                (mobile only, z-bottom-nav)
```

### 1.2 AppHeader

Persistent header. Height `--header-height` (56px).

| Element | Desktop | Mobile |
| --- | --- | --- |
| Logo / product name | Left | Left, abbreviated |
| Market switcher (JP / US) | Left, after logo | In a dropdown |
| Global search | Center, 360px wide | Icon that opens a full-screen sheet |
| **DataFreshnessIndicator** | Right | Right, compact |
| Alert bell with unread count | Right | Right |
| Theme toggle | Right, in overflow menu | In settings |

Content spec:

| Field | label_en | label_ja | Example |
| --- | --- | --- | --- |
| product name | AI Stock Research | AIリサーチ | |
| market JP | Japan | 日本株 | |
| market US | United States | 米国株 | |
| search placeholder | Search ticker or company | 銘柄コード・企業名で検索 | |
| alerts | Alerts | 通知 | `3` |

### 1.3 DataFreshnessIndicator (critical component)

**This component must appear on every screen.** The Japanese price source runs on a free plan with
a 12-week delay; hiding that fact causes bad decisions.

Collapsed form in the header:

```
データ鮮度: 一部遅延 ▾
```

Expanded popover:

| Field | label_ja | Example value | Visual |
| --- | --- | --- | --- |
| J-Quants (research prices) | J-Quants（リサーチ用株価） | `2026-05-31` | Warning color, `12週遅延（無料プラン）` |
| yfinance (current prices) | yfinance（現在値） | `2026-08-22` | Success color, `約15-20分遅延` |
| EDINET | EDINET（開示資料） | `2026-08-22` | Success color |
| EDGAR | EDGAR（米国開示） | `2026-08-22` | Success color |
| TDnet | TDnet（適時開示） | `2026-08-19` | Danger color, `3日連続で取得に失敗` |
| FRED | FRED（為替・マクロ） | `2026-08-22` | Success color |

Props:

```ts
interface DataFreshnessIndicatorProps {
  sources: Array<{
    source: string;
    labelJa: string;
    latestAsOf: string;          // "2026-05-31"
    expectedAsOf: string;
    delayNoteJa?: string;        // "12週遅延（無料プラン）"
    status: "ok" | "delayed" | "stale" | "failed";
  }>;
  variant?: "compact" | "full";
}
```

Status derivation:

| Condition | status | Color |
| --- | --- | --- |
| `latestAsOf >= expectedAsOf` | `ok` | `--status-success` |
| Known structural delay (J-Quants free plan) | `delayed` | `--status-warning` |
| 1-3 business days behind expected | `stale` | `--status-warning` |
| More than 3 business days behind | `failed` | `--status-danger` |

The collapsed label reflects the worst status among sources: `最新` / `一部遅延` / `取得エラー`.

### 1.4 Sidebar

Vertical navigation, width `--sidebar-width` (240px), collapsible to `--sidebar-width-collapsed`.

| Order | Icon | label_en | label_ja | Route |
| --- | --- | --- | --- | --- |
| 1 | layout-dashboard | Dashboard | ダッシュボード | `/` |
| 2 | star | Recommendations | 推奨銘柄 | `/recommendations` |
| 3 | filter | Screener | スクリーナー | `/screener` |
| 4 | file-text | Filings | 決算資料 | `/filings` |
| 5 | trending-up | FX & Macro | 為替・マクロ | `/macro` |
| 6 | flask-conical | Model Lab | モデルラボ | `/model-lab` |
| 7 | bot | Agent | エージェント | `/agent` |
| 8 | briefcase | Portfolio | ポートフォリオ | `/portfolio` |
| 9 | settings | Settings | 設定 | `/settings` |

Active item: `--accent` foreground, `--accent-bg` background, 2px left border in `--accent`.

The Recommendations item shows a count badge when new recommendations were generated today.

### 1.5 BottomNav (mobile only)

Five items. Screens not listed here are reached through the Dashboard or the search sheet.

| Order | Icon | label_ja | Route |
| --- | --- | --- | --- |
| 1 | layout-dashboard | ホーム | `/` |
| 2 | star | 推奨 | `/recommendations` |
| 3 | search | 検索 | `/screener` |
| 4 | file-text | 資料 | `/filings` |
| 5 | briefcase | 保有 | `/portfolio` |

Height `--bottom-nav-height` plus `env(safe-area-inset-bottom)`.

## 2. Primitives (shadcn/ui based)

| Component | Variants | Notes |
| --- | --- | --- |
| `Button` | `primary`, `secondary`, `ghost`, `outline`, `danger` | Sizes `sm` (32px), `md` (40px), `lg` (48px). Mobile minimum 44px |
| `Input` | `default`, `error` | Numeric inputs use `inputMode="decimal"` and tabular figures |
| `Select` | `default` | Native on mobile |
| `Combobox` | `default` | Used for ticker search with async results |
| `Checkbox`, `Radio`, `Switch` | | Switch used for kill switch and boolean settings |
| `Tabs` | `underline`, `pill` | `underline` for page-level, `pill` for in-card |
| `Badge` | `neutral`, `info`, `success`, `warning`, `danger`, `accent` | 11px, `--radius-sm` |
| `Tooltip` | | 220ms delay. Touch devices show on tap, not hover |
| `Popover` | | |
| `Dialog` | `sm` (420px), `md` (600px), `lg` (840px) | Becomes a bottom sheet on mobile |
| `Sheet` | `right`, `bottom` | |
| `Accordion` | | Used for filing lists and grouped filters |
| `Table` | `default`, `dense` | Sticky header, sortable columns |
| `Skeleton` | | Matches the final layout dimensions |
| `Toast` | `info`, `success`, `warning`, `danger` | Bottom-right on desktop, top on mobile |
| `Progress` | `linear`, `circular` | Used for job progress and cost gauges |
| `Separator` | `horizontal`, `vertical` | |
| `ScrollArea` | | |

## 3. Data display components

### 3.1 MetricCard

A single KPI with an optional change indicator.

```ts
interface MetricCardProps {
  labelJa: string;
  value: string;                       // pre-formatted, e.g. "3,125円"
  change?: { value: string; direction: "up" | "down" | "flat" };
  subLabelJa?: string;                 // "前日比"
  sampleSize?: number;                 // renders "(n=34)"
  freshness?: { asOf: string; isDelayed: boolean; noteJa?: string };
  size?: "sm" | "md" | "lg";
  state?: "default" | "loading" | "empty" | "error";
}
```

Rendering rules:

- The value uses `--text-metric-lg` for `lg`, `--text-metric` for `md`, `--text-metric-sm` for `sm`.
- Change uses `--dir-up` / `--dir-down` / `--dir-flat` and always includes a sign.
- If `sampleSize` is provided, render it in `--text-caption` / `--fg-tertiary` immediately after
  the value: `58% (n=34)`.
- If `freshness.isDelayed` is true, show a small warning-colored clock icon with the note as a
  tooltip.
- Null value renders as `—` in `--fg-muted`.

Example:

```
定量スコア
78.4  ▲ +3.2
セクター内 12/187
```

### 3.2 DirectionValue

Inline value with direction coloring. Used pervasively in tables.

```ts
interface DirectionValueProps {
  value: number;
  format: "percent" | "currency-jpy" | "currency-usd" | "number" | "zscore";
  showSign?: boolean;                  // default true
  showArrow?: boolean;                 // default false
  precision?: number;
  invertDirection?: boolean;           // for metrics where lower is better
}
```

**Always renders a sign.** The direction color meaning is user-configurable, so color alone is
insufficient. Example outputs: `+8.23%`, `-1.42%`, `±0.00%`.

`invertDirection` is used for metrics like volatility or drawdown where a lower value is favorable.

### 3.3 ScoreBadge

```ts
interface ScoreBadgeProps {
  score: number;                       // 0-100
  rank?: number;
  total?: number;
  showBand?: boolean;                  // renders the band label
  size?: "sm" | "md";
}
```

Renders `78.4` with the background from the score band token, plus optional `12/187`.

### 3.4 ConvictionBadge

```ts
interface ConvictionBadgeProps {
  level: "low" | "medium" | "high";
  score?: number;                      // 0.0-1.0
  sampleSize?: number;                 // n_prior_samples
  showTooltip?: boolean;
}
```

| level | label_ja |
| --- | --- |
| `high` | 確信度 高 |
| `medium` | 確信度 中 |
| `low` | 確信度 低 |

Tooltip content when `sampleSize` is below 20:

```
過去の類似ケースが n=8 件のみのため、確信度を「低」に固定しています
```

**When the underlying data does not support a high conviction, the badge must not render as high.**
This constraint is enforced in the API, but the component also renders the sample size so the basis
is visible.

### 3.5 ReasonCodeChip

```ts
interface ReasonCodeChipProps {
  code: string;                        // "VAL_CHEAP_VS_SECTOR"
  polarity: "positive" | "negative" | "warning";
  onClick?: () => void;                // filters the list by this code
}
```

Reason code labels (complete list, matching `../05-scoring-screening.md` §7.4):

| code | label_ja | polarity |
| --- | --- | --- |
| `VAL_CHEAP_VS_SECTOR` | セクター内で割安 | positive |
| `VAL_CHEAP_VS_HISTORY` | 過去水準比で割安 | positive |
| `MOM_STRONG_12M` | 12ヶ月モメンタム強い | positive |
| `MOM_NEAR_52W_HIGH` | 52週高値圏 | positive |
| `MOM_ABOVE_MA200` | 200日線上 | positive |
| `QLT_HIGH_ROIC` | 高ROIC | positive |
| `QLT_LOW_LEVERAGE` | 低レバレッジ | positive |
| `QLT_CLEAN_ACCRUALS` | 利益の質が良好 | positive |
| `GRW_ACCELERATING` | 成長が加速 | positive |
| `REV_UP_GUIDANCE` | 会社予想の上方修正 | positive |
| `REV_DOWN_GUIDANCE` | 会社予想の下方修正 | negative |
| `VOL_LOW_REGIME` | 低ボラティリティ | positive |
| `FX_TAILWIND` | 為替が追い風 | positive |
| `FX_HEADWIND` | 為替が逆風 | negative |
| `LLM_POSITIVE_GUIDANCE` | 開示トーンが前向き | positive |
| `LLM_NEW_RISK_DISCLOSED` | 新規リスクの開示 | negative |
| `EVENT_EARNINGS_SOON` | 決算発表が近い | warning |
| `DATA_STALE` | データが古い | warning |
| `MODEL_LOW_CONFIDENCE` | モデルの直近成績が低下 | warning |
| `RANK_FILL` | 定量順位による補充 | warning |

Colors: positive uses `--status-info` on `--status-info-bg`; negative uses `--status-danger` on
`--status-danger-bg`; warning uses `--status-warning` on `--status-warning-bg`.

**Negative and warning chips are rendered at the same size and prominence as positive chips.**
Do not visually de-emphasize them or push them to the end of the list.

### 3.6 ForecastValue (critical component)

Renders a forecast. **Structurally incapable of rendering a point estimate alone.**

```ts
interface ForecastValueProps {
  point: number;
  ciLo: number;                        // required, not optional
  ciHi: number;                        // required, not optional
  ciLevel: 60 | 80 | 95;
  format: "percent" | "currency-jpy" | "number";
  hitRate?: number;
  sampleSize?: number;
  beatsBaseline?: boolean;
  baselineNoteJa?: string;
}
```

`ciLo` and `ciHi` are required props. There is no way to render this component without an interval.

Rendering:

```
+2.4%  [-3.1%, +7.9%]
80%予測区間 ／ 過去の的中率 58%（n=34）
```

When `beatsBaseline === false`:

```
+2.4%  [-3.1%, +7.9%]
ランダムウォークに対する優位性は確認できていません（DM検定 p=0.68）
```

The baseline note renders in `--status-warning` at `--text-caption`. It is never hidden behind a
tooltip.

### 3.7 SparklineChart

Inline chart for table cells. Width 80-120px, height 24px. Single stroke in `--chart-1`, no axes, no
fill. Final point marked with a 3px dot in the direction color.

### 3.8 PriceChart

```ts
interface PriceChartProps {
  bars: Array<{ date: string; open: number; high: number; low: number; close: number; volume: number }>;
  type: "line" | "candle";
  range: "1m" | "3m" | "6m" | "1y" | "2y" | "5y" | "max";
  overlays?: Array<"ma20" | "ma50" | "ma200" | "bb20">;
  volumePane?: boolean;
  markers?: Array<{ date: string; kind: "filing" | "earnings" | "recommendation" | "trade"; labelJa: string }>;
  source: string;
  isDelayed: boolean;
  delayNoteJa?: string;
}
```

**The source and delay state are rendered as a caption directly under the chart**, not in a tooltip:

```
出所: J-Quants（リサーチ用・12週遅延、最新 2026-05-31）
```

Markers: filings render as small triangles below the axis; recommendations as diamonds; user trades
as circles in the direction color. Clicking a marker opens the corresponding filing or
recommendation.

### 3.9 FanChart

For FX and return forecasts. Historical line plus forecast cone.

```ts
interface FanChartProps {
  historical: Array<{ date: string; value: number }>;
  forecasts: Array<{
    modelId: string;
    labelJa: string;
    isBaseline: boolean;
    points: Array<{ date: string; point: number; ciLo80: number; ciHi80: number; ciLo95: number; ciHi95: number }>;
  }>;
  currentValue: number;
}
```

- The 95% band uses `--chart-ci-95`, the 80% band `--chart-ci-80`, nested.
- The baseline model (random walk) is always drawn as a dashed line in `--chart-baseline`.
- A vertical separator marks the boundary between historical and forecast.
- Legend states which model beat the baseline and which did not.

### 3.10 FactorRadar

Radar chart of the six factor groups (value, momentum, quality, growth, low volatility, revision).
Displays the stock's z-scores against the sector median. Axis range fixed to -3 to +3 so charts are
comparable between stocks.

### 3.11 DataTable

```ts
interface DataTableProps<T> {
  columns: Array<{
    key: keyof T;
    labelJa: string;
    align?: "left" | "right" | "center";
    width?: number;
    sortable?: boolean;
    sticky?: boolean;
    render?: (row: T) => ReactNode;
    tooltipJa?: string;
  }>;
  rows: T[];
  density?: "default" | "dense";
  totalCount?: number;
  truncated?: boolean;
  onRowClick?: (row: T) => void;
  mobileLayout: "cards" | "scroll";
  state?: "default" | "loading" | "empty" | "error";
}
```

Rules:

- Numeric columns are right-aligned with tabular figures.
- The first column (ticker + name) is sticky on horizontal scroll.
- `mobileLayout: "cards"` converts each row into a card on mobile. **Prefer this over horizontal
  scrolling** for the screener and portfolio tables.
- When `truncated` is true, render a footer: `500件で表示を打ち切りました。条件を絞ってください。`
- Column headers with a `tooltipJa` show an info icon explaining the metric.

## 4. Domain components

### 4.1 RecommendationCard (the most important component)

Two variants: `compact` for lists and dashboards, `full` for the detail view.

```ts
interface RecommendationCardProps {
  rec: {
    recId: string;
    ticker: string;
    market: "JP" | "US";
    nameLocal: string;
    nameEn?: string;
    sectorName: string;
    action: "watch" | "accumulate" | "reduce" | "avoid";
    horizon: "H5" | "H20";
    conviction: "low" | "medium" | "high";
    convictionScore: number;
    thesisJa: string;
    bearCaseJa: string;                // never empty
    invalidationJa: string;
    reasonCodes: string[];
    expectedRet: number;
    expectedRetLo: number;             // required
    expectedRetHi: number;             // required
    hitRatePrior: number | null;
    nPriorSamples: number;
    quantScore: number;
    qualScore: number | null;
    factorScores: Record<string, number>;
    entryRefPrice: number;
    entryRefSource: string;
    entryRefNoteJa: string;
    citations: Array<{ docId: string; page: number; quote: string }>;
    dataFreshness: Array<{ source: string; latestAsOf: string }>;
    criticVerdict: "approved" | "revised" | "rejected";
    criticNotesJa?: string;
    flags: string[];
  };
  variant: "compact" | "full";
}
```

Action labels:

| action | label_ja | Note |
| --- | --- | --- |
| `watch` | 注目 | Deliberately not "買い" (buy) |
| `accumulate` | 積み増し検討 | |
| `reduce` | 縮小検討 | |
| `avoid` | 回避 | |

**Structure of the `full` variant, in this exact order:**

```
RecommendationCard (full)
├── Header
│   ├── ticker + company name + sector
│   ├── ActionBadge + HorizonBadge + ConvictionBadge
│   └── ScoreBadge (quant) + qual score delta
├── ForecastValue                       期待超過リターン + CI + hit rate
├── ReasonCodeChip list                 (positive, negative, warning intermixed)
├── ThesisSection                       強気論拠
├── BearCaseSection                     弱気論拠  <- always visible, never collapsed
├── InvalidationSection                 この見立てを捨てる条件
├── FactorRadar + factor score table
├── CitationList                        根拠資料（引用付き）
├── ReferencePriceRow                   参考価格（遅延あり）+ stop/target
├── PastPerformanceRow                  類似条件の過去実績
├── DataFreshnessRow
├── CriticNoteSection                   レビュー結果
└── Actions: ウォッチリストに追加 / 売買記録を作成 / 銘柄詳細へ
```

**The bear case section is visually equal in weight to the thesis section.** Same typography, same
padding, adjacent to it. Do not put it behind a "show more" control, do not shrink the font, do not
place it below the fold of the card. Rendering the bear case in a warning-tinted panel is acceptable
and preferred, but it must not be dismissible.

`compact` variant shows: header row, ForecastValue, up to 4 reason-code chips, the first line of the
thesis, and a one-line bear-case preview with a "弱気論拠を見る" affordance that expands in place.
Even the compact variant indicates that a bear case exists.

Content spec for section headings:

| Section | label_en | label_ja |
| --- | --- | --- |
| Thesis | Bull case | 強気論拠 |
| Bear case | Bear case | 弱気論拠 |
| Invalidation | Invalidation condition | この見立てを捨てる条件 |
| Citations | Supporting documents | 根拠資料 |
| Reference price | Reference price | 参考価格 |
| Past performance | Similar past cases | 類似条件の過去実績 |
| Critic note | Review result | レビュー結果 |

### 4.2 CitationList

```ts
interface CitationListProps {
  citations: Array<{
    docId: string;
    docTitle: string;
    filedAt: string;
    page: number;
    quote: string;
    verified: "verified" | "verified_fuzzy" | "not_found" | "unchecked";
  }>;
}
```

Each entry:

```
[有価証券報告書] 第122期 有価証券報告書  2026-03-31  p.12  ✓検証済み
「北米市場においては競合他社の価格政策により競争環境が厳しさを増しており」
                                                    [原文を開く]
```

The quote is rendered in a bordered blockquote using `--bg-surface-sunken`. Clicking `原文を開く`
opens the PDF at the cited page.

Verification status:

| status | label_ja | Color |
| --- | --- | --- |
| `verified` | 検証済み | `--status-success` |
| `verified_fuzzy` | 検証済み（表記差あり） | `--status-success` |
| `not_found` | 原文で確認できません | `--status-danger` |
| `unchecked` | 未検証 | `--status-neutral` |

A `not_found` citation means the LLM fabricated the quote. Render it prominently in the danger color
with an explanatory note. Recommendations containing such a citation are rejected by the Critic and
should not normally reach the UI, but the component must handle the case.

### 4.3 FilingListItem

```
2026-04-28  [決算短信]  2026年3月期 第1四半期決算短信〔日本基準〕（連結）
            要約: 売上高12兆3,450億円（前年同期比+8.2%）、通期予想を上方修正
            [PDF]  [要約を見る]  [トーン: 前向き]
```

| Element | Rendering |
| --- | --- |
| Date | `--text-caption`, `--fg-tertiary` |
| Doc type badge | `Badge`, color varies by type |
| Title | `--text-body`, `--fg-primary`, clickable, opens PDF |
| Summary preview | `--text-body-sm`, `--fg-secondary`, 2-line clamp |
| Guidance tone badge | `positive` / `neutral` / `cautious` / `negative` |

Doc type badge colors:

| doc_type | label_ja | Color |
| --- | --- | --- |
| `guidance_revision` | 業績予想の修正 | `--status-warning` (highest information value, emphasized) |
| `earnings_flash` | 決算短信 | `--status-info` |
| `annual_report` | 有価証券報告書 | `--status-neutral` |
| `quarterly_report` | 四半期報告書 | `--status-neutral` |
| `buyback` | 自己株式の取得 | `--status-info` |
| `stock_split` | 株式分割 | `--status-info` |
| `dividend_revision` | 配当予想の修正 | `--status-info` |
| others | (per type) | `--status-neutral` |

Guidance tone labels:

| tone | label_ja |
| --- | --- |
| `positive` | 前向き |
| `neutral` | 中立 |
| `cautious` | 慎重 |
| `negative` | 弱気 |

### 4.4 FilterBuilder (screener)

```ts
interface FilterBuilderProps {
  fields: Array<{
    key: string;
    labelJa: string;
    group: string;                      // "バリュエーション", "クオリティ", ...
    type: "number" | "percent" | "select" | "multiselect" | "boolean" | "date";
    unit?: string;
    min?: number;
    max?: number;
    tooltipJa?: string;
  }>;
  filters: Array<{ field: string; op: string; value: unknown }>;
  presets: Array<{ id: string; labelJa: string; descriptionJa: string; filters: [] }>;
  savedFilters: Array<{ id: string; labelJa: string }>;
}
```

Operator labels:

| op | label_ja |
| --- | --- |
| `gte` | 以上 |
| `lte` | 以下 |
| `gt` | より大きい |
| `lt` | より小さい |
| `eq` | と等しい |
| `ne` | と等しくない |
| `in` | のいずれか |
| `between` | の範囲 |
| `is_not_null` | 値がある |

Preset labels (matching `../05-scoring-screening.md` §9.2):

| id | label_ja | description_ja |
| --- | --- | --- |
| `value_quality` | 割安クオリティ | セクター内で割安かつROICが高い銘柄 |
| `revision_momentum` | 上方修正モメンタム | 会社予想が上方修正され、モメンタムも強い銘柄 |
| `weak_yen_beneficiary` | 円安メリット | 円安局面で恩恵を受けやすい銘柄 |
| `strong_yen_beneficiary` | 円高メリット | 円高局面で恩恵を受けやすい銘柄 |
| `low_vol_dividend` | 低ボラ配当 | ボラティリティが低く配当利回りが高い銘柄 |
| `pre_earnings` | 決算前チェック | 5営業日以内に決算発表がある保有・ウォッチ銘柄 |
| `high_growth` | 高成長 | 売上・EPSがともに15%以上成長 |
| `value_trap_warning` | バリュートラップ注意 | 割安だがクオリティが低い銘柄 |

The `value_trap_warning` preset is rendered with a warning-colored icon. Including a cautionary
preset alongside the opportunity-seeking ones is intentional.

### 4.5 JobTimeline

Horizontal timeline of the six agent jobs.

```
Collector ──► Analyst ──► Researcher ──► Strategist ──► Critic ──► Evaluator
  成功         成功          部分            成功         成功        成功
  4分12秒      8分03秒       2分41秒         1分18秒      0分52秒     0分14秒
```

| status | label_ja | Color |
| --- | --- | --- |
| `success` | 成功 | `--status-success` |
| `partial` | 部分 | `--status-warning` |
| `failed` | 失敗 | `--status-danger` |
| `running` | 実行中 | `--status-info`, animated |
| `interrupted` | 中断 | `--status-warning` |
| `skipped` | スキップ | `--status-neutral` |
| `pending` | 待機 | `--fg-muted` |

A running job shows an inline progress bar with `完了 42 / 61` and an estimated remaining time.
On mobile the timeline stacks vertically.

### 4.6 CostGauge

```ts
interface CostGaugeProps {
  period: "daily" | "monthly";
  spentUsd: number;
  capUsd: number;
  breakdown?: Array<{ purposeJa: string; usd: number; calls: number; cacheHitRate?: number }>;
  killSwitchOn: boolean;
}
```

```
今日の使用額  $0.42 / $1.00   ████████░░░░░░░░░░░░  42%
```

Bar color: `--status-success` below 60%, `--status-warning` from 60% to 90%, `--status-danger` above
90%. When `killSwitchOn`, the bar is fully `--status-danger` and a note reads
`LLM呼び出しを停止しています`.

### 4.7 AgentMemoryList

Displays accumulated lessons.

```
[パターン] JP市場 · confidence 0.72 · n=119 · 使用 34回
JP市場のH20で REV_UP_GUIDANCE が立つケースは、同時に MOM_STRONG_12M が
立つ場合の的中率が68%（n=31）だが、単独では51%（n=88）。上方修正のみを
根拠にした推奨は確信度を上げない。
根拠: 2026-02-01から2026-08-01の推奨119件。…
適用前的中率 54% → 適用後 58%
                                              [無効化]  [編集]
```

| category | label_ja | Color |
| --- | --- | --- |
| `lesson` | 教訓 | `--status-info` |
| `bias` | 偏り | `--status-warning` |
| `pattern` | パターン | `--accent` |
| `caveat` | 注意点 | `--status-warning` |

Inactive lessons render at 50% opacity with a `無効` badge.

When `hitRateAfter < hitRateBefore`, the delta renders in `--status-danger` with a note:
`この教訓は成績を悪化させている可能性があります`.

### 4.8 TradeJournalEntry

```
2026-08-22  買い  7203 トヨタ自動車  100株 @ 3,125円   手数料 275円
判断理由: 上方修正と割安さを評価。北米の競争環境は懸念だが為替の追い風が
          上回ると判断
心理状態: 自信あり     連動推奨: [推奨カードを見る]
出口計画: 3,420円で半分、2,890円割れで全部撤退
評価損益: +2.4%（+7,500円）
                                              [レビューを書く]  [編集]
```

Emotion tag labels:

| tag | label_ja |
| --- | --- |
| `confident` | 自信あり |
| `fomo` | 乗り遅れ懸念 |
| `fearful` | 不安 |
| `neutral` | 平常 |

The emotion tag is a required field when recording a trade. It feeds the execution-quality analysis
on the portfolio screen.

### 4.9 ModelHealthPanel

```
Rank IC（直近20日）    0.041     過去1年の62パーセンタイル    正常
信頼区間カバレッジ      42%       想定 60%                    要注意
特徴量ドリフト          2項目     KS検定 p<0.01               正常
```

When coverage deviates from the expected level by more than 15 points, render a warning note:

```
信頼区間が実際より狭い可能性があります。期待リターンの区間は
参考値として扱ってください。
```

### 4.10 BacktestResultCard

```
value_quality_h20      2024-08-01 〜 2026-08-01      月次リバランス, 20銘柄

年率リターン   12.4%      シャープレシオ    0.82
最大DD        -18.2%      ソルティノ        1.14
的中率         54.2%      情報レシオ        0.61
売買回転率     28.4%      取引コスト累計     -3.2%

Deflated Sharpe Ratio  0.71  (試行回数 142)
試行回数を考慮すると、この結果は偶然の可能性があります

手数料 5.0bps ／ スリッページ 10.0bps ／ 回転率上限 30.0%
```

**The cost parameters are always displayed.** A backtest result without visible cost assumptions is
not interpretable.

When `dsr <= 0.95`, the warning line is mandatory and rendered in `--status-warning`.
When `dsr > 0.95`, render `試行回数を考慮しても統計的に有意です（DSR=0.97）` in
`--status-success`.

### 4.11 WarningBanner

Renders the API `warnings[]` array (see `../09-api-spec.md` §1.2).

```ts
interface WarningBannerProps {
  warnings: Array<{
    code: string;
    messageJa: string;
    severity: "info" | "warning" | "error";
    source?: string;
    section?: string;
  }>;
  dismissible?: boolean;
}
```

Section-scoped warnings render inline within the affected section rather than at the page top, so
the user can tell which part of the screen is degraded.

## 5. Composition rules

1. **Every page renders `warnings[]` from its API response.** No page silently ignores warnings.
2. **Every page shows `DataFreshnessIndicator`** via the header, at minimum.
3. Any component displaying a rate also displays its sample size.
4. Any component displaying a forecast uses `ForecastValue`, which requires an interval.
5. `RecommendationCard` in the `full` variant always renders the bear-case section.
6. Tables on mobile default to `mobileLayout: "cards"` unless the data is genuinely tabular and
   narrow (three columns or fewer).
7. Charts always carry a source and delay caption beneath them.
8. Loading states use `Skeleton` matched to the final layout dimensions to avoid layout shift.
9. Never render a bare number whose sign matters without an explicit sign character.
10. Interactive elements on touch devices have a minimum 44px hit area, achieved with padding rather
    than font size.
