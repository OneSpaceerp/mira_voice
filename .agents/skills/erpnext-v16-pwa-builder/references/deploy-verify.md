# Deploy and verify

Getting the app onto a real site, and the checks that catch the failures that
actually happen.

## Ship

```bash
# on the server bench
bench get-app https://github.com/nsd-eg/my_pwa.git
bench --site erp.client.com install-app my_pwa
bench --site erp.client.com migrate
bench build --app my_pwa                 # runs frontend's yarn build via package.json
bench --site erp.client.com clear-cache
bench restart
```

On an existing install, an update is:

```bash
bench update --apps my_pwa --no-backup=false
# or, explicitly:
cd apps/my_pwa && git pull
bench setup requirements --app my_pwa
bench build --app my_pwa
bench --site erp.client.com migrate
bench --site erp.client.com clear-cache && bench restart
```

Two things about `bench build --app my_pwa`: it needs **Node ≥24** and it needs
`frontend/node_modules` — the app-root `package.json` `postinstall` script is what
makes `yarn install` at the bench root reach into `frontend/`. On a low-RAM VPS
(the usual 2 GB ERPNext box) a Vite build of a frappe-ui app can OOM; either build
locally and commit the artifacts to a deploy branch, or give node more headroom:

```bash
NODE_OPTIONS=--max-old-space-size=2048 bench build --app my_pwa
```

## Serving requirements

- **HTTPS is mandatory.** No service worker, no install, no push, no geolocation,
  no camera over plain HTTP. `localhost` is the only exception. `bench setup
  lets-encrypt <site>` or terminate TLS at your proxy.
- **Do not let nginx cache the www page.** `no_cache = 1` in `get_context` handles
  Frappe's own cache, but an aggressive proxy cache in front will hand a stale
  CSRF token to a new session. Exclude `/my-pwa` and `/my-pwa/*` from proxy
  caching.
- **Long-cache the hashed assets.** `/assets/my_pwa/frontend/*` filenames are
  content-hashed; a one-year immutable cache is correct and makes repeat loads
  instant. `/assets/my_pwa/frontend/sw.js` and `manifest.webmanifest` must
  **not** be long-cached — cap them at a few minutes, or users never receive
  updates.

```nginx
location ^~ /assets/my_pwa/frontend/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
    try_files $uri =404;
}
location = /assets/my_pwa/frontend/sw.js {
    add_header Cache-Control "no-cache";
    add_header Service-Worker-Allowed "/my-pwa/";
    try_files $uri =404;
}
location = /assets/my_pwa/frontend/manifest.webmanifest {
    add_header Cache-Control "no-cache";
    try_files $uri =404;
}
```

- **Websockets must be proxied** for realtime to work in production
  (`/socket.io/` → the node socketio port). Frappe's generated nginx config does
  this; a hand-written or containerised proxy often does not.

## Verification checklist

Work it top to bottom. Each line has caught a real production break.

### Build and routing

- [ ] `bench --site <site> migrate` exits clean, no pending patches
- [ ] `bench build --app my_pwa` exits clean; `my_pwa/public/frontend/index.html`
      and `my_pwa/www/<route>.html` both exist and have today's timestamp
- [ ] `curl -sI https://site/my-pwa` → 200, `Content-Type: text/html`
- [ ] Deep link works: paste `https://site/my-pwa/orders/SO-0001` in a fresh tab
      → the app loads that screen, not a Frappe 404 (this tests
      `website_route_rules`, not vue-router)
- [ ] Browser refresh on any inner route does not 404
- [ ] No 404s in the Network tab for `/assets/my_pwa/frontend/*`

### Session and data

- [ ] View source in production: `window.csrf_token` is a hex string, not the
      literal `{{ csrf_token }}`
- [ ] Log in through the app; a write succeeds (no `CSRFTokenError`)
- [ ] Log out → back button does not resurrect the previous session's data
- [ ] A user *without* the app's role sees the domain-gate screen, not a blank
      dashboard or a raw traceback
- [ ] Call one list endpoint as a low-privilege user and confirm it returns only
      their rows (this is the `get_all` vs `get_list` check — do it by hand, with
      curl, at least once per app)
- [ ] Realtime: change a record in Desk, the open SPA list updates

### PWA

- [ ] Chrome DevTools → Application → Manifest: no errors; icons resolve;
      "Installability" green
- [ ] Application → Service Workers: one worker, status **activated**, scope
      `/my-pwa/` (not `/assets/…`)
- [ ] Install to home screen on a real Android phone and a real iPhone
- [ ] Installed app opens **standalone** — no URL bar, no Safari toolbar
- [ ] Bottom navigation clears the iOS home indicator; header clears the notch
- [ ] Cold start shows your splash, not a white flash (iOS: means the
      `apple-touch-startup-image` tags matched)
- [ ] Airplane mode → relaunch: shell renders, previously-opened list shows cached
      rows, a write fails with a visible message (not a silent no-op)
- [ ] Deploy a new build while a session is open: an update bar appears, nothing
      white-screens, reloading picks up the new version
- [ ] Push: permission prompt appears only after the user opts in; a test
      notification arrives on Android; on iOS-in-Safari the toggle is hidden with
      an explanation

### Performance and polish

- [ ] Lighthouse (mobile, throttled) — PWA installable, Performance ≥ 80,
      Accessibility ≥ 90
- [ ] First load on simulated Slow 4G under ~3 s to interactive
- [ ] `manualChunks` splits frappe-ui out; no single chunk over ~500 KB gzipped
- [ ] Tap targets ≥ 44 px; no horizontal scroll at 360 px width
- [ ] Every user-facing string goes through `__()`; switch site language and spot
      check
- [ ] RTL (if targeting Arabic): `dir="rtl"` on `<html>` does not break the shell

## The five failures that actually happen

**1. Stale bundle after deploy.** Someone committed `public/frontend/` or forgot
`bench build`. Symptom: new code invisible, or a chunk 404. Fix: gitignore the
build outputs, make `bench build --app` part of the deploy script, and check the
`index.html` timestamp.

**2. Service worker scoped to `/assets/…`.** The app "has no service worker"
despite the file existing. Symptom: nothing works offline, install prompt never
fires. Fix: register with `{ scope: '/my-pwa/' }` + the `Service-Worker-Allowed`
header, or serve `sw.js` from the app route.

**3. `skipWaiting()` mid-session white screens.** Only affects users who had the
app open during a deploy, so it never reproduces on your machine. Fix: the waiting
lifecycle in `pwa-runtime.md`.

**4. `frappe.get_all` in a whitelisted endpoint.** Every user sees every row. It
passes every test you wrote as Administrator. Fix: `get_list`, and one manual
curl as a low-privilege user before go-live.

**5. CSRF failures on first write after idle.** Usually a proxy caching the www
page, or `frappe.db.commit()` missing after `get_csrf_token()`. Fix: both of the
above.

## Handing over

Ship these with the app, not in your head:

- `README.md` with the frappe-ui track you chose and why, the dev loop, and the
  build command.
- The nginx snippet above, because the next person to move the site will not know
  about `Service-Worker-Allowed`.
- A `site_config.json` key list the app depends on (`push_relay_server_url`,
  `socketio_port`, any feature flags).
- The Firebase project owner and where the service account lives, if you used
  push.
- Which of the three offline layers you actually shipped (see `data-layer.md`) —
  written down, so nobody promises a client that writes work offline when they
  don't.
