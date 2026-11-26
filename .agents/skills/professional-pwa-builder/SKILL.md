---
name: professional-pwa-builder
description: Build a Progressive Web App that is indistinguishable from a native mobile app — full-bleed app shell with safe-area and notch handling, keyboard-aware layout, native motion via the View Transitions API, edge-swipe and gesture navigation, a service-worker update lifecycle that never white-screens, local-first offline data, device capabilities (push, badging, share, biometrics, camera), and packaging for the Play Store and App Store. Framework-agnostic (React, Vue, Svelte, Angular, vanilla). Use for any PWA where the goal is native-grade feel, or when diagnosing why a web app "feels like a website".
---

# Professional PWA Builder

A web app gives itself away in a handful of specific, fixable ways: a visible URL
bar, a grey flash on tap, text that selects when you swipe, a bounce at the top of
a list, a keyboard that covers the field you are typing in, a page that cuts to
the next screen instead of sliding, and a header tucked under the notch. Each has a
known fix. This skill is those fixes, organised by layer, plus the architecture
that makes the app feel instant rather than merely look right.

None of it is framework-specific. Where a framework matters — a Vite plugin, a
router hook — that is called out.

## Start by diagnosing, not building

If a PWA already exists and "feels like a website", find out which layer is
failing before touching code. Almost always it is one or two of these:

| Symptom | Layer | Fix |
|---|---|---|
| URL bar visible when launched from home screen | Manifest | `display: standalone` + iOS meta tags → `references/native-shell.md` |
| Grey/blue flash on tap; long-press shows a menu; text selects while scrolling | CSS normalisation | `references/native-shell.md` |
| Header under the notch; bottom bar under the home indicator | Safe areas | `env(safe-area-inset-*)` → `references/native-shell.md` |
| Keyboard covers the input or the submit button | Viewport | `interactive-widget` + Visual Viewport → `references/native-shell.md` |
| Screens cut instead of sliding | Motion | View Transitions API → `references/motion-and-gestures.md` |
| No way back on iOS standalone | Gestures | Edge-swipe handler → `references/motion-and-gestures.md` |
| Scroll bounces/rubber-bands at the edges | Scroll physics | `overscroll-behavior` → `references/motion-and-gestures.md` |
| White flash on cold start (iOS) | Splash | `apple-touch-startup-image` → `references/native-shell.md` |
| Every screen waits on the network | Architecture | Local-first → `references/offline-and-sync.md` |
| Random white screens after a deploy | SW lifecycle | Waiting worker → `references/offline-and-sync.md` |
| Data disappears after a week (iOS) | Storage | Install + `persist()` → `references/offline-and-sync.md` |

## The five layers

Work them in this order. Each is cheap once the one below it is right, and
expensive to retrofit.

**1. Shell and geometry** — manifest, display mode, iOS meta tags, safe-area
insets, viewport and keyboard, CSS normalisation, splash screens. This is the
layer that makes the app *stop looking like a browser*, and it is perhaps two
hundred lines total. → `references/native-shell.md`

**2. Motion and input** — page transitions with real physics, gesture navigation,
scroll behaviour, touch targets, haptics, 60 fps discipline. This is what makes it
*feel* native rather than merely look native. → `references/motion-and-gestures.md`

**3. Data and offline** — service worker caching tiers, the update lifecycle,
local-first reads, background sync, conflict handling. This is what makes it feel
*instant*, which is the difference users actually notice.
→ `references/offline-and-sync.md`

**4. Capabilities** — push, badging, share, share target, file handling,
biometrics/passkeys, camera, geolocation, and what iOS will and will not do.
→ `references/capabilities-and-shipping.md`

**5. Distribution** — install prompts, TWA for Play, the Apple Guideline 4.2
problem, and when a native wrapper is genuinely required.
→ `references/capabilities-and-shipping.md`

## Choosing a stack

The framework matters less than the discipline, but it is not free:

| Stack | Runtime cost | PWA tooling | Mobile UI |
|---|---|---|---|
| **Svelte / SvelteKit** | Lowest — compiles away, no VDOM | `@vite-pwa/sveltekit` | Framework7, Skeleton |
| **Vue / Nuxt** | Low — fine-grained reactivity | `vite-plugin-pwa`, `@vite-pwa/nuxt` | Ionic Vue, Vant, frappe-ui 1.x mobile family |
| **React / Next** | Higher; needs disciplined route chunking | `vite-plugin-pwa`, `next-pwa` | Ionic React, Radix + Tailwind |
| **Angular** | Largest baseline bundle | `@angular/pwa` (built-in SW) | Ionic Angular, Material |
| **Rust/C++/Go → WASM** | Near-native, alongside JS | n/a — a worker, not an app shell | Canvas / WebGL / WebGPU |

Use TypeScript. The contracts that break silently in a PWA are exactly the ones
across boundaries — the network, the service worker thread, and the IndexedDB
tier — and those are where types pay for themselves.

**On budget Android hardware, bundle size is the feature.** A 200 KB app that
hydrates in 400 ms beats a 900 KB app with nicer components, every time, on the
devices your users actually have. Budget it: ≤ 200 KB gzipped for the initial
route, everything else lazy.

## Principles

- **Latency is the tell.** Native apps read from a local database and paint in the
  current frame. Any interaction that waits on a round-trip before showing
  something reads as "web". Render from cache, reconcile after.
- **Fixed shell, scrolling content.** `html, body { height: 100%; overflow: hidden }`
  and one designated scroll container. This is what stops the whole page moving
  when the keyboard opens.
- **Take away browser behaviours deliberately, and replace them.** Disabling
  text selection, context menus, rubber-banding and zoom makes the app feel
  native — and removes affordances. If you disable edge-swipe history, you owe the
  user a back gesture. If you disable text selection, you owe them long-press copy
  where copying matters.
- **Progressive enhancement, not feature detection theatre.** `'vibrate' in
  navigator` guards are one line. An app that throws on an iPhone because it
  assumed the Badging API is an app that was only tested on Android.
- **Test on the real floor of your device range.** A three-year-old mid-range
  Android and any iPhone. The desktop responsive simulator cannot show you the
  keyboard, the notch, the launcher icon mask, or a 4× slower CPU.

## The checklist

Run this against a build on a real phone before calling it done.

**Shell**
- [ ] Launched from home screen: no URL bar, no browser toolbar
- [ ] Header clears the notch / Dynamic Island; bottom bar clears the home indicator
- [ ] Rotate to landscape and back: nothing clipped, nothing overlapping
- [ ] Cold start shows a splash, not a white rectangle (iOS especially)
- [ ] Launcher icon is not a white square with your logo shrunk inside it
      (maskable icon)

**Input**
- [ ] No grey/blue flash on tap anywhere
- [ ] Long-press on a button or image does nothing; long-press on selectable text
      still works
- [ ] Scrolling past the end does not rubber-band the page
- [ ] Double-tap does not zoom; pinch-zoom either works or is deliberately off
- [ ] Focus an input: the field and its submit button stay visible above the
      keyboard
- [ ] Inputs are ≥ 16 px so iOS does not zoom the viewport on focus
- [ ] Every touch target ≥ 44 px

**Motion**
- [ ] Forward navigation slides in from the right; back slides out to the right
- [ ] Edge-swipe from the left goes back (iOS standalone has no browser gesture)
- [ ] Android hardware back closes an open sheet before it navigates
- [ ] Everything runs at 60 fps on the slowest target device
- [ ] `prefers-reduced-motion` shortens transitions rather than breaking them

**Data**
- [ ] Airplane mode: the app opens and shows real, cached content
- [ ] A write while offline either queues visibly or fails visibly — never
      silently
- [ ] Deploying a new version does not white-screen an open session
- [ ] Nothing authenticated survives logout in any cache

**Capabilities**
- [ ] Every capability call is feature-detected; nothing throws on iOS
- [ ] Notification permission is requested from a user action, never on load
- [ ] The app is honest in-UI about what it cannot do on the current platform

**Distribution**
- [ ] Installable (Lighthouse PWA audit green)
- [ ] Install prompt appears after a success, not on first paint
- [ ] iOS gets Share-sheet instructions with the actual glyph, and only in Safari
