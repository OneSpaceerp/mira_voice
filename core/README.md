# core/ — Mira Core

The control plane of Mira Voice: REST API (FastAPI), auth, the data model (PostgreSQL 16, SQLAlchemy 2 + Alembic), and — from Phase 1 — Asterisk control over ARI, config generation, workers, webhooks and push.

## Run the checks (needs Docker for the test database)

```bash
cd core
uv sync                      # Python 3.12 + locked dependencies (uv.lock)
uv run pytest                # starts a throwaway PostgreSQL 16, applies the migrations, runs the tests
uv run mypy                  # strict typing
uv run ruff check --config ../ruff.toml . && uv run ruff format --config ../ruff.toml --check .
```

## Layout

| Path | What |
| --- | --- |
| `src/mira_core/config.py` | Settings from the environment (`/opt/mira/.env` keys: `POSTGRES_*`, `MIRA_JWT_SECRET`, …) |
| `src/mira_core/models/` | Data model v1: tenants, users, extensions, trunks, queues, queue members, IVR flows, calls, call events, recordings |
| `src/mira_core/api/` | `/health`, `/health/ready`, `/api/v1/auth/{token,me}`, `/api/v1/tenants`, `/api/v1/users` |
| `src/mira_core/security.py` | Argon2id password hashes, HS256 JWT (minimum key length enforced, `exp/iat/sub/type` required) |
| `src/mira_core/api/extensions.py` | `/api/v1/extensions` — create (SIP password shown once), list, delete, rotate password |
| `src/mira_core/api/trunks.py` | `/api/v1/trunks` — carrier trunks (registration, IP-auth) and GSM gateways (SIP account shown once); carrier passwords encrypted, never returned |
| `src/mira_core/api/routes.py` | `/api/v1/outbound-routes` (pattern → ordered trunks, failover, caller ID) and `/api/v1/inbound-routes` (DID → extension) |
| `src/mira_core/asterisk_config.py` | Generates `extensions_mira.conf`, `pjsip_mira.conf` (trunks) and Kamailio's `dispatcher.list`; reloads Asterisk (ARI) and Kamailio (JSON-RPC) only when a file changed (ADR 0006, 0007) |
| `src/mira_core/api/calls.py` | `/api/v1/calls` — history, `/live` (from Valkey), call detail with events, `/{id}/hangup`, click-to-call (`POST /calls`) |
| `src/mira_core/call_tracker.py` | ARI events → `calls` + `call_events` + live state: direction, numbers, agent, outcome; reconcile after a restart (ADR 0008) |
| `src/mira_core/ari_events.py` | The event worker `mira-core call-events` (service `core-events`): ARI WebSocket with subscribeAll + event filter, reconnects, health marker, Valkey restart detection |
| `src/mira_core/live.py` | Live state in Valkey: `mira:call:<id>`, `mira:tenant:<id>:calls`, pub/sub `mira:tenant:<id>:events` |
| `src/mira_core/api/flows.py`, `api/prompts.py`, `api/voicemails.py` | Mira Flow (task 1.4): flows with drafts, publish, versions, rollback, `/flows/schema`; prompt library with AR/EN/FR WAV uploads; voicemail list, play, delete |
| `src/mira_core/flows/` | `schema.py` = Mira Flow v1 format, `validate.py` = wiring and reference checks, `engine.py` = runs a flow on a call, `worker.py` = `mira-core ivr` (service `core-ivr`), `http_dip.py` = safe data dips (ADR 0009, 0010) |
| `src/mira_core/crypto.py` | Fernet encryption with `MIRA_DATA_KEY` for secrets Mira must read back (carrier passwords) |
| `src/mira_core/asterisk_config.py` | Generated dialplan (one context per tenant) + ARI reload (ADR 0006) |
| `src/mira_core/cli.py` | `mira-core create-admin --email …`, `ensure-db-roles`, `render-config`, `call-events` (the ARI event worker), `ivr` (the Mira Flow engine) |
| `migrations/` | Alembic (async). One migration per change; `uv run alembic check` must say nothing to do. 0002 = the read-only views Asterisk reads (realtime); 0003 = trunk credentials, outbound/inbound routes, views without trunks; 0004 = index of calls in progress; 0005 = flows, versions, prompts; 0006 = flow numbers, inbound routes to flows, voicemails |
| `tests/` | pytest + httpx against a real PostgreSQL (testcontainers) |

## Rules built in

- **Roles:** `platform_admin` (no tenant) › `tenant_admin` › `supervisor` › `agent`. The database enforces "platform admin ⇔ no tenant".
- **Tenant isolation:** every tenant-owned row has `tenant_id`; other tenants' objects answer 404, never 403.
- **Tokens follow the account:** disabling a user, changing a role or suspending a tenant cuts access on the next request.
- **No secrets at rest in clear:** passwords Argon2id; SIP passwords (extensions, GSM gateways) only as digest HA1; carrier passwords encrypted with Fernet (`MIRA_DATA_KEY`) and written only to the Asterisk-only 0640 trunk file.

## On the server

`deploy/install.sh` builds `mira/core`, and `mira.service` runs PostgreSQL, a one-shot `core-migrate` (`alembic upgrade head`) and `core` — all on 127.0.0.1. First platform admin:

```bash
cd /opt/mira && sudo docker compose exec core mira-core create-admin --email it@example.com --name "IT"
```

API docs (from the server itself, or through an SSH tunnel): `http://127.0.0.1:8000/docs`.
