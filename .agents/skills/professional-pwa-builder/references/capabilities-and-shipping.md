# Capabilities and shipping

What the web can reach on a device, what iOS will not give you, and how to get the
app into the stores if you must.

## Capability matrix

| Domain | Web API | Android Chrome | iOS Safari |
|---|---|---|---|
| Push notifications | Web Push (VAPID, RFC 8030) | Yes | **16.4+, installed to Home Screen only** |
| Launcher badge | `navigator.setAppBadge()` | Yes | 16.4+, standalone only |
| Share out | `navigator.share()` | Yes | Yes |
| Receive shares | Web Share Target (manifest) | Yes | No |
| Biometrics | WebAuthn / passkeys | Yes | Yes |
| Camera / mic | `getUserMedia` | Yes | Yes (HTTPS; standalone has quirks) |
| Barcode scan | `BarcodeDetector` | Yes | No — use `zxing-wasm` or `@zxing/library` |
| Geolocation | `navigator.geolocation` | Yes | Yes |
| Background sync | Background Sync API | Yes | No |
| Periodic background sync | Periodic Background Sync | Installed only | No |
| File system | File System Access API | Yes | Read-only pickers |
| Bluetooth / USB / HID / NFC | Web Bluetooth, WebUSB, WebHID, Web NFC | Yes | **No** |
| Contacts | Contact Picker API | Yes | No |
| Wake lock | Screen Wake Lock | Yes | 16.4+ |
| Payments | Payment Request API | Yes | Yes (Apple Pay) |

Feature-detect every one of these. One unguarded call is the difference between
"works on my phone" and an app that throws on half the install base.

```js
const can = {
  push: 'PushManager' in window && 'serviceWorker' in navigator,
  badge: 'setAppBadge' in navigator,
  share: 'share' in navigator,
  shareFiles: (files) => navigator.canShare?.({ files }) ?? false,
  vibrate: 'vibrate' in navigator,
  barcode: 'BarcodeDetector' in window,
  webauthn: 'PublicKeyCredential' in window,
  wakeLock: 'wakeLock' in navigator,
  bgSync: 'serviceWorker' in navigator && 'SyncManager' in window,
}
```

And be honest in the UI. If barcode scanning is core and iOS lacks
`BarcodeDetector`, ship the WASM fallback — do not show a disabled button.

## Push

```js
// permission — ONLY from a user gesture, never on load
export async function enablePush(vapidPublicKey) {
  if (Notification.permission === 'denied') return { ok: false, reason: 'blocked' }
  if ((await Notification.requestPermission()) !== 'granted') return { ok: false, reason: 'declined' }

  const reg = await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,                       // required; silent push is not allowed
    applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
  })
  await fetch('/api/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(sub),
  })
  return { ok: true }
}
```

```js
// sw.js
self.addEventListener('push', (event) => {
  const data = event.data?.json() ?? {}
  event.waitUntil(
    self.registration.showNotification(data.title ?? 'Update', {
      body: data.body,
      icon: '/icons/icon-192.png',
      badge: '/icons/badge-72.png',              // monochrome, Android status bar
      tag: data.tag,                             // collapses duplicates
      renotify: false,
      data: { url: data.url },
      actions: data.actions?.slice(0, 2),        // 2 is the practical maximum
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url
  if (!url) return
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) if (c.url === url && 'focus' in c) return c.focus()
      return self.clients.openWindow(url)
    }),
  )
})
```

Rules that matter:

- **Never prompt on load.** A denied permission is effectively permanent — the
  user must dig into site settings to reverse it. One careless auto-prompt costs
  you that user forever. Ask from an explicit control, after explaining what they
  will receive.
- **`userVisibleOnly: true` is mandatory** and means every push must show a
  notification. There is no silent push on the web.
- **`tag`** collapses repeats about the same subject instead of stacking twelve.
- **Focus an existing window** rather than always calling `openWindow`, or a
  notification storm opens twenty tabs.
- **`badge`** must be a monochrome transparent PNG — Android renders it as a mask
  in the status bar; a colour icon becomes a grey blob.
- Handle `Notification.permission === 'denied'` with an explanation, not a toggle
  that silently does nothing.

**iOS**: 16.4+, and only once the app is installed to the Home Screen. In a Safari
tab there is no push at all. Detect and explain; do not show a control that cannot
work.

## Badging

```js
export async function setBadge(count) {
  if (!('setAppBadge' in navigator)) return
  try {
    count > 0 ? await navigator.setAppBadge(count) : await navigator.clearAppBadge()
  } catch {}
}
```

Drive it from the same source as the in-app unread count, and clear it when the
user opens that screen. A badge that never clears trains people to ignore it.

## Share

```js
export async function share({ title, text, url, files }) {
  if (files?.length && navigator.canShare?.({ files })) {
    return navigator.share({ title, text, files })
  }
  if ('share' in navigator) return navigator.share({ title, text, url })
  await navigator.clipboard.writeText(url)        // honest fallback
  toast('Link copied')
}
```

`navigator.share` must be called **synchronously from a user gesture** — awaiting
something first invalidates the gesture and it silently rejects. Prepare the data
before the click handler.

Receiving shares (Android only) is manifest config:

```json
"share_target": {
  "action": "/app/share",
  "method": "POST",
  "enctype": "multipart/form-data",
  "params": {
    "title": "title", "text": "text", "url": "url",
    "files": [{ "name": "attachments", "accept": ["image/*", "application/pdf"] }]
  }
}
```

Your service worker intercepts the POST to `/app/share`, stashes the payload, and
redirects to a UI route.

## Biometrics / passkeys

WebAuthn gives real Face ID / Touch ID / Android biometric unlock, supported
everywhere modern. Two uses:

- **Passkeys as the primary credential** — no password at all. The right answer
  for a new consumer app.
- **A local re-auth gate** — the session stays valid but the app requires a
  biometric check to open or to approve a sensitive action. This is what makes an
  enterprise PWA feel trustworthy, and it maps directly to the "native
  capabilities" Apple looks for at review.

```js
const cred = await navigator.credentials.create({
  publicKey: {
    challenge: serverChallenge,                      // from your server, single-use
    rp: { name: 'Enterprise', id: location.hostname },
    user: { id: userIdBytes, name: email, displayName: fullName },
    pubKeyCredParams: [{ type: 'public-key', alg: -7 }, { type: 'public-key', alg: -257 }],
    authenticatorSelection: { authenticatorAttachment: 'platform', userVerification: 'required', residentKey: 'preferred' },
    timeout: 60000,
  },
})
```

`authenticatorAttachment: 'platform'` restricts to the device's built-in
authenticator (the biometric sensor) rather than a USB key. Use `@simplewebauthn/browser`
and `@simplewebauthn/server` rather than hand-rolling the CBOR and attestation
verification — the cryptography is not where you want a bug.

## Camera and scanning

```js
const stream = await navigator.mediaDevices.getUserMedia({
  video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } },
})
```

`{ ideal: 'environment' }` rather than `{ exact: … }` — `exact` throws on devices
without a rear camera instead of degrading.

Barcodes: `BarcodeDetector` where available, `zxing-wasm` elsewhere (iOS). Always
stop the tracks when done (`stream.getTracks().forEach(t => t.stop())`) or the
camera indicator stays on, which users find alarming.

Requesting camera permission in an iOS standalone PWA has historically been flaky
across versions. Test it on the actual iOS version your users run, and provide a
file-input fallback (`<input type="file" accept="image/*" capture="environment">`)
which always works.

## Distribution

### Install prompt

```js
let deferred = null
window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferred = e })
window.addEventListener('appinstalled', () => { deferred = null; track('pwa_installed') })

export async function promptInstall() {
  if (!deferred) return false
  deferred.prompt()
  const { outcome } = await deferred.userChoice
  deferred = null
  return outcome === 'accepted'
}

export const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true
```

- Prompt **after a success**, not on first paint. A user who has just completed
  something has a reason to want the app.
- Suppress when already standalone, or previously installed, or dismissed
  recently (re-ask after ~30 days).
- Keep a quiet permanent entry point too ("Install app" in settings) for people
  who decide later.
- **iOS**: no `beforeinstallprompt`. Detect iOS + not standalone + **Safari**, and
  show a sheet with the actual share glyph: "Tap ⎋ then Add to Home Screen". In
  Chrome or Firefox on iOS there is no Add to Home Screen at all — say "Open in
  Safari to install" rather than giving instructions that cannot be followed.

### Google Play — TWA

Trusted Web Activity wraps your PWA in an Android App Bundle that launches
full-screen in Chrome with no address bar, verified via Digital Asset Links.

```bash
npx @bubblewrap/cli init --manifest https://example.com/manifest.json
npx @bubblewrap/cli build
```

- Host `/.well-known/assetlinks.json` with your signing-key fingerprint, or the
  app launches **with an address bar** — the most common TWA mistake.
- Your PWA must pass the installability criteria; Bubblewrap checks.
- Updates ship by deploying the web app. Only the shell needs a Play release.
- Play policy requires the app to be more than a thin wrapper, but enforcement is
  far lighter than Apple's.

### Apple App Store — Guideline 4.2

> *"Your app should include features, content, and UI that elevate it beyond a
> repackaged website. If your app is not particularly useful, unique, or
> 'app-like', it doesn't belong on the App Store."*

A bare `WKWebView` loading a remote URL gets rejected. To pass with a Capacitor or
native shell:

- **Bundle the assets locally.** The app must launch and render in Airplane Mode.
  A blank screen or a connection error on first open is an automatic rejection —
  and it is the specific thing reviewers test.
- **Use native plugins for real capabilities**: APNs push (not Web Push), native
  biometrics, native camera for scanning, CoreHaptics, native share sheet.
- **Add something the website does not have**: offline mode, widgets, Siri
  shortcuts, Handoff, deep links.
- **Native navigation chrome** where it matters, rather than web controls that
  look foreign.

Capacitor is the pragmatic path: keep the same web codebase, add native plugins,
ship one binary per store.

**Ask whether you need the App Store at all.** For an internal enterprise tool, a
B2B field app, or anything distributed to a known user base, an installed PWA
delivers the same experience with no review, no annual fee, no 30 % cut, and
same-day updates. The App Store is a distribution channel — if you are not using
the channel, you are paying its costs for nothing.

## Analytics and diagnostics

Instrument what you cannot otherwise see:

- `display-mode` at session start (installed vs browser) — this tells you whether
  your install funnel works at all.
- `beforeinstallprompt` fired / prompted / accepted / dismissed.
- Service worker: installed, waiting, update applied, update dismissed.
- Offline sessions, queued writes, sync failures, conflicts surfaced.
- Push: permission requested / granted / denied / revoked.
- Web Vitals (LCP, INP, CLS) **segmented by installed vs browser** — they differ
  substantially, and the installed numbers are the ones your real users live with.

Report errors from the service worker too. An error in the worker is invisible to
page-level error handlers, and a worker that throws on `install` fails silently.
