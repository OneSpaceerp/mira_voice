# desk/src/styles

Mira Desk styles use **CSS custom properties only** — no Tailwind (ADR 0005). Vue components write `color: var(--ink)`, `padding-inline: var(--space-4)`; never a raw colour, px value off the scale, or a primitive like `--red-600`.

| File | What | Edit? |
| --- | --- | --- |
| `tokens.css` | All tokens: light (`:root`), dark (`[data-theme="dark"]`), and follow-the-OS when `data-theme` is absent. Type styles as `--type-<style>-{family,size,line,weight,tracking}` | **Generated** — change `design-system/tokens.json`, run `node design-system/tools/build-tokens.mjs` |
| `tokens.ts` | Typed token names (`ColorToken`, `cssVar()`, `duration`, `chartSeries`) for the rare TS that needs a token | **Generated** |
| `base.css` | Box sizing, body type, Arabic font switch via `lang`, LTR islands for numbers/timers, focus ring, touch minimum, reduced motion, wallboard | Hand-written |

```ts
// main.ts
import './styles/tokens.css'
import './styles/base.css'
```

Theme: leave `data-theme` off to follow the OS; set `document.documentElement.dataset.theme = 'dark' | 'light'` when the agent chooses (remember the choice per device, not per account — shared PCs). Wallboard pages always set `data-theme="dark"`.

RTL: `<html lang="ar" dir="rtl">`; logical properties (`margin-inline-start`, `padding-block`, `inset-inline-end`) everywhere; phone numbers, timers and the dial pad in `.mv-ltr` / `.mv-number` / `.mv-timer`.
