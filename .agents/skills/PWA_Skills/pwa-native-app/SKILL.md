---
name: pwa-native-app
description: Build or upgrade a Progressive Web App that installs and feels like a native mobile app — distinctive design system, app shell, gestures, sheets, transitions, offline-first data, install/update UX, push, iOS/Android quirks, and store packaging with PWABuilder. Use for any PWA, service worker, manifest, offline, installable, "add to home screen", or "make my web app feel native" request.
---

# PWA Native App

Build PWAs that people mistake for native apps: they launch instantly from the home screen, never show a dinosaur, respond to touch like UIKit/Material, survive bad networks, update gracefully, and ship to Google Play, Microsoft Store, the App Store and Store.app from one codebase.

**Platform truth as of late 2026. Re-verify anything marked ⟳ with a quick search before promising it to a client.**

---

## 0. Principles (read first)

1. **Behaviour before appearance.** Native feel comes from instant response, correct gestures, back behaviour, keyboard handling and zero layout jank. Good colours on a janky shell still feel like a website.
2. **Offline is architecture, not a feature.** Decide up front what must work with no network: the shell, cached reads and queued writes. Bolted-on offline fails.
3. **Progressive enhancement, always.** Feature-detect every capability, and never sniff the user agent to decide whether an API exists. The app must work in a plain browser tab and get better when installed.
4. **Respect the OS.** Use native scrolling and the system font for body text. Leave the back gesture, text selection in content, and accessibility settings to the OS. Brand character comes from colour, display type, iconography and motion.
5. **One codebase, adaptive details.** Use one layout system. Adapt small things per platform (back chevron, sheet style, haptics) and per form factor (tab bar → nav rail ≥ 840px).
6. **Never trap users on stale code.** Every caching decision needs an update path.

---

## 1. Workflow

Work through these phases in order. Each phase has a "done when" check.

| # | Phase | Done when |
|---|-------|-----------|
| 1 | **Discover**: app type, users, offline needs, target stores, stack, brand | You can state: shell type (SPA/MPA), offline scope, push yes/no, stores |
| 2 | **Design direction & tokens** (§3) | Tokens for light and dark exist, aesthetic is named, type pair chosen |
| 3 | **Scaffold** with the right toolchain (§2) | `build` produces a manifest and `sw.js` |
| 4 | **App shell + native UX layer** (§4) | Safe areas, tab bar/rail, sheets, transitions, keyboard all handled |
| 5 | **Manifest, icons, splash** (§5) | `pwa-check` shows 0 errors for the manifest |
| 6 | **Service worker & caching** (§6) | Offline reload and deep links work; update prompt works |
| 7 | **Offline data & sync** (§7) | Writes made offline are queued and replayed; pending count is visible |
| 8 | **Install & update UX** (§8) | Custom install CTA on all platforms; "Reload to update" toast |
| 9 | **Capabilities** (§9): push, badge, share, files, shortcuts… | Each one is feature-detected with a fallback |
| 10 | **Performance & a11y** (§10) | Core Web Vitals budget met on a mid-tier Android; WCAG AA |
| 11 | **Verify** (§11) | Automated checks pass, plus a real-device checklist on iOS and Android |
| 12 | **Package & publish** (§12) | Store packages built, `assetlinks.json` live, listings ready |

Ask at most 2–3 questions up front (stores? push? existing stack/brand?). Otherwise pick sensible defaults and state them.

If this skill's folder contains `templates/` and `scripts/`, copy from them. Otherwise use the inline code below, which is the same material in condensed form.

---

## 2. Stack choice (pick one, don't mix SW generators)

| Situation | Use | Notes |
|---|---|---|
| React / Vue / Svelte / Solid / Lit / vanilla on **Vite** | `vite-plugin-pwa` 2.x + Workbox 7.4 | Default choice. Use `strategies:'injectManifest'` once you need push, sync or share target. Add `@vite-pwa/assets-generator` for icons |
| SvelteKit | `@vite-pwa/sveltekit` | Or SvelteKit's native `src/service-worker.ts` for tiny apps |
| Nuxt | `@vite-pwa/nuxt` (or `@serwist/nuxt`) | |
| Astro | `@vite-pwa/astro` | MPA: use network-first navigations |
| **Next.js** (App Router) | **Serwist**: `@serwist/next` (webpack build: `next build --webpack`) or `@serwist/turbopack` | **Never `next-pwa`** (abandoned in 2022). `@ducanh2912/next-pwa` has been superseded by Serwist |
| Angular | `@angular/pwa` (ngsw) | Configure `ngsw-config.json` dataGroups |
| No framework, want the PWABuilder path | `npx @pwabuilder/cli create my-app` (Lit + Shoelace + Vite + Workbox) | Opinionated, used by the PWABuilder team. `pwa start`, `pwa build` |
| Existing site, minimal change | PWABuilder Studio (VS Code) or hand-written manifest + Workbox `generateSW` | |
| Needs deep native APIs (NFC on iOS, HealthKit, BLE on iOS, background GPS) | Capacitor around the same web code | A PWA can't do these on iOS. Say so early |

**Serwist / Next.js minimum (verified example):**
```js
// next.config.mjs
import withSerwistInit from "@serwist/next";
const withSerwist = withSerwistInit({ swSrc: "app/sw.ts", swDest: "public/sw.js", cacheOnNavigation: true,
  additionalPrecacheEntries: [{ url: "/~offline", revision: crypto.randomUUID() }] });
export default withSerwist({ reactStrictMode: true });
```
```ts
// app/sw.ts
import { defaultCache } from "@serwist/next/worker";
import { Serwist, type PrecacheEntry, type SerwistGlobalConfig } from "serwist";
declare global { interface WorkerGlobalScope extends SerwistGlobalConfig { __SW_MANIFEST: (PrecacheEntry | string)[] | undefined } }
declare const self: ServiceWorkerGlobalScope;
new Serwist({ precacheEntries: self.__SW_MANIFEST, skipWaiting: true, clientsClaim: true, navigationPreload: true,
  runtimeCaching: defaultCache,
  fallbacks: { entries: [{ url: "/~offline", matcher: ({ request }) => request.destination === "document" }] },
}).addEventListeners();
```
Add `app/manifest.ts` (`MetadataRoute.Manifest`), gitignore `public/sw*`, and set tsconfig `lib: ["dom","dom.iterable","esnext","webworker"]`.

**vite-plugin-pwa core config (tested, builds clean):**
```ts
VitePWA({
  strategies: 'injectManifest', srcDir: 'src', filename: 'sw.ts',
  registerType: 'prompt',            // user decides when to reload — never yank the page
  injectRegister: false,             // register yourself (update UX)
  pwaAssets: { config: true },       // pwa-assets.config.ts → icons + apple-touch-icon
  injectManifest: { globPatterns: ['**/*.{js,css,html,svg,png,webp,avif,woff2,ico}'] },
  devOptions: { enabled: true, type: 'module', navigateFallback: 'index.html' },
  manifest: { /* §5 */ },
})
```
TS: `"types": ["vite/client","vite-plugin-pwa/client"]` and `"lib": ["ES2022","DOM","DOM.Iterable","WebWorker"]`.

---

## 3. Design system: make it distinctive and native

### 3.1 Pick a direction before you write code
State in one line: *purpose → audience → feeling → the one memorable thing*. Examples: "field-instrument dark UI with ember accent", "editorial calm with oversized serif numerals", "playful rounded toybox". Commit to it. Avoid the "AI default" look: purple-blue gradient on white, Inter everywhere, identical 8px radii, centred hero plus three cards, grey shadows on everything.

### 3.2 Typography
- **Body/UI = system stack.** It's instant, works offline, matches the OS, and has no FOUT:
  `system-ui, -apple-system, "Segoe UI Variable Text", "Segoe UI", Roboto, "Noto Sans", "Noto Sans Arabic", sans-serif`
- **Character = display face** for titles and numbers: `ui-rounded` (SF Pro Rounded on Apple, free), or one self-hosted variable woff2 (Fraunces, Instrument Serif, Space Grotesk, Bricolage Grotesque, IBM Plex Sans Arabic for Arabic). Precache it, `font-display: swap`, subset it, preload only that one file.
- Type scale ~1.2–1.25. Large titles 28–40px with tight tracking (−0.02em) and `text-wrap: balance`. Body 16–17px. Captions 12–13px. Never go below 11px.

### 3.3 Colour
- Tokens as CSS custom properties in **OKLCH** (perceptually even ramps). Light and dark sets via `prefers-color-scheme`, and optionally an in-app override using `:root[data-theme]`.
- One dominant neutral family, one sharp accent, semantic ok/warn/danger. Text contrast ≥ 4.5:1 and UI parts ≥ 3:1.
- `accent-color: var(--primary)` themes native checkboxes, radios, range inputs and progress bars.
- **theme-color must be solid** (no gradients or alpha). Ship one per scheme: `<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0f1720">`. Make the manifest `theme_color`/`background_color` match your launch screen.

### 3.4 Shape, depth, material
- Radii by size: chips/inputs 10, cards 16, sheets 24–28, pills 999. Use hairline separators (`0.5px`) on iOS-like lists.
- Translucent bars ("Liquid Glass" on iOS 26, M3 surfaces): `background: color-mix(in oklab, var(--surface) 80%, transparent); backdrop-filter: saturate(180%) blur(20px)` plus `-webkit-` prefix. Only use this on the bars and sheets, not on scrolling content, because it costs GPU. Fall back under `@media (prefers-reduced-transparency: reduce)`.

### 3.5 Motion (it decides whether the app feels native)
- Durations: 100–150ms for press feedback, 200–250ms for small moves, 300–400ms for page and sheet transitions. Use decelerating easing such as `cubic-bezier(.05,.7,.1,1)` (M3 emphasized). For springs use CSS `linear()` easing with a cubic-bezier fallback.
- Animate only `transform`, `opacity`, `translate`, `scale` and `filter`. Never animate layout properties.
- Every animation must be interruptible and must honour `prefers-reduced-motion`. Under reduced motion, crossfade or cut instead of sliding or scaling.
- Use motion where it carries meaning: page push/pop, sheet rise, list insert/remove, press scale 0.97, tab icon squish. Don't add scattered decorative animation.

### 3.6 Platform-adaptive touches (via `data-os` on `<html>`)
| Element | iOS | Android / Material |
|---|---|---|
| Back | chevron "‹ Title", left | arrow ←, left |
| Primary action | nav-bar text button | FAB / filled button |
| Modals | bottom sheet with grabber, drag to dismiss | bottom sheet or full-screen dialog |
| Lists | inset grouped, hairlines, chevrons | full-bleed, ripple/state layer |
| Haptics | light tick on toggles/selection | `navigator.vibrate(5–10)` |
Keep everything else identical. Over-adapting doubles the QA load.

### 3.7 RTL and i18n (Arabic and others)
Use logical properties throughout (`margin-inline-start`, `inset-inline-end`, `padding-block`). Set `dir` and `lang` on `<html>` and in the manifest. Mirror directional icons and slide transitions with `transform: scaleX(var(--dir-x))` where `:root:dir(rtl){--dir-x:-1}`. Don't mirror media controls or logos.

---

## 4. App shell and native UX layer

### 4.1 `<head>` (complete)
```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<meta name="theme-color" content="#f4f1ea" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1720" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<meta name="apple-mobile-web-app-title" content="Short Name">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"> <!-- content under status bar; pad with safe-area -->
<meta name="format-detection" content="telephone=no">
<link rel="icon" href="/favicon.ico" sizes="48x48"><link rel="icon" href="/logo.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png"> <!-- opaque bg, no transparency -->
<link rel="manifest" href="/manifest.webmanifest">
<style>html{background:#f4f1ea}@media (prefers-color-scheme:dark){html{background:#0f1720}}</style> <!-- no white flash -->
```
Never use `user-scalable=no` or `maximum-scale=1`. They break accessibility. Stop iOS focus-zoom by giving inputs a 16px font instead.

### 4.2 Base behaviour CSS (the native feel)
```css
html { -webkit-text-size-adjust:100%; text-size-adjust:100%; scroll-padding-top: calc(var(--appbar-h) + env(safe-area-inset-top)); }
body { min-height:100dvh; margin:0; -webkit-tap-highlight-color:transparent; overscroll-behavior-y:none; -webkit-font-smoothing:antialiased; }
button, .tab, .row, .appbar, .tabbar, [role=button] {            /* chrome is not text */
  -webkit-user-select:none; user-select:none; -webkit-touch-callout:none; touch-action:manipulation; }
input, textarea, select { font-size:max(16px,1rem); }             /* iOS won't zoom */
:focus-visible { outline:2.5px solid var(--primary); outline-offset:2px; }
.pressable { transition: transform 120ms cubic-bezier(.2,.8,.2,1); } .pressable:active { transform: scale(.97); }
@media (hover:hover) and (pointer:fine) { .row:hover { background: var(--surface-2); } }  /* no sticky hover on touch */
html:has(dialog[open]) { overflow:hidden; }                       /* scroll lock behind modals */
```
- **Viewport units:** `100dvh` for full-height screens and `100svh` for heroes that mustn't jump. Never use bare `100vh` on mobile.
- **Safe areas:** expose `--safe-t/r/b/l: env(safe-area-inset-*, 0px)` and pad the app bar top, tab bar bottom, and both sides in landscape (`max(16px, var(--safe-l))`).
- **Let the document scroll** (not an inner `div`) on phones. You keep native momentum, iOS tap-status-bar-to-top and correct keyboard behaviour. Use `position: sticky` for the app bar and `fixed` for the tab bar. Give inner scrollers (sheets, side panels) `overscroll-behavior: contain`.
- Leave selection enabled in content (articles, messages, IDs). Disable it only on chrome.

### 4.3 Shell layout
- **App bar:** sticky, translucent, 52px plus `--safe-t`, large title on top-level screens. In standalone mode there is **no browser back button**, so every non-root screen needs an in-app back button (show it via `@media (display-mode: standalone)` or `data-standalone`).
- **Tab bar** (3–5 destinations): fixed bottom, 56–64px plus `--safe-b`, icon + label, `aria-current="page"`, filled icon when active. Each tab keeps its own scroll position and navigation stack. Hide it while the keyboard is open.
- **≥ 840px:** the tab bar becomes a **nav rail** (88px), and ≥ 1200px a sidebar. Centre the content with `max-inline-size` (~760px for reading, wider for dashboards).
- **FAB:** bottom end, above the tab bar, 56px.
- **Toasts/snackbars:** above the tab bar, `role="status"`, one action max ("Undo", "Reload").
- **Desktop installed:** `display_override: ["window-controls-overlay","standalone"]`. Put the app bar in `env(titlebar-area-x/y/width/height)` with `app-region: drag` (buttons get `no-drag`). Update `<title>` per route because it becomes the window title.

### 4.4 Navigation and page transitions
- **MPA / SSR:** add `@view-transition { navigation: auto; }` (Chrome/Edge 126+, Safari 18.2+). Give persistent chrome a `view-transition-name` (`appbar`, `tabbar`) so it stays still while `main` animates.
- **SPA:** use the **Navigation API** (Baseline since early 2026 ⟳) + `document.startViewTransition()`, tagging the transition type `forward`/`back` so CSS can slide in the right direction:
```ts
navigation.addEventListener('navigate', (e) => {
  if (!e.canIntercept || e.hashChange || e.downloadRequest || e.formData) return;
  const back = e.navigationType === 'traverse' && e.destination.index < navigation.currentEntry.index;
  e.intercept({ scroll: 'after-transition', handler: () => {
    const vt = document.startViewTransition?.(() => render(new URL(e.destination.url)));
    vt?.types?.add(back ? 'back' : 'forward');           // types: Chrome 125+/Safari 18.2+
    return vt?.finished ?? render(new URL(e.destination.url));
  }});
});
```
```css
html:active-view-transition-type(forward)::view-transition-old(main){animation:vt-out-start .34s var(--ease-emph)}
html:active-view-transition-type(forward)::view-transition-new(main){animation:vt-in-end .34s var(--ease-emph)}
/* back = mirror; keyframes translate by calc(var(--dir-x)*±30%/100%) so RTL flips automatically */
```
  Fall back to click interception + `popstate` when `window.navigation` is missing. Framework routers (React Router, Vue Router, SvelteKit, Next) all have view-transition hooks, so use those.
- **Shared-element transitions:** set the same `view-transition-name` on the list thumbnail and the detail hero. Names must be unique per page.
- **Back closes one layer.** Opening a sheet, dialog or full-screen viewer must `history.pushState`, and closing it via the UI calls `history.back()`. Then the Android back gesture, Esc, and your ✕ button all share one path. A destructive confirm should consume back without navigating.
- **Speculative loading (Chromium):** `<script type="speculationrules">{"prefetch":[{"where":{"href_matches":"/*"},"eagerness":"moderate"}]}</script>` for near-instant MPA navigations.

### 4.5 Sheets, dialogs, popovers (native elements first)
- Use `<dialog>` + `showModal()` for sheets and alerts (focus trap, Esc and inert background for free). Add `closedby="any"` for light-dismiss. Use `popover` for menus and tooltips, with **anchor positioning** for placement (Chrome 125+, Safari 26) and an `@supports` fallback. Invoker commands (`commandfor`/`command`) give you declarative open/close.
- Entry/exit animation with no JS:
```css
dialog.sheet{position:fixed;inset:auto 0 0 0;margin:0 auto;max-inline-size:640px;border:0;border-radius:26px 26px 0 0;
  padding-bottom:calc(20px + env(safe-area-inset-bottom));translate:0 100%;
  transition:translate .34s var(--ease-emph),overlay .34s allow-discrete,display .34s allow-discrete}
dialog.sheet[open]{translate:0 0} @starting-style{dialog.sheet[open]{translate:0 100%}}
dialog.sheet::backdrop{background:#0000;transition:background-color .34s,overlay .34s allow-discrete,display .34s allow-discrete}
dialog.sheet[open]::backdrop{background:#0006} @starting-style{dialog.sheet[open]::backdrop{background:#0000}}
```
- **Drag to dismiss:** pointer events on the grabber. While dragging set `translate: 0 ${dy}px` with transitions disabled. On release, close if `dy > 30%` of the height or velocity > 0.6 px/ms, otherwise snap back. (`templates/src/pwa/sheet.ts`.)

### 4.6 Gestures and feedback
- Use native scroll, `scroll-snap-type: x mandatory` for carousels and pagers, and `overscroll-behavior` to stop scroll chaining. Don't use smooth-scroll hijack libraries.
- **Custom pull-to-refresh:** only on feed-like screens. Use `overscroll-behavior-y: contain` on the scroller, track `touchmove` while `scrollTop===0`, add resistance (`dy*0.4`), trigger at about 70px and show a spinner, then haptic + refresh.
- **Swipe actions on rows:** pointer events with `touch-action: pan-y` on the row, reveal actions behind it, snap open or closed. Always provide a non-gesture alternative (a menu).
- **Haptics:** `navigator.vibrate(8)` on Android/Chromium. **iOS has no Vibration API.** Toggling a hidden `<input type="checkbox" switch>` through its `<label>` triggers the system haptic on iOS 18+ Safari. It's unofficial, so call it only inside user gestures and treat it as a bonus (`haptic()` in `platform.ts`, or the `web-haptics` / `ios-haptics` packages).
- **Perceived speed:** use optimistic UI (apply first, reconcile later), show skeletons shaped like the real content instead of spinners, and preload the next screen's data on `pointerdown`.
- **Touch targets:** ≥ 44×44pt (iOS) / 48×48dp (Android), with ≥ 8px between targets.

### 4.7 Keyboard
- `interactive-widget=resizes-content` makes Chromium (108+) and Firefox (132+) shrink the layout viewport, so fixed footers rise above the keyboard. **Safari ignores it.** On iOS, read `visualViewport` and set `--kb-inset` plus `data-keyboard="open"` (`trackVirtualKeyboard()` in `platform.ts`). Use that to hide the tab bar and pad sheets.
- Always set `inputmode`, `enterkeyhint`, `autocomplete` (`one-time-code`, `email`, `tel`, `street-address`) and correct `type` attributes. Use `autocapitalize`/`spellcheck` deliberately.
- Chat composers: sticky bottom, `padding-bottom: max(var(--safe-b), var(--kb-inset))`, auto-growing textarea (`field-sizing: content` where supported, with a JS fallback).

### 4.8 Detect the install context
```ts
const standalone = ['standalone','fullscreen','minimal-ui','window-controls-overlay']
  .some(m => matchMedia(`(display-mode: ${m})`).matches) || (navigator as any).standalone === true;
// Store wrappers (PWABuilder): document.referrer 'android-app://…' (Play TWA),
// 'app-info://platform/microsoft-store' (MS Store), cookie 'app-platform=iOS App Store' (iOS shell)
```
Use CSS `@media (display-mode: browser)` to show "Install"/web-only affordances and `(display-mode: standalone)` for app-only chrome. Open external links with `target="_blank" rel="noopener"`. Out-of-scope navigation leaves the app on iOS.

---

## 5. Manifest, icons, splash

### 5.1 Recommended manifest
```json
{
  "id": "/",
  "name": "Fieldnote — Field Work Companion",
  "short_name": "Fieldnote",
  "description": "Capture site visits, photos and tasks — online or off.",
  "lang": "en", "dir": "auto",
  "start_url": "/?source=pwa",
  "scope": "/",
  "display": "standalone",
  "display_override": ["window-controls-overlay", "standalone"],
  "orientation": "any",
  "theme_color": "#0f1720",
  "background_color": "#0f1720",
  "categories": ["productivity", "business"],
  "launch_handler": { "client_mode": ["navigate-existing", "auto"] },
  "icons": [
    { "src": "/pwa-192x192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "/pwa-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "/maskable-icon-512x512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" },
    { "src": "/monochrome-512.png", "sizes": "512x512", "type": "image/png", "purpose": "monochrome" }
  ],
  "screenshots": [
    { "src": "/screenshots/narrow-1.png", "sizes": "1080x1920", "type": "image/png", "form_factor": "narrow", "label": "Today view" },
    { "src": "/screenshots/wide-1.png", "sizes": "1920x1080", "type": "image/png", "form_factor": "wide", "label": "Desktop dashboard" }
  ],
  "shortcuts": [
    { "name": "New visit", "short_name": "Visit", "url": "/?action=new-visit&source=shortcut",
      "icons": [{ "src": "/pwa-96x96.png", "sizes": "96x96", "type": "image/png" }] }
  ],
  "share_target": { "action": "/share-target", "method": "POST", "enctype": "multipart/form-data",
    "params": { "title": "title", "text": "text", "url": "url", "files": [{ "name": "media", "accept": ["image/*"] }] } }
}
```
Optional members, used when they fit: `file_handlers` (+ `launchQueue`), `protocol_handlers` (`web+app`), `edge_side_panel`, `scope_extensions` (+ `/.well-known/web-app-origin-association`), `related_applications` + `prefer_related_applications`, `iarc_rating_id`, `note_taking`.

### 5.2 Validation rules (PWABuilder + browsers). Breaking one blocks packaging or install
- `name` ≥ 2 chars. `short_name` **required for PWABuilder**, 3–12 chars.
- `start_url` must sit inside `scope`. Set a stable **`id`**: it keeps install identity if `start_url` changes and is required by `navigator.install()`/`<install>` for the current app.
- Icons: at least one `purpose:"any"` (or no purpose) ≥ **512×512** and one ≥ 192. **Maskable must be a separate entry. Never use `"any maskable"`** (PWABuilder rejects it, and maskable art looks wrong as "any"). Maskable art keeps key content inside the central 80% circle (≈10% padding per side; 20–30% padding feels safer).
- Shortcut icons need a 96×96 entry.
- Colours: hex. `"none"` breaks packaging. No empty nested arrays (`"icons": [[]]` → "Failed to download icon 404").
- Files must exist with the declared sizes and MIME types (bad MIME → "Could not find MIME for Buffer").
- Serve the manifest as `application/manifest+json`, ideally named `manifest.webmanifest` or `manifest.json` at the root.
- Screenshots: include both `narrow` (portrait, mobile) and `wide` (landscape, desktop) with `label`. They unlock Chrome's rich install sheet and feed store listings.

### 5.3 Icon and splash generation
- `@vite-pwa/assets-generator` with `minimal2023Preset` from one square SVG generates pwa-64/192/512, maskable-512, apple-touch-icon-180 and favicon. Add 96 for shortcuts.
- PWABuilder's image generator (report card → Manifest → Icons) gives per-platform zips for Windows, Android and iOS.
- **Monochrome icon** (white silhouette on transparent) for Android themed icons and the notification badge.
- **iOS:** `apple-touch-icon` 180×180, opaque. Since iOS/Safari 26, SVG and data-URL icons work and manifest icons are honoured ⟳. **Splash:** iOS shows a blank `background_color` screen unless you ship `apple-touch-startup-image` links per device size and orientation. Generate them with `npx pwa-asset-generator logo.svg public/splash --splash-only --background "#0f1720"`. Data/blob URLs for splash broke in iOS 17.6+, so use real PNG files. Splash images are cached hard; bust them by changing the file name.

---

## 6. Service worker and caching

### 6.1 Strategy per resource
| Resource | Strategy | Notes |
|---|---|---|
| Hashed build assets (JS/CSS/fonts/icons) | **Precache** | Revisioned by the build. `cleanupOutdatedCaches()` |
| App shell HTML (SPA) | **Precache** + `NavigationRoute(createHandlerBoundToURL('/index.html'))` | Instant launch. Denylist `/api`, files, POST targets |
| HTML pages (MPA/SSR) | **NetworkFirst**, `networkTimeoutSeconds: 3`, + **navigation preload** | Offline page fallback |
| Images / avatars / media thumbs | **CacheFirst** + `ExpirationPlugin({maxEntries, maxAgeSeconds, purgeOnQuotaError:true})` | `CacheableResponsePlugin({statuses:[0,200]})` for cross-origin |
| Google Fonts CSS / files | SWR / CacheFirst 1y | Better: self-host |
| API GET (lists, details) | **NetworkFirst** 3–5s timeout, or **SWR** for tolerant data | Short max-age, `statuses:[200]` |
| Auth, session, payments, POST/PUT/DELETE | **NetworkOnly** | Never cache. Writes go through the outbox (§7) |
| Large media / video | Don't precache. Use `RangeRequestsPlugin` if you cache it | |

### 6.2 `src/sw.ts` (condensed from the tested template)
```ts
/// <reference lib="webworker" />
import { cleanupOutdatedCaches, createHandlerBoundToURL, matchPrecache, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute, setCatchHandler } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import { clientsClaim } from 'workbox-core';
declare let self: ServiceWorkerGlobalScope & { __WB_MANIFEST: any };

self.addEventListener('message', (e) => { if (e.data?.type === 'SKIP_WAITING') self.skipWaiting(); });
clientsClaim(); cleanupOutdatedCaches(); precacheAndRoute(self.__WB_MANIFEST);

registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), { denylist: [/^\/api\//, /^\/share-target/, /\/[^/?]+\.[^/]+$/] }));
registerRoute(({ request }) => request.destination === 'image', new CacheFirst({ cacheName: 'images', plugins: [
  new CacheableResponsePlugin({ statuses: [0, 200] }), new ExpirationPlugin({ maxEntries: 250, maxAgeSeconds: 2592000, purgeOnQuotaError: true })] }));
registerRoute(({ url, request, sameOrigin }) => sameOrigin && request.method === 'GET' && url.pathname.startsWith('/api/') && !/^\/api\/(auth|session)/.test(url.pathname),
  new NetworkFirst({ cacheName: 'api', networkTimeoutSeconds: 4, plugins: [new CacheableResponsePlugin({ statuses: [200] }), new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 604800 })] }));
registerRoute(({ request, sameOrigin }) => sameOrigin && ['style','script','worker'].includes(request.destination), new StaleWhileRevalidate({ cacheName: 'assets' }));
setCatchHandler(async ({ request }) => request.destination === 'document' ? (await matchPrecache('/offline.html')) ?? Response.error() : Response.error());
```
The full template adds: MPA mode with navigation preload, share-target POST handling, Background Sync, push/notificationclick/pushsubscriptionchange.

### 6.3 Rules that prevent production incidents
- Serve `sw.js` from the **root** (scope `/`) with `Cache-Control: no-cache`. **Never rename it or change its URL** (old clients would keep the old one forever).
- Never CacheFirst un-hashed URLs or HTML. Never cache responses that carry `Set-Cookie` or personal data under shared keys. Clear caches and IndexedDB on logout.
- Opaque (status 0) responses count ~7MB each toward quota in Chromium, so cap them with `maxEntries`.
- Keep the precache lean (shell + critical routes, about < 2–3MB). Runtime-cache the rest.
- **Kill switch:** if a bad SW ships, deploy `selfDestroying: true` (vite-plugin-pwa) or a no-op SW that calls `self.registration.unregister()` + `caches.keys()→delete` and posts a reload. Send `Clear-Site-Data: "cache", "storage"` only as a last resort.
- Dev: SW behaviour is only trustworthy in `build && preview`. In DevTools use **Update on reload** and **Bypass for network** while developing.

---

## 7. Offline data and sync

- **Storage:** IndexedDB via `idb` (tiny) or Dexie (queries, live queries). Cache Storage is for HTTP responses only. `localStorage` is for tiny prefs only (synchronous and limited, and it can throw, so wrap it in try/catch).
- **Read path (local-first):** render from IndexedDB immediately, then fetch and reconcile. Show "Updated 5 min ago" when stale.
- **Write path (outbox):** write locally → enqueue `{id: uuid, url, method, body}` → flush when online. The **server must dedupe on the idempotency key**. Send in order. 5xx/408/429 = retry with backoff. Other 4xx = park the item for user review, don't loop.
- **Sync triggers:** Background Sync `registration.sync.register('outbox-sync')` (Chromium only) **plus** fallbacks for iOS/Firefox: `online` event, `visibilitychange → visible`, and app start. The SW and the page import the same `outbox.ts`.
- **UI:** an offline pill, a "3 changes waiting to sync" badge, per-item pending/failed state with Retry, and toasts like "Saved offline · will sync".
- **Conflicts:** pick a policy per entity: last-write-wins (with `updatedAt`), field-level merge, or a server-authoritative rejection shown to the user. CRDTs (Yjs/Automerge) are for collaborative text and boards.
- **Quota and eviction:** call `navigator.storage.persist()` after install or meaningful use (granted heuristically, and installed apps usually qualify). Check `navigator.storage.estimate()`. Safari 17+ gives browser and home-screen apps up to ~60% of disk per origin, but data is still **best-effort** and can be evicted after a period of non-use. Design every local store so it can be rebuilt from the server.
- **Periodic Background Sync** (Chromium, installed apps, engagement-gated): use it for content freshness, not for correctness.

---

## 8. Install and update UX

### 8.1 Installability reality
| Platform | How users install | What you control |
|---|---|---|
| Chrome/Edge desktop & Android | Omnibox icon / menu / your button via `beforeinstallprompt` | Manifest (name, icons, start_url, display) + HTTPS. Since Chrome 108 (mobile) / 112 (desktop) the menu install no longer needs a fetch handler, but the **automatic prompt still wants a SW with a fetch handler** |
| Chromium, new (⟳ trial/rollout) | `navigator.install()` from a click, or the declarative `<install>` element (Chrome/Edge 148–153 origin trial) | Requires manifest `id`. Feature-detect `'install' in navigator` / `window.HTMLInstallElement` |
| iOS/iPadOS Safari (and other iOS browsers since 16.4) | Share ▸ Add to Home Screen. **iOS 26: every site opens as a web app by default** ("Open as Web App" toggle) | No prompt API. Show your own instruction sheet |
| macOS Safari 17+ | File/Share ▸ Add to Dock | Instruction sheet |
| Firefox Android | Menu ▸ Install / Add to Home screen | Instruction sheet |
| Firefox desktop | Windows only since 143 ("taskbar tabs"), not the full spec | Treat as a browser tab |
| In-app browsers (Instagram, FB, TikTok, LINE) | Can't install | "Open in Safari/Chrome" banner |

### 8.2 Install CTA pattern
- Capture `beforeinstallprompt` (`preventDefault()`), and **don't prompt on first visit**. Offer install after value is shown (a completed key action, or 3+ visits). Put it in context ("Install to get offline access and reminders"), in a header button, a settings row, or a post-success sheet. Snooze for 14 days after a dismissal.
- `install()` order: deferred BIP → `navigator.install()` → manual sheet (iOS/mac/Firefox) → "open in browser". Both APIs need user activation, so call them only from a click. (`templates/src/pwa/install.ts`.)
- The manual iOS sheet should show the real Share glyph, 3 steps, and a screenshot or animation. Detect iPadOS as `MacIntel && maxTouchPoints > 1`.
- Ready-made option: `@khmyznikov/pwa-install` web component (`<pwa-install manifest-url="/manifest.webmanifest">`). It handles iOS/macOS instructions, in-app browsers, rich screenshots, BIP and the Web Install API.
- Track `appinstalled`, `start_url ?source=pwa`, and `getInstalledRelatedApps()` (needs `related_applications` with `platform:"webapp"`).

### 8.3 Update UX
- `registerType: 'prompt'`. When a new SW is waiting, show a toast "New version ready · Reload". The action calls `updateSW(true)` (posts SKIP_WAITING, then reloads on `controllerchange`). Never auto-reload while a form is dirty.
- Installed apps stay open for days, so call `registration.update()` on `visibilitychange → visible` and hourly. Skip the call when offline.
- Use `autoUpdate` only for content sites with no in-progress user state.
- Store wrappers (TWA, MSIX, iOS shell) load your live site, so **web deploys update every store install**. Resubmit only when the manifest identity, icons, or native shell change.

---

## 9. Capabilities catalogue (always feature-detect)

| Capability | Support (late 2026 ⟳) | Key code / note |
|---|---|---|
| **Web Push** | Chromium, Firefox, Safari macOS 16+, **iOS/iPadOS 16.4+ only when installed to the Home Screen** | Ask via a button (never on load). VAPID (`npx web-push generate-vapid-keys`), `pushManager.subscribe({userVisibleOnly:true, applicationServerKey})`, store the subscription server-side, delete it on 404/410. **Always show a notification for every push**, or the subscription gets revoked |
| **Declarative Web Push** | Safari iOS/iPadOS 18.4+, macOS 15.5+ | Send one JSON shape everywhere: `{"web_push":8030,"notification":{"title":"…","body":"…","navigate":"https://app/x","app_badge":"3"}}`. Safari displays it without a SW. Your SW `push` handler should parse the same shape for Chromium/Firefox (template does). `window.pushManager` lets you subscribe without a SW on Safari |
| Badging | Chromium desktop installed, Safari macOS/iOS 16.4+ installed (with notification permission) | `navigator.setAppBadge?.(n)` / `clearAppBadge()`, also callable from the SW on push |
| Web Share (send) | Mobile everywhere, Safari, Chromium desktop on Win/ChromeOS/mac | `navigator.canShare?.({files})` then `navigator.share({...})` inside a gesture |
| Share Target (receive) | Android Chromium installed, ChromeOS, Windows | Manifest `share_target`. POST multipart handled in the SW → 303 redirect |
| App shortcuts | Android, Windows/macOS Chromium, iOS no | Manifest `shortcuts` (≤ 4 recommended, 96px icons) |
| File Handling | Chromium desktop installed | `file_handlers` + `launchQueue.setConsumer(p => p.files…)` |
| File System Access | Chromium desktop. Safari 26 has WritableStream on OPFS | Fall back to `<input type=file>` + download |
| Protocol handlers | Chromium desktop | `protocol_handlers: [{protocol:"web+app", url:"/open?u=%s"}]` |
| Screen Wake Lock | Chromium, Safari 16.4+ (installed iOS works on modern iOS ⟳) | `navigator.wakeLock.request('screen')`, re-acquire when the page becomes visible |
| Camera / scanning | Everywhere (`getUserMedia`, `<input type=file accept="image/*" capture>`) | `BarcodeDetector` on Chromium Android/macOS, else ZXing/`zxing-wasm` |
| Geolocation | Everywhere, permission-gated | Ask in context. TWA "location delegation" skips the browser prompt |
| Passkeys / WebAuthn | Everywhere | Best login for installed apps. `autocomplete="username webauthn"` conditional UI |
| WebOTP / SMS autofill | Chromium Android API. iOS via `autocomplete="one-time-code"` | |
| Contact Picker | Chromium Android | `navigator.contacts.select(['name','tel'])` |
| Payment Request / Digital Goods | Payment Request widely supported. Digital Goods = Play Billing inside a TWA | Play requires Play Billing for digital goods in the Play build |
| Vibration | Android Chromium/Firefox, **not iOS** | iOS switch-haptic trick (§4.6) |
| Orientation lock | Android, fullscreen only | Design responsive instead |
| Background Sync / Periodic Sync | Chromium only | Fallback triggers (§7) |
| Window Controls Overlay, tabbed mode, side panel | Chromium desktop | `display_override` |
| Web Bluetooth / USB / Serial / NFC | Chromium (NFC Android only), **none on iOS** | If it's core on iOS → Capacitor |

---

## 10. Performance and accessibility budgets

- **Core Web Vitals on a mid-tier Android over 4G:** LCP < 2.5s, INP < 200ms, CLS < 0.1. Repeat visits served from the SW should paint the shell in < 1s.
- Initial JS ≤ ~150–170KB gzip. Split code by route, lazy-load heavy widgets (charts, editors, maps), and move heavy work to Web Workers.
- Images: AVIF/WebP, `srcset`/`sizes`, explicit `width`/`height` or `aspect-ratio`, `loading="lazy"` below the fold, `fetchpriority="high"` on the LCP image.
- Long lists: virtualise, or use `content-visibility: auto; contain-intrinsic-size: auto 72px`.
- Fonts: system stack plus ≤ 1 preloaded woff2.
- **A11y:** semantic landmarks, focus management on route change (move focus to `<main>` or `<h1>`), `aria-live` for toasts and sync status, visible focus, reduced motion/transparency/contrast media queries, `forced-colors` support, labels on icon buttons, and no zoom blocking.

---

## 11. Verification (Lighthouse no longer has a PWA category; it was removed in v12, 2024)

1. **Automated audit:** `node scripts/pwa-check.mjs dist` (or a deployed URL). It checks the head tags, every manifest rule in §5.2, icons and screenshots on disk with real pixel sizes, SW presence and fetch handling, the offline fallback, and headers in URL mode.
2. **E2E smoke** (Playwright, `scripts/pwa-e2e.mjs`): SW controls the page → offline reload renders the shell → an offline deep link is served by the shell → the offline write is queued → screenshots are generated for the manifest.
3. **DevTools → Application:** Manifest pane (installability errors, computed **App ID**), Service Workers (update and waiting state), Storage quota. Also `chrome://serviceworker-internals` and `chrome://web-app-internals`.
4. **PWABuilder report card** (pwabuilder.com → URL): fix every red item, review yellow ones, and check the App Capabilities card.
5. **Lighthouse** for performance, a11y and best practices.
6. **Real devices (required):**
   - iOS: add to Home Screen. Check the icon, splash, status bar and safe areas in portrait and landscape. Kill the app and relaunch offline. Check the keyboard with chat/forms, push after install, and that the in-app back button exists. Debug with Safari ▸ Develop ▸ [device] ▸ [web app].
   - Android: install via the prompt (rich sheet with screenshots). Check the maskable icon shape, back gesture closing sheets, and offline launch.
   - Desktop: window title per route, WCO title bar, shortcuts on the right-click/jump list.
7. **Testing on a phone over the LAN** needs HTTPS: `npx vite --host` + `mkcert`, or a tunnel (`cloudflared tunnel --url http://localhost:5173`).

---

## 12. Packaging and publishing with PWABuilder

**Prerequisites:** public HTTPS URL, complete manifest (`name`, `short_name` ≥ 3, ≥ 512 "any" icon, `start_url`, `description`), a working SW. Developer accounts: Microsoft ~$19 one-time, Google $25 one-time, Apple $99/year. Flow: pwabuilder.com → enter URL → report card → **Package for stores** → pick a platform → fill options → Download.

### 12.1 Google Play (Trusted Web Activity via Bubblewrap)
- Packages need Android 7.0+ (API 24). Options: package ID (`com.domain.app`), version name + **version code (must increase every upload)**, theme/nav colours (light and dark), icon/maskable/monochrome URLs, splash fade, display (standalone / fullscreen / fullscreen-sticky), **notification delegation** (push without a browser prompt), **location delegation**, **Play Billing** (Digital Goods API), fallback (Custom Tabs or WebView).
- **Signing:** "New" for a first release. **Keep `signing.keystore` + `signing-key-info.txt` forever** (back them up). For updates choose "Use mine" and upload the same key.
- **Digital Asset Links:** upload `assetlinks.json` to `https://<domain>/.well-known/assetlinks.json`, at the **domain root, not the app sub-path**. After the first upload, Play re-signs the app, so copy **Play Console → Setup → App integrity → App signing SHA-256** into `sha256_cert_fingerprints` (keep both fingerprints, comma-separated).
- Address bar still showing? Check, in order: fingerprint missing, file location, **cross-origin redirect** (package the canonical URL you redirect *to*, e.g. `www`), invalid JSON, a cached old file (clear Chrome site data). The "Chrome is in use" banner on first run is normal.
- Play listing: set target audience **13+** (TWAs can't target children). Upload the `.aab`.

### 12.2 Microsoft Store (MSIX)
- Partner Center → Apps and games → New product → **MSIX or PWA app** → reserve a name → **Product identity**: copy **Package ID, Publisher ID, Publisher display name** into PWABuilder. The app name must match the reserved name exactly.
- Upload **both** `.msixbundle` and `.classic.appxbundle`. Restricted-capability warnings (`runFullTrust`) are expected. Review takes 24–48h.
- Extras: `windows-web-app-link` + `uap3:AppUriHandler` for link handling. Rating prompt: `ms-windows-store://review/?ProductId=…`.

### 12.3 Apple App Store (experimental; WKWebView Swift shell)
- Needs a Mac with Xcode (iOS 17+ SDK), or a cloud Mac / CI. Unzip → `cd src && pod install` (`brew install cocoapods`; `pod repo update` if you hit privacy-manifest errors) → open the **`.xcworkspace`** (not .xcodeproj) → run in a simulator.
- Apple Developer → Identifiers: bundle ID **matching PWABuilder's**, with Associated Domains (+ Push if used). Then certificate (CSR via Keychain) → App Store provisioning profile → App Store Connect app record → Xcode signing (Release: Apple Distribution, manual, team, profile) → Product ▸ Archive → Distribute → Upload → submit for review.
- Turn off unused capabilities. **Review risk (Guideline 4.2, minimum functionality):** the app must feel like an app, not a website. Use native-feel navigation, offline behaviour and real value. A thin wrapper of a marketing site gets rejected.
- Push in the shell goes through Firebase Cloud Messaging (uncomment the TODOs in `AppDelegate.swift`, real device only). StoreKit 2 IAP is possible via the PWABuilder ios-pwa-wrap example. You can also enable the Mac App Store listing from the same build.

### 12.4 Others
- **Store.app:** free open web app store. Requires name, short_name, icons, start_url, description. Claim your domain.
- **Meta Quest:** PWABuilder can generate Quest packages.
- **Common PWABuilder errors:** 403 → whitelist UA `PWABuilderHttpAgent` or pause Cloudflare Bot Fight Mode. "unable to verify the first certificate" → incomplete SSL chain (test with SSL Labs). `none` colours, nested empty arrays and bad icon MIME types → fix the manifest.

---

## 13. Anti-patterns (reject these in reviews)

- Prompting for install or notifications on first load, or nagging after a dismissal
- `"purpose": "any maskable"`; a missing 512 icon; a missing `short_name`/`id`
- CacheFirst on HTML or API data; no `ExpirationPlugin`; caching auth or personal responses
- `skipWaiting()` on install with no prompt while users have unsaved state; no update UI at all
- `100vh` layouts, ignoring safe areas, `user-scalable=no`, 14px inputs (iOS zoom)
- Inner `div` scroll containers for whole pages on mobile; scroll-hijack libraries
- No in-app back button in standalone mode; sheets that the back gesture doesn't close
- Spinners everywhere instead of skeletons and optimistic UI; layout-property animations
- Testing only in Chrome desktop. iOS behaviour must be tested on a real iPhone
- Using `next-pwa`, CRA's SW, or Lighthouse PWA scores as a quality bar (all obsolete)
- `navigator.onLine` as the truth (it only means "has a network interface"). Handle fetch failures instead
- Shipping a store wrapper without `assetlinks.json` (address bar), or losing the signing key

---

## 14. Definition of done

- [ ] Design direction named. Light and dark token sets. Display face + system body. AA contrast
- [ ] `<head>` complete (viewport-fit, per-scheme theme-color, apple-touch-icon, manifest)
- [ ] Shell: safe areas, sticky translucent app bar, tab bar → rail ≥ 840px, in-app back in standalone
- [ ] Transitions: view transitions with forward/back direction, persistent chrome, reduced-motion honoured
- [ ] Sheets/dialogs on `<dialog>`, closed by the back gesture, drag to dismiss
- [ ] Keyboard: interactive-widget + iOS `--kb-inset`, correct inputmode/enterkeyhint/autocomplete
- [ ] Manifest passes `pwa-check` with 0 errors (id, short_name, separate maskable, 96 shortcut icons, narrow + wide screenshots)
- [ ] SW: precached shell, per-resource strategies, offline page, no caching of auth, lean precache
- [ ] Offline writes queued with idempotency keys. Pending/failed UI. Fallback sync triggers for iOS
- [ ] Install CTA on Chromium (BIP / `navigator.install`) + iOS/mac/Firefox instructions + in-app-browser notice
- [ ] "Reload to update" prompt + update checks on foreground
- [ ] Push (if used): user-initiated permission, declarative-format payload, notificationclick focuses the existing window, 410 cleanup
- [ ] CWV budget met on a mid-tier Android. A11y checks pass
- [ ] Real-device pass on iOS + Android + desktop
- [ ] Store packages built. `assetlinks.json` (with the Play signing SHA-256) live. Keystore backed up
