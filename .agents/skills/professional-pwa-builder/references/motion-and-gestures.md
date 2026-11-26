# Motion and gestures

Geometry makes an app *look* native. Motion makes it *feel* native. This is the
layer people cannot articulate but always notice.

## Page transitions

Historically this meant wrapping components in transition libraries that fought
the router and thrashed layout. The **View Transitions API** does it at the engine
level: the browser snapshots the old state, you mutate the DOM, it snapshots the
new state, and it animates between them as pseudo-elements — off the main thread,
no layout thrashing, no duplicate component trees.

```js
export function navigate(to, direction = 'forward') {
  if (!document.startViewTransition) {
    render(to)                      // no API: just navigate, no animation
    return
  }

  document.documentElement.dataset.direction = direction

  const transition = document.startViewTransition(async () => {
    await render(to)                // your router's actual DOM update
  })

  transition.finished.finally(() => {
    delete document.documentElement.dataset.direction
  })
}
```

```css
@keyframes slide-out-left  { from { transform: translateX(0); }      to { transform: translateX(-20%); opacity: .8; } }
@keyframes slide-in-right  { from { transform: translateX(100%); }   to { transform: translateX(0); } }
@keyframes slide-out-right { from { transform: translateX(0); }      to { transform: translateX(100%); } }
@keyframes slide-in-left   { from { transform: translateX(-20%); opacity: .8; } to { transform: translateX(0); } }

[data-direction="forward"]::view-transition-old(root) {
  animation: 350ms cubic-bezier(0.32, 0.72, 0, 1) both slide-out-left;
}
[data-direction="forward"]::view-transition-new(root) {
  animation: 350ms cubic-bezier(0.32, 0.72, 0, 1) both slide-in-right;
}
[data-direction="backward"]::view-transition-old(root) {
  animation: 350ms cubic-bezier(0.32, 0.72, 0, 1) both slide-out-right;
  z-index: 1;
}
[data-direction="backward"]::view-transition-new(root) {
  animation: 350ms cubic-bezier(0.32, 0.72, 0, 1) both slide-in-left;
  z-index: 0;
}

@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) { animation-duration: 1ms !important; }
}
```

The details that make this read as iOS rather than as "a web animation":

- **`cubic-bezier(0.32, 0.72, 0, 1)`** approximates Apple's CoreAnimation easing:
  fast start, long settle. A linear or `ease` curve is instantly recognisable as
  not-native.
- **The outgoing screen moves 20 %, not 100 %.** iOS parallaxes the departing view
  at a fraction of the incoming view's distance. Moving both fully looks like a
  slideshow.
- **`z-index` flips by direction.** Going forward the new screen covers the old;
  going back the *old* screen slides off *over* the new one. Get this backwards
  and back-navigation looks wrong in a way nobody can name.
- **350 ms**, not 200 and not 500. Shorter reads as a cut, longer as sluggish.

Router integration:

- **Vue Router**: wrap `router.afterEach`'s DOM update, or use the
  `@vueuse/core` view-transition helper. Derive direction from history depth.
- **React Router / Next**: `React.startTransition` inside `startViewTransition`;
  Next has first-class guidance for the App Router.
- **SvelteKit**: `onNavigate` returns a promise — the documented hook for exactly
  this.

Direction detection: keep a monotonically increasing index in `history.state` and
compare on each navigation. `popstate` alone does not tell you forward from back.

**Shared-element transitions** (a list row expanding into a detail header) come
from `view-transition-name` on the same logical element in both screens. Assign it
dynamically to just the tapped row — a `view-transition-name` must be unique in
the document at snapshot time, and duplicates silently disable the whole
transition.

Support: same-document view transitions shipped in Chromium first, then Safari,
then Firefox, and are broadly available across engines now; cross-document (MPA)
transitions followed later and are the newer half — check current support before
relying on those. Either way, keep the `if (!document.startViewTransition)` guard:
it degrades to an instant cut, which is exactly the right fallback, and it costs
one line.

## Gesture navigation

**In a standalone iOS PWA there is no browser back gesture and no back button.**
Whatever you do not build, the user does not have. This surprises people every
time.

```js
export function initEdgeSwipe(onBack, { edge = 20, threshold = 75 } = {}) {
  let startX = 0, startY = 0, tracking = false

  window.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return
    startX = e.touches[0].clientX
    startY = e.touches[0].clientY
    tracking = startX <= edge
  }, { passive: true })

  window.addEventListener('touchmove', (e) => {
    if (!tracking) return
    const dx = e.touches[0].clientX - startX
    const dy = Math.abs(e.touches[0].clientY - startY)
    if (dy > dx) tracking = false          // it's a scroll, not a back-swipe
  }, { passive: true })

  window.addEventListener('touchend', (e) => {
    if (!tracking) return
    if (e.changedTouches[0].clientX - startX > threshold) onBack()
    tracking = false
  }, { passive: true })
}
```

`{ passive: true }` on all three is required — a non-passive touch listener blocks
scrolling on the compositor and produces exactly the jank you are trying to avoid.

That version is a **threshold** gesture: it commits or does not. An
**interactive** one — where the screen tracks the finger and rubber-bands back if
you release early — feels significantly better and costs more code: translate the
outgoing view by `dx` during `touchmove` (using `transform`, never `left`), and on
`touchend` either complete or spring back based on distance *and* velocity. If the
app is deep-navigation heavy, it is worth it. If it is two levels deep, the
threshold version is fine.

**Android hardware back** fires `popstate`. Make open overlays consume it first:

```js
window.addEventListener('popstate', (e) => {
  if (sheetIsOpen()) { closeSheet(); history.pushState(null, '', location.href); return }
  // else let the router handle it
})
```

Users hit back to dismiss a sheet, not to leave the screen. Getting this wrong is a
top complaint on Android.

## Scroll

- **One scroll container per screen**, not nested ones. Nested scroll on touch is
  ambiguous and feels broken.
- `overscroll-behavior-y: contain` on inner containers (keeps the bounce local),
  `none` on the body (kills browser pull-to-refresh so you can build your own).
- **Custom pull-to-refresh** needs a spring, a rotating indicator that tracks the
  pull distance, and a haptic tick at the trigger threshold. A refresh that just
  appears after a plain drag reads as web.
- **Momentum**: `-webkit-overflow-scrolling: touch` is legacy but harmless; modern
  iOS does momentum by default.
- **Scroll restoration** is yours to manage. `history.scrollRestoration = 'manual'`
  and store per-route scroll offsets. Returning to a list at the top instead of
  where the user was is one of the clearest "this is a website" signals.
- **Long lists**: virtualise past a few hundred rows, and use
  `content-visibility: auto` with `contain-intrinsic-size` on off-screen blocks as
  a cheap first step.

## Touch targets and feedback

- **44 × 44 px minimum**, with ≥ 8 px between adjacent targets. Expand the hit area
  with padding or a pseudo-element rather than making the visual element bigger.
- **Visible response within 100 ms.** `active:scale-95` plus a 120 ms transition
  is enough; below ~100 ms the tap feels dead.
- **`touch-action: manipulation`** on interactive elements removes the historical
  ~300 ms double-tap-zoom delay without disabling zoom globally.
- Use `:active` styling, not `:hover`, for touch feedback. On mobile, `:hover`
  sticks after the tap and leaves a "stuck highlight".

## Haptics

```js
const PATTERNS = {
  light: 10,
  medium: 20,
  heavy: 40,
  success: [10, 30, 15],
  warning: [20, 40, 20],
  error: [20, 50, 20, 50],
  selection: 5,
}

export function haptic(type = 'light') {
  if (!('vibrate' in navigator)) return
  try { navigator.vibrate(PATTERNS[type] ?? 10) } catch {}
}
```

Where it earns its place: the moment a pull-to-refresh crosses its threshold,
toggle switches, successful submits, destructive confirmations, a barcode scan
landing. Where it does not: every tap. Over-buzzing is worse than silence, and
users turn vibration off at the OS level.

`navigator.vibrate` is **Android-only** — iOS Safari does not expose it, and there
is no Web API for CoreHaptics. If tactile feedback is essential to the product
(a scanner, a POS), that is a genuine argument for a Capacitor wrapper on iOS.

## Performance

Native-grade means 60 fps sustained, on the slowest device you support.

- **Animate only `transform` and `opacity`.** Anything else (`left`, `width`,
  `height`, `margin`) triggers layout on the main thread and drops frames.
- **`will-change` sparingly** — on the element about to animate, removed
  afterwards. Leaving it on promotes layers permanently and exhausts GPU memory on
  cheap phones.
- **Web Animations API over `setInterval`/`requestAnimationFrame` loops** for
  discrete animations: it runs on the compositor and keeps running while the main
  thread is busy.
- **Budget the initial route**: ≤ 200 KB gzipped. Everything else lazy, by route.
- **Preload the next likely route** on intent (link in viewport, pointer down),
  not on load.
- **Move heavy work off the main thread**: parsing, crypto, image processing →
  Web Worker; genuinely heavy numerics → WebAssembly.
- **Images**: AVIF/WebP, explicit `width`/`height` to prevent layout shift,
  `loading="lazy"` below the fold, `decoding="async"`.
- **Measure on hardware, throttled.** Chrome DevTools 4× CPU throttling
  approximates a mid-range Android; a real three-year-old device is better.
  Lighthouse on a desktop tells you almost nothing about how this feels in a
  warehouse.

## Loading states

- **Skeletons matching the real layout**, not spinners. They make the wait feel
  shorter and eliminate the content jump on arrival.
- **No skeleton under ~200 ms** — a flash of skeleton is worse than a brief pause.
  Delay it.
- **Optimistic UI where reverting is cheap** (marking read, toggling a star) and
  never where it is not (submitting a payment, approving a document).
- **Never a full-screen blocking spinner.** Render the shell, skeleton the parts.
  On a slow connection a full-screen spinner is indistinguishable from a hang, and
  users kill the app.
