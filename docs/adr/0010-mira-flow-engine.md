# 0010: The Mira Flow engine (IVR over ARI), voicemail, data-dip safety

- Status: accepted (stage 2 of task 1.4; the visual builder is stage 3)
- Date: 2026-11-26
- Task: 1.4 (BUILD_GUIDE)

## Context
ADR 0009 fixed the flow format (`mira-flow/1`). This ADR decides how flows run on live calls, how calls reach them, how voicemail is stored, and how the HTTP data dip is kept safe.

Constraints:
- The dialplan stays generated (ADR 0006).
- Call records come from the event worker (ADR 0008).
- Callers type account numbers and PINs into IVRs.
- The data dip runs on a server where every internal service listens on loopback.

## Decision

### 1. How calls reach a flow
- An inbound route's destination is an extension **or** a flow (`destination_flow_id`; exactly one, enforced in the database).
- A flow can also have an internal `number` (it may not clash with an extension), so staff can dial it to test or use it.
- Both generate `Stasis(mira-ivr,<flow id>)` in the tenant's contexts, followed by `Hangup()`.
- Only flows with a published version are routed; a route to an unpublished flow is refused by the API.
- Rollback needs no dialplan change: the engine reads the current published version on every call.

### 2. The engine: `mira-core ivr`, Compose service `core-ivr`
- It listens to ARI as the Stasis application `mira-ivr` (no subscribeAll) and runs one asyncio task (`FlowRun`) per call.
- On `StasisStart` it loads the published version, the tenant's timezone and language, which languages each prompt has, and queue numbers. It then checks that the channel's `tenantid` owns the flow (defence in depth).
- Events are routed to the run by channel id. Playback and recording events name their channel as `target_uri`.
- Health uses the same marker as `core-events`. Errors in one call never stop the others.

| Node | What the engine does |
| --- | --- |
| play | `POST /channels/{id}/play` with `sound:mira/<tenant>/<lang>/<prompt>`, the exact file. Language order: the call's language, then the tenant's default, then any recording that exists |
| menu | Keys typed during the prompt interrupt it (`DELETE /playbacks/{id}`). Typed-ahead keys are kept |
| collect | Up to `max_digits`, stops at the terminator; under `min_digits` goes to `timeout_next` |
| time | Evaluated in the tenant's timezone (or the node's). Holidays are closed. `to` is exclusive |
| language | Also sets `CHANNEL(language)`, so prompts after a transfer match |
| transfer / queue | `POST /channels/{id}/continue` into the tenant's own context: extensions, outbound routes and caller-ID rules all apply |
| voicemail | Greeting (or `vm-intro`), then `POST /channels/{id}/record` (wav, beep, `#` ends, 10 s silence ends). The message is saved even when the caller simply hangs up |
| hangup | `DELETE /channels/{id}` |

**Limits:** at most 200 steps and 30 minutes per call. Any engine error hangs the call up cleanly instead of leaving the caller in silence.

### 3. IVR path, without the digits
- `call_events` gets `FlowStarted`, one `FlowNode` per node (node id and type), and `FlowEnded` (outcome and last node).
- Variables, and so the digits a caller typed, are never written anywhere.

### 4. Voicemail
- Messages are ARI recordings in Asterisk's spool, kept in a `voicemail` volume across container rebuilds.
- Each message gets a `voicemails` row: tenant, mailbox (an extension number), caller, call, flow, duration, heard flag.
- The API plays the audio through ARI (`GET /recordings/stored/{name}/file`), so Core needs no access to Asterisk's files.
- Who sees what: agents see the mailboxes of their own extensions; supervisors and tenant admins see the tenant's.
- Listening marks a message heard. Deleting removes the recording too.

### 5. Data dip safety (`flows/http_dip.py`)
- The host is fixed in the flow (ADR 0009).
- At call time every address the host resolves to must pass the check below, and the request goes to that checked IP. The `Host` header and TLS SNI carry the name (httpx `sni_hostname`), so certificates are verified as usual and DNS cannot swap the address between check and connect.
- **Always blocked:** loopback (every Mira service listens there), link-local (cloud metadata at 169.254.169.254), multicast, unspecified and reserved addresses, and IPv4-mapped forms of these.
- **Private LAN ranges** are allowed on the Server edition, where ERPNext is usually on the LAN. Mira Cloud sets `MIRA_FLOW_HTTP_ALLOW_PRIVATE=false`.
- No redirects; answers are capped at 64 KB and must be JSON; timeout ≤ 5 s. Any failure goes to `error_next`.

## Consequences
- One engine per Asterisk node, like `core-events`. Calls already in a flow while `core-ivr` restarts are lost (Asterisk ends them when the app goes away), so upgrades should drain or happen off-hours.
- Calls that end inside a flow (voicemail, hangup) keep the tracker's outcome, `no_answer`, while the IVR outcome is in `FlowEnded`. Reports (task 2.4) combine the two, and queue answers come with task 1.5.
- Voicemail retention follows the tenant's recording retention once task 1.6 adds the retention job.
