# Manifest and install

A manifest an admin can edit without a deploy, and an install prompt that works on
both platforms.

## Why a DocType, not a static file

A static `manifest.json` in `public/` means every rebrand, colour change or new
client site is a code change. Rendering it from a Single DocType means the admin
edits it in Desk. `Monogramm/frappe_pwa` established this pattern and it holds up.

### The DocTypes

**`Web App Manifest`** (Single):

| Field | Type | Notes |
|---|---|---|
| `app_name` | Data | required — manifest `name` |
| `short_name` | Data | ≤ 12 chars or launchers truncate it |
| `description` | Small Text | |
| `start_url` | Data | default `/app` for Desk, `/` for a portal |
| `scope` | Data | must contain `start_url` |
| `display` | Select | `standalone` / `fullscreen` / `minimal-ui` / `browser` |
| `orientation` | Select | `any` / `portrait-primary` / `landscape-primary` |
| `theme_color` | Color | must match the top of the rendered page |
| `background_color` | Color | the splash background |
| `lang`, `dir` | Data / Select | `ar` + `rtl` for Arabic deployments |
| `prefer_related_applications` | Check | |
| `icons` | Table → `Web App Manifest Icon` | `src`, `sizes`, `type`, `purpose` |
| `categories` | Table → `Web App Manifest Category` | |
| `screenshots` | Table → `Web App Manifest Screenshot` | drives the richer Android install UI |
| `related_applications` | Table → `…Related Application` | |

Add a `purpose` field on the icon child table (`any` / `maskable` /
`any maskable`). Monogramm's original omits it, which means Android either crops
your logo or pads your icon depending on the launcher. Ship **separate** 192 and
512 files for `any` and for `maskable` — maskable art needs ~20 % safe padding
that looks wrong when used as `any`.

### Rendering it

```python
# site_pwa/www/manifest.py
import json
import frappe

no_sitemap = 1
no_cache = 1
base_template_path = "templates/www/manifest.json"


def get_context(context):
	m = frappe.get_cached_doc("Web App Manifest")

	context.app_name = m.app_name or "ERPNext"
	context.short_name = m.short_name
	context.description = m.description
	context.start_url = m.start_url or "/app"
	context.scope = m.scope or "/"
	context.display = m.display or "standalone"
	context.orientation = m.orientation
	context.theme_color = m.theme_color
	context.background_color = m.background_color
	context.lang = m.lang
	context.dir = m.dir

	icons = [
		{k: v for k, v in row.items() if v}
		for row in frappe.get_all(
			"Web App Manifest Icon",
			filters={"parenttype": "Web App Manifest", "parent": m.name},
			fields=["src", "sizes", "type", "purpose"],
		)
	]
	context.icons = json.dumps(
		icons or [{"src": "/assets/frappe/images/favicon.png", "sizes": "128x128", "type": "image/png"}]
	)
	return context
```

```jinja
{# site_pwa/templates/www/manifest.json #}
{
  "name": {{ app_name | tojson }}
  {%- if short_name %}, "short_name": {{ short_name | tojson }}{% endif %}
  {%- if description %}, "description": {{ description | tojson }}{% endif %}
  {%- if start_url %}, "start_url": {{ start_url | tojson }}{% endif %}
  {%- if scope %}, "scope": {{ scope | tojson }}{% endif %}
  {%- if display %}, "display": {{ display | tojson }}{% endif %}
  {%- if orientation %}, "orientation": {{ orientation | tojson }}{% endif %}
  {%- if theme_color %}, "theme_color": {{ theme_color | tojson }}{% endif %}
  {%- if background_color %}, "background_color": {{ background_color | tojson }}{% endif %}
  {%- if lang %}, "lang": {{ lang | tojson }}{% endif %}
  {%- if dir %}, "dir": {{ dir | tojson }}{% endif %}
  , "icons": {{ icons }}
}
```

Use `| tojson` on every string rather than bare `"{{ value }}"`. A quote or
backslash in an app name produces invalid JSON and a manifest that silently does
nothing, and the original Monogramm template has exactly that hole.

`frappe.get_cached_doc` matters — this file is fetched on every cold start of every
installed client.

### Linking it

Desk and website templates both render a `<head>` you can extend. The portable
route is `web_include_js` / `app_include_js` injecting the tag:

```js
if (!document.querySelector('link[rel="manifest"]')) {
  const link = document.createElement('link')
  link.rel = 'manifest'
  link.href = '/manifest.json'
  document.head.appendChild(link)
}
```

For iOS, the manifest is mostly ignored, so also inject the meta tags:

```js
const metas = [
  ['apple-mobile-web-app-capable', 'yes'],
  ['apple-mobile-web-app-title', window.frappe?.boot?.sitename || 'ERPNext'],
  ['apple-mobile-web-app-status-bar-style', 'default'],
  ['theme-color', '#ffffff'],
]
for (const [name, content] of metas) {
  if (document.querySelector(`meta[name="${name}"]`)) continue
  const m = document.createElement('meta')
  m.name = name
  m.content = content
  document.head.appendChild(m)
}
```

Use `default` (or `black`) for the iOS status bar style here, **not**
`black-translucent`. Translucent draws content under the status bar, and Desk's
layout knows nothing about `env(safe-area-inset-top)` — your navbar will sit under
the clock. Translucent is for apps you control the CSS of; that is the SPA skill,
not this one.

`start_url` deserves thought: `/app` drops the user into Desk's last workspace;
`/app/todo` or a specific workspace is usually kinder. For a portal, `/me` or the
relevant portal page.

## Icons

```bash
npx pwa-asset-generator ./logo.svg ./site_pwa/public/manifest \
  --background "#ffffff" --padding "12%" --maskable true --favicon \
  --path-override "/assets/site_pwa/manifest"
```

Then enter the generated paths into the `Web App Manifest Icon` table (or seed
them in an `after_install` fixture so a fresh install is already correct).

Minimum viable set: 192×192 `any`, 192×192 `maskable`, 512×512 `any`, 512×512
`maskable`, plus a 180×180 `apple-touch-icon`.

## Install prompt

Chromium fires `beforeinstallprompt`. iOS fires nothing.

```js
// site_pwa/public/js/install.js
let deferredPrompt = null

const isIos = () => /iphone|ipad|ipod/.test(navigator.userAgent.toLowerCase())
const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  deferredPrompt = e
  showInstallAffordance()
})

window.addEventListener('appinstalled', () => {
  deferredPrompt = null
  hideInstallAffordance()
  localStorage.setItem('site_pwa:installed', '1')
})

async function doInstall() {
  if (!deferredPrompt) return
  deferredPrompt.prompt()
  const { outcome } = await deferredPrompt.userChoice
  if (outcome !== 'accepted') localStorage.setItem('site_pwa:dismissed', Date.now())
  deferredPrompt = null
  hideInstallAffordance()
}

function shouldOffer() {
  if (isStandalone() || localStorage.getItem('site_pwa:installed')) return false
  const dismissed = Number(localStorage.getItem('site_pwa:dismissed') || 0)
  return Date.now() - dismissed > 30 * 24 * 3600 * 1000     // re-ask after a month
}
```

Where to put the affordance:

- **A persistent, quiet entry point**: an "Install app" item in Desk's user
  dropdown or the portal footer, always available, never nagging. This should
  always exist.
- **A one-time banner**, at most once a month, only if `shouldOffer()`. Monogramm's
  original routes the user to a dedicated `/install` page; a banner with an inline
  button converts better.

Do not show the banner on first page load of a first visit. The user has not
decided they want your app yet.

### iOS

There is no programmatic install on iOS. Detect and instruct:

```js
if (isIos() && !isStandalone() && shouldOffer()) {
  // render a bottom sheet:
  //   "Install <App>"
  //   "Tap [share glyph] then 'Add to Home Screen'"
}
```

Render the actual share glyph inline — an SVG of the iOS share icon. "Tap Share"
in text is regularly missed; the glyph is not. Also: this only works in **Safari**.
In Chrome or Firefox on iOS there is no Add to Home Screen at all, so detect the
in-app browser and say "Open this page in Safari to install" instead of giving
instructions that cannot be followed.

### Why installing matters on iOS beyond convenience

Safari's ITP evicts CacheStorage and IndexedDB after **7 days of inactivity** for
sites that are not installed. Once added to the Home Screen, that relaxes. And Web
Push on iOS requires installation — there is no push in a Safari tab, ever. So on
iOS the install prompt is load-bearing, not cosmetic.

## Offline page

A single static page the service worker falls back to. Keep it tiny, inline
everything, and make it honest:

```html
<!-- site_pwa/www/offline.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>Offline</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           display: flex; align-items: center; justify-content: center; height: 100vh;
           margin: 0; text-align: center; color: #1f272e; background: #f4f5f6; }
    .card { max-width: 20rem; padding: 2rem; }
    button { margin-top: 1.25rem; padding: 0.625rem 1.25rem; border: 0; border-radius: 8px;
             background: #171717; color: #fff; font-size: 15px; }
  </style>
</head>
<body>
  <div class="card">
    <h1 style="font-size:18px;margin:0 0 .5rem">You're offline</h1>
    <p style="font-size:14px;color:#6b7280;margin:0">
      This page needs a connection. Anything you already opened is still available.
    </p>
    <button onclick="location.reload()">Try again</button>
  </div>
</body>
</html>
```

Do not promise offline capability the site does not have. "You're offline" is
true; "Working offline" is not.
