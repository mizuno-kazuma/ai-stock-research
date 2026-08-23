# Design System

Dark-first design system. Light mode is fully specified and must be supported. All values are given
as CSS custom properties intended to map directly onto a Tailwind theme extension.

## 1. Color

### 1.1 Base palette (dark theme, default)

| Token | Value | Usage |
| --- | --- | --- |
| `--bg-base` | `#0B0E14` | Page background |
| `--bg-surface` | `#131722` | Cards, panels |
| `--bg-surface-raised` | `#1A1F2E` | Modals, popovers, dropdowns |
| `--bg-surface-sunken` | `#080A0F` | Table headers, code blocks, inset areas |
| `--bg-hover` | `#1F2536` | Hover state on interactive surfaces |
| `--bg-active` | `#252C40` | Pressed state |
| `--bg-selected` | `#1B2A45` | Selected row, active filter chip |
| `--border-subtle` | `#1E2433` | Dividers, table row separators |
| `--border-default` | `#2A3244` | Card borders, input borders |
| `--border-strong` | `#3D4759` | Focused input, emphasized separators |
| `--fg-primary` | `#E6E9F0` | Body text, primary numbers |
| `--fg-secondary` | `#9AA4B8` | Labels, secondary text |
| `--fg-tertiary` | `#6B7688` | Captions, timestamps, units |
| `--fg-muted` | `#4A5468` | Disabled text, null placeholders (`—`) |
| `--fg-inverse` | `#0B0E14` | Text on solid accent backgrounds |

### 1.2 Base palette (light theme)

| Token | Value |
| --- | --- |
| `--bg-base` | `#F7F8FA` |
| `--bg-surface` | `#FFFFFF` |
| `--bg-surface-raised` | `#FFFFFF` |
| `--bg-surface-sunken` | `#EFF1F5` |
| `--bg-hover` | `#F0F2F6` |
| `--bg-active` | `#E6E9EF` |
| `--bg-selected` | `#E4EDFB` |
| `--border-subtle` | `#E8EAEF` |
| `--border-default` | `#D5D9E0` |
| `--border-strong` | `#B0B7C3` |
| `--fg-primary` | `#131722` |
| `--fg-secondary` | `#525C6E` |
| `--fg-tertiary` | `#77808F` |
| `--fg-muted` | `#A0A8B5` |
| `--fg-inverse` | `#FFFFFF` |

### 1.3 Direction colors (user-switchable, critical)

Price direction color conventions are **opposite** between Japan and the US. In Japan, red means
up and blue means down. In the US, green means up and red means down. This product covers both
markets, so the choice cannot be hardcoded. It is a user setting stored as
`settings["ui.direction_colors"]` with values `"jp"` or `"us"`.

**Components must only reference the semantic tokens `--dir-up`, `--dir-down`, `--dir-flat`.**
Never reference a raw green or red value for direction.

#### Mode `jp` (Japanese convention, default) — dark theme

| Token | Value | Meaning |
| --- | --- | --- |
| `--dir-up` | `#F2545B` | Up (red) |
| `--dir-up-bg` | `#3A1418` | Up, background fill |
| `--dir-up-border` | `#7A2830` | Up, border |
| `--dir-down` | `#4B93F5` | Down (blue) |
| `--dir-down-bg` | `#0F2340` | Down, background fill |
| `--dir-down-border` | `#22497F` | Down, border |
| `--dir-flat` | `#8B95A8` | Unchanged |
| `--dir-flat-bg` | `#1C2230` | Unchanged, background fill |

#### Mode `us` (US convention) — dark theme

| Token | Value | Meaning |
| --- | --- | --- |
| `--dir-up` | `#3FBF7F` | Up (green) |
| `--dir-up-bg` | `#0E2E20` | Up, background fill |
| `--dir-up-border` | `#1F6444` | Up, border |
| `--dir-down` | `#F2545B` | Down (red) |
| `--dir-down-bg` | `#3A1418` | Down, background fill |
| `--dir-down-border` | `#7A2830` | Down, border |
| `--dir-flat` | `#8B95A8` | Unchanged |
| `--dir-flat-bg` | `#1C2230` | Unchanged, background fill |

#### Mode `jp` — light theme

| Token | Value |
| --- | --- |
| `--dir-up` | `#D93A42` |
| `--dir-up-bg` | `#FDECEE` |
| `--dir-up-border` | `#F5B8BC` |
| `--dir-down` | `#1F6FD8` |
| `--dir-down-bg` | `#E8F1FD` |
| `--dir-down-border` | `#AFCEF7` |
| `--dir-flat` | `#6E7788` |
| `--dir-flat-bg` | `#F0F2F5` |

#### Mode `us` — light theme

| Token | Value |
| --- | --- |
| `--dir-up` | `#1E9E63` |
| `--dir-up-bg` | `#E6F6EE` |
| `--dir-up-border` | `#A8DFC3` |
| `--dir-down` | `#D93A42` |
| `--dir-down-bg` | `#FDECEE` |
| `--dir-down-border` | `#F5B8BC` |
| `--dir-flat` | `#6E7788` |
| `--dir-flat-bg` | `#F0F2F5` |

#### Implementation

```css
:root { /* dark, jp is default */
  --dir-up: #F2545B;
  --dir-down: #4B93F5;
}
:root[data-direction-colors="us"] {
  --dir-up: #3FBF7F;
  --dir-down: #F2545B;
}
:root[data-theme="light"] { /* light + jp */
  --dir-up: #D93A42;
  --dir-down: #1F6FD8;
}
:root[data-theme="light"][data-direction-colors="us"] {
  --dir-up: #1E9E63;
  --dir-down: #D93A42;
}
```

Switching is instant, with no page reload, by toggling the `data-direction-colors` attribute on the
root element.

**Accessibility requirement**: because the meaning of the color is configurable, direction must
always additionally carry a sign or arrow. Render `+2.31%` or `▲2.31%`, never a bare `2.31%` whose
meaning depends only on color.

### 1.4 Semantic status colors

These are fixed and do not change with the direction-color setting.

| Token | Dark | Light | Usage |
| --- | --- | --- | --- |
| `--status-info` | `#4B93F5` | `#1F6FD8` | Informational notices |
| `--status-info-bg` | `#0F2340` | `#E8F1FD` | |
| `--status-success` | `#3FBF7F` | `#1E9E63` | Job succeeded, verified citation |
| `--status-success-bg` | `#0E2E20` | `#E6F6EE` | |
| `--status-warning` | `#E8A33D` | `#B87716` | Stale data, partial failure, cost approaching cap |
| `--status-warning-bg` | `#33240C` | `#FDF3E2` | |
| `--status-danger` | `#F2545B` | `#D93A42` | Job failed, rejected recommendation, cap exceeded |
| `--status-danger-bg` | `#3A1418` | `#FDECEE` | |
| `--status-neutral` | `#8B95A8` | `#6E7788` | Skipped, not applicable |
| `--status-neutral-bg` | `#1C2230` | `#F0F2F5` | |

### 1.5 Accent

| Token | Dark | Light | Usage |
| --- | --- | --- | --- |
| `--accent` | `#5B8DEF` | `#2F6FE0` | Primary buttons, links, active nav |
| `--accent-hover` | `#7BA5F5` | `#2560CC` | |
| `--accent-bg` | `#141F35` | `#E9F0FD` | Subtle accent surface |
| `--accent-fg` | `#FFFFFF` | `#FFFFFF` | Text on accent |
| `--focus-ring` | `#7BA5F5` | `#2F6FE0` | 2px outline, 2px offset |

### 1.6 Score bands

Quant score is 0-100. Use a graduated scale that does not reuse direction colors, so a score band
is never confused with a price move.

| Range | Token | Dark | Light | Label (ja) |
| --- | --- | --- | --- | --- |
| 80-100 | `--score-band-5` | `#8B5CF6` | `#7C3AED` | 非常に高い |
| 65-79 | `--score-band-4` | `#6D7FF0` | `#5566DD` | 高い |
| 45-64 | `--score-band-3` | `#5A7186` | `#6B7C8E` | 中位 |
| 30-44 | `--score-band-2` | `#7A6A55` | `#95805F` | 低い |
| 0-29 | `--score-band-1` | `#8A5A52` | `#A3675C` | 非常に低い |

### 1.7 Conviction levels

| Level | Token | Dark | Light | Label (ja) |
| --- | --- | --- | --- | --- |
| `high` | `--conviction-high` | `#8B5CF6` | `#7C3AED` | 確信度 高 |
| `medium` | `--conviction-medium` | `#6D7FF0` | `#5566DD` | 確信度 中 |
| `low` | `--conviction-low` | `#6B7688` | `#77808F` | 確信度 低 |

Low conviction is deliberately rendered in a muted neutral rather than a warning color. Low
conviction is the normal, honest default when sample sizes are small; it is not an error.

### 1.8 Chart colors

| Purpose | Token | Dark | Light |
| --- | --- | --- | --- |
| Primary series | `--chart-1` | `#5B8DEF` | `#2F6FE0` |
| Secondary series | `--chart-2` | `#8B5CF6` | `#7C3AED` |
| Tertiary series | `--chart-3` | `#3FBF7F` | `#1E9E63` |
| Quaternary series | `--chart-4` | `#E8A33D` | `#B87716` |
| Quinary series | `--chart-5` | `#E066A6` | `#C4408A` |
| Benchmark / baseline | `--chart-baseline` | `#6B7688` | `#8A93A2` |
| Grid lines | `--chart-grid` | `#1E2433` | `#E8EAEF` |
| Axis labels | `--chart-axis` | `#6B7688` | `#77808F` |
| CI band 80% | `--chart-ci-80` | `rgba(91,141,239,0.22)` | `rgba(47,111,224,0.16)` |
| CI band 95% | `--chart-ci-95` | `rgba(91,141,239,0.10)` | `rgba(47,111,224,0.08)` |
| Crosshair | `--chart-crosshair` | `#4A5468` | `#A0A8B5` |

The baseline series (for example the random-walk reference in the FX forecast chart) is always
rendered in the muted `--chart-baseline` color with a dashed stroke, so the model line and the
baseline are visually distinguishable at a glance.

## 2. Typography

### 2.1 Font families

```css
--font-sans: "Inter", "Noto Sans JP", -apple-system, BlinkMacSystemFont,
             "Hiragino Kaku Gothic ProN", "Yu Gothic UI", sans-serif;
--font-mono: "JetBrains Mono", "SF Mono", "Cascadia Code", Consolas, monospace;
--font-numeric: "Inter", sans-serif;   /* with font-variant-numeric: tabular-nums */
```

Japanese text requires a CJK font in the stack. `Noto Sans JP` covers this. Latin glyphs come from
`Inter` first so that numbers and English labels stay consistent.

### 2.2 Numeric rendering (important)

All numbers in tables, cards, and metrics use:

```css
font-variant-numeric: tabular-nums;
font-feature-settings: "tnum" 1;
```

Without tabular figures, digits have proportional widths and columns of numbers do not align. In a
data-dense financial tool this is immediately noticeable and makes scanning harder.

### 2.3 Type scale

| Token | Size / line-height | Weight | Usage |
| --- | --- | --- | --- |
| `--text-display` | 32px / 40px | 600 | Page hero number (portfolio total) |
| `--text-h1` | 24px / 32px | 600 | Page title |
| `--text-h2` | 20px / 28px | 600 | Section title |
| `--text-h3` | 16px / 24px | 600 | Card title |
| `--text-h4` | 14px / 20px | 600 | Subsection label |
| `--text-body` | 14px / 22px | 400 | Body copy, thesis and bear-case text |
| `--text-body-sm` | 13px / 20px | 400 | Table cells, dense lists |
| `--text-caption` | 12px / 16px | 400 | Timestamps, units, sample sizes |
| `--text-micro` | 11px / 14px | 500 | Badges, reason-code chips |
| `--text-metric-lg` | 28px / 34px | 600 | Primary KPI value |
| `--text-metric` | 20px / 26px | 600 | Secondary KPI value |
| `--text-metric-sm` | 16px / 22px | 600 | Inline metric in a table |

Japanese text at 13px and below becomes hard to read. Use `--text-body-sm` (13px) as the smallest
size for Japanese prose. `--text-caption` and `--text-micro` are reserved for numbers, dates, and
short labels.

### 2.4 Line length

Constrain prose blocks (thesis, bear case, invalidation condition, LLM summaries) to a maximum of
`68ch`. Long Japanese paragraphs at full container width are hard to read.

## 3. Spacing

4px base scale.

| Token | Value |
| --- | --- |
| `--space-0` | 0 |
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |
| `--space-16` | 64px |

Conventions:

| Context | Spacing |
| --- | --- |
| Card internal padding (desktop) | `--space-5` (20px) |
| Card internal padding (mobile) | `--space-4` (16px) |
| Gap between cards | `--space-4` (16px) |
| Gap between page sections | `--space-8` (32px) |
| Table cell padding | `--space-3` vertical, `--space-4` horizontal |
| Table cell padding (dense mode) | `--space-2` vertical, `--space-3` horizontal |
| Form field vertical gap | `--space-4` |
| Inline chip gap | `--space-2` |
| Page horizontal padding (desktop) | `--space-8` |
| Page horizontal padding (mobile) | `--space-4` |

## 4. Radius

| Token | Value | Usage |
| --- | --- | --- |
| `--radius-sm` | 4px | Chips, badges, small inputs |
| `--radius-md` | 8px | Buttons, inputs, table containers |
| `--radius-lg` | 12px | Cards, panels |
| `--radius-xl` | 16px | Modals, sheets |
| `--radius-full` | 9999px | Pills, avatars, toggle knobs |

## 5. Elevation

Dark themes should use border contrast rather than heavy shadows. Shadows are subtle and only used
for elements that genuinely float.

| Token | Dark | Light | Usage |
| --- | --- | --- | --- |
| `--shadow-none` | `none` | `none` | Cards on a page (use border instead) |
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.4)` | `0 1px 2px rgba(16,24,40,0.06)` | Sticky headers |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.45)` | `0 4px 12px rgba(16,24,40,0.10)` | Dropdowns, popovers |
| `--shadow-lg` | `0 12px 32px rgba(0,0,0,0.55)` | `0 12px 32px rgba(16,24,40,0.14)` | Modals, bottom sheets |

**Never apply shadows to charts or data rows.** They add visual noise without carrying information.

## 6. Motion

| Token | Value | Usage |
| --- | --- | --- |
| `--duration-instant` | 80ms | Hover, color change |
| `--duration-fast` | 150ms | Toggle, chip selection |
| `--duration-normal` | 220ms | Dropdown, tooltip, accordion |
| `--duration-slow` | 320ms | Modal, drawer, bottom sheet |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Entering |
| `--ease-in` | `cubic-bezier(0.7, 0, 0.84, 0)` | Exiting |
| `--ease-in-out` | `cubic-bezier(0.65, 0, 0.35, 1)` | Moving |

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Do not animate numbers counting up.** In a financial tool, an animated number is briefly wrong,
and a user glancing at the screen may read the intermediate value.

## 7. Layout tokens

| Token | Value |
| --- | --- |
| `--sidebar-width` | 240px |
| `--sidebar-width-collapsed` | 64px |
| `--header-height` | 56px |
| `--bottom-nav-height` | 56px |
| `--content-max-width` | 1600px |
| `--prose-max-width` | 68ch |

## 8. Breakpoints

| Name | Range | Layout |
| --- | --- | --- |
| `mobile` | < 768px | Single column, bottom navigation, cards instead of tables |
| `tablet` | 768px - 1279px | Two columns, collapsed sidebar |
| `desktop` | 1280px - 1919px | Full sidebar, three-column grids |
| `wide` | >= 1920px | Same as desktop, content capped at `--content-max-width` |

## 9. Z-index

| Token | Value | Usage |
| --- | --- | --- |
| `--z-base` | 0 | |
| `--z-sticky` | 10 | Sticky table headers |
| `--z-header` | 20 | App header |
| `--z-sidebar` | 30 | Sidebar |
| `--z-bottom-nav` | 40 | Mobile bottom navigation |
| `--z-dropdown` | 50 | Dropdowns, popovers, tooltips |
| `--z-overlay` | 60 | Modal backdrop |
| `--z-modal` | 70 | Modals, bottom sheets |
| `--z-toast` | 80 | Toasts |
| `--z-banner` | 90 | Offline and kill-switch banners (always on top) |

The offline banner and the LLM kill-switch banner sit above modals, because the user needs to know
the system is degraded even while a dialog is open.

## 10. Tailwind theme mapping

```js
// tailwind.config.ts (extract)
theme: {
  extend: {
    colors: {
      bg: {
        base: "var(--bg-base)",
        surface: "var(--bg-surface)",
        raised: "var(--bg-surface-raised)",
        sunken: "var(--bg-surface-sunken)",
      },
      fg: {
        primary: "var(--fg-primary)",
        secondary: "var(--fg-secondary)",
        tertiary: "var(--fg-tertiary)",
        muted: "var(--fg-muted)",
      },
      dir: {
        up: "var(--dir-up)",
        down: "var(--dir-down)",
        flat: "var(--dir-flat)",
      },
      status: {
        info: "var(--status-info)",
        success: "var(--status-success)",
        warning: "var(--status-warning)",
        danger: "var(--status-danger)",
      },
      accent: "var(--accent)",
    },
    fontFamily: {
      sans: "var(--font-sans)",
      mono: "var(--font-mono)",
    },
    borderRadius: {
      sm: "var(--radius-sm)",
      md: "var(--radius-md)",
      lg: "var(--radius-lg)",
      xl: "var(--radius-xl)",
    },
  },
}
```

## 11. Token usage rules

1. Never use a hex value directly in a component. Always reference a token.
2. Never use `--status-success` or `--status-danger` for price direction. Use `--dir-up` /
   `--dir-down`.
3. Never use `--dir-up` / `--dir-down` for job status or validation state. Use the status tokens.
4. Score bands use their own scale and never reuse direction or status colors.
5. `--fg-muted` is the only correct color for a null placeholder (`—`).
6. A badge or chip always pairs a foreground token with its matching `-bg` token.
