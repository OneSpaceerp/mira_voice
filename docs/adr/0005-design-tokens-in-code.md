# 0005 — Design tokens in code: one generator, CSS variables for Mira Desk (no Tailwind), a Flutter ThemeExtension for Mira Phone

- Status: accepted
- Date: 2026-11-25

## Context
Task 0.5 turns `design-system/tokens.json` into code for Mira Desk (Vue) and Mira Phone (Flutter). The design system allows "Tailwind (if used)". `tokens.css` had been produced by the design-system page, held colours and scales but no text styles, and only switched to dark with `data-theme="dark"` although the token chapter says to follow the OS by default. Flutter cannot use OKLCH, which is how every colour is defined.

## Decision
1. **One generator**, `design-system/tools/build-tokens.mjs` (Node, no dependencies), reads `tokens.json` and writes `design-system/tokens.css`, `desk/src/styles/tokens.css`, `desk/src/styles/tokens.ts` and `phone/packages/mira_design/lib/src/mira_tokens.g.dart`. Generated files are never edited; a pre-commit hook (`--check`) fails when they are stale.
2. **Mira Desk uses CSS custom properties only — no Tailwind.** The token chapter already prescribes `var(--token)` in Vue; a utility framework would add a second vocabulary and make raw values (`p-[13px]`, `bg-red-600`) easy to slip in. Generated: every token plus text styles as `--type-<style>-{family,size,line,weight,tracking}`. Hand-written `base.css`: Arabic font via `lang`, LTR islands for numbers/timers, focus ring, touch minimum, reduced motion.
3. **Theme selection:** light by default; `data-theme="dark|light"` when the user chooses; **follows the OS** (`prefers-color-scheme`) when `data-theme` is absent. Primitives are emitted once (they do not change per theme).
4. **Mira Phone:** package `phone/packages/mira_design` with `MiraTokens` (a `ThemeExtension`, light + dark: every semantic and component colour, themed shadows) and `MiraTheme.light()/dark(arabic:)` building Material 3 `ThemeData` with the documented mapping (`mira-red` → primary, `surface` → surface, `danger` → error, neutral secondary). Primitives are not exposed to widgets.
5. **Colour conversion:** OKLCH → sRGB per CSS Color 4 is checked against the sRGB hex the design tool recorded for each primitive (≤ 2/255 per channel; differences only at the gamut edge). Flutter uses the **recorded hex**, so the brand red is exactly `#BE0007` everywhere.
6. **The accessibility chapter's contrast table is executable:** the generator tests recompute all 37 rows in both themes and fail if a ratio changes or drops below its WCAG target.

## Consequences
- Changing a colour = edit `tokens.json`, run the generator, run `node --test design-system/tools/`; CSS, TS and Dart change together.
- Components in Mira Desk must be written with CSS (scoped styles + tokens); no Tailwind utility classes. Revisit only if a concrete need appears (ADR).
- Fonts (IBM Plex Sans / Sans Arabic / Mono, Archivo — SIL OFL) still have to be self-hosted in Mira Desk (no Google Fonts call from an on-prem PWA) and bundled in Mira Phone: tasks 2.1 and Phase 3.
- The reference components in `design-system/components/` still use a few literal font sizes; Mira Desk components use the `--type-*` tokens instead.
