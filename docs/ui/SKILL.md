---
name: ai-stock-research-ui
description: Design system, component inventory, and screen specifications for an AI-driven stock research and trade-decision-support tool covering Japanese and US equities. Upload this file to Figma Make as the primary instruction document when generating any screen of this product. Read the referenced files for tokens, components, states, and per-screen specifications.
---

# AI Stock Research UI Specification

This is the primary instruction file for generating the UI of an AI-driven stock research and
trade-decision-support tool. All structural and instructional prose in these documents is written
in English for generation quality. **All in-app copy that a user actually reads is Japanese**, and
is provided as paired `label_en` / `label_ja` fields. Render the `label_ja` value in the UI.

## 1. Product summary

A single-user tool that collects public market data and regulatory filings for Japanese (TSE) and
US equities, runs statistical analysis and LLM-based qualitative analysis, and presents
**decision-support material**. It does not place orders. The user is always the decision maker.

Target user: one individual investor, Japanese speaker, checks the tool in the morning and evening,
on desktop and on a phone.

## 2. Non-negotiable design principles

These are product requirements, not stylistic preferences. Violating them makes the product
misleading. Apply them to every screen.

1. **Never present a forecast as a certainty.** Every forecast must be shown together with a
   confidence interval and a historical hit rate. A point estimate rendered alone is a defect.
2. **Every recommendation card must show a bear case.** The bear case is not collapsed behind a
   "show more" toggle by default on the detail view. A recommendation without a bear case cannot
   exist in the data model, so there is no empty state for it.
3. **Always show data freshness.** The Japanese price source runs on a free plan with a 12-week
   delay. Hiding this causes bad decisions. The app header carries a persistent freshness
   indicator, and any price shown as "current" is labeled as a delayed reference value.
4. **Show sample sizes next to any rate.** Render "hit rate 58% (n=34)", never "hit rate 58%".
5. **Show negative information with the same prominence as positive information.** Reason codes
   include warning codes such as stale data and model degradation. Do not visually de-emphasize
   them.
6. **Partial data is a first-class state, not an error.** When one data source fails, render the
   sections that do work and mark the failed section explicitly. Never blank the whole screen.
7. **Up/down colors are a user setting, not a fixed choice.** The Japanese convention (red = up,
   blue = down) and the US convention (green = up, red = down) are opposite. Use semantic tokens
   only. Never hardcode green or red for direction.
8. **Never use the words "buy" or "sell" as a system instruction.** Actions are labeled
   "注目" (watch), "積み増し検討" (consider accumulating), "縮小検討" (consider reducing),
   "回避" (avoid).

## 3. Visual direction

- Dark first. Light mode is fully specified and must be supported, but dark is the default.
- Dense but calm. This is a data tool used daily; it should not fatigue the eye.
- Numbers are the primary content. Use tabular figures so digits align in columns.
- Restrained use of color. Color carries meaning (direction, severity, score bands) and is not
  decorative.
- No emoji anywhere in the UI.
- Charts are functional, not decorative. No gradients under lines, no 3D, no drop shadows on data.

## 4. Reading order for these documents

| Order | File | Contents |
| --- | --- | --- |
| 1 | `design-system.md` | Color, typography, spacing, radius, elevation, motion tokens. Direction-color switching. |
| 2 | `components.md` | Component inventory with props, variants, and composition rules. |
| 3 | `states.md` | Empty, loading, error, partial-data, offline, and stale-data states for every component. |
| 4 | `interaction-patterns.md` | Navigation, responsive rules, breakpoints, focus and keyboard behavior. |
| 5 | `screens/01-dashboard.md` … `screens/10-settings.md` | One file per screen, 10 screens total. |
| 6 | `sample-data.json` | Realistic mock data. Use this to populate every screen. |

## 5. Screen list

| # | File | Route | Purpose |
| --- | --- | --- | --- |
| 01 | `screens/01-dashboard.md` | `/` | Morning overview: market, FX, top recommendations, portfolio, alerts, job status |
| 02 | `screens/02-recommendations.md` | `/recommendations` | Recommendation cards with thesis, bear case, citations, past performance |
| 03 | `screens/03-stock-detail.md` | `/stocks/[market]/[ticker]` | Single stock: chart, factors, financials, filings, recommendation history |
| 04 | `screens/04-screener.md` | `/screener` | Filter builder and results table |
| 05 | `screens/05-filings-hub.md` | `/filings` | Cross-ticker filing feed with one-click PDF access |
| 06 | `screens/06-fx-macro.md` | `/macro` | USDJPY forecast fan chart, baseline comparison, rate differential, macro series |
| 07 | `screens/07-model-lab.md` | `/model-lab` | Rank IC, feature importance, backtest results, Deflated Sharpe Ratio |
| 08 | `screens/08-agent-console.md` | `/agent` | Job timeline, LLM cost, critic rejection stats, agent memory, kill switch |
| 09 | `screens/09-portfolio-journal.md` | `/portfolio` | Positions, trade journal, recommendation-quality vs execution-quality analysis |
| 10 | `screens/10-settings.md` | `/settings` | Direction colors, theme, cost caps, data plan, notifications |

## 6. Screen file format

Every screen file uses the identical structure so it can be parsed uniformly. Do not deviate.

```
# NN. Screen Name

## Purpose
## Route
## Layout
### Desktop (>= 1280px)
### Tablet (768px - 1279px)
### Mobile (< 768px)
## Component tree
## Content spec
## States
## Interactions
## Data source
```

- **Layout** gives explicit grid definitions for each breakpoint.
- **Component tree** is indented so the hierarchy can be built directly.
- **Content spec** gives every string as a `label_en` / `label_ja` pair with realistic inline data
  examples. There is no lorem ipsum anywhere.
- **States** covers empty, loading, error, and partial-data.
- **Interactions** lists each interactive element and its destination.

## 7. Language rules

| Element | Language |
| --- | --- |
| All visible UI copy | Japanese (`label_ja`) |
| Company names (Japanese equities) | Japanese (`トヨタ自動車`) |
| Company names (US equities) | English (`Apple Inc.`) |
| Ticker symbols | As-is (`7203`, `AAPL`) |
| Filing titles | Original language of the filing |
| Quotes from filings | Original language, unmodified |
| Numbers and units | Japanese formatting: `1兆2,340億円`, `3,125円`, `152.34円`, `+8.2%` |
| Dates | `2026年8月22日` in prose, `2026-08-22` in tables and technical contexts |
| Code, routes, field names | English |

## 8. Data formatting rules

| Data | Format | Example |
| --- | --- | --- |
| JPY price | Integer with thousands separator + `円` | `3,125円` |
| USD price | 2 decimals + `$` prefix | `$189.42` |
| Large JPY amount | Japanese units | `1兆2,340億円`, `5,120億円` |
| Percentage change | Signed, 2 decimals, `%` | `+8.23%`, `-1.42%` |
| Score (0-100) | 1 decimal | `78.4` |
| z-score | Signed, 2 decimals | `+1.42`, `-0.21` |
| Confidence interval | Bracketed range | `+2.4% [-3.1%, +7.9%]` |
| Rate with sample size | Percentage + parenthetical n | `58% (n=34)` |
| Volume | Thousands separator + `株` | `8,234,100株` |
| Date in table | ISO | `2026-08-22` |
| Datetime | Japanese, JST | `2026年8月22日 18:35` |
| Null / unavailable | Em dash, muted color | `—` |

**Never render `null` as `0`.** A missing PER and a PER of zero mean entirely different things.
Use `—` in the muted foreground color.

## 9. Accessibility requirements

- Contrast ratio of at least 4.5:1 for body text, 3:1 for large text, in both themes.
- **Direction must never be conveyed by color alone.** Always pair the color with a sign (`+` / `-`)
  or an arrow glyph, because the color meaning is user-configurable and because of color vision
  deficiency.
- All interactive elements reachable by keyboard, with a visible focus ring.
- Minimum tap target 44 x 44 px on touch.
- Charts have an accessible table equivalent behind a toggle.
- `aria-live="polite"` for the job-progress region and alert counts.
- Respect `prefers-reduced-motion` by disabling all non-essential transitions.

## 10. What not to generate

- Do not generate order-entry UI. There is no buy or sell button anywhere in this product.
- Do not generate login, signup, or account-management screens. Single user, no auth in Phase A.
- Do not generate onboarding tours or marketing pages.
- Do not generate a chat interface. LLM output appears as structured summaries with citations, not
  as a conversation.
- Do not generate social features, sharing, or comment threads.
- Do not add price alerts triggered by thresholds. Alerts are system health and filing events only.

## 11. Reference to the engineering specification

The screens are backed by the API described in `../09-api-spec.md`. Field names in the content specs
match that API. If a screen spec and the API spec disagree, the API spec is authoritative for field
names and the screen spec is authoritative for presentation.
