# PWA runtime

Manifest, service worker, update lifecycle, install prompts, push. The parts that
turn a Vue app served by Frappe into something a user installs and trusts.

## Manifest

Declared in `vite.config.js` so it is emitted with content-hashed paths:

```js
import { VitePWA } from 'vite-plugin-pwa'

VitePWA({
  strategies: 'injectManifest',     // you own sw.js
  srcDir: 'public',
  filename: 'sw.js',
  injectRegister: null,             // you register it yourself, in main.js
  registerType: 'prompt',           // NOT autoUpdate — see the lifecycle below
  devOptions: { enabled: false },
  manifest: {
    id: '/my-pwa',
    name: 'My PWA',
    short_name: 'My PWA',
    description: 'Everyday operations at your fingertips',
    start_url: '/my-pwa',
    scope: '/my-pwa',
    display: 'standalone',
    display_override: ['window-controls-overlay', 'standalone'],
    orientation: 'portrait-primary',
    background_color: '#ffffff',
    theme_color: '#ffffff',
    lang: 'en',
    dir: 'ltr',
    icons: [
      { src: '/assets/my_pwa/manifest/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/assets/my_pwa/manifest/icon-192.maskable.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: '/assets/my_pwa/manifest/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/assets/my_pwa/manifest/icon-512.maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
    shortcuts: [
      { name: 'New Order', url: '/my-pwa/orders/new', icons: [{ src: '/assets/my_pwa/manifest/icon-192.png', sizes: '192x192' }] },
    ],
  },
})
```

- **`scope` must contain `start_url`.** Set both to your route. Without `scope`,
  the SW's default scope is its own directory (`/assets/my_pwa/frontend/`) and
  navigation requests to `/my-pwa` are never intercepted — the app appears to have
  no service worker at all. This is the #1 silent PWA failure on Frappe.
- **`id`** pins app identity across `start_url` changes. Add it now; changing
  `start_url` later without an `id` makes the OS treat it as a different app.
- **Separate `any` and `maskable` icons.** One file tagged both (what Frappe HR
  does) means Android either crops your logo or pads your icon, depending on
  launcher. Maskable art needs ~20% safe padding; `any` art should not have it.
- **`orientation: 'portrait-primary'`** only if the app genuinely does not work in
  landscape. Locking orientation on a tablet-heavy deployment is a complaint
  generator.

Serve the manifest link from `index.html` — `vite-plugin-pwa` injects it, or add
it manually at `/assets/my_pwa/frontend/manifest.webmanifest`.

## Icons and splash screens

Generate, do not hand-cut:

```bash
npx pwa-asset-generator ./logo.svg ./my_pwa/public/manifest \
  --background "#ffffff" --padding "12%" \
  --icon-only false --favicon --maskable true \
  --index ./frontend/index.html --path-override "/assets/my_pwa/manifest"
```

iOS ignores the manifest for launch screens entirely; without
`<link rel="apple-touch-startup-image">` tags matched to each device geometry, the
app cold-starts to a white rectangle. Frappe HR ships **28** of them (14 devices ×
portrait/landscape). Let the generator emit the tags and paste them into
`index.html`.

Commit the generated assets to `my_pwa/public/manifest/` — they are source, not
build output.

## Service worker: the update lifecycle

This is the part that separates a PWA people keep from one they uninstall.

**Frappe HR's `sw.js` ends with a bare `self.skipWaiting()`.** Do not copy that.
It means: the moment a new worker downloads, it evicts the active one mid-session.
The page is still running the old JS, which then requests a lazy chunk that the new
precache no longer has — and the user gets a white screen or a
`Failed to fetch dynamically imported module` on the next navigation. It is
intermittent, it only bites users who had the app open during a deploy, and it is
maddening to reproduce.

The correct shape — new worker waits, the app asks, the user decides:

```js
// frontend/public/sw.js
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'
import { clientsClaim } from 'workbox-core'
import { registerRoute } from 'workbox-routing'
import { NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// App data: fresh when online, last-known when not.
registerRoute(
  ({ url }) => url.pathname.startsWith('/api/'),
  new NetworkFirst({
    cacheName: 'api',
    networkTimeoutSeconds: 5,
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 86400 })],
  }),
)

// User-uploaded files: serve instantly, refresh in the background.
registerRoute(
  ({ url }) => url.pathname.startsWith('/files/'),
  new StaleWhileRevalidate({
    cacheName: 'files',
    plugins: [new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 7 * 86400 })],
  }),
)

// Wait until the app says go.
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting()
})

self.addEventListener('activate', () => clientsClaim())
```

and in the app:

```js
// src/utils/pwa.js
import { registerSW } from 'virtual:pwa-register'

export const updateAvailable = ref(false)
let applyUpdate = () => {}

export function initPWA() {
  applyUpdate = registerSW({
    onNeedRefresh() { updateAvailable.value = true },   // render an in-app bar
    onOfflineReady() { /* optional toast */ },
  })
}

export function reloadForUpdate() { applyUpdate(true) }
```

Render a small, dismissible bar: *"A new version is ready — Reload"*. Auto-apply it
only on a genuinely idle transition (app returns to foreground with no unsaved
form). Never mid-form.

**Never `NetworkFirst` or `CacheFirst` an HTML navigation to `/api/method/login`,
`/api/method/logout`, or anything that sets a cookie.** Exclude them explicitly:

```js
registerRoute(({ url }) => /\/api\/method\/(login|logout)/.test(url.pathname), new NetworkOnly())
```

A cached login response is how a second user on a shared tablet ends up in the
first user's session.

Also: **do not cache authenticated JSON on a shared device** without clearing it on
logout.

```js
// call from session.logout.onSuccess, before window.location.reload()
export async function purgeCaches() {
  if ('caches' in window) {
    for (const k of await caches.keys()) if (k !== 'workbox-precache') await caches.delete(k)
  }
  const { clear } = await import('idb-keyval')
  await clear()     // drops frappe-ui's cacheKey entries
}
```

## Registering the worker

Frappe serves built assets under `/assets/<app>/frontend/`, so the SW file lives
there — but it must control `/my-pwa`. The `scope` in the manifest is not enough;
pass it at registration, and make sure the response carries
`Service-Worker-Allowed`:

```js
navigator.serviceWorker.register('/assets/my_pwa/frontend/sw.js', {
  type: 'classic',
  scope: '/my-pwa/',
})
```

If the browser refuses with *"The path of the provided scope is not under the max
scope allowed"*, add the header in nginx:

```nginx
location = /assets/my_pwa/frontend/sw.js {
    add_header Service-Worker-Allowed "/my-pwa/";
    try_files $uri =404;
}
```

The simpler alternative, when you control the route: serve `sw.js` from a www page
at `/my-pwa/sw.js` so its default scope is already correct. That costs a Python
round-trip on registration only, and removes an nginx dependency you will forget
about the next time the site moves hosts.

## Install prompts

Chromium fires `beforeinstallprompt`; iOS fires nothing and requires the Share
sheet. Handle both, and **do not ambush the user on first paint** — prompt after
they have done something successful.

```js
const deferred = ref(null)
const showAndroidDialog = ref(false)
const showIosSheet = ref(false)

const isIos = () => /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase())
const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  deferred.value = e
})

window.addEventListener('appinstalled', () => {
  deferred.value = null
  showAndroidDialog.value = false
  localStorage.setItem('my_pwa:installed', '1')
})

export function maybeOfferInstall() {
  if (isStandalone() || localStorage.getItem('my_pwa:install_dismissed')) return
  if (deferred.value) showAndroidDialog.value = true
  else if (isIos()) showIosSheet.value = true
}

export async function install() {
  if (!deferred.value) return
  deferred.value.prompt()
  const { outcome } = await deferred.value.userChoice
  if (outcome !== 'accepted') localStorage.setItem('my_pwa:install_dismissed', '1')
  deferred.value = null
}
```

Detail Frappe HR gets wrong and you should not: it checks only
`window.navigator.standalone`, which is iOS-only, so on Android the dialog can
reappear for an already-installed app. `matchMedia('(display-mode: standalone)')`
is the cross-platform check; keep the `navigator.standalone` fallback for old iOS.

The iOS sheet must *show* the Share glyph, not describe it — "Tap ⎋ then Add to
Home Screen" with the actual icon inline. Users do not recognise the word "Share".

## Push notifications

### Option 1 — Frappe's relay (the v16-native path)

Frappe v16 ships `frappe.push_notification` talking to a
**notification_relay** server that holds the Firebase credentials. Enable Push
Notification Settings and set `push_relay_server_url` in site config. Client side:

```js
// main.js
import FrappePushNotification from '../public/frappe-push-notification'

window.frappePushNotification = new FrappePushNotification('my_pwa')

let swUrl = '/assets/my_pwa/frontend/sw.js'
if (window.frappe?.boot?.push_relay_server_url) {
  const config = await window.frappePushNotification.fetchWebConfig()
  swUrl += `?config=${encodeURIComponent(JSON.stringify(config))}`
}
const reg = await navigator.serviceWorker.register(swUrl, { type: 'classic', scope: '/my-pwa/' })
if (window.frappe?.boot?.push_relay_server_url) await window.frappePushNotification.initialize(reg)
```

The Firebase web config is passed **as a query string on the SW URL** because a
service worker cannot import app state. The SW reads it back with
`new URL(location).searchParams.get('config')` and calls `initializeApp`. That
query string also makes the SW URL change when config changes, which forces an
update — convenient, and worth knowing when you are debugging why the SW
"reinstalled itself".

`frappe-push-notification.js` (copy it from `hrms/frontend/public/`) handles token
lifecycle: `enableNotification()` asks permission, gets an FCM token, compares it
with `localStorage`, unsubscribes the old one and calls
`frappe.push_notification.subscribe`. `disableNotification()` reverses it. Keep a
user-facing toggle wired to those two — an app that silently subscribes and offers
no way out gets its notifications blocked at the OS level.

In the SW:

```js
import { initializeApp } from 'firebase/app'
import { getMessaging, onBackgroundMessage } from 'firebase/messaging/sw'

const jsonConfig = new URL(location).searchParams.get('config')
try {
  const messaging = getMessaging(initializeApp(JSON.parse(jsonConfig)))
  onBackgroundMessage(messaging, (payload) => {
    self.registration.showNotification(payload.data.title, {
      body: payload.data.body || '',
      icon: payload.data.notification_icon,
      data: { url: payload.data.click_action },
    })
  })
  self.addEventListener('notificationclick', (event) => {
    event.notification.close()
    const url = event.notification.data?.url
    if (url) event.waitUntil(clients.openWindow(url))
  })
} catch (e) { console.log('FCM not configured', e) }
```

### Option 2 — direct FCM HTTP v1 (no relay server)

For a self-hosted ERPNext where standing up a second service is not worth it, talk
to Google directly from your app. Store the Firebase **service account JSON** in a
password field on a Single, mint an OAuth token with a signed JWT, POST to
`https://fcm.googleapis.com/v1/projects/<project_id>/messages:send`, and prune
tokens that come back `404`/`UNREGISTERED`. `omfsakib/pwa_frappe`'s `fcm.py` is a
complete, readable implementation of exactly this — `frappe-desk-pwa` walks
through it.

Tradeoff: you own credential rotation and the outbound call, and every site needs
its own Firebase project. In exchange there is no relay to deploy, monitor or
trust.

### iOS reality

- Web Push works on iOS **16.4+ and only when installed to the Home Screen**. In
  Safari tabs there is no push, ever. Say this in the UI when you detect iOS and
  `!isStandalone()` — do not show a permission toggle that cannot work.
- iOS suspends background JS within seconds of backgrounding. No background sync,
  no long uploads while minimised.
- Notification `actions` behave differently on WebKit vs Chromium; Frappe HR
  branches on a `isChrome()` check — use `data.url` + `notificationclick` on
  Chromium, `actions` on WebKit.

## Badging

```js
export async function syncBadge(count) {
  if (!('setAppBadge' in navigator)) return
  try {
    count > 0 ? await navigator.setAppBadge(count) : await navigator.clearAppBadge()
  } catch (e) { /* non-fatal */ }
}
```

Supported on Chromium, Windows, and iOS 16.4+ standalone PWAs. Drive it from the
same resource that feeds your in-app unread count, and clear it when the user opens
the notifications screen.

## Storage durability

Safari's ITP evicts CacheStorage and IndexedDB after **7 days of inactivity** for
sites that are *not* installed. Once added to the Home Screen, that eviction rule
relaxes. So on iOS: the install prompt is not a nice-to-have, it is what makes your
offline cache survive a long weekend.

Request persistence where supported:

```js
if (navigator.storage?.persist) await navigator.storage.persist()
```

## Runtime checklist

- [ ] `scope` and `start_url` both `/my-pwa`, SW registered with a matching scope
- [ ] Separate `any` and `maskable` icons at 192 and 512
- [ ] `apple-touch-startup-image` tags generated for the devices you support
- [ ] New deploy shows an update bar; does not reload mid-form
- [ ] `login`/`logout` excluded from every caching strategy
- [ ] Logout purges runtime caches and IndexedDB
- [ ] Install prompt appears after a success, not on first paint; suppressed when
      already standalone; iOS gets the Share-sheet sheet with a real glyph
- [ ] Push toggle is off by default, reversible, and hidden on iOS-in-browser
- [ ] `navigator.storage.persist()` requested
- [ ] Airplane mode: shell renders, cached lists render, writes fail *visibly*
