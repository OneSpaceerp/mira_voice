# Offline and sync

Native apps feel instant because the UI reads from a local database and paints in
the current frame. The network is a background reconciliation process, not a
blocking dependency. This is the deepest of the five layers and the one users
notice most, even though they cannot name it.

## Caching tiers

Do not apply one strategy to everything. Categorise by what the resource *is*:

| Resource | Strategy | Why |
|---|---|---|
| Content-hashed bundles, vendor chunks, fonts | **Precache** (build-time manifest) | Immutable by definition; the filename changes when the content does |
| App shell HTML, icons, semi-static config | **Stale-while-revalidate** | Instant paint, refreshed silently for next time |
| Read APIs, lists, documents | **Network-first** with a short timeout + cache fallback | Fresh when online, usable when not |
| Writes, auth, anything `POST` | **Network-only**, plus your own queue | A cached write is a correctness bug |
| User-uploaded images and files | **Cache-first with expiry** | Large, immutable per URL, expensive to refetch |

```js
// sw.js — Workbox
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'
import { clientsClaim } from 'workbox-core'
import { registerRoute, setDefaultHandler } from 'workbox-routing'
import { NetworkFirst, NetworkOnly, StaleWhileRevalidate, CacheFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'
import { CacheableResponsePlugin } from 'workbox-cacheable-response'

precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// Auth: never cached, never queued blindly.
registerRoute(({ url }) => /\/(login|logout|auth)\b/.test(url.pathname), new NetworkOnly())

// Read APIs
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/api/'),
  new NetworkFirst({
    cacheName: 'api',
    networkTimeoutSeconds: 5,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 86400 }),
    ],
  }),
)

// Files and images
registerRoute(
  ({ request }) => ['image', 'font'].includes(request.destination),
  new CacheFirst({
    cacheName: 'media',
    plugins: [new ExpirationPlugin({ maxEntries: 150, maxAgeSeconds: 30 * 86400, purgeOnQuotaError: true })],
  }),
)

// App shell
registerRoute(({ request }) => request.mode === 'navigate', new StaleWhileRevalidate({ cacheName: 'shell' }))

setDefaultHandler(new NetworkOnly())
```

`purgeOnQuotaError: true` matters more than it looks: when a device runs low on
storage the browser starts evicting, and without it a quota error can leave a
cache in a state that breaks every subsequent request.

## The update lifecycle

This is where most PWAs fail in a way that is invisible in testing and obvious in
production.

**The failure**: a service worker that calls `self.skipWaiting()` unconditionally
on install. A user has the app open. You deploy. The new worker downloads and
immediately evicts the active one. The page is still running the *old* JS, which
then requests a lazy chunk the new precache no longer contains — white screen, or
`Failed to fetch dynamically imported module`. It only affects users who had the
app open during a deploy, so it never reproduces on your machine.

Frappe HR's own `sw.js` ends with a bare `self.skipWaiting()`. Many production
PWAs do. Do not copy it.

**The fix** — the worker waits until the app says go:

```js
// sw.js
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting()
})
self.addEventListener('activate', () => clientsClaim())
```

```js
// app
import { registerSW } from 'virtual:pwa-register'   // vite-plugin-pwa

let apply
export const updateReady = ref(false)

export function initPWA() {
  apply = registerSW({
    immediate: true,
    onNeedRefresh() { updateReady.value = true },
    onOfflineReady() { /* optional one-time toast */ },
    onRegisteredSW(url, reg) {
      // check hourly — a long-lived installed app otherwise never learns about updates
      reg && setInterval(() => reg.update(), 60 * 60 * 1000)
    },
  })
}

export const applyUpdate = () => apply?.(true)
```

Then render a persistent, dismissible bar: *"A new version is available —
Reload"*. Rules:

- **Never auto-reload while the user is doing something.** Mid-form, mid-scroll,
  mid-upload — never.
- Auto-applying on a genuinely idle transition (app returns to foreground, no
  unsaved state, no open overlay) is reasonable and feels magical when it works.
- Guard `controllerchange` against reload loops with a boolean.
- **The periodic `reg.update()` is not optional for installed apps.** Without a
  navigation, a home-screen app can run an old worker for weeks.

## Local-first data

Cached HTTP responses make an app *tolerate* being offline. A local database makes
it feel *native*.

The model: **the UI reads and writes the local store only.** A sync process moves
changes to and from the server. The user never waits on a network round-trip to
see the result of their own action.

```
  UI  ⇄  local store (IndexedDB)  ⇄  sync engine  ⇄  server
        ^ synchronous, same frame     ^ async, retrying, invisible
```

Options, roughly by weight:

| Tool | Use when |
|---|---|
| **idb-keyval** | Simple key/value caching of responses. What frappe-ui's `cacheKey` uses. Start here. |
| **Dexie.js** | You need queries, indexes and transactions over structured data, without a sync protocol |
| **RxDB / PouchDB** | You want replication built in and can run a compatible backend |
| **TinyBase / Verdant / Yjs** | Collaborative or multi-device editing with CRDT conflict resolution |
| **SQLite via WASM (OPFS)** | Genuinely relational offline data, complex local queries |

**Do not reach for a CRDT because it sounds rigorous.** Most business apps need
"the server wins, and tell the user when their edit was rejected". That is a
timestamp comparison and a dialog, not a distributed-systems problem.

### Write queue

The minimum honest implementation:

```js
// every mutation becomes a durable, idempotent record
async function enqueue(op) {
  await db.outbox.add({
    id: crypto.randomUUID(),          // idempotency key the server dedupes on
    op,                               // { type, url, method, body }
    baseVersion: op.body?.modified,   // for stale-write detection
    attempts: 0,
    createdAt: Date.now(),
  })
  applyOptimistically(op)             // UI updates now, marked pending
  void flush()
}

async function flush() {
  if (!navigator.onLine) return
  for (const item of await db.outbox.orderBy('createdAt').toArray()) {
    try {
      const res = await send(item)
      await db.outbox.delete(item.id)
      reconcile(item, res)            // replace the optimistic row with the server's
    } catch (err) {
      if (isConflict(err)) { await surfaceConflict(item, err); await db.outbox.delete(item.id) }
      else if (isFatal(err)) { await markFailed(item, err) }   // visible, not silent
      else { await db.outbox.update(item.id, { attempts: item.attempts + 1 }) }
      break                            // preserve order; stop on first failure
    }
  }
}

window.addEventListener('online', flush)
document.addEventListener('visibilitychange', () => !document.hidden && flush())
```

Non-negotiables:

- **Idempotency key per operation**, echoed to the server, so a retry after an
  ambiguous timeout does not create a duplicate record. Without it, "your order
  was submitted three times" is a matter of when, not if.
- **Preserve order.** Stop on the first failure rather than skipping ahead;
  operations usually depend on each other.
- **Send the base version** and let the server reject stale writes. Last-write-wins
  silently destroying a colleague's edit is the worst possible outcome, and it is
  the default if you do nothing.
- **Failures must be visible.** A queue that silently accumulates poison messages
  is worse than refusing the write. Cap attempts, then surface it with a way to
  retry or discard.
- **Bound the queue.** Refuse new writes past a limit and say so.

### Background Sync

```js
// app
const reg = await navigator.serviceWorker.ready
if ('sync' in reg) await reg.sync.register('outbox-flush')

// sw.js
self.addEventListener('sync', (event) => {
  if (event.tag === 'outbox-flush') event.waitUntil(flushFromServiceWorker())
})
```

Chromium only. **Not supported in Safari**, and iOS suspends background JS within
seconds of backgrounding regardless. So: Background Sync is an *enhancement*. The
`online` + `visibilitychange` flush above is the baseline that must work
everywhere, and on iOS it is the only thing that works.

## Storage durability

- **Safari's ITP evicts CacheStorage and IndexedDB after 7 days of inactivity** for
  sites that are *not* installed to the Home Screen. Once installed, that relaxes.
  On iOS the install prompt is what makes offline data survive a long weekend.
- Request persistence where it exists:

```js
if (navigator.storage?.persist) {
  const granted = await navigator.storage.persist()
  // Chromium grants based on engagement/install heuristics; Firefox may prompt
}
```

- **Know your budget**: `navigator.storage.estimate()` returns `{ usage, quota }`.
  Check it before caching a large dataset, and handle `QuotaExceededError` — it is
  a normal condition on a full phone, not an exceptional one.
- Have an eviction policy of your own. If cached data vanishes, the app must
  refetch gracefully, not show empty screens as if the data was deleted.

## Security

- **Never cache authenticated responses on a shared device without clearing on
  logout.** On a warehouse tablet this is how one user sees another's data.

```js
export async function purgeAll() {
  if ('caches' in window) {
    for (const k of await caches.keys()) await caches.delete(k)
  }
  if (window.indexedDB?.databases) {
    for (const { name } of await indexedDB.databases()) name && indexedDB.deleteDatabase(name)
  }
  localStorage.clear()
  sessionStorage.clear()
}
```

- **Do not put tokens in `localStorage`** if you can use an httpOnly cookie. If you
  must, keep them in memory and accept re-auth on reload.
- **Never cache a response with a `Set-Cookie`** or any auth endpoint.
- **A service worker can read every response on its origin.** Treat `sw.js` as
  privileged code: review it like server code, and never `importScripts` from a
  third-party origin.
- Encrypting IndexedDB with a key that also lives in the browser buys very little.
  The real control is not storing what you do not need.

## Telling the user the truth

The UX half of offline, and the half that is usually skipped:

- **A persistent banner while offline**, not a toast. The user needs to know
  *while* reading stale data.
- **Say when data was last refreshed** on any screen where staleness has
  consequences. "Updated 14 minutes ago" prevents an argument with a customer.
- **Mark pending writes visibly** — a dot, a "Sending…" label. They must be able
  to see what has not landed.
- **Distinguish offline from error.** They are different problems with different
  user actions.
- **`navigator.onLine` only knows about the network interface**, not whether your
  server is reachable. Treat a failed request as the stronger signal.
- **Do not claim more than you shipped.** "Works offline" that means "reads work,
  writes are lost" is the fastest way to lose a field team's trust — and they will
  find out on the worst possible day.
