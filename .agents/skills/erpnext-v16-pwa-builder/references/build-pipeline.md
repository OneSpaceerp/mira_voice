# Build pipeline

How the Vue app becomes a page Frappe serves. Get this wrong and everything else
works in dev and 404s in production.

## The contract

```
frontend/          →  vite build  →  my_pwa/public/frontend/   (assets, base=/assets/my_pwa/frontend/)
                                  →  my_pwa/www/my-pwa.html    (a copy of the built index.html)
```

Three values must agree or the app loads a blank page:

| Value | Must be |
|---|---|
| Vite `base` | `/assets/<app>/<outdir-leaf>/` — how Frappe serves `public/` |
| Vite `build.outDir` | `../<app>/public/<outdir-leaf>` |
| Copied `index.html` destination | `../<app>/www/<www-page-name>.html` |

and `<www-page-name>` must be the `to_route` in `website_route_rules`.

---

## Track B (default) — frappe-ui 1.x, plugin does the wiring

`frappe-ui/vite` computes `base`, `outDir` and the html copy from one option.

### `package.json`

```json
{
  "name": "my-pwa-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "frappe-ui": "beta",
    "vue": "^3.5.12",
    "vue-router": "^4.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^6",
    "autoprefixer": "^10.4",
    "postcss": "^8.4",
    "tailwindcss": "^3.4",
    "vite": "^7",
    "vite-plugin-pwa": "^1.3",
    "workbox-core": "^7.4",
    "workbox-precaching": "^7.4",
    "workbox-routing": "^7.4",
    "workbox-strategies": "^7.4",
    "workbox-expiration": "^7.4"
  }
}
```

`vite-plugin-pwa` is at **1.x** now (peers: `workbox-build`/`workbox-window`
`^7.4.1`, Vite 3–8). Frappe HR v16 pins `^0.20.5`; the config shape below is
compatible with both, but on Track A do not upgrade the plugin without also
re-testing the service worker, since `registerType` and `injectRegister`
defaults changed.

**Tailwind must be v3.** `npm create vite` now scaffolds Tailwind v4, which ignores
the v3-shaped preset frappe-ui ships — the design tokens then silently never load
and every `bg-surface-*` class is a no-op. If you scaffolded with the default:

```bash
npm uninstall tailwindcss @tailwindcss/vite
npm i -D tailwindcss@^3.4 postcss autoprefixer
```

Do **not** install `unplugin-icons`, `unplugin-auto-import`, `unplugin-vue-components`
or `lucide-static` — they are already frappe-ui dependencies and its vite plugin
wires them.

### `vite.config.js`

```js
import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    frappeui({
      frontendRoute: '/my-pwa',        // drives base, outDir and www/my-pwa.html
      frappeTypes: {                    // optional: DocType JSON → TS interfaces
        input: { my_pwa: ['My Order', 'My Order Item'] },
        output: 'src/types/doctypes.ts',
      },
    }),
    vue(),
    VitePWA({ /* see pwa-runtime.md */ }),
  ],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
})
```

`frontendRoute: '/my-pwa'` makes the plugin infer
`indexHtmlPath = '../my_pwa/www/my-pwa.html'`, so `website_route_rules` must use
`"to_route": "my-pwa"` and the controller beside it is `www/my_pwa.py` (Frappe
pairs them by replacing `-` with `_`). To choose a different page name, or to turn
sourcemaps back on, pass `buildConfig` explicitly:

```js
frappeui({
  frontendRoute: '/my-pwa',
  buildConfig: {
    indexHtmlPath: '../my_pwa/www/mobile.html',   // then to_route is "mobile"
    sourcemap: false,                              // the plugin's default since #909
  },
})
```

**Plugin order matters when `VitePWA` is in the list.** `frappeui()` must come
first: its `buildConfig` sets `base` and `outDir` during `config`, and
`vite-plugin-pwa` reads `base` to compute the service worker's scope and the
precache manifest's URLs. Put `VitePWA` before it and you get a precache manifest
pointing at `/` instead of `/assets/my_pwa/frontend/`. Both of them transform
`index.html`; `buildConfig` copies the **final** file on `writeBundle`, so the
copy already contains the PWA tags.

What each sub-plugin does (all on by default except `frappeTypes`):

| Sub-plugin | Effect |
|---|---|
| `frappeProxy` | Dev server proxies `/api`, `/app`, `/assets`, `/files`, `/private`, `/login` to the bench, reading the port from `sites/common_site_config.json`, with per-host routing so multi-site benches work |
| `jinjaBootData` | Injects, **into the production build only**, a Jinja loop that writes every `context.boot` key onto `window` |
| `buildConfig` | Sets `base`, `outDir`, and copies `index.html` to `www/` on `writeBundle` |
| `lucideIcons` | `~icons/lucide/*` resolution and auto-import of `<LucideArrowRight />` |
| `barrelImports` | Resolves `import { Button } from 'frappe-ui'` to the declaring module, so dev never serves the whole barrel |
| `siteBanner` | Prints clickable dev URLs for every site the app is installed on |
| `frappeTypes` | Generates TS interfaces from DocType JSON, regenerating only on change |

**`jinjaBootData` changes how you read boot.** It writes each key to `window`
directly, so it's `window.csrf_token`, `window.site_name`, `window.socketio_port`
— *not* `window.frappe.boot.*`. If you are porting Frappe HR code, that's the one
line to change. To keep the HRMS shape instead, disable `jinjaBootData: false` and
write the script tag yourself (Track A below).

Prototyping with no Frappe backend at all:
`frappeui({ frappeProxy: false, jinjaBootData: false, buildConfig: false })`.

### `tailwind.config.js`

```js
import preset, { content } from 'frappe-ui/tailwind'

/** @type {import('tailwindcss').Config} */
export default {
  presets: [preset],
  content: [...content, './index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      screens: { standalone: { raw: '(display-mode: standalone)' } },
      padding: {
        'safe-top': 'env(safe-area-inset-top)',
        'safe-bottom': 'env(safe-area-inset-bottom)',
        'safe-left': 'env(safe-area-inset-left)',
        'safe-right': 'env(safe-area-inset-right)',
      },
    },
  },
}
```

**Spread the exported `content`.** Tailwind v3 does not merge a preset's `content`
into the app config, so frappe-ui's own source globs must be listed by the app.
Hand-copying a `node_modules/frappe-ui/src/**` glob drops `icons/**` and the
utility classes for them never compile.

The `standalone:` variant and `safe-*` padding are the two extensions every mobile
PWA needs; they are not in the preset. See
`erpnext-v16-hrms-style-pwa-builder` for how they are used.

### `src/style.css`

```css
@import 'frappe-ui/style.css';
```

That one import emits `@tailwind base/components/utilities` plus the Inter font.
Adding the directives again emits every Tailwind layer twice.

`@import 'frappe-ui/src/style.css'` fails — anything outside the package `exports`
map is blocked. Same for `frappe-ui/tailwind/preset` (use `frappe-ui/tailwind`).

---

## Track A / C — explicit config (Frappe HR parity)

This is the Frappe HR v16 `vite.config.js`, which predates the plugin doing the
work. Use it on `frappe-ui@0.1.105` + Ionic, or when you want every path visible.

```js
import path from 'path'
import fs from 'fs'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: { port: 8080, proxy: getProxyOptions(), allowedHosts: true },
  plugins: [
    vue(),
    frappeui(),
    VitePWA({ /* see pwa-runtime.md */ }),
  ],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  build: {
    outDir: '../my_pwa/public/frontend',
    emptyOutDir: true,
    target: 'es2015',
    commonjsOptions: { include: [/tailwind.config.js/, /node_modules/] },
    sourcemap: true,
    rollupOptions: { output: { manualChunks: { 'frappe-ui': ['frappe-ui'] } } },
  },
  optimizeDeps: {
    include: ['frappe-ui > feather-icons', 'showdown', 'tailwind.config.js', 'engine.io-client'],
  },
})

function getProxyOptions() {
  const config = getCommonSiteConfig()
  const webserver_port = config ? config.webserver_port : 8000
  return {
    '^/(app|login|api|assets|files|private)': {
      target: `http://127.0.0.1:${webserver_port}`,
      ws: true,
      router: (req) => `http://${req.headers.host.split(':')[0]}:${webserver_port}`,
    },
  }
}

function getCommonSiteConfig() {
  let dir = path.resolve('.')
  while (dir !== '/') {
    if (fs.existsSync(path.join(dir, 'sites')) && fs.existsSync(path.join(dir, 'apps'))) {
      const p = path.join(dir, 'sites', 'common_site_config.json')
      return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p)) : null
    }
    dir = path.resolve(dir, '..')
  }
  return null
}
```

with `package.json` scripts doing the `base` and the html copy:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "vite build --base=/assets/my_pwa/frontend/ && yarn copy-html-entry",
    "copy-html-entry": "cp ../my_pwa/public/frontend/index.html ../my_pwa/www/my-pwa.html"
  }
}
```

`cp` is not portable to a Windows dev box. If anyone on the team builds on Windows,
replace it with a two-line Node script:

```js
// frontend/copy-entry.js  →  "copy-html-entry": "node copy-entry.js"
import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
const dest = '../my_pwa/www/my-pwa.html'
mkdirSync(dirname(dest), { recursive: true })
copyFileSync('../my_pwa/public/frontend/index.html', dest)
console.log(`copied index.html → ${dest}`)
```

Tailwind config for Track A/C (0.1.x preset path differs):

```js
import frappeUIPreset from 'frappe-ui/src/tailwind/preset'
export default {
  presets: [frappeUIPreset],
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
    './node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}',
    '../node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: { extend: { /* standalone + safe-* as above */ } },
}
```

Both glob roots are needed because yarn may hoist `frappe-ui` to the app root.

---

## `index.html`

The entry is a **Jinja template** in production and a plain file in dev. On Track
A/C you write the boot script yourself:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1.0, viewport-fit=cover, maximum-scale=1.0, user-scalable=no, interactive-widget=resizes-content"
    />
    <title>My PWA</title>

    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="My PWA" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="theme-color" content="#ffffff" />

    <link rel="icon" type="image/png" sizes="196x196" href="/assets/my_pwa/manifest/favicon-196.png" />
    <link rel="apple-touch-icon" href="/assets/my_pwa/manifest/apple-icon-180.png" />
    <!-- apple-touch-startup-image links: generate them, see pwa-runtime.md -->
  </head>
  <body class="antialiased">
    <div id="app"></div>
    <div id="modals"></div>
    <div id="popovers"></div>

    <script>
      window.csrf_token = "{{ csrf_token }}"
      window.site_name = '{{ site_name }}'
      if (!window.frappe) window.frappe = {}
      frappe.boot = {{ boot }}
    </script>

    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- `#modals` and `#popovers` are the teleport targets frappe-ui 0.1.x overlays use.
  Omit them and dialogs render inside the scroll container and clip.
- In **dev**, Vite serves this file raw — `window.csrf_token` is the literal string
  `"{{ csrf_token }}"`. frappe-ui detects and ignores that; your own code must too.
  The dev boot comes from `get_context_for_dev` (see `backend.md`).
- `viewport-fit=cover` + `black-translucent` puts the app edge-to-edge under the
  notch. That is only safe if your layout respects `env(safe-area-inset-*)`.
  Frappe HR uses `content="white"` instead, which is the timid but always-correct
  choice. See `professional-pwa-builder` for the tradeoff.
- `interactive-widget=resizes-content` fixes keyboard-overlap on Chromium 108+ and
  Firefox 132+. WebKit ignores it; the Visual Viewport polyfill is in
  `professional-pwa-builder`.

On **Track B** with `jinjaBootData` enabled, delete the inline `<script>` block —
the plugin appends its own before `</body>` at build time, and the keys land on
`window` directly.

---

## Dev loop

```bash
# terminal 1
bench start

# terminal 2
cd apps/my_pwa/frontend && yarn dev     # http://localhost:8080/my-pwa
```

The proxy forwards `/api`, `/assets`, `/files`, `/login` to the bench, so cookies,
CSRF and websockets work against your real site. Log in once at
`http://localhost:8080/login` and the session cookie carries over.

A few dev-only truths worth knowing before you debug them for an hour:

- **Vite serves `/` , Frappe serves `/my-pwa`.** With `createWebHistory('/my-pwa')`
  you must open `localhost:8080/my-pwa`, not `localhost:8080`.
- **`allowedHosts: true`** is needed if you test on a phone over the LAN or a
  tunnel; Vite 5+ rejects unknown Host headers otherwise.
- **Service workers in dev are a trap.** `vite-plugin-pwa`'s
  `devOptions.enabled: true` is useful for testing the SW, and a liability
  otherwise — a stale dev SW will serve you yesterday's bundle and make you think
  HMR broke. When in doubt: DevTools → Application → Service Workers → Unregister,
  and tick "Update on reload".

## Production build

```bash
cd apps/my_pwa/frontend && yarn build
# or, from the bench root, if package.json scripts delegate:
bench build --app my_pwa
```

Wire the delegation in the **app-root** `package.json` so `bench build` works:

```json
{
  "private": true,
  "name": "my_pwa",
  "scripts": {
    "postinstall": "cd frontend && yarn install --check-files",
    "dev": "cd frontend && yarn dev",
    "build": "cd frontend && yarn build"
  }
}
```

## When it breaks

| Symptom | Cause |
|---|---|
| Blank page, 404s on `/assets/my_pwa/frontend/index-*.js` | `base` doesn't match `outDir`'s leaf, or `bench build` never ran |
| `/my-pwa` shows Frappe's 404 | `website_route_rules` `to_route` ≠ the www page filename, or the html was never copied |
| Page loads, every write fails with `CSRFTokenError` | `www/*.py` missing `frappe.db.commit()` after `get_csrf_token()`, or you're reading `window.frappe.boot.csrf_token` on a Track-B build (it's `window.csrf_token`) |
| `Package subpath './src/style.css' is not defined by "exports"` | frappe-ui 1.x — use `frappe-ui/style.css` and `frappe-ui/tailwind` |
| Every `bg-surface-*` / `text-ink-*` renders unstyled | Tailwind v4 installed, or `content` missing the spread frappe-ui globs |
| `Could not resolve '~icons/lucide/…'` | `frappeui()` plugin absent or `lucideIcons` disabled |
| `injection "Symbol(router)" not found` | `app.use(router)` missing, or a frappe-ui component rendered outside the router |
| Works in dev, styles missing in prod | `tailwind.config.js` not in `build.commonjsOptions.include` (Track A/C) |
| Stale UI after deploy for existing users | Service worker update lifecycle — see `pwa-runtime.md` |
