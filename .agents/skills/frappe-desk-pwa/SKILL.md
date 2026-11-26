---
name: frappe-desk-pwa
description: Make an existing Frappe/ERPNext site installable and offline-capable without building a separate SPA — add a web app manifest, a scoped service worker, an install prompt and FCM push to the Desk or the website portal, driven by DocTypes an admin can edit. Use when the user wants ERPNext itself on a phone home screen, an installable portal or web form, push notifications from Notification Log, or a lightweight PWA layer over Desk rather than a custom Vue app.
---

# Frappe Desk PWA

Layer PWA capability onto the site that already exists. No Vue app, no Vite, no
second frontend — a manifest, a service worker, an install prompt and push
notifications delivered through a normal Frappe app.

This is the right answer far more often than people expect. It is also the wrong
answer in specific ways, and knowing which is the point of this skill.

## Is this the right path?

| Situation | Path |
|---|---|
| "I want ERPNext on my phone's home screen" | **This skill** |
| "Our customer portal should be installable" | **This skill** |
| "Send push notifications for assignments and mentions" | **This skill** (push section alone) |
| "Field staff need a fast offline app with 4 screens" | `erpnext-v16-pwa-builder` — a real SPA |
| "Desk is too heavy/complex for our warehouse team" | `erpnext-v16-pwa-builder` — the problem is Desk, not the manifest |
| "Make Desk work offline" | **Neither.** See the honesty section below |

### Be honest about what this gets you

An installable Desk is **Desk in a chromeless window**. It is genuinely useful —
one tap from the home screen, no URL bar, an app icon in the launcher, push
notifications — and it costs a day instead of a month.

It does **not** make Desk a mobile app. Desk's list and form views are dense,
desktop-first, and assume a pointer. It does not make Desk work offline in any
meaningful sense: Desk is a large JS application that talks to the server for
nearly everything, and caching its bundles aggressively is actively dangerous
(see below). If the complaint is "Desk is hard to use on a phone", a manifest will
not fix it, and shipping one as if it does will cost you the client's trust.

Say this out loud before quoting the work.

## The four pieces

| Piece | What it is | Reference |
|---|---|---|
| **Manifest** | `/manifest.json` rendered from a Single DocType so an admin edits name, colors, icons | `references/manifest-and-install.md` |
| **Service worker** | A *scoped, conservative* worker — offline fallback page and static asset caching, not a blanket cache | `references/service-worker.md` |
| **Install prompt** | `beforeinstallprompt` on Chromium, a Share-sheet hint on iOS | `references/manifest-and-install.md` |
| **Push** | FCM, either through Frappe v16's relay or direct to Google's HTTP v1 API | `references/push-notifications.md` |

## Scaffold

```bash
bench new-app site_pwa
bench --site erp.client.com install-app site_pwa
bench --site erp.client.com set-config developer_mode 1
```

```python
# site_pwa/hooks.py
app_name = "site_pwa"
app_title = "Site PWA"

# Registration + install UI on the portal…
web_include_js = ["pwa.bundle.js"]
web_include_css = ["pwa.bundle.css"]

# …and inside Desk
app_include_js = ["pwa.bundle.js"]
app_include_css = ["pwa.bundle.css"]

doc_events = {
    "Notification Log": {"after_insert": "site_pwa.fcm.send_push_notification"},
}

website_route_rules = [
    {"from_route": "/install", "to_route": "install"},
]
```

`app_include_*` targets Desk, `web_include_*` targets the website/portal. Most
deployments want both. Frappe v16 bundles these — `site_pwa/public/js/pwa.bundle.js`
is built by `bench build --app site_pwa`.

Then work through the three references in order: manifest → service worker → push.

## The rules that keep this safe

Three of these have caused real production incidents in Frappe PWA apps that are
public on GitHub. They are not hypothetical.

1. **Never cache-first the Desk bundles.** Desk assets are versioned by a query
   string, not a content hash, and `bench build` replaces them in place. A
   cache-first service worker will serve yesterday's `desk.bundle.js` against
   today's server API and produce errors nobody can reproduce. Use network-first
   with a cache fallback, or exclude `/assets/frappe/` entirely.
2. **Never cache authenticated HTML or JSON without clearing it on logout.** On a
   shared warehouse tablet, a cached `/api/method/frappe.client.get` response is
   one user seeing another user's data.
3. **Never cache `/api/method/login`, `/api/method/logout`, or any `POST`.**
   Scope the fetch handler to `GET` and same-origin, explicitly.
4. **Scope the worker deliberately.** A worker at `/sw.js` claims the whole origin
   — including Desk, the website, and every app. That is usually what you want
   here, and it is exactly why rules 1–3 matter so much.
5. **Version the cache and clean up on activate.** A cache name with no version is
   a cache you can never invalidate without asking users to clear site data.
6. **HTTPS or nothing.** No service worker, no install, no push over plain HTTP.

## Verify

- [ ] `/manifest.json` returns valid JSON with resolvable icons; DevTools →
      Application → Manifest shows no errors
- [ ] Service worker activates, scope is what you intended, and
      `caches.keys()` shows one versioned cache
- [ ] Install on Android; install on iOS via Share → Add to Home Screen
- [ ] Installed app opens standalone
- [ ] **Deploy a new `bench build` and confirm Desk loads the new assets** —
      this is the test that catches rule 1
- [ ] Log in as user A, log out, log in as user B: no trace of A's data
- [ ] Offline: a cached page or the offline fallback renders instead of the
      browser's dinosaur
- [ ] Push: a Notification Log insert reaches the device; the token is removed
      when the user disables notifications
- [ ] Turn the service worker off (unregister) and confirm the site still works
      normally — your PWA layer must be removable
