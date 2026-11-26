# Native shell and geometry

The layer that stops the app looking like a browser. Roughly two hundred lines
total, and it accounts for most of the perceived difference.

## Manifest

```json
{
  "id": "/app",
  "name": "Enterprise Mobile",
  "short_name": "Enterprise",
  "description": "…",
  "start_url": "/app?source=pwa",
  "scope": "/app",
  "display": "standalone",
  "display_override": ["window-controls-overlay", "standalone"],
  "orientation": "portrait-primary",
  "background_color": "#0F172A",
  "theme_color": "#0F172A",
  "lang": "en",
  "dir": "ltr",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/icons/maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable" },
    { "src": "/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [
    { "src": "/screens/home-540x1170.png", "sizes": "540x1170", "type": "image/png", "form_factor": "narrow" }
  ],
  "shortcuts": [
    { "name": "New order", "url": "/app/orders/new", "icons": [{ "src": "/icons/new-96.png", "sizes": "96x96" }] }
  ]
}
```

Field by field, what actually matters:

- **`display: standalone`** removes browser chrome. `fullscreen` also takes the
  status bar — correct for a game or a kiosk, wrong for an app with a header.
  `minimal-ui` keeps a slim back/reload affordance, which is a reasonable hedge on
  Android for a deep-navigation app.
- **`display_override`** lets desktop use `window-controls-overlay`, drawing your
  content into the title bar. Order matters: first supported value wins.
- **`scope` must contain `start_url`.** Navigation outside `scope` opens in a
  browser tab — which is occasionally what you want (an external link) and usually
  a bug. Getting this wrong is also how a service worker ends up never controlling
  the pages you care about.
- **`id`** pins app identity independently of `start_url`. Without it, changing
  `start_url` later makes the OS treat it as a different app and the user has two
  icons.
- **Separate `any` and `maskable` icons.** Maskable art needs ~20 % padding inside
  a safe circle, because Android clips to a circle, squircle or rounded square
  depending on launcher. The same file used for both is either cropped or floating
  in white space. This is the single most common visible manifest mistake.
- **`screenshots` with `form_factor`** unlocks the richer Android install dialog,
  which converts noticeably better than the minimal one.
- **`orientation`** locks rotation. Only do it if landscape genuinely does not
  work; on a tablet deployment, locking is a complaint generator.

## iOS meta tags

Apple does not read most of the manifest. These go in `<head>`:

```html
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-title" content="Enterprise" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="theme-color" content="#0F172A" />

<meta
  name="viewport"
  content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover, interactive-widget=resizes-content"
/>

<link rel="apple-touch-icon" href="/icons/apple-touch-icon-180.png" />
```

**`apple-mobile-web-app-status-bar-style` is a real decision, not a default.**

| Value | Behaviour |
|---|---|
| `default` / `black` | iOS reserves an opaque status bar strip above your content. Safe, and your layout never needs `safe-area-inset-top`. Your app visibly starts below a bar. |
| `black-translucent` | Your canvas occupies the **entire** display, under the status bar, notch and Dynamic Island. Genuinely full-bleed — and every top-pinned element now *must* respect `safe-area-inset-top` or it renders under the clock. |

Choose `black-translucent` if you want full-bleed and are willing to own the
insets. Choose `default` if the app has a solid-colour header and you would rather
not think about it. Frappe HR chooses the safe path (`white`); a consumer-grade app
chooses translucent. **Do not choose translucent and then forget the insets** —
that is strictly worse than either.

`user-scalable=no` / `maximum-scale=1` stops the double-tap zoom that makes taps
feel laggy, at the cost of an accessibility affordance. If your app has body text
people read, consider leaving zoom enabled and fixing tap latency with
`touch-action: manipulation` instead.

## Safe-area insets

```css
:root {
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-right: env(safe-area-inset-right, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-left: env(safe-area-inset-left, 0px);
}

.app-header {
  position: fixed;
  inset: 0 0 auto 0;
  height: calc(52px + var(--safe-top));
  padding-top: var(--safe-top);
  background: var(--surface);
  z-index: 1000;
}

.tab-bar {
  position: fixed;
  inset: auto 0 0 0;
  height: calc(56px + var(--safe-bottom));
  padding-bottom: var(--safe-bottom);
  background: var(--surface);
  z-index: 1000;
}

.scroll-container {
  padding-top: calc(52px + var(--safe-top));
  padding-bottom: calc(56px + var(--safe-bottom));
}
```

Numbers worth knowing: modern iPhones reserve roughly 44–59 px at the top
(depending on notch vs Dynamic Island) and 34 px at the bottom for the home
indicator. Landscape adds left/right insets — `--safe-left` and `--safe-right` are
not decorative, and an app that only handles top and bottom breaks the moment
someone rotates.

`env()` resolves to `0px` everywhere else, so this costs nothing on other devices.

The bottom inset is not only cosmetic: the home-indicator strip is a **system
gesture zone**. A button placed inside it receives the OS's swipe-up instead of
your tap.

In Tailwind:

```js
theme: {
  extend: {
    padding: {
      'safe-top': 'env(safe-area-inset-top)',
      'safe-bottom': 'env(safe-area-inset-bottom)',
      'safe-left': 'env(safe-area-inset-left)',
      'safe-right': 'env(safe-area-inset-right)',
    },
    screens: { standalone: { raw: '(display-mode: standalone)' } },
  },
}
```

The `standalone:` variant matters because in a browser tab the browser's own
chrome already occupies that space — applying the inset there adds a dead band.

## Viewport height

`100dvh` is correct in a browser tab, where it tracks the collapsing address bar.
In an **installed iOS PWA it is unreliable on cold boot**: with no browser chrome
to expand or contract, WebKit often fails to initialise dynamic viewport metrics
and returns a wrong value until an orientation change forces recalculation.

So for the root container of a standalone PWA:

```css
html, body, #root {
  height: 100%;      /* not 100dvh, not 100vh */
  margin: 0;
  overflow: hidden;  /* the shell never scrolls; a container inside it does */
}
```

`height: 100%` chained from `html` down is stable everywhere. Reserve `dvh` for
components inside a correctly-sized root, where it behaves.

## Keyboard

The keyboard is the largest single source of "this feels broken".

**Chromium 108+ and Firefox 132+**: `interactive-widget=resizes-content` in the
viewport meta contracts the layout viewport to the visible area. Fixed elements
stay put relative to what the user can see. One attribute, done.

**WebKit does not support it.** iOS treats the keyboard as a floating layer over
the layout viewport, scrolls the window unpredictably, and lets fixed-position
elements drift. Track the Visual Viewport and expose the obscured height as a CSS
variable:

```js
(() => {
  const vv = window.visualViewport
  if (!vv) return

  let raf = 0
  const update = () => {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
      document.documentElement.style.setProperty('--keyboard-inset', `${inset}px`)
      document.documentElement.classList.toggle('keyboard-open', inset > 80)
    })
  }

  vv.addEventListener('resize', update)
  vv.addEventListener('scroll', update)
  update()
})()
```

```css
.composer {
  position: fixed;
  bottom: calc(var(--keyboard-inset, 0px) + var(--safe-bottom));
  left: 0; right: 0;
  transition: bottom 0.1s cubic-bezier(0.2, 0, 0, 1);
}

/* the tab bar is meaningless while typing */
.keyboard-open .tab-bar { display: none; }
```

- `requestAnimationFrame` coalescing matters — `resize` and `scroll` both fire
  during the keyboard animation, and updating a CSS variable per event janks.
- The `> 80` threshold distinguishes a keyboard from an address-bar collapse.
- Add `--keyboard-inset` to the bottom padding of the scroll container too, or the
  last item in a list is unreachable while typing.
- **Inputs must be ≥ 16 px** or iOS Safari zooms the viewport on focus and the
  whole layout jumps. This is non-negotiable and catches everyone once.
- `scrollIntoView({ block: 'center' })` on focus, after a short delay, keeps the
  active field visible on WebKit.

## CSS normalisation

The browser behaviours that give a web app away, and their fixes:

| Property | Value | Removes |
|---|---|---|
| `-webkit-tap-highlight-color` | `transparent` | The grey/blue rectangle flash on tap |
| `user-select` | `none` | Accidental text selection and the magnifier during swipes |
| `-webkit-touch-callout` | `none` | The long-press "Save Image / Copy Link" sheet |
| `touch-action` | `manipulation` or `pan-y` | Double-tap-to-zoom delay; constrains gestures to one axis |
| `overscroll-behavior-y` | `none` / `contain` | Rubber-band bounce and browser pull-to-refresh |
| `scrollbar-width` / `::-webkit-scrollbar` | `none` / `display: none` | Persistent scrollbars, which no native list has |

```css
*, *::before, *::after {
  -webkit-tap-highlight-color: transparent;
  -webkit-touch-callout: none;
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  overscroll-behavior: none;
  user-select: none;
  -webkit-user-select: none;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  background-color: #0F172A;
  color-scheme: dark light;
}

/* give text back wherever it is content */
input, textarea, [contenteditable="true"], .selectable, p, li, h1, h2, h3 {
  user-select: text;
  -webkit-user-select: text;
  -webkit-touch-callout: default;
}

.scroll-container {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
  touch-action: pan-y;
  scrollbar-width: none;
}
.scroll-container::-webkit-scrollbar { display: none; }
```

**A blanket `user-select: none` is a real cost.** Users copy order numbers, phone
numbers, addresses and error messages out of apps constantly. The re-enable rule
above is not optional — extend it to every element that carries a value someone
might need elsewhere.

`overscroll-behavior-y: contain` rather than `none` on inner containers keeps the
bounce inside that container instead of chaining to the page, which is the native
behaviour; `none` on the body kills browser pull-to-refresh so you can build your
own.

`color-scheme` on `body` tells the UA to render form controls and scrollbars in
the matching scheme — without it, native controls stay light on a dark app.

## Splash screens

Android generates a splash from `background_color`, `theme_color` and the icons.
Nothing to do.

**iOS ignores the manifest for launch screens** and shows a blank white window
unless you supply `<link rel="apple-touch-startup-image">` for each device
geometry, matched by media query:

```html
<link rel="apple-touch-startup-image"
      media="(device-width: 430px) and (device-height: 932px) and (-webkit-device-pixel-ratio: 3) and (orientation: portrait)"
      href="/splash/apple-splash-1290-2796.png" />
<link rel="apple-touch-startup-image"
      media="(device-width: 393px) and (device-height: 852px) and (-webkit-device-pixel-ratio: 3) and (orientation: portrait)"
      href="/splash/apple-splash-1179-2556.png" />
<!-- …one pair (portrait + landscape) per supported device… -->
```

Common geometries:

| Device class | CSS px | DPR | Asset |
|---|---|---|---|
| iPhone Pro Max (16/15) | 430 × 932 | 3× | 1290 × 2796 |
| iPhone Pro (16/15) | 393 × 852 | 3× | 1179 × 2556 |
| iPhone 15/14/13 | 390 × 844 | 3× | 1170 × 2532 |
| iPhone 14 Plus / 13 Pro Max | 428 × 926 | 3× | 1284 × 2778 |
| iPhone SE 3 | 375 × 667 | 2× | 750 × 1334 |
| iPad Pro 13" | 1024 × 1366 | 2× | 2048 × 2732 |
| iPad Air 11" | 820 × 1180 | 2× | 1640 × 2360 |

Do not hand-cut these. Frappe HR ships 28 tags (14 devices × two orientations),
and it generated them:

```bash
npx pwa-asset-generator ./logo.svg ./public/splash \
  --background "#0F172A" --splash-only --portrait-only false \
  --index ./index.html --path-override "/splash"
```

It renders through headless Chromium and writes the `<link>` tags into your
`index.html`. Re-run it when Apple ships a new geometry; a device with no matching
media query falls back to white.

The splash must **match your app's first paint** — same background colour, logo in
the same position. A splash that differs from the loaded UI produces a visible
jump that reads worse than no splash.

## Fonts

- Self-host. A Google Fonts request on a cold, offline-ish start is a flash of
  invisible text at exactly the wrong moment.
- `font-display: swap`, and a system-font fallback stack with matching metrics so
  the swap does not reflow.
- Subset aggressively. A variable font subset to Latin + your language is often
  under 30 KB; the full family is ten times that.
- Preload only the one face used above the fold.

## Dark mode

```css
:root { color-scheme: light dark; }
```

Then define the palette as custom properties on `:root`, override under
`@media (prefers-color-scheme: dark)`, and let an explicit `[data-theme]`
attribute win over both. Swap `<meta name="theme-color">` at runtime when the
theme changes, or the status bar stays the wrong colour — a very visible seam in
standalone mode:

```js
document.querySelector('meta[name="theme-color"]')
  ?.setAttribute('content', isDark ? '#0F172A' : '#FFFFFF')
```
