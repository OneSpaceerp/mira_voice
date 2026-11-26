# Backend wiring

Everything the Frappe side of a v16 SPA PWA needs: packaging, routing, the boot
page, the API module, permissions, and the DocTypes the app reads.

## `pyproject.toml`

```toml
[project]
name = "my_pwa"
authors = [{ name = "Nest Software Development", email = "info@nsd-eg.com" }]
description = "Mobile PWA on ERPNext v16"
requires-python = ">=3.14,<3.15"
readme = "README.md"
dynamic = ["version"]
dependencies = []

[build-system]
requires = ["flit_core >=3.4,<4"]
build-backend = "flit_core.buildapi"

[tool.bench.frappe-dependencies]
frappe = ">=16.0.0,<17.0.0"
erpnext = ">=16.0.0,<17.0.0"

[tool.ruff]
line-length = 110
target-version = "py310"          # syntax target for the linter, not the runtime

[tool.ruff.lint]
select = ["F", "E", "W", "I", "UP", "B", "RUF"]
ignore = ["E501", "B904", "W191", "E101", "F401"]

[tool.ruff.format]
quote-style = "double"
indent-style = "tab"              # Frappe is tab-indented; match it
```

`requires-python` tracks the **framework** (Frappe v16 pins `>=3.14,<3.15`).
`target-version` tracks what **syntax Ruff should assume** — ERPNext v16 itself
still lints at `py310`, because the codebase avoids 3.11+ syntax for
backportability. They are different knobs; a mismatch is not a bug.

`[tool.bench.frappe-dependencies]` makes `bench get-app` refuse to install your
app onto a v15 bench instead of failing mysteriously at import time.

## `hooks.py`

The whole SPA needs exactly one routing rule and one app-screen entry:

```python
app_name = "my_pwa"
app_title = "My PWA"
app_publisher = "Nest Software Development"
app_description = "Mobile PWA on ERPNext v16"
app_email = "info@nsd-eg.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

app_logo_url = "/assets/my_pwa/images/logo.svg"
app_home = "/my-pwa"

add_to_apps_screen = [
	{
		"name": "my_pwa",
		"logo": "/assets/my_pwa/images/logo.svg",
		"title": "My PWA",
		"route": "/my-pwa",
		"has_permission": "my_pwa.api.check_app_permission",
	}
]

# Every SPA sub-path resolves to the single www page. vue-router does the rest.
# Page name "my-pwa" → my_pwa/www/my-pwa.html (template) + my_pwa/www/my_pwa.py (controller)
website_route_rules = [
	{"from_route": "/my-pwa/<path:app_path>", "to_route": "my-pwa"},
]

# Expose extra keys to Desk's boot (NOT to your SPA — see www/ below)
extend_bootinfo = "my_pwa.utils.extend_bootinfo"

after_install = "my_pwa.install.after_install"
```

Four things people get wrong here:

- **`to_route` is the www page name, not the URL.** `"to_route": "my-pwa"`
  resolves to `my_pwa/www/my-pwa.html`. The `from_route` URL and the page name do
  not have to match — Frappe HR serves `/hrms` from `www/hrms`, PWA Builder serves
  `/pwa-builder` from `www/frontend`.
- **A hyphenated page name is fine, and its controller is underscored.** Frappe
  resolves the `.py` by replacing `-` with `_`, so `www/my-pwa.html` pairs with
  `www/my_pwa.py`. That is exactly the pairing `frappe-ui/vite`'s
  `frontendRoute: '/my-pwa'` produces by default. Do not rename the `.py` to match
  the hyphen — a hyphenated Python module cannot be imported.
- **Whether the bare route needs its own rule depends on the page name.** A www
  page named `my-pwa` already answers `/my-pwa`, so only the `<path:app_path>`
  wildcard needs a rule — that is why Frappe HR lists one. If the page is named
  differently from the URL (PWA Builder serves `/pwa-builder` from `www/frontend`)
  you need **both** entries:
  ```python
  website_route_rules = [
      {"from_route": "/my-pwa", "to_route": "frontend"},
      {"from_route": "/my-pwa/<path:app_path>", "to_route": "frontend"},
  ]
  ```
  When in doubt, list both — a duplicate rule is harmless, a missing one is a 404
  on the app's own home URL.
- **`extend_bootinfo` is Desk's boot, not your SPA's.** Your SPA's boot comes from
  `get_context` below. Setting one does not populate the other.

Two SPAs in one app is normal and supported — Frappe HR ships `frontend/` (the
mobile PWA at `/hrms`) and `roster/` (a desktop tool at `/hr`) side by side, each
with its own route rule, www page, vite project and build script.

## `www/my_pwa.py` — the bootloader

This is the single highest-leverage file in the app. Everything it returns is in
the first HTML response, so the SPA starts with identity, CSRF and translations
already in hand instead of three round-trips.

```python
import frappe
from frappe.boot import load_translations

no_cache = 1


def get_context(context):
	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep — persists the freshly minted session/token

	context = frappe._dict()
	context.csrf_token = csrf_token
	context.site_name = frappe.local.site
	context.boot = get_boot()
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	"""Vite's dev server serves its own index.html, so it never runs Jinja.
	The SPA fetches boot from here instead when import.meta.env.DEV."""
	if not frappe.conf.developer_mode:
		frappe.throw(frappe._("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	bootinfo = frappe._dict(
		{
			"site_name": frappe.local.site,
			"socketio_port": frappe.conf.get("socketio_port") or 9000,
			"push_relay_server_url": frappe.conf.get("push_relay_server_url") or "",
			"default_route": "/my-pwa",
		}
	)
	bootinfo.lang = frappe.local.lang
	load_translations(bootinfo)
	return bootinfo
```

- **`no_cache = 1` is mandatory.** Without it Frappe may serve a cached page that
  carries someone else's CSRF token.
- **`frappe.db.commit()` before returning.** `get_csrf_token()` can create the
  session row; a GET request will not commit it for you, and the token the HTML
  carries then does not exist server-side.
- **Reassigning `context = frappe._dict()`** (rather than mutating the passed-in
  context) is what Frappe HR does; it keeps website-theme keys from leaking into
  the SPA's boot payload.
- **Never put secrets in boot.** It is rendered into HTML that the browser caches
  and the service worker may store. User id, lang, socket port, feature flags —
  yes. API keys, tokens for third parties, salary figures — no.
- `load_translations(bootinfo)` fills `bootinfo.__messages`, which the SPA's
  translation plugin reads synchronously. Without it, every screen's first paint
  is in English and then flickers.

### Serving guests

If the app has a public surface (a booking form, a status page), add
`allow_guest` handling here and let the router decide. If it is employees-only,
`no_cache = 1` plus the route guard is enough — an unauthenticated visitor gets
the SPA shell and is immediately redirected to `/login`.

## `www/my-pwa.html`

**Do not write this file.** It is the Vite build output, copied into place by the
build script (Track A/C) or by the `frappe-ui/vite` `buildConfig` plugin (Track B).
The `.py` above is hand-written and committed; the `.html` is generated. Add both
build artifacts to `.gitignore`:

```gitignore
my_pwa/public/frontend/
my_pwa/www/my-pwa.html
```

## `api.py` — the SPA's server surface

Two rules decide whether this file is safe: **every method is a public HTTP
endpoint**, and **the SPA is not a trusted client** — anyone can call these with
curl and a session cookie.

```python
import frappe
from frappe import _


@frappe.whitelist()
def get_current_user_info() -> dict:
	return frappe.db.get_value(
		"User",
		frappe.session.user,
		["name", "first_name", "full_name", "user_image", "time_zone"],
		as_dict=True,
	) | {"roles": frappe.get_roles()}


@frappe.whitelist()
def get_my_orders(status: str | None = None, limit: int = 20, start: int = 0) -> list[dict]:
	filters = {"owner": frappe.session.user, "docstatus": ["!=", 2]}
	if status:
		filters["status"] = status

	return frappe.get_list(
		"Sales Order",
		filters=filters,
		fields=["name", "transaction_date", "grand_total", "status", "customer"],
		order_by="modified desc",
		limit_page_length=min(int(limit), 100),   # cap: a client can ask for 1e9
		limit_start=int(start),
	)


@frappe.whitelist(methods=["POST"])
def approve_request(name: str) -> dict:
	doc = frappe.get_doc("Material Request", name)
	doc.check_permission("submit")            # explicit, not implied
	if doc.docstatus != 0:
		frappe.throw(_("Only draft requests can be approved"))
	doc.submit()
	return {"name": doc.name, "status": doc.status}


def check_app_permission() -> bool:
	"""Used by add_to_apps_screen to hide the tile from users who can't use it."""
	if frappe.session.user == "Administrator":
		return True
	return bool(frappe.db.exists("Employee", {"user_id": frappe.session.user}))
```

Checklist for every endpoint you add:

- **`frappe.get_list`, not `frappe.get_all`**, whenever the caller is a user.
  `get_all` **skips permissions** — it is for trusted server code only. This is the
  single most common data-leak bug in Frappe SPAs.
- **`methods=["POST"]` on anything that writes.** A GET-able mutation is a CSRF
  and a prefetch hazard.
- **Cap and coerce every client-supplied number.** `limit`, `start`, page sizes.
- **`doc.check_permission(...)` or `frappe.has_permission(...)` before acting**,
  even when a route guard already checked. Guards are UX.
- **Return dicts and lists, not `Document` objects.** Serialising a whole doc ships
  fields the SPA never needed and sometimes shouldn't see.
- **Row-level scoping is a hook, not an `if`.** For "users only see their own
  records", register `permission_query_conditions` so *every* path — list view,
  report, API — is scoped, rather than filtering in one endpoint.

### Standard endpoints you do not need to write

The SPA can call these directly through `useCall` / `createResource`:

| Need | Endpoint |
|---|---|
| Login / logout | `login`, `logout` |
| Link-field autocomplete | `frappe.desk.search.search_link` (POST) |
| Generic list with report-view semantics | `frappe.desk.reportview.get` |
| "Can this user create X?" | `frappe.client.has_permission` |
| Workflow transitions | `frappe.model.workflow.get_transitions`, `…apply_workflow` |
| Translations | `frappe.translate.load_all_translations` |
| Push subscribe/unsubscribe | `frappe.push_notification.subscribe` / `.unsubscribe` |
| Any doc CRUD (v16) | `/api/v2/document/<DocType>[/<name>]` |

**API v2** is what frappe-ui's `useDoc` / `useList` / `useNewDoc` target
(`/api/v2/document/…`, `/api/v2/method/…`). v1 (`/api/resource`, `/api/method`)
still works and is what `frappe-js-sdk` and `createResource` use. Both are live in
v16 — just don't mix them for the same entity in the same app.

## Realtime

Emit from the server, subscribe in the SPA. Frappe HR's convention is one event
name carrying a resource cache key:

```python
frappe.publish_realtime(
	"my_pwa:refetch_resource",
	{"cache_key": "my_pwa:my_orders"},
	user=doc.owner,
)
```

The client listens once and reloads the matching cached resource — see
`data-layer.md`. Frappe's built-in `list_update` event (emitted on every
insert/update of a subscribed doctype) covers the generic case without any server
code; subscribe with `socket.emit("doctype_subscribe", "Sales Order")`.

## Push notifications

v16 ships `frappe/push_notification.py`, which talks to a **notification relay**
server (`frappe/notification_relay`, self-hostable) holding the Firebase service
account. Your site config needs `push_relay_server_url`, and Push Notification
Settings must be enabled.

```python
from frappe.push_notification import PushNotification

PushNotification("my_pwa").send_notification_to_user(
	user_id=doc.owner,
	title=_("Order approved"),
	body=doc.name,
	link=f"/my-pwa/orders/{doc.name}",
)
```

The client side (token registration, the FCM service worker, permission UX) is in
`pwa-runtime.md`, along with the **self-hosted alternative** — talking to Google's
FCM HTTP v1 API directly from your app, with no relay server — which is the right
call for an isolated self-hosted ERPNext where you do not want a second service.

## DocTypes for the app's own data

Model before you code (`erpnext-app-builder` covers this in depth). PWA-specific
notes:

- **A device/session DocType** (`FCM User Token`-style: `user`, `token`,
  `last_seen`) is how you deliver push. Keep it in your app, not in a Single.
- **Sync-conflict fields.** If the SPA writes offline, store the client's
  `modified` timestamp and reject stale writes server-side rather than letting
  last-write-win silently clobber.
- **Settings as a Single** (`My PWA Settings`) for anything an admin should tune
  without a deploy: feature flags, refresh intervals, branding colors. Expose it
  through one cached whitelisted method.
- Permissions live in the DocType JSON and ship with the app; do not hand-edit
  Role Permission Manager on production and hope it survives the next migrate.
