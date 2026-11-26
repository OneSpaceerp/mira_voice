# Service worker for a Frappe site

The dangerous piece. A worker at origin scope intercepts **every** request to
Desk, the website, every app, and the REST API. Get the strategy wrong and you
break the site for users in a way that survives a redeploy, because their browser
keeps serving your stale cache.

## Read this before writing a line

`Monogramm/frappe_pwa`'s service worker — the one most Frappe PWA tutorials copy —
does **stale-while-revalidate on every GET, including Desk bundles**. It also
precaches `/`, `/assets/frappe/js/lib/…` and `frappe-web.min.js` by name.

That was reasonable for a 2021 portal. On a modern ERPNext it is a liability:

- Frappe's Desk assets are cache-busted by a **query string** (`?ver=…`), not a
  content hash, and `bench build` replaces the files at the same paths. A
  stale-while-revalidate cache serves the previous build to every user on their
  first load after a deploy — so the first paint after every deploy runs old JS
  against a new server.
- The precache list is hardcoded filenames. When Frappe renames a bundle, the
  install step's `cache.addAll` rejects, and (in that implementation) the failure
  is swallowed — you get a worker that installs successfully and caches nothing.
- Caching `/` while logged in stores an authenticated HTML page in a cache that
  outlives logout.

So: **network-first for anything dynamic, and do not touch the API.** Below is a
worker that is safe on a live ERPNext.

## A conservative worker

```js
// site_pwa/www/sw.js  (a Jinja template — see below for why)
const VERSION = '{{ sw_version }}'
const STATIC_CACHE = `site-pwa-static-v${VERSION}`
const PAGE_CACHE = `site-pwa-pages-v${VERSION}`
const OFFLINE_URL = '/offline'

// Only things that are genuinely immutable or that we own.
const PRECACHE = [OFFLINE_URL, '/manifest.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((c) => c.addAll(PRECACHE))
      .catch((err) => console.error('[SW] precache failed', err)),   // visible, not swallowed
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== STATIC_CACHE && k !== PAGE_CACHE).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting()
})

function isApi(url) {
  return url.pathname.startsWith('/api/') || url.pathname.startsWith('/private/')
}

function isAuthEndpoint(url) {
  return /\/api\/method\/(login|logout)/.test(url.pathname)
}

// Content-hashed app assets only — NOT /assets/frappe/ (query-string versioned).
// Vite/Rollup hashes are base-62-ish, not hex, so match on shape not charset.
function isImmutableAsset(url) {
  if (url.search) return false                     // a ?ver= means it is NOT content-hashed
  return /\/assets\/[^/]+\/(frontend|dist)\/.+[.-][A-Za-z0-9_-]{8,}\.(js|css|woff2?|png|svg|jpe?g|avif|webp)$/
    .test(url.pathname)
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Hard exclusions. Everything here goes straight to the network, untouched.
  if (request.method !== 'GET') return
  if (url.origin !== self.location.origin) return
  if (isApi(url) || isAuthEndpoint(url)) return
  if (url.pathname.startsWith('/socket.io/')) return
  if (request.headers.get('range')) return          // media range requests

  // 1. Immutable hashed assets: cache-first, safe because the name changes on change.
  if (isImmutableAsset(url)) {
    event.respondWith(
      caches.match(request).then((hit) =>
        hit || fetch(request).then((res) => {
          if (res.ok) caches.open(STATIC_CACHE).then((c) => c.put(request, res.clone()))
          return res
        }),
      ),
    )
    return
  }

  // 2. Navigations: network-first, fall back to the cached page, then the offline page.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) caches.open(PAGE_CACHE).then((c) => c.put(request, res.clone()))
          return res
        })
        .catch(async () =>
          (await caches.match(request)) ||
          (await caches.match(OFFLINE_URL)) ||
          new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } }),
        ),
    )
    return
  }

  // 3. Everything else (including /assets/frappe/*): network-first, cache as fallback only.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok && res.type === 'basic') {
          caches.open(STATIC_CACHE).then((c) => c.put(request, res.clone()))
        }
        return res
      })
      .catch(() => caches.match(request)),
  )
})
```

What each decision buys you:

- **`request.method !== 'GET'` → return early.** Returning without calling
  `respondWith` hands the request to the browser untouched. Every write, every
  login, every file upload bypasses the worker entirely.
- **`isApi` exclusion.** No authenticated JSON in any cache, so logout has nothing
  to leak. If you later want offline reads, add a *narrow, explicit* allowlist of
  specific read-only endpoints — never a prefix match on `/api/`.
- **Network-first for navigations** means a deploy is picked up on the next load
  when online, and the user still gets something when offline.
- **Cache-first only for content-hashed filenames.** The regex deliberately
  excludes `/assets/frappe/…?ver=` because those are not content-hashed.
- **Cleanup on activate** keyed on `VERSION` is how you invalidate everything at
  once.

## Versioning the worker

Bump `VERSION` and every cache name changes, so `activate` drops the old ones.
Render it from a Single so it can be bumped without a deploy:

```python
# site_pwa/www/sw.py
import frappe

no_sitemap = 1
no_cache = 1
base_template_path = "templates/www/sw.js"


def get_context(context):
	sw = frappe.get_cached_doc("Service Worker")
	context.sw_version = sw.version or 1
	return context
```

Serve it with the right headers or browsers will cache the worker itself:

```nginx
location = /sw.js {
    add_header Cache-Control "no-cache, no-store, must-revalidate";
    add_header Service-Worker-Allowed "/";
    proxy_pass http://frappe;
}
```

A `Service Worker` Single with an `Increment version` button that bumps and clears
website cache gives the admin a working "force everyone to refresh" lever —
genuinely useful during a rollout.

## Registration

```js
// site_pwa/public/js/register-sw.js  → bundled into pwa.bundle.js
if ('serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' })

      reg.addEventListener('updatefound', () => {
        const installing = reg.installing
        if (!installing) return
        installing.addEventListener('statechange', () => {
          // "installed" + an existing controller == an update, not a first install
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            showUpdateBar(() => {
              installing.postMessage({ type: 'SKIP_WAITING' })
            })
          }
        })
      })

      let reloading = false
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (reloading) return
        reloading = true
        window.location.reload()
      })
    } catch (err) {
      console.error('[PWA] SW registration failed', err)
    }
  })
}
```

The `reloading` guard on `controllerchange` is not optional — without it, a
worker that claims clients can trigger a reload loop.

Serving `/sw.js` from a www page means its scope is `/` by default and the
`Service-Worker-Allowed` header is belt-and-braces.

## Clearing on logout

Frappe's logout is a page navigation, so hook it client-side:

```js
// in pwa.bundle.js, on the Desk/portal
frappe.router?.on?.('change', () => {})   // no-op; kept for context

async function purgeOnLogout() {
  if (!('caches' in window)) return
  for (const key of await caches.keys()) await caches.delete(key)
  const reg = await navigator.serviceWorker?.getRegistration()
  await reg?.unregister()      // optional but decisive on shared devices
}

// Desk exposes a logout hook; on the portal, intercept the logout link.
document.addEventListener('click', (e) => {
  const a = e.target.closest('a[href="/?cmd=web_logout"], a[href*="logout"]')
  if (a) purgeOnLogout()
}, true)
```

On a shared device, unregistering is the safest choice; the next login
re-registers on load.

## Removability

Ship a kill switch. If the worker misbehaves in production you need a way to
neutralise it that does not require every user to clear site data:

```js
// deploy this as /sw.js to disable the PWA layer entirely
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', async () => {
  for (const k of await caches.keys()) await caches.delete(k)
  await self.registration.unregister()
  const clients = await self.clients.matchAll()
  clients.forEach((c) => c.navigate(c.url))
})
```

Keep this file in the repo with a note. The day you need it, you will need it
urgently.

## Testing it properly

Manual checks that actually catch problems:

1. Install, then run `bench build` on the server and reload. You must get the new
   assets. (This is the rule-1 test.)
2. DevTools → Application → Service Workers → check **Offline**, then navigate.
   You should see the offline page, not a broken Desk.
3. Log in as A, log out, log in as B. `caches.keys()` and the Network tab should
   show nothing of A's.
4. DevTools → Application → Storage → look at cache size after a week of use. If
   it is growing without bound, your cache has no expiry — add one, or restrict
   what goes in.
5. Unregister the worker and confirm the site behaves normally.
