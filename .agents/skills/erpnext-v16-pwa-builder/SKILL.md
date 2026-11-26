---
name: erpnext-v16-pwa-builder
description: Build, scaffold and ship a decoupled Progressive Web App on Frappe/ERPNext v16 — a Vue 3 + frappe-ui + Vite SPA served from your own Frappe app at its own route, with session auth, the v2 REST API, realtime, offline caching, FCM push and installable PWA runtime. Use when creating a mobile app, field-service tool, employee or customer portal, kiosk, or any "app-like" frontend on top of ERPNext v16, and when wiring www bootloaders, website_route_rules, vite build output or bench build for such an app.
---

# ERPNext v16 PWA Builder

Build the Frappe-native shape of a mobile web app: **one Frappe app** that carries
both the server (DocTypes, whitelisted API, hooks) and a **Vue 3 SPA** under
`frontend/`, built by Vite into `<app>/public/frontend/` and served by a Jinja page
in `<app>/www/`. This is exactly how Frappe HR, Helpdesk, CRM, Gameplan and Drive
are built, and it is the only layout `bench build` and `bench get-app` cooperate with.

This skill covers the **whole app**: backend wiring, build pipeline, data layer,
PWA runtime, deployment. For the mobile look-and-feel (screen archetypes, list and
form UX, navigation shell), use **`erpnext-v16-hrms-style-pwa-builder`**. For
adding a manifest and service worker to the *existing* Desk or website instead of
building an SPA, use **`frappe-desk-pwa`**. For native-grade polish that is not
Frappe-specific (safe areas, gestures, view transitions, store packaging), use
**`professional-pwa-builder`**.

## Decide before you scaffold

**Is an SPA the right shape at all?**

| The user wants | Build |
|---|---|
| A mobile app experience, own navigation, offline, installable | This skill — decoupled SPA |
| Desk, just installable on phones with a manifest and offline shell | `frappe-desk-pwa` — no SPA |
| A few extra fields/buttons inside Desk | Neither. Custom fields + form scripts (`erpnext-app-builder`) |
| A public marketing/portal page | Frappe Website / Web Pages, not an SPA |

**Which frappe-ui track?** This is the one decision that shapes every file. Pick
once, write it in the app's README, do not mix.

| Track | Stack | Choose when |
|---|---|---|
| **B — default** | `frappe-ui@beta` (1.0.x), Tailwind v3, Vite 7, Node ≥20.19 | New apps. Ships `MobileShell`, `MobileNav`, `BottomSheet`, `PageHeaderMobile`, semantic dark-mode tokens, `useCall`/`useList`/`useDoc`, and a vite plugin that does the Frappe wiring for you. |
| **A — Ionic parity** | `frappe-ui@0.1.105` + `@ionic/vue@7` (exact Frappe HR v16 stack) | You need a real native page stack: hardware-accelerated push/pop transitions, swipe-back, `ion-refresher` pull-to-refresh, action sheets — for free, today, without hand-building them. |
| **C — conservative** | `frappe-ui@^0.1.248`, no Ionic | You want a stable 0.1.x API and will hand-build the mobile shell (this is what `marley_frontend` does). |

Track B is the default because the mobile primitives now exist upstream and the
`frappe-ui/vite` plugin removes most of the boilerplate. If 1.0-beta API churn
bites mid-project, **fall back to Track C** (same data layer, same build plugin,
stable components) rather than patching around the beta.

## Non-negotiables for v16

Verified against `frappe/frappe@version-16` and `frappe/erpnext@version-16`:

- **Python `>=3.14,<3.15`.** Frappe v16 pins this exactly; ERPNext v16 requires
  `>=3.14`. Your app's `pyproject.toml` must not claim a lower floor.
  (Ruff's `target-version` is a *syntax* target and is unrelated — ERPNext v16
  still lints at `py310`. Do not "fix" one to match the other.)
- **Node `>=24`** for the bench/Frappe build. The Vite frontend has its own floor
  (frappe-ui 1.x needs ≥20.19); Node 24 satisfies both.
- **`pyproject.toml` with `flit_core`.** No `setup.py`, no `requirements.txt`.
- **Never edit `frappe/` or `erpnext/`.** Everything lives in your app.
- **Every whitelisted method is a public door.** `@frappe.whitelist()` +
  permission check + input validation, every time. See `references/backend.md`.
- **Schema is files, not database rows.** DocType JSON, workspaces and reports
  are committed to git; `bench --site <site> migrate` applies them.
- **Wrap user-facing strings**: `_("…")` in Python, `__("…")` in JS/Vue, from the
  first line. Retrofitting translations into a built SPA is miserable.

## Scaffold

```bash
bench new-app my_pwa                       # canonical Frappe app layout
bench --site dev.local install-app my_pwa
bench --site dev.local set-config developer_mode 1

cd apps/my_pwa
mkdir frontend && cd frontend
npm create vite@latest . -- --template vue
```

Then, in order:

1. `references/backend.md` — `hooks.py` route rules, the `www/` bootloader, the
   API module, permissions.
2. `references/build-pipeline.md` — `vite.config.js`, `tailwind.config.js`,
   `index.html`, the `public/frontend` → `www/<route>.html` handoff, dev proxy.
3. `references/data-layer.md` — session/auth, `useCall`/`useList`/`useDoc` (or
   `createResource`), realtime, file upload, workflow, offline caching.
4. `references/pwa-runtime.md` — manifest, service worker, the **correct** update
   lifecycle, install prompts, push notifications, badging.
5. `references/deploy-verify.md` — build, ship, and the checklist that catches the
   five failures that actually happen.

Build the UI itself with **`erpnext-v16-hrms-style-pwa-builder`**.

## The shape you are aiming for

```
apps/my_pwa/
├── pyproject.toml                 # flit_core, requires-python >=3.14,<3.15
├── package.json                   # thin: scripts that delegate to frontend/
├── frontend/                      # the Vue SPA — a separate npm project
│   ├── index.html                 # the Jinja-flavoured entry (csrf_token, boot)
│   ├── vite.config.js             # base=/assets/my_pwa/frontend/, outDir ../my_pwa/public/frontend
│   ├── tailwind.config.js         # frappe-ui preset + safe-area + standalone variant
│   ├── public/sw.js               # your service worker source (injectManifest)
│   └── src/{main.js,router/,data/,components/,views/,utils/}
└── my_pwa/
    ├── hooks.py                   # website_route_rules → the www page
    ├── api.py                     # whitelisted endpoints for the SPA
    ├── www/
    │   ├── my_pwa.py              # get_context: csrf_token + boot  (committed)
    │   └── my-pwa.html            # BUILD OUTPUT — generated, gitignored
    └── public/
        ├── frontend/              # BUILD OUTPUT — generated, gitignored
        └── manifest/              # icons + apple splash screens (committed)
```

The `.py` / `.html` name mismatch is intentional: Frappe pairs a www template with
its controller by replacing `-` with `_`, so `my-pwa.html` is served by
`my_pwa.py`. A hyphenated Python module would not import.

Two of those paths are **build artifacts**: `my_pwa/www/my-pwa.html` and
`my_pwa/public/frontend/`. Frappe HR gitignores both and regenerates them on every
build. Commit them and you will ship a stale bundle the first time someone forgets
to rebuild.

## Working rules

- **Boot data beats a request waterfall.** `csrf_token`, `site_name`,
  `socketio_port`, translations and the default route all arrive in the first HTML
  response via `get_context`. Do not fetch them.
- **Route the SPA, don't route Frappe.** One `website_route_rules` entry sends
  `/myapp/<path:app_path>` to one www page; `vue-router` owns everything after
  that. `createWebHistory("/myapp")`.
- **Guard on the router, enforce on the server.** `router.beforeEach` decides what
  the user *sees*; `frappe.has_permission` decides what they *get*. A route guard
  is UX, never security.
- **Employee-style gating belongs in the guard.** Frappe HR sends any logged-in
  user who is not an Employee to an `InvalidEmployee` screen instead of a blank
  dashboard. Do the equivalent for your domain entity.
- **Verify each phase before stacking on it.** `bench migrate` clean → `yarn dev`
  proxying → `yarn build` producing `www/<route>.html` → app installable →
  offline reload works. A red console three phases back is unrecoverable guesswork.

## Verify before you call it done

Run `references/deploy-verify.md`'s checklist. The short version, in the order
things actually break:

1. `bench --site <site> migrate` clean, `bench build --app my_pwa` clean.
2. Visiting `/myapp` serves your SPA, not a 404 or the Desk.
3. `window.csrf_token` is a real token in production HTML (not the literal
   `{{ csrf_token }}`) and writes succeed.
4. Installed from the home screen, the app opens **standalone** with no browser
   chrome, and its bottom bar clears the iOS home indicator.
5. Airplane mode → app shell still renders; a cached list still shows rows.
6. Shipping a new build does **not** white-screen an open session (see the update
   lifecycle in `references/pwa-runtime.md` — Frappe HR's own `sw.js` calls
   `self.skipWaiting()` unconditionally, which is the bug you must not copy).
