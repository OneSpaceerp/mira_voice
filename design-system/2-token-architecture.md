# Token architecture

**Three tiers, one direction of reference: components → semantic → primitives.** Change a primitive and every theme follows; change a semantic token and every component follows; never put a raw value in a component.

| Tier | Example | Who uses it |
| --- | --- | --- |
| **Primitive** — raw OKLCH values in even perceptual steps | `red-600` = oklch(50.4% 0.206 28.5) (#BE0007) | Only semantic tokens |
| **Semantic** — purpose, with a light and a dark value | `mira-red`, `surface`, `ink`, `state-live`, `danger`, `focus-ring` | Screens and components |
| **Component** — one decision per component part | `button-primary-bg` → `{mira-red}`, `call-answer-bg` → `{state-live-strong}` | That component only |

## Scales

- Colour primitives: `red`, `green`, `amber`, `blue`, `clay` (terracotta) at 50–950, and a warm `neutral` 0–950 plus `neutral-ink`. Steps are equal in OKLCH lightness, so `-700` of any hue reads equally dark.
- Spacing: 4, 8, 12, 16, 24, 32, 48, 64 px (`space-1 … space-16`). Eight steps, no more.
- Radius: 6 / 10 / 16 / 24 / pill.
- Size: control heights 32 / 40 / 48, `touch-min` 44, `call-button` 64, `dial-key` 72, `sidebar` 240, `call-panel` 360.
- Motion: `duration-fast/base/slow` 120 / 200 / 320 ms, `ease-standard`, `ease-exit`.
- Type: groups Display, App, Reading, Arabic, Data (see Typography).

## Naming

`<role>-<variant>`, lowercase, hyphenated: `state-ringing-soft`, `button-secondary-border`. Soft = tinted background for that state; strong = fill that carries white content. New tokens need a usage note or they are not added.

## Using the tokens

`tokens.json` is the only source. `node design-system/tools/build-tokens.mjs` generates `tokens.css` (`:root` / `[data-theme="dark"]` / follow-the-OS when `data-theme` is absent), Mira Desk's `desk/src/styles/tokens.{css,ts}` and Mira Phone's `MiraTokens` (ADR 0005); never edit those files. Set the theme on `<html data-theme="dark">` only when the user chooses; otherwise the OS decides. Always render wallboards dark.

**Vue 3 (Mira Desk, admin, Mira Flow):** import `tokens.css` once; write component CSS with `var(--token)` only. Arabic: `<html dir="rtl" lang="ar">` and logical CSS properties (`margin-inline-start`, `padding-inline`), never left/right.

**Tailwind:** not used in Mira Desk (ADR 0005 — CSS variables only). If a future surface adopts it, map semantic tokens, not primitives:

```js
// tailwind.config.js (excerpt)
theme: { extend: { colors: {
  surface: 'var(--surface)', raised: 'var(--surface-raised)', ink: 'var(--ink)', muted: 'var(--ink-muted)',
  brand: 'var(--mira-red)', live: 'var(--state-live)', ringing: 'var(--state-ringing)', hold: 'var(--state-hold)', danger: 'var(--danger)'
}, borderRadius: { md: 'var(--radius-md)', lg: 'var(--radius-lg)', xl: 'var(--radius-xl)' } } }
```

**Flutter (Mira Phone):** package `phone/packages/mira_design` — generated `MiraTokens` ThemeExtension (light + dark) and `MiraTheme.light()/dark(arabic:)`, which map `mira-red` → `ColorScheme.primary`, `surface` → `surface`, `danger` → `error`; text styles from the App and Arabic groups; use `EdgeInsetsDirectional` everywhere for RTL.

**Frappe / ERPNext (Mira Connect):** keep Frappe's own Desk look; use Mira tokens only inside the call pop-up and the Mira Voice workspace cards (`mira-red` header bar, StatusPill colours), loaded as one small CSS file from the app's `hooks.py`.

## Rules

1. Never use a raw hex or a primitive in a component.
2. One red thing per screen.
3. State colour + word, never colour alone.
4. If the scale doesn't fit, change the layout; a new token needs a usage note and a reason.
