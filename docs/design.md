# TerraRun design system (v2)

Calm, precise and solid, in the spirit of Strava, Nike Run Club, Apple
Fitness and Runna. Hierarchy comes from **size, spacing and contrast**, not
from heavy weights or colour effects.

## Rules

- **No gradients anywhere.** No `LinearGradient`, `RadialGradient`, glows or
  coloured shadows. Every surface is one solid colour.
- **Two-tone base plus one signature colour:** near black and near white, with
  a soft lime reserved for what matters most (your territory, Run, Start).
- **Light type:** most text is regular (400) or medium (500). Semibold (600)
  only for screen titles, the one big number on a card, and buttons.
  Never 700 or 800.
- **Tight corners:** cards and sheets 10 px, inputs and buttons 8 px, chips and
  small badges 6 px. Only avatars, the location dot and the round map buttons
  stay circular. No pill-shaped cards.
- **Flat:** separate surfaces with a 1 px line or a step in surface colour,
  not shadows.

## Tokens (`lib/theme/app_theme.dart`)

| Token | Value | Use |
|---|---|---|
| `bg` | `#090B0D` | Screen background (near black) |
| `surface` | `#121518` | Cards, sheets, nav bar |
| `surfaceHigh` | `#1B1F24` | Pressed states, inputs, selected segment background |
| `line` | `#262B31` | 1 px dividers and card borders |
| `text` | `#F4F6FA` | Primary text, primary buttons (near white) |
| `textSecondary` | `#A3ACBD` | Labels, secondary text |
| `textMuted` | `#6B7589` | Captions, disabled |
| `onLight` | `#090B0D` | Text on near-white buttons |
| `signature` | `#C6F36A` | Signature colour (soft lime), used sparingly: your territory number and shape, the Run tab, Start run, progress, your "You" badge. Never body text. `onSignature` `#090B0D` sits on it. |
| `accent` | `#F4F6FA` | Same as `text`: the primary action is a solid near-white button with near-black text |
| `positive` | `#4ADE80` | Good GPS, gains |
| `warning` | `#FBBF24` | Fair GPS, location problems |
| `negative` | `#F87171` | Poor GPS, stop run, destructive actions |
| `mine` | = `signature` | Your territory and route on the map (solid; fill at 28% opacity) |
| `rivalPalette` | muted solid hues: `#60A5FA #F59E0B #34D399 #F472B6 #A78BFA #F87171 #22D3EE` | Other players' territory |

## Type (Inter, via `google_fonts`)

| Style | Size / weight | Use |
|---|---|---|
| `display` | 32 / 600, tracking −0.5 | Onboarding headline only |
| `title` | 20 / 600 | Screen titles |
| `headline` | 17 / 600 | Section titles, card titles |
| `body` | 15 / 400 | Body text |
| `bodySecondary` | 14 / 400, `textSecondary` | Supporting text |
| `label` | 13 / 500, `textSecondary` | Stat labels, list metadata |
| `caption` | 12 / 400, `textMuted` | Timestamps, fine print |
| `overline` | 11 / 500, tracking 0.8, uppercase, `textMuted` | Small section labels |
| `stat(size)` | given size / 500, tabular figures | Numbers. The one hero number on a screen may use 600. |
| `button` | 15 / 600 | Buttons |

Units after numbers ("km", "/km", "m²") are smaller, `textSecondary`, weight 400.

## Components

- **Primary button:** solid `text` background, `onLight` label, 48 px high,
  8 px radius. **Secondary:** transparent with 1 px `line` border, `text` label.
  **Destructive:** solid `negative`.
- **Segmented control:** `surface` track, 8 px radius, selected segment
  `surfaceHigh` with `text` label; unselected `textSecondary`. No near-white
  selected pill.
- **Cards:** `surface`, 1 px `line` border, 10 px radius, 16 px padding.
- **Stat grid (Strava style):** label above value, values in a 2- or 3-column
  grid separated by 1 px lines.
- **Lists:** rows with 1 px dividers, not a card per row.
- **Bottom nav:** `surface`, 1 px top line, outline icons; selected item `text`,
  others `textMuted`; the Run tab is a solid signature-colour circle with a near-black icon.
- **Map:** keep the muted dark base map. Route lines solid, 4 px.
  The location dot is near-white with a near-black ring.

## Inspiration to borrow from

- **Strava:** activity detail (map on top, stat grid, splits table), feed cards
  with a small map preview, profile header with Follow / Edit buttons.
- **Nike Run Club:** big confident run timer, generous whitespace.
- **Apple Fitness:** restrained colour, clean stat typography.
- **Runna:** compact segmented controls and tidy cards.
