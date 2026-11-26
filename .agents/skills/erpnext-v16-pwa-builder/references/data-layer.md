# Data layer

Auth, fetching, realtime, files, workflow and offline caching between a Vue SPA
and Frappe v16.

## Two generations of the same idea

frappe-ui ships both. Pick one per app.

| | Legacy resources | Modern composables |
|---|---|---|
| API | `createResource`, `createListResource`, `createDocumentResource` | `useCall`, `useList`, `useDoc`, `useDoctype`, `useNewDoc` |
| Frappe API | v1 (`/api/method`, `/api/resource`) | **v2** (`/api/v2/method`, `/api/v2/document`) |
| Ships in | every version, incl. 0.1.105 | 0.1.10x+ (partial), complete in 1.x |
| Offline cache | opt-in `cache:` key, in-memory + IDB | `cacheKey`, IndexedDB via `idb-keyval` |
| Status | supported and un-deprecated through 1.x | recommended for new code |
| Used by | Frappe HR v16 | frappe-ui 1.x docs, new Frappe apps |

**Track A (Ionic/0.1.105): use legacy resources.** **Track B (1.x): use `use*`.**
Mixing them for the same doctype means two caches that drift.

---

## Session and auth

Frappe's session is a **cookie**. The SPA does not hold a token; it reads the
`user_id` cookie to know whether it is logged in, and every request carries the
cookie plus the CSRF header (frappe-ui's fetch layer adds
`X-Frappe-CSRF-Token` from `window.csrf_token` automatically).

```js
// src/data/session.js
import { computed, reactive } from 'vue'
import { createResource, call } from 'frappe-ui'
import { userResource } from './user'
import router from '@/router'

export function sessionUser() {
  const cookies = new URLSearchParams(document.cookie.split('; ').join('&'))
  const user = cookies.get('user_id')
  return !user || user === 'Guest' ? null : user
}

export const session = reactive({
  user: sessionUser(),
  isLoggedIn: computed(() => !!session.user),

  login: async (email, password) => {
    const res = await call('login', { usr: email, pwd: password })
    if (res.message === 'Logged In') {
      userResource.reload()
      session.user = sessionUser()
      router.replace({ path: '/' })
    }
    return res
  },

  // Frappe returns a tmp_id when 2FA is on; the second call completes login
  otp: async (tmp_id, otp) => {
    const res = await call('login', { tmp_id, otp })
    if (res.message === 'Logged In') {
      session.user = sessionUser()
      router.replace({ path: '/' })
    }
    return res
  },

  logout: createResource({
    url: 'logout',
    onSuccess() {
      userResource.reset()
      session.user = sessionUser()
      router.replace({ name: 'Login' })
      window.location.reload()   // drops every in-memory cache
    },
  }),
})
```

`window.location.reload()` on logout is deliberate. Resetting resources by hand
leaves stale caches (and IndexedDB entries) behind; a reload is the only reliable
way to guarantee the next user sees nothing of the previous one. **On a shared
device this is a security requirement, not a convenience** — also clear the IDB
cache explicitly if you use `cacheKey` (see Offline below).

### The route guard

```js
router.beforeEach(async (to, _from, next) => {
  let isLoggedIn = session.isLoggedIn
  try {
    if (isLoggedIn) await userResource.reload()    // server is the authority
  } catch {
    isLoggedIn = false                              // cookie existed but is dead
  }

  if (!isLoggedIn) {
    return ['Login', 'ForgotPassword'].includes(to.name) ? next() : next({ name: 'Login' })
  }

  // domain gate: this app is for employees only
  await employeeResource.promise
  if (!employeeResource.data || employeeResource.data.user_id !== userResource.data.name) {
    return next({ name: 'InvalidEmployee' })
  }

  if (['Login', 'ForgotPassword'].includes(to.name)) return next({ name: 'Home' })
  next()
})
```

The `try/catch` around `reload()` is the part people skip. A `user_id` cookie
outlives the server session; without the catch, an expired session leaves the user
staring at a spinner on a screen that will never load.

Give the domain gate its own screen (`InvalidEmployee`) explaining what's wrong and
who to contact. A logged-in user bounced to `/login` with no message files a
support ticket.

---

## Fetching — modern (`use*`)

```ts
import { useCall, useList, useDoc, useNewDoc, useDoctype } from 'frappe-ui'
```

**Read a method.** Auto-fetches on mount (`immediate` defaults `true`).

```ts
const summary = useCall<Summary>({
  url: '/api/v2/method/my_pwa.api.get_dashboard_summary',
  cacheKey: 'my_pwa:summary',
})
// summary.data | summary.loading | summary.error   — reactive object, no .value
```

**Write a method.** `immediate: false`, then `await submit(params)`.

```ts
const approve = useCall<Order, { name: string }>({
  url: '/api/v2/method/my_pwa.api.approve_request',
  method: 'POST',
  immediate: false,
  onError: (e) => toast.error(e.message),
})
await approve.submit({ name: order.name })
```

`await submit()` only sequences under the default `refetch: false`. Set
`refetch: true` and `submit` returns before the request goes out — a classic
"why did my redirect fire early" bug.

**List a doctype.** Note `refetch` defaults to **`true`** here (unlike `useCall`),
so reactive `filters`/`orderBy` refetch automatically.

```ts
const status = ref('Open')
const orders = useList<Order>({
  doctype: 'Sales Order',
  fields: ['name', 'customer', 'grand_total', 'status'],
  filters: () => ({ status: status.value }),
  orderBy: 'modified desc',
  limit: 20,
  cacheKey: ['my_pwa:orders', status],
})
// orders.data (null until first response — guard it), orders.next(), orders.hasNextPage
// writes: orders.insert.submit(values) | orders.setValue.submit({name, ...}) | orders.delete.submit({name})
```

`start` and `limit` are **readonly** — page with `next()` / `previous()`, never by
assigning.

**One document.** Returns `doc`, **not** `data`. Documents are shared through a
reactive store: every `useDoc` and matching `useList` row for the same
doctype/name is the same object, so a write from anywhere updates all of them.

```ts
const order = useDoc<Order>({
  doctype: 'Sales Order',
  name: () => route.params.name,
  methods: { sendReminder: 'send_reminder' },   // → order.sendReminder.submit()
})
await order.setValue.submit({ status: 'Closed' })
```

`useDoc` has **no** `cacheKey`, `refetch`, `initialData`, `onSuccess` or `onError`
option — only `doctype`, `name`, `baseUrl`, `url`, `methods`, `immediate`,
`staleOnError`, `transform`. Use `order.onSuccess(cb)` (which returns an
unsubscribe) for the callback.

**A new document.**

```ts
const draft = useNewDoc('Sales Order', { status: 'Draft' })
// bind straight to draft.doc.customer, then:
const created = await draft.submit()     // resolves with the server-assigned name
```

---

## Fetching — legacy (`createResource`)

The Frappe HR pattern: one module per domain under `src/data/`, exporting shared
singleton resources.

```js
// src/data/orders.js
import { createResource, createListResource } from 'frappe-ui'
import dayjs from '@/utils/dayjs'

export const myOrders = createResource({
  url: 'my_pwa.api.get_my_orders',
  params: { limit: 20 },
  auto: true,
  cache: 'my_pwa:my_orders',
  transform: (rows) => rows.map((r) => ({ ...r, when: dayjs(r.transaction_date).format('D MMM') })),
  onSuccess: () => summary.reload(),
})

export const orderList = createListResource({
  doctype: 'Sales Order',
  fields: ['name', 'customer', 'grand_total', 'status'],
  filters: { docstatus: ['!=', 2] },
  orderBy: 'modified desc',
  pageLength: 20,
  auto: false,
  cache: 'my_pwa:orders',
})
```

- **`cache:` is what makes it a singleton.** Two modules calling `createResource`
  with the same cache key get the same object, and the socket handler below can
  find it by key. Without a cache key there is no cross-component sharing.
- `transform` runs on every response — keep it pure and cheap; it is not a place
  for network calls.
- `auto: true` fetches on creation, which means **at module import time** — before
  login on a cold start. For anything permission-sensitive use `auto: false` and
  `reload()` from the view, or the first paint fires a 403.

### Infinite scroll against `reportview`

Frappe HR's generic list hits `frappe.desk.reportview.get`, which returns
`{keys: [...], values: [[...]]}` rather than dicts, and zips them in `transform`:

```js
const documents = createResource({
  url: 'frappe.desk.reportview.get',
  onSuccess: (data) => {
    if (data.values?.length < PAGE_LENGTH) hasNextPage.value = false
  },
  transform(data) {
    if (!data.length) return []
    const rows = data.values.map((v) =>
      Object.fromEntries(data.keys.map((k, i) => [k, v[i]])),
    )
    // append when paging, replace on first page
    return documents.params.start ? documents.data.concat(rows) : rows
  },
})

function fetchList(start = 0) {
  documents.submit({
    doctype: 'Sales Order',
    fields: ['name', 'customer', 'status'],
    order_by: '`tabSales Order`.modified desc',
    page_length: PAGE_LENGTH,
    start,
    filters: [['Sales Order', 'docstatus', '!=', '2'], ...appliedFilters],
  })
}
```

Note `order_by` needs the backticked table prefix. Prefer `useList` or
`createListResource` unless you specifically need report-view filter semantics.

### Link fields (autocomplete)

```js
const options = createResource({
  url: 'frappe.desk.search.search_link',
  method: 'POST',
  params: { doctype, txt: '', filters },
  transform: (data) =>
    data.map((d) => ({
      label: d.description && d.label !== d.value ? `${d.label} : ${d.value}` : d.value,
      value: d.value,
    })),
})
const onQuery = debounce((q) => { options.update({ params: { doctype, txt: q, filters } }); options.reload() }, 300)
```

Two details worth copying from Frappe HR's `Link.vue`: debounce at **300 ms**, and
**inject the current value** into the options list if the server's first page does
not contain it — otherwise editing an existing record shows an empty combobox.

---

## Realtime

```js
// src/socket.js
import { io } from 'socket.io-client'
import { getCachedResource } from 'frappe-ui/src/resources/resources'
import { getCachedListResource } from 'frappe-ui/src/resources/listResource'

export function initSocket() {
  const host = window.location.hostname
  const siteName = window.site_name
  const port = window.location.port ? `:${window.frappe?.boot?.socketio_port || 9000}` : ''
  const protocol = port ? 'http' : 'https'

  const socket = io(`${protocol}://${host}${port}/${siteName}`, {
    withCredentials: true,
    reconnectionAttempts: 5,
  })

  socket.on('my_pwa:refetch_resource', ({ cache_key }) => {
    const r = getCachedResource(cache_key) || getCachedListResource(cache_key)
    r?.reload()
  })

  return socket
}
```

Provide it once (`app.provide('$socket', socket)`) and inject where needed.

The `port ? 'http' : 'https'` trick is how Frappe HR distinguishes dev (explicit
port, plain http) from production (behind nginx/TLS, socket proxied on 443). On a
reverse-proxied production site the socket path is handled by nginx — do not
hardcode `:9000` there.

Generic doctype updates without any server code:

```js
export function useListUpdate(socket, doctype, callback) {
  socket.emit('doctype_subscribe', doctype)     // subscribe once per doctype
  socket.on('list_update', (d) => { if (d.doctype === doctype) callback(d.name) })
}
```

Guard the subscribe with a module-level `Set` so remounting a list view does not
stack duplicate handlers — Frappe HR keeps a `reactive({})` of subscribed
doctypes for exactly this.

On a PWA, **reconnect on resume**: mobile browsers kill sockets when the app is
backgrounded. Listen for `visibilitychange` and refetch the visible screen's
resources rather than trusting the socket to have caught up.

---

## File upload

Frappe HR base64-encodes in the client and posts to its own endpoint, which works
around `FileReader` being patched by Zone.js under Ionic:

```js
function getFileReader() {
  const fr = new FileReader()
  return fr['__zone_symbol__originalInstance'] || fr
}
```

For everything else, frappe-ui's `FileUploadHandler` / `<FileUploader>` posts
multipart to `/api/method/upload_file` and gives you progress. Prefer it — base64
inflates payloads ~33% and is a real cost on 3G.

Server-side, always pass `is_private=1` for anything business data, and attach to
the document (`attached_to_doctype` / `attached_to_name`) so permissions follow.

---

## Workflow

```js
const workflowDoc = createResource({
  url: 'my_pwa.api.get_workflow',
  params: { doctype },
  cache: ['my_pwa:workflow', doctype],
})

const transitions = createResource({
  url: 'frappe.model.workflow.get_transitions',
  params: { doc },
  transform: (data) =>
    data
      .filter((t) => t.allow_self_approval || userResource.data.name !== doc.owner)
      .map((t) => t.action),
})

await createResource({ url: 'frappe.model.workflow.apply_workflow', params: { doc, action } }).reload()
```

The self-approval filter matters: without it a requester sees "Approve" on their
own request, clicks it, and gets a server error they cannot interpret.

Read-only state: compare the doc's workflow state's `allow_edit` roles against
`userResource.data.roles`, and render the form disabled rather than letting the
user type into fields the server will reject.

---

## Offline

Three layers, in order of how much they buy you:

**1. Cached resources (free).** `cacheKey` / `cache:` persists the last response in
IndexedDB (`idb-keyval`). On a cold offline start the cached value renders
immediately while the refetch fails silently in the background. This alone turns a
blank error screen into a usable read-only app. Use it on every list and dashboard
the user opens first.

**2. Precached shell (service worker).** The HTML/JS/CSS are precached by
Workbox, so the app boots offline. See `pwa-runtime.md`.

**3. Queued writes (you build it).** Frappe has no offline write protocol. If the
app must accept input offline:

- Write the intent to IndexedDB with a client-generated idempotency key.
- Render it optimistically, visibly marked "pending".
- Flush on `online` and on app resume; on success, replace the optimistic row with
  the server's.
- Send the client's `modified` timestamp with the write and let the server reject
  stale updates (`frappe.throw` on mismatch) instead of silently clobbering.
- Cap the queue and surface failures — a silent queue that never drains is worse
  than refusing the write.

Be honest with the user about which of the three you shipped. "Works offline" that
means "reads work, writes are lost" is the fastest way to lose trust in a
field-service tool.

---

## Translations

Boot carries `__messages`; load them before mounting so nothing flickers.

```js
// src/plugins/translationsPlugin.js — the Frappe HR shape, condensed
let messages = {}

async function load() {
  if (window.frappe?.boot?.__messages) { messages = window.frappe.boot.__messages; return }
  const url = new URL('/api/method/frappe.translate.load_all_translations', location.origin)
  url.searchParams.set('lang', window.frappe?.boot?.lang ?? navigator.language)
  url.searchParams.set('hash', window.frappe?.boot?.translations_hash || Math.random())
  try { messages = (await (await fetch(url)).json()) || {} } catch (e) { console.error(e) }
}

export function __(txt, replace, context = null) {
  if (!txt || typeof txt !== 'string') return txt
  let out = (context && messages[`${txt}:${context}`]) || messages[txt] || txt
  if (replace && typeof replace === 'object') {
    let i = 0
    out = out.replace(/\{(\w*)\}/g, (m, k) => {
      if (k === '') k = i++
      return k == +k && replace[k] !== undefined ? replace[k] : m
    })
  }
  return out
}

export const translationsPlugin = {
  isReady: () => Promise.allSettled([load()]),
  install(app) {
    app.config.globalProperties.__ = __
    app.provide('$translate', __)
  },
}
```

Mount only after it resolves:

```js
router.isReady().then(async () => {
  await translationsPlugin.isReady()
  app.mount('#app')
})
```

For an Arabic/RTL deployment, also set `dir` on `<html>` from `boot.lang` at this
point, and use logical CSS properties (`ms-`/`me-`, `ps-`/`pe-`) rather than
`ml-`/`mr-` throughout — retrofitting RTL into Tailwind directional classes is a
full-app rewrite.
