/// <reference lib="webworker" />
// sw.ts — production service worker (Workbox 7 via vite-plugin-pwa injectManifest).
import { cleanupOutdatedCaches, createHandlerBoundToURL, matchPrecache, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute, setCatchHandler } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { CacheableResponsePlugin } from 'workbox-cacheable-response';
import * as navigationPreload from 'workbox-navigation-preload';
import { clientsClaim } from 'workbox-core';
import { flush, SYNC_TAG } from './pwa/outbox';

declare let self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<string | { url: string; revision: string | null }> };

/** 'spa' = serve the precached shell for every navigation (instant, app-like).
 *  'mpa' = network-first HTML with navigation preload + offline page (SSR / multi-page sites). */
const NAV_MODE: 'spa' | 'mpa' = 'spa';
const OFFLINE_URL = '/offline.html';
const NEVER_CACHE = [/^\/api\/auth\//, /^\/api\/session/, /\/logout/];   // auth & session stay network-only

// ---------- Lifecycle ----------
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();  // sent by updateSW(true) after the user taps "Reload"
});
clientsClaim();
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);                            // hashed build assets + index.html + offline.html

// ---------- Navigations ----------
if (NAV_MODE === 'spa') {
  registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html'), {
    denylist: [/^\/api\//, /^\/share-target/, /\/[^/?]+\.[^/]+$/],  // APIs, POST targets, files
  }));
} else {
  navigationPreload.enable();                                     // HTML request starts while SW boots
  registerRoute(new NavigationRoute(new NetworkFirst({
    cacheName: 'pages',
    networkTimeoutSeconds: 3,                                      // flaky 3G → fall back to cache fast
    plugins: [new CacheableResponsePlugin({ statuses: [200] }), new ExpirationPlugin({ maxEntries: 50 })],
  })));
}

// ---------- Runtime caching ----------
registerRoute(
  ({ request, sameOrigin }) => sameOrigin && (request.destination === 'style' || request.destination === 'script' || request.destination === 'worker'),
  new StaleWhileRevalidate({ cacheName: 'assets' }),
);
registerRoute(
  ({ request }) => request.destination === 'image',
  new CacheFirst({
    cacheName: 'images',
    plugins: [
      new CacheableResponsePlugin({ statuses: [0, 200] }),
      new ExpirationPlugin({ maxEntries: 250, maxAgeSeconds: 30 * 86400, purgeOnQuotaError: true }),
    ],
  }),
);
registerRoute(
  ({ url }) => url.origin === 'https://fonts.googleapis.com',
  new StaleWhileRevalidate({ cacheName: 'font-css' }),
);
registerRoute(
  ({ url }) => url.origin === 'https://fonts.gstatic.com',
  new CacheFirst({
    cacheName: 'font-files',
    plugins: [new CacheableResponsePlugin({ statuses: [0, 200] }), new ExpirationPlugin({ maxEntries: 30, maxAgeSeconds: 365 * 86400 })],
  }),
);
registerRoute(
  ({ url, request, sameOrigin }) => sameOrigin && request.method === 'GET' && url.pathname.startsWith('/api/') && !NEVER_CACHE.some((r) => r.test(url.pathname)),
  new NetworkFirst({
    cacheName: 'api',
    networkTimeoutSeconds: 4,
    plugins: [new CacheableResponsePlugin({ statuses: [200] }), new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 7 * 86400, purgeOnQuotaError: true })],
  }),
);

// ---------- Offline fallbacks ----------
setCatchHandler(async ({ request }) => {
  if (request.destination === 'document') return (await matchPrecache(OFFLINE_URL)) ?? Response.error();
  if (request.destination === 'image') {
    return new Response('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3"><rect width="4" height="3" fill="#8884"/></svg>',
      { headers: { 'content-type': 'image/svg+xml' } });
  }
  return Response.error();
});

// ---------- Share target (manifest share_target, POST multipart) ----------
registerRoute(
  ({ url, request }) => url.pathname === '/share-target' && request.method === 'POST',
  async ({ request }) => {
    const form = await request.formData();
    const cache = await caches.open('shared-files');
    const files = form.getAll('media').filter((f): f is File => f instanceof File);
    await Promise.all(files.map((f, i) => cache.put(`/shared/${Date.now()}-${i}`, new Response(f, { headers: { 'content-type': f.type, 'x-filename': encodeURIComponent(f.name) } }))));
    const q = new URLSearchParams({ title: String(form.get('title') ?? ''), text: String(form.get('text') ?? ''), url: String(form.get('url') ?? ''), files: String(files.length) });
    return Response.redirect(`/?share=1&${q}`, 303);
  },
  'POST',
);

// ---------- Background Sync (Chromium). Other browsers flush from the page (outbox.ts) ----------
self.addEventListener('sync', (event: Event & { tag?: string; waitUntil?: (p: Promise<unknown>) => void }) => {
  if (event.tag !== SYNC_TAG) return;
  event.waitUntil?.(flush().then(async () => {
    for (const c of await self.clients.matchAll({ type: 'window' })) c.postMessage({ type: 'OUTBOX_FLUSHED' });
  }));
});

// ---------- Push: accepts Declarative Web Push (Safari 18.4+) JSON AND legacy flat JSON ----------
// Server payload (send this shape everywhere):
// { "web_push": 8030, "notification": { "title": "…", "body": "…", "navigate": "https://app/x", "tag": "…", "app_badge": "3" } }
self.addEventListener('push', (event) => {
  event.waitUntil((async () => {
    let data: any = {};
    try { data = event.data?.json() ?? {}; } catch { data = { notification: { title: 'New activity', body: event.data?.text() } }; }
    const n = data.notification ?? data;
    await self.registration.showNotification(n.title ?? 'New activity', {
      body: n.body, tag: n.tag, lang: n.lang, dir: n.dir, silent: n.silent, requireInteraction: n.require_interaction,
      icon: n.icon ?? '/pwa-192x192.png',
      badge: n.badge ?? '/pwa-96x96.png',                       // Android status-bar glyph (monochrome works best)
      data: { url: n.navigate ?? n.url ?? '/' },
    } as NotificationOptions);
    const badge = Number(n.app_badge);
    const nav = self.navigator as WorkerNavigator & { setAppBadge?: (n?: number) => Promise<void> };
    if (Number.isFinite(badge) && nav.setAppBadge) await nav.setAppBadge(badge);
  })());                                                          // ALWAYS show a notification: silent pushes get the subscription revoked
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL(event.notification.data?.url ?? '/', self.location.origin).href;
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const win = wins.find((w) => new URL(w.url).origin === self.location.origin) as WindowClient | undefined;
    if (win) { await win.focus(); await win.navigate(target).catch(() => win.postMessage({ type: 'NAVIGATE', url: target })); return; }
    await self.clients.openWindow(target);
  })());
});

self.addEventListener('pushsubscriptionchange', (event: Event & { waitUntil?: (p: Promise<unknown>) => void }) => {
  // Re-subscribe and tell the server (keys rotate / subscriptions expire).
  event.waitUntil?.(self.clients.matchAll({ type: 'window' }).then((cs) => cs.forEach((c) => c.postMessage({ type: 'PUSH_RESUBSCRIBE' }))));
});
