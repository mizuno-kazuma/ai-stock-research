# Interaction Patterns

Navigation, responsive behavior, keyboard handling, and interaction conventions. All user-visible
copy is Japanese.

## 1. Navigation model

### 1.1 Structure

Flat, single-level navigation. Nine top-level destinations, no nested menus.

```
/                              ダッシュボード
/recommendations               推奨銘柄
/screener                      スクリーナー
/filings                       決算資料
/macro                         為替・マクロ
/model-lab                     モデルラボ
/agent                         エージェント
/portfolio                     ポートフォリオ
/settings                      設定

/stocks/[market]/[ticker]      銘柄詳細（一覧からの遷移先。ナビには出さない）
```

The stock detail route is reached from lists rather than from the navigation, so it does not appear
in the sidebar or bottom navigation.

### 1.2 Desktop navigation

Persistent left sidebar, 240px, collapsible to 64px (icons only) with the state persisted in
`localStorage`. The active item shows an accent background and a 2px left border. The header and
sidebar stay in the viewport; only `main` scrolls.

### 1.3 Mobile navigation

Bottom navigation with five items (see `components.md` §1.5). The four destinations not in the
bottom bar are reached as follows:

| Destination | Mobile access |
| --- | --- |
| 為替・マクロ | Dashboard FX card, tap through |
| モデルラボ | Settings, or dashboard model-health card |
| エージェント | Dashboard job-status card, or the alert bell |
| 設定 | Header overflow menu |

This is deliberate. The screens omitted from the bottom bar are the ones that are impractical on a
phone (see `../10-mobile-pwa.md` §4.1), and putting them one tap deeper keeps the primary bar clean.

### 1.4 Market switching

The JP / US market switch is global and persists across navigation, stored in
`settings["ui.default_market"]`.

| Screen | Market switch behavior |
| --- | --- |
| Dashboard | Switches all content |
| Recommendations | Switches the list |
| Screener | Switches the universe, resets incompatible filters (for example TSE sector codes) |
| Filings | Switches the source (EDINET/TDnet vs EDGAR) |
| FX & Macro | No effect (always cross-market) |
| Model Lab | Switches the model set |
| Portfolio | Shows both markets; does not switch |
| Stock detail | Determined by the route |

When switching markets resets filters, show a toast: `市場の切替により一部の条件をリセットしました`.

### 1.5 Breadcrumbs

Used only on the stock detail screen, since every other screen is top level.

```
推奨銘柄 › 7203 トヨタ自動車
```

The first segment reflects the actual referrer (推奨銘柄 / スクリーナー / 決算資料 / ポートフォリオ)
so back-navigation returns to the correct list with its state intact.

## 2. Responsive rules

### 2.1 Breakpoints

| Name | Range |
| --- | --- |
| `mobile` | < 768px |
| `tablet` | 768px - 1279px |
| `desktop` | 1280px - 1919px |
| `wide` | >= 1920px |

### 2.2 Layout transformation

| Element | Desktop | Tablet | Mobile |
| --- | --- | --- | --- |
| Navigation | Sidebar 240px | Sidebar 64px (icons) | Bottom nav |
| Page grid | 12 columns | 8 columns | 1 column |
| Card grid | 3 up | 2 up | 1 up |
| Data table | Full table | Full table, horizontal scroll | **Card list** |
| Filter panel | Left panel 320px | Collapsible drawer | Bottom sheet |
| Chart height | 360px | 300px | 240px |
| Recommendation card | Full variant, 2-column internal | Full variant, 1 column | Full variant, stacked |
| Detail panel | Right drawer 480px | Right drawer 400px | Full-screen sheet |
| Global search | Inline 360px | Inline 280px | Full-screen sheet |
| Page padding | 32px | 24px | 16px |

### 2.3 Table to card conversion

On mobile, wide tables become card lists rather than horizontally scrolling tables. Horizontal
scrolling of a wide financial table on a phone is unusable.

Desktop row:

```
7203  トヨタ自動車  輸送用機器  78.4  +1.42  -0.21  +1.85  9.2x  0.98x  11.8%  +2.4%
```

Mobile card:

```
┌────────────────────────────────────────┐
│ 7203  トヨタ自動車          スコア 78.4 │
│ 輸送用機器                              │
│                                         │
│ バリュー  +1.42     クオリティ  -0.21   │
│ 改定      +1.85     PER         9.2x    │
│                                         │
│ ML予測（H20）  +2.4% [-3.1%, +7.9%]     │
└────────────────────────────────────────┘
```

Which columns appear on the card is specified per screen. Not every column survives the conversion;
the card shows the 4-6 fields that matter for scanning, and tapping opens the full detail.

Exception: tables with three or fewer narrow columns (for example the macro series list) stay as
tables on mobile.

### 2.4 Chart adaptation

| Aspect | Desktop | Mobile |
| --- | --- | --- |
| Height | 360px | 240px |
| X-axis ticks | 8-12 | 4-5 |
| Y-axis | Both sides when there are two series | Left only |
| Legend | Inline above the chart | Below the chart, wrapped |
| Tooltip | On hover, follows the cursor | On tap, pinned; tap elsewhere to dismiss |
| Crosshair | On hover | On drag |
| Range selector | Button group, 7 options | Scrollable chip row |
| Volume pane | Shown | Hidden by default, toggleable |

**Never require horizontal scrolling of a chart on mobile.** Change the visible range instead.

### 2.5 Safe areas

```css
.app-header    { padding-top: env(safe-area-inset-top); }
.bottom-nav    { padding-bottom: env(safe-area-inset-bottom); }
.page-content  { padding-left: max(16px, env(safe-area-inset-left));
                 padding-right: max(16px, env(safe-area-inset-right)); }
```

Viewport meta: `width=device-width, initial-scale=1, viewport-fit=cover`.

## 3. Interaction conventions

### 3.1 Row and card activation

| Element | Click / tap | Result |
| --- | --- | --- |
| Screener result row | Anywhere except an action button | Navigate to stock detail |
| Recommendation card (compact) | Anywhere except chips and links | Expand to full variant in place |
| Recommendation card (full) | Ticker or company name | Navigate to stock detail |
| Filing list item | Title | Open the PDF |
| Filing list item | Summary preview | Expand the summary in place |
| Reason code chip | Chip | Filter the current list by that code |
| Job timeline node | Node | Open the job detail drawer |
| Chart marker | Marker | Open the associated filing or recommendation |
| Position row | Anywhere | Expand to show related trades |
| Agent memory item | Item | Expand to show the full evidence text |

Rule: a click that navigates and a click that expands in place are never on the same target. The
ticker navigates; the card body expands.

### 3.2 PDF opening

PDFs open in a new tab with `Content-Disposition: inline`, so the browser renders them rather than
downloading them. On mobile this keeps the document inside Safari or Chrome instead of dumping it
into the Files app.

When a citation with a page number is clicked, append the page fragment:

```
/api/v1/documents/edinet:S100XYZW/file?disposition=inline#page=12
```

`[要検証]` Not all mobile PDF viewers honor `#page=`. If the fragment is ignored, the document still
opens at page 1, which is an acceptable degradation. Show the page number in the citation text so
the user can navigate manually.

### 3.3 Filter interaction

| Interaction | Behavior |
| --- | --- |
| Add a condition | Field dropdown, then operator, then value. Value input type matches the field type |
| Apply | Explicit `適用` button on desktop; auto-apply after 500ms debounce on mobile |
| Remove a condition | X on the chip |
| Reset | `条件をリセット` clears all conditions and returns to the default sort |
| Preset selection | Replaces all conditions; shows a toast naming the preset |
| Save current filter | Prompts for a name, stores in `settings["screener.saved_filters"]` |
| URL sync | Conditions are serialized into the query string so a filter state is linkable and survives reload |

URL synchronization matters for a research tool. Being able to reload the page and land on the same
filter, or keep two filter states in two tabs, is worth the implementation cost.

### 3.4 Sorting

| Interaction | Behavior |
| --- | --- |
| Click a sortable header | Cycles descending, ascending, then default |
| Shift-click | Adds a secondary sort key (desktop only) |
| Mobile | Sort selector in the toolbar rather than header clicks (headers are too small to tap) |

Default sorts:

| Screen | Default sort |
| --- | --- |
| Recommendations | `conviction` desc, then `total_score` desc |
| Screener | `quant_score` desc |
| Filings | `filed_at` desc |
| Portfolio positions | Position value desc |
| Trade journal | `executed_at` desc |
| Backtest list | `run_at` desc |
| Agent jobs | `started_at` desc |

Null values always sort last regardless of direction. A null PER should not appear at the top of an
ascending PER sort as if it were the cheapest stock.

### 3.5 Pull to refresh

Enabled on mobile for the dashboard, recommendations, filings, and portfolio screens. Triggers a
refetch of the screen's queries. During refresh, the existing content stays visible with a spinner
at the top (state `loading-refresh`, never a blanked screen).

Disabled on the screener and model lab, where a refresh is not meaningful and would discard filter
state.

### 3.6 Infinite scroll versus pagination

| Screen | Pattern | Reason |
| --- | --- | --- |
| Filings | Infinite scroll | Chronological browsing |
| Trade journal | Infinite scroll | Chronological browsing |
| Screener results | Pagination (100 per page) | Users compare specific rows and need stable positions |
| Recommendations | No paging (max 10 per day) | |
| Agent jobs | Pagination (50 per page) | |
| Alerts | Infinite scroll | |

Infinite scroll for a comparison table is a poor fit because losing scroll position while comparing
rows is disruptive.

### 3.7 Drawer and sheet behavior

| Content | Desktop | Mobile |
| --- | --- | --- |
| Job detail | Right drawer 480px | Full-screen sheet |
| Document summary | Right drawer 480px | Bottom sheet, 80% height |
| Filter panel | Inline left panel | Bottom sheet, 90% height |
| Trade entry form | Dialog 600px | Full-screen sheet |
| Recommendation detail | In-page expansion | In-page expansion |
| Global search | Dropdown | Full-screen sheet |

Drawers and sheets close on Escape, on backdrop click, and on swipe-down (mobile bottom sheets only).
Forms with unsaved changes confirm before closing: `入力内容を破棄しますか`.

## 4. Keyboard

### 4.1 Global shortcuts

| Key | Action |
| --- | --- |
| `/` | Focus global search |
| `g` then `d` | Go to dashboard |
| `g` then `r` | Go to recommendations |
| `g` then `s` | Go to screener |
| `g` then `f` | Go to filings |
| `g` then `p` | Go to portfolio |
| `g` then `a` | Go to agent |
| `m` | Toggle the JP / US market |
| `t` | Toggle theme |
| `?` | Show the shortcut list |
| `Escape` | Close the topmost overlay |

Sequential shortcuts (`g` then a letter) follow the common convention and avoid conflicting with
browser shortcuts.

### 4.2 List navigation

| Key | Action |
| --- | --- |
| `j` / `ArrowDown` | Next row |
| `k` / `ArrowUp` | Previous row |
| `Enter` | Open the focused row |
| `o` | Open the focused row in a new tab |
| `w` | Add the focused row to the watchlist |
| `Space` | Expand or collapse the focused row |

### 4.3 Focus management

- The focus ring is a 2px `--focus-ring` outline with 2px offset, always visible on keyboard focus.
- Opening a dialog moves focus to the first interactive element; closing it restores focus to the
  trigger.
- Focus is trapped inside dialogs and sheets.
- Skip link at the top of the page: `メインコンテンツへスキップ`.
- Navigating to a new route moves focus to the page heading and announces it via a live region.

## 5. Data refresh behavior

### 5.1 Automatic refetch

| Data | Interval | Condition |
| --- | --- | --- |
| Job status | 15s | Only while a job is running, and only on the agent and dashboard screens |
| Alert count | 60s | Always |
| Current prices | 60s | Only on the portfolio and stock detail screens, only during market hours |
| Cost gauge | 60s | Only on the agent and settings screens |
| Everything else | None | Manual or navigation-triggered only |

`refetchOnWindowFocus` is disabled globally to avoid burning mobile data every time the app is
brought to the foreground (see `../09-api-spec.md` §4).

### 5.2 SSE for job progress

The agent console and the dashboard job card subscribe to `/api/v1/agent/events`. On disconnect,
reconnect with exponential backoff (1s, 2s, 4s, 8s, capped at 30s). After five failures, fall back
to 15-second polling and show `リアルタイム更新を停止しました。15秒ごとに更新します`.

### 5.3 Optimistic updates

| Action | Optimistic | Rollback message |
| --- | --- | --- |
| Add to watchlist | Yes | ウォッチリストへの追加に失敗しました |
| Remove from watchlist | Yes | 削除に失敗しました |
| Mark alert as read | Yes | (silent) |
| Toggle a setting | Yes | 設定の保存に失敗しました |
| Deactivate a lesson | Yes | 無効化に失敗しました |
| Save a trade | **No** | — |
| Delete a trade | **No** | — |
| Activate weights | **No** | — |
| Run a job | **No** | — |

Trade records and weight activation are not optimistic. These are consequential writes where showing
success before confirmation is misleading.

## 6. Search

### 6.1 Global search

Triggered by `/` or clicking the search field. Debounce 250ms, minimum 1 character.

Matching, in this priority order:

1. Exact ticker match (`7203`, `AAPL`)
2. Ticker prefix match
3. Japanese company name, partial match
4. English company name, partial match

Each issuer appears once. SCD2 history rows and JP 4-digit / 5-digit (`1301` / `13010`) collapse
to a single hit. Previous queries must not remain visible while the current query is in flight.

Results group by type:

```
銘柄
  7203  トヨタ自動車          輸送用機器    スコア 78.4
  7267  ホンダ                輸送用機器    スコア 62.1

最近見た銘柄
  6758  ソニーグループ

保有銘柄
  8035  東京エレクトロン
```

Held positions and recently viewed tickers are surfaced as separate groups because those are the
most likely search targets.

`[要検証]` Japanese company name search should ideally match kana as well as kanji (`とよた` matching
`トヨタ自動車`). This requires a `name_kana` column in the `securities` table. If the data source
does not provide kana readings, kanji and katakana matching alone is acceptable.

### 6.2 Empty and no-result states

```
「9999」に一致する銘柄が見つかりません

・銘柄コードは4桁（日本株）またはティッカー（米国株）で入力してください
・銘柄マスタが最新か確認してください（最終更新 2026-08-18）
```

## 7. Error recovery

| Situation | Recovery |
| --- | --- |
| Section fetch failed | Inline retry button, retries only that query |
| Mutation failed | Toast with a retry action; form data is preserved |
| SSE disconnected | Auto-reconnect, then fall back to polling |
| Offline | Queue writes, show the offline banner, sync on reconnect |
| API entirely unreachable | Page-level error with diagnostic commands |
| Stale cache after long absence | Refetch on mount; show cached data during the refetch |

**A failed mutation never clears the form.** Losing typed input on a network error is unacceptable,
particularly for the trade journal where the user may be entering data on a phone.

## 8. Loading transitions

| Transition | Behavior |
| --- | --- |
| Route change | Immediately render the shell and heading, stream sections in |
| Filter apply | Keep the previous results visible at 60% opacity with a progress bar on top |
| Sort change | Client-side when the data is already loaded; no loading state |
| Market switch | Skeleton the content area; keep the header and navigation |
| Range change on a chart | Keep the previous chart visible, overlay a subtle spinner |
| Expanding a card | No loading state if the data is already present; skeleton the new section otherwise |

Never blank content that is already on screen in order to show a loading state. Dim it and overlay
progress instead.

## 9. Touch gestures

| Gesture | Context | Action |
| --- | --- | --- |
| Pull down | Dashboard, recommendations, filings, portfolio | Refresh |
| Swipe down | Bottom sheet | Dismiss |
| Swipe left / right | Chart | Pan the time range |
| Pinch | Chart | Zoom the time range |
| Long press | Table row / card | Show a context menu (watchlist, open in new tab, copy ticker) |
| Tap | Chart | Pin the tooltip at that point |
| Tap outside | Pinned tooltip | Dismiss |

Swipe-to-delete is not used anywhere. Destructive actions require an explicit button and
confirmation; an accidental swipe must not delete a trade record.

## 10. Notification and alert surfacing

| Channel | Content | Behavior |
| --- | --- | --- |
| Header bell badge | Unread alert count | Always visible; opens the alert list |
| Toast | Result of a user-initiated action | Auto-dismiss after 4s |
| Persistent banner | Offline, kill switch, agent down | Not dismissible while the condition holds |
| Inline section notice | Section-level failure | Rendered in the affected section |
| Webhook | Batch completion, failures, cost warnings | External, see `../10-mobile-pwa.md` §5 |

Alerts are grouped by category (`data` / `cost` / `model` / `runtime`) with severity ordering. Alerts
older than 30 days are archived automatically.

## 11. Interaction patterns to avoid

| Anti-pattern | Reason |
| --- | --- |
| Animating numbers counting up | The intermediate value is briefly wrong and may be read |
| Auto-refresh that changes sort order or scroll position | Disruptive while comparing rows |
| Toast for background job completion without a link | The user cannot act on it |
| Hiding the bear case behind a toggle | Violates the core product principle |
| Color-only direction indication | The color meaning is user-configurable |
| Horizontal scroll for wide tables on mobile | Unusable |
| Modal on top of modal | Confusing; use in-place expansion instead |
| Confirmation dialog for reversible actions | Adds friction without protecting anything |
| Blanking loaded content to show a loading state | Perceived as slower and loses context |
| Infinite scroll on a comparison table | Losing scroll position while comparing is disruptive |
| Rendering `null` as `0` | Semantically wrong and can produce a wrong decision |
