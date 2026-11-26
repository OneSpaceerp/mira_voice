# Push notifications

Two ways to get FCM push out of a Frappe v16 site. Pick by whether you are willing
to run a relay service.

| | Relay (Frappe-native) | Direct FCM HTTP v1 |
|---|---|---|
| Extra service to deploy | yes — `frappe/notification_relay` | no |
| Credentials live | on the relay | in your site's DB (encrypted password field) |
| Firebase project | one relay can serve many sites | one per site |
| Code you maintain | almost none | ~150 lines |
| Right for | Frappe Cloud, multi-site hosting | a self-hosted single-tenant ERPNext |

Both end at the same place: an FCM token per user-device, and a service worker
showing the notification.

---

## Option 1 — Frappe's relay

v16 ships `frappe/push_notification.py`. Setup:

1. Deploy or point at a `notification_relay` instance.
2. `bench --site erp.client.com set-config push_relay_server_url https://relay.example.com`
3. In Desk: **Push Notification Settings** → enable. It validates that the config
   key exists and throws a clear error if not.

Server-side send:

```python
from frappe.push_notification import PushNotification

PushNotification("site_pwa").send_notification_to_user(
	user_id=doc.for_user,
	title=_("New assignment"),
	body=doc.subject,
	link=frappe.utils.get_url(doc.link or "/app"),
	icon=frappe.utils.get_url("/assets/site_pwa/manifest/icon-192.png"),
)
```

There are also `send_notification_to_topic`, `add_topic` / `remove_topic` and
`subscribe_topic` / `unsubscribe_topic` for broadcast groups — useful for "all
warehouse staff" without maintaining your own recipient lists.

Client-side, v16 exposes two whitelisted endpoints:

```
GET /api/method/frappe.push_notification.subscribe?fcm_token=…&project_name=site_pwa
GET /api/method/frappe.push_notification.unsubscribe?fcm_token=…&project_name=site_pwa
```

The Firebase **web config** comes from the relay
(`notification_relay.api.get_config?project_name=…`), which also returns the VAPID
public key. The client fetches it and hands it to the service worker **as a query
string on the SW URL**, because a service worker cannot read app state:

```js
const config = await fetchWebConfig()          // from the relay
const swUrl = `/sw.js?config=${encodeURIComponent(JSON.stringify(config))}`
const reg = await navigator.serviceWorker.register(swUrl, { scope: '/' })
```

`hrms/frontend/public/frappe-push-notification.js` is a complete, well-documented
client for this — token lifecycle, permission, localStorage comparison,
subscribe/unsubscribe. Copy it rather than rewriting it.

---

## Option 2 — direct FCM HTTP v1

No relay. Your app mints a Google OAuth token from a service account and posts to
FCM itself. `omfsakib/pwa_frappe`'s `fcm.py` is the reference implementation;
what follows is its shape with the security notes that matter.

### Setup

1. Firebase console → create a project → add a **Web app** → copy the web config
   (apiKey, authDomain, projectId, messagingSenderId, appId).
2. Project settings → Cloud Messaging → **Web Push certificates** → generate a key
   pair → copy the **VAPID public key**.
3. Project settings → Service accounts → **Generate new private key** → a JSON
   file. This is a credential for your whole Firebase project. Treat it like a
   password.

### DocTypes

**`Service Worker`** (Single) gains:

| Field | Type | Notes |
|---|---|---|
| `enable_fcm` | Check | |
| `fcm_web_config` | Code (JSON) | the web config — not secret, the client needs it |
| `fcm_vapid_public_key` | Data | not secret |
| `fcm_service_account_json` | **Password** | secret. Must be a Password field so Frappe encrypts it and `get_password()` is the only way out |

**`FCM User Token`**: `user` (Link → User), `fcm_token` (Data, unique),
`device_label` (Data), `last_seen` (Datetime). One row per user-device.

### Server

```python
import json, time
import frappe
from frappe import _
from frappe.utils import get_url, get_url_to_form, strip_html


@frappe.whitelist()
def get_fcm_config() -> dict:
	s = frappe.get_cached_doc("Service Worker")
	if not s.enable_fcm:
		frappe.throw(_("Push notifications are not enabled on this site"))
	if not s.fcm_web_config or not s.fcm_vapid_public_key:
		frappe.throw(_("FCM is not configured. Set the web config and VAPID key in Service Worker settings."))
	try:
		config = json.loads(s.fcm_web_config)
	except ValueError:
		frappe.throw(_("FCM Web Config must be valid JSON"))
	return {"config": config, "vapid_public_key": s.fcm_vapid_public_key}


@frappe.whitelist(methods=["POST"])
def subscribe(fcm_token: str) -> dict:
	if not fcm_token:
		frappe.throw(_("fcm_token is required"))
	user = frappe.session.user
	if user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if frappe.db.exists("FCM User Token", {"user": user, "fcm_token": fcm_token}):
		return {"success": True, "message": "Already subscribed"}
	frappe.get_doc({"doctype": "FCM User Token", "user": user, "fcm_token": fcm_token}).insert(
		ignore_permissions=True
	)
	frappe.db.commit()  # nosemgrep
	return {"success": True, "message": "Subscribed"}


@frappe.whitelist(methods=["POST"])
def unsubscribe(fcm_token: str) -> dict:
	if not fcm_token:
		frappe.throw(_("fcm_token is required"))
	frappe.db.delete("FCM User Token", {"user": frappe.session.user, "fcm_token": fcm_token})
	frappe.db.commit()  # nosemgrep
	return {"success": True, "message": "Unsubscribed"}
```

Two hardening changes over the reference implementation, both worth making:

- **`methods=["POST"]` on subscribe/unsubscribe.** As GETs they are CSRF-able and
  can be triggered by a prefetch.
- **`unsubscribe` scoped to `frappe.session.user`** (as above), so one user cannot
  delete another's token by guessing it. The reference already does this; do not
  "simplify" it to delete by token alone.

The OAuth + send path:

```python
def get_fcm_access_token(service_account: dict) -> str:
	import jwt, requests

	token_url = "https://oauth2.googleapis.com/token"
	now = int(time.time())
	key = service_account["private_key"]
	if isinstance(key, str):
		key = key.replace("\\n", "\n")

	assertion = jwt.encode(
		{
			"iss": service_account["client_email"],
			"scope": "https://www.googleapis.com/auth/firebase.messaging",
			"aud": token_url,
			"exp": now + 3600,
			"iat": now,
		},
		key,
		algorithm="RS256",
	)
	res = requests.post(
		token_url,
		data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
		timeout=15,
	)
	res.raise_for_status()
	return res.json()["access_token"]


def send_direct_fcm(service_account_json, user_id, title, body, link=None, icon=None) -> bool:
	import requests

	tokens = frappe.get_all("FCM User Token", filters={"user": user_id}, fields=["name", "fcm_token"])
	if not tokens:
		return False

	service_account = json.loads(service_account_json)
	access_token = get_fcm_access_token(service_account)
	url = f"https://fcm.googleapis.com/v1/projects/{service_account['project_id']}/messages:send"
	headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

	sent = 0
	for row in tokens:
		data = {"title": title, "body": body}
		if link:
			data["click_action"] = link
		if icon:
			data["notification_icon"] = icon

		res = requests.post(
			url, json={"message": {"token": row.fcm_token, "data": data}}, headers=headers, timeout=15
		)
		if res.status_code == 200:
			sent += 1
		elif res.status_code == 404 or "UNREGISTERED" in res.text:
			# the device uninstalled or the token rotated — prune it
			frappe.delete_doc("FCM User Token", row.name, ignore_permissions=True, delete_permanently=True)
			frappe.db.commit()  # nosemgrep
		else:
			frappe.log_error(f"FCM {res.status_code}: {res.text}", "PWA push failed")
	return sent > 0
```

Notes that matter in production:

- **`{"message": {"token": …, "data": {…}}}` — a data-only message, no
  `notification` key.** Data-only means your service worker's
  `onBackgroundMessage` always runs, so you control the rendering. Include a
  `notification` block and Chrome renders it itself and your handler may not fire.
- **Cache the access token.** It is valid an hour; minting one per notification is
  a wasted round-trip to Google on every send. `frappe.cache.set_value` with a
  3000-second TTL.
- **Prune `UNREGISTERED` tokens**, or the table grows forever and every send gets
  slower.
- **Always `timeout=` on `requests`.** Without it a hung Google endpoint blocks a
  worker indefinitely.
- **This belongs in a background job.** Hooked to `after_insert` it runs inline in
  the request that created the Notification Log; a slow FCM call then delays a
  user's save. `frappe.enqueue` it.

### Wiring it to Frappe's notifications

```python
# hooks.py
doc_events = {"Notification Log": {"after_insert": "site_pwa.fcm.enqueue_push"}}
```

```python
NOTIFICATION_TITLES = {
	"Mention": "New Mention",
	"Assignment": "Assignment Update",
	"Share": "Document Shared With You",
	"Energy Point": "Energy Point Update",
	"Alert": "Alert",
}


def enqueue_push(doc, method=None):
	frappe.enqueue("site_pwa.fcm.send_push_notification", queue="short", log_name=doc.name)


def send_push_notification(log_name: str):
	doc = frappe.get_doc("Notification Log", log_name)
	try:
		s = frappe.get_cached_doc("Service Worker")
		if not s.enable_fcm:
			return
		sa = s.get_password("fcm_service_account_json", raise_exception=False)
		if not sa:
			return

		if doc.link:
			link = get_url(doc.link)
		elif doc.document_type and doc.document_name:
			link = get_url(get_url_to_form(doc.document_type, doc.document_name))
		else:
			link = get_url("/app")

		send_direct_fcm(
			service_account_json=sa,
			user_id=doc.for_user,
			title=NOTIFICATION_TITLES.get(doc.type, "New Notification"),
			body=strip_html(doc.subject or "")[:200],
			link=link,
			icon=get_default_icon(),
		)
	except Exception:
		frappe.log_error(title="PWA push failed", message=frappe.get_traceback())
```

Notification Log is inserted for mentions, assignments, shares, energy points and
alerts — so hooking it gives you push for everything Frappe already notifies about,
with no per-doctype work.

A test helper earns its keep:

```python
@frappe.whitelist()
def test_push_notification(user: str | None = None):
	"""bench --site <site> execute site_pwa.fcm.test_push_notification --args "['Administrator']" """
	user = user or frappe.session.user
	doc = frappe.get_doc({
		"doctype": "Notification Log", "for_user": user, "from_user": "Administrator",
		"type": "Alert", "subject": "Test push from site_pwa.",
	}).insert(ignore_permissions=True)
	return doc.name
```

---

## Client side (both options)

```js
import { initializeApp } from 'firebase/app'
import { getMessaging, getToken, deleteToken, isSupported, onMessage } from 'firebase/messaging'

let messaging = null
let registration = null

export async function initPush(swRegistration) {
  if (!(await isSupported())) return false
  registration = swRegistration
  const { config } = await (await fetch('/api/method/site_pwa.fcm.get_fcm_config')).json().then(r => r.message)
  messaging = getMessaging(initializeApp(config))
  onMessage(messaging, (payload) => showForegroundNotification(payload))
  return true
}

export async function enableNotifications() {
  if ((await Notification.requestPermission()) !== 'granted') return false

  const { vapid_public_key } = (await (await fetch('/api/method/site_pwa.fcm.get_fcm_config')).json()).message
  const token = await getToken(messaging, {
    vapidKey: vapid_public_key,
    serviceWorkerRegistration: registration,
  })

  const old = localStorage.getItem('site_pwa:fcm_token')
  if (old && old !== token) await post('/api/method/site_pwa.fcm.unsubscribe', { fcm_token: old })
  await post('/api/method/site_pwa.fcm.subscribe', { fcm_token: token })
  localStorage.setItem('site_pwa:fcm_token', token)
  return true
}

export async function disableNotifications() {
  const token = localStorage.getItem('site_pwa:fcm_token')
  if (!token) return
  try { await deleteToken(messaging) } catch {}
  await post('/api/method/site_pwa.fcm.unsubscribe', { fcm_token: token })
  localStorage.removeItem('site_pwa:fcm_token')
}
```

And in the worker:

```js
import { initializeApp } from 'firebase/app'
import { getMessaging, onBackgroundMessage } from 'firebase/messaging/sw'

const raw = new URL(location).searchParams.get('config')
if (raw) {
  try {
    const messaging = getMessaging(initializeApp(JSON.parse(raw)))
    onBackgroundMessage(messaging, (payload) => {
      self.registration.showNotification(payload.data.title, {
        body: payload.data.body || '',
        icon: payload.data.notification_icon,
        badge: '/assets/site_pwa/manifest/badge-72.png',
        tag: payload.data.tag || 'site-pwa',      // collapses duplicates
        data: { url: payload.data.click_action },
      })
    })
  } catch (e) { console.log('[SW] FCM not configured', e) }
}

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url
  if (!url) return
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      // focus an existing tab on that URL instead of opening a third one
      for (const c of list) if (c.url === url && 'focus' in c) return c.focus()
      return self.clients.openWindow(url)
    }),
  )
})
```

`tag` collapses repeat notifications about the same document instead of stacking
twelve of them. Focusing an existing window rather than always calling
`openWindow` is what users expect and what stops a notification storm from opening
twenty tabs.

## Permission UX

- **Never call `Notification.requestPermission()` on page load.** A denied
  permission is effectively permanent — the user has to dig into site settings to
  undo it. One careless auto-prompt costs you push for that user forever.
- Ask from an explicit **Enable notifications** toggle in the user's settings, or
  after they do something that implies they want updates (submitting a request for
  approval).
- Explain what they will receive, before the browser dialog.
- Keep the toggle reversible and make `disableNotifications()` actually delete the
  token server-side.
- Handle `Notification.permission === 'denied'` by showing "Notifications are
  blocked in your browser settings" rather than a toggle that does nothing.

## iOS

- Web Push works on **iOS 16.4+ and only for PWAs installed to the Home Screen.**
  In a Safari tab there is no push at all.
- Detect `isIos() && !isStandalone()` and replace the toggle with "Add this app to
  your Home Screen to receive notifications" plus the install instructions.
- `navigator.setAppBadge()` works on iOS 16.4+ standalone — drive it from your
  unread count.
- iOS suspends background JS within seconds of backgrounding; push is delivered by
  the OS, but do not expect any background processing between notifications.

## Verify

- [ ] Test notification arrives on Android Chrome, foreground and background
- [ ] Tapping it opens the right document, focusing an existing tab if open
- [ ] Disabling the toggle removes the `FCM User Token` row
- [ ] Uninstalling the app then sending produces an `UNREGISTERED` prune, not a
      growing error log
- [ ] `fcm_service_account_json` is a Password field and does not appear in
      `frappe.get_doc(...).as_dict()` output or any API response
- [ ] The send runs in a background job, not inline in the save
- [ ] On iOS Safari (not installed), the UI explains instead of offering a toggle
