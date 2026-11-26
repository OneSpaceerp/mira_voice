# 0008: ARI call events, call records and live state (Valkey)

- Status: accepted
- Date: 2026-11-26
- Task: 1.3 (BUILD_GUIDE)

## Context
Task 1.3 asks for a Python ARI client in Mira Core, call events in `call_events`, and live state in Redis. The study names "Redis (start) → NATS when scaling" for live state and the event bus.

Constraints:
- **Who controls calls.** Calls are still routed by the generated dialplan (ADR 0006/0007). Stasis control, where ARI drives the call, arrives with the IVR engine (task 1.4). Mira must follow every call now without taking it over.
- **One codebase.** On-premise (Server) and multi-tenant (Cloud) editions share it, and the call history must always say which tenant a call belongs to.
- **Restarts.** The worker restarts on upgrades and crashes, but no call may be lost or left "in progress" forever.
- **Privacy.** Callers type card and account numbers on their keypads, so the event trail must never contain DTMF.
- **Licence.** Redis 8 is licensed RSALv2 / SSPLv1 / AGPLv3, which raises questions for software NSD ships to customers on-premise.

## Decision

### 1. One event worker per Asterisk node: `mira-core call-events`
- It runs as the Compose service `core-events`, from the same image as Core.
- It connects to `ws://127.0.0.1:8088/ari/events?app=mira&subscribeAll=true`, with credentials in an `Authorization` header (never in the URL).
- `subscribeAll` delivers events for every channel without putting channels into Stasis, so the dialplan keeps routing.
- An ARI `eventFilter` limits the stream to ten channel event types. DTMF, variable and dialplan-application events never leave Asterisk.
- The websockets `connect()` iterator reconnects with exponential backoff.
- Health: the worker touches a marker file every 10 s while connected; the container is healthy if the marker is less than 60 s old.

### 2. A call is a linkedid
- `ari.conf` sets `channelvars = CHANNEL(linkedid)`, so every channel's JSON says which call it belongs to (verified on Asterisk 22.12: both legs carry the first channel's id).
- The tenant comes from the channel's `tenantid`, which is set on every Mira endpoint. Channels without one, such as the lab extensions, are not recorded.

### 3. The rules, in `call_tracker.py`

| Field | Rule |
| --- | --- |
| Direction | Inbound when the first channel is a trunk; outbound when a trunk leg is dialled; internal otherwise |
| Called number | First real extension the first channel reaches, i.e. the DID on trunk calls |
| Answered | When a *dialled* channel goes Up |
| Agent | The extension user who placed an internal or outbound call, or who answered an inbound one |
| Outcome | `answered` / `busy` (Dial BUSY, cause 17) / `failed` (CHANUNAVAIL, CONGESTION, causes 1, 3, 34, 38) / `no_answer` otherwise |

A call that Asterisk answers by itself (a prompt, the echo test) is not "answered" by anyone. IVR answers come with task 1.4.

### 4. Storage
- **`calls` row:** created at the first channel, updated as events arrive, closed when the last channel is destroyed.
- **`call_events`:** keeps eight event types, each reduced to channel name, state, dial status, bridge id or hangup cause. Nothing a caller typed is kept.

### 5. Restart safety
After every (re)connect the worker reads `GET /channels` and reconciles:
- Open calls whose channels are gone are closed with a `MiraReconciled` event, keeping `answered` if they were answered.
- Calls still in progress are picked up again.
- Live state is rebuilt from scratch.

A partial index `ix_calls_open` (migration 0004) keeps the lookup of open calls cheap.

### 6. Live state in Valkey 9.1 (`valkey/valkey:9.1.4-trixie`)
Valkey is the Linux Foundation's BSD-3-licensed fork of Redis. It speaks the same protocol, and the standard `redis` Python client works unchanged. The study's "Redis" means "a Redis-protocol store"; this ADR fixes the product.

| Item | Detail |
| --- | --- |
| `mira:call:<id>` | Hash for one active call, 12 h TTL as a safety net |
| `mira:tenant:<id>:calls` | Set of the tenant's active calls |
| `mira:tenant:<id>:events` | Pub/sub: `call.started`, `call.updated`, `call.ended` (for wallboards and Mira Desk, tasks 2.x) |
| Network | `127.0.0.1:6379` only; host networking like the other services |
| Password | `REDIS_PASSWORD` from `.env`, written into a config file inside the container, never on a command line |
| Persistence | None: live state is rebuilt from Asterisk. Runs as the `valkey` user |

### 7. Call-control API (`/api/v1/calls`)

| Endpoint | What it does |
| --- | --- |
| `GET /calls` | History, newest first, paged with `before` |
| `GET /calls/live` | Active calls, from Valkey |
| `GET /calls/{id}` | One call with its events |
| `POST /calls/{id}/hangup` | Hangs up every channel of the call |
| `POST /calls` | Click-to-call: ring the user's own extension, then dial the number from it through the tenant's dialplan, with the same routes and caller-ID rules as a dialled call |

Who may use them:
- Agents see and hang up only their own calls.
- Supervisors and tenant admins handle their whole tenant.
- Platform admins must name the tenant.
- Only tenant admins may click-to-call from someone else's extension.

## Consequences
- With subscribeAll, every channel event crosses the WebSocket. The event filter keeps that to channel lifecycle events; the load test (task 2.7) will measure the worker. NATS replaces Valkey pub/sub when Cloud needs several consumers.
- Each Asterisk node needs its own worker. With several nodes (Mira Cloud), linkedids are unique per node, so one table is fine.
- Call outcomes for queue and IVR calls (abandoned, answered by the IVR) need the Stasis events of tasks 1.4–1.5; the rules above are written to be extended there.
- Valkey keeps nothing on disk. If Valkey alone restarts, the worker notices within 10 s (its `run_id` changes) and publishes every live call again from memory. While Valkey is down, call records still go to PostgreSQL; only the live view is missing.
- Tenants with call records cannot be deleted. That was already the rule: tenants are suspended, and call records fall under retention.
