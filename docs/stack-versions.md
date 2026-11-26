# Stack versions

Claude Code fills this table from **context7** before using a library (see CLAUDE.md rule 2). One row per library; update the row when you upgrade.

How versions were picked (task 0.1, 2026-11-25): context7 for docs, requirements and the hook syntax; the official registries (PyPI, npm, Flutter's release feed, GitHub releases, downloads.asterisk.org) for the exact latest stable number, because context7's indexed versions can lag. "Pin" means the version new code starts on; Dependabot/upgrade tasks move it later.

## Platforms and runtimes

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Ubuntu Server | 24.04 LTS and **26.04 LTS** (26.04.1 tested) | 2026-11-26 | — (ubuntu.com release notes) | Both are targets (ADR 0012). 26.04.1 released 27 Aug 2026, supported to 2031; it ships **rust-coreutils** (uutils) as `coreutils` and **sudo-rs** as `sudo`: the installer is tested on it, keep scripts to POSIX/GNU-common flags |
| Asterisk | 22 LTS (22.12.0) | 2026-11-25 | /asterisk/asterisk (22.6.0 indexed), /websites/asterisk | Bug fixes to Oct 2028, security fixes to Oct 2029 (asterisk.org). See Telephony below |
| Python (Mira Core) | 3.12 | 2026-11-25 | — | Ubuntu 24.04's system Python; Docker image `python:3.12-slim`. FastAPI 0.165 and SQLAlchemy 2.1 need ≥ 3.11 |
| Python (Mira Connect) | 3.14 | 2026-11-25 | /websites/frappe_io_framework | Required by Frappe v16 (install docs). Lives only inside the Frappe bench |
| Node.js | 24 LTS (24.22.3) | 2026-11-25 | — (nodejs.org/dist) | One Node for the repo: Frappe v16 requires 24; Vite 8 needs ≥ 20.19/22.12; create-vue and Vitest 5 need ≥ 22.12. **Ubuntu 24.04's apt `nodejs` is 18 — too old; install 24 with nvm** |

## Deployment (deploy/)

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Docker Engine | latest `docker-ce` from Docker's apt repo (`noble` or `resolute`, stable) | 2026-11-26 | /docker/docs | Install steps from docs.docker.com/engine/install/ubuntu: remove `docker.io` etc., key in `/etc/apt/keyrings/docker.asc`, deb822 `docker.sources`. **Published container ports bypass ufw** (Docker docs, "Docker and ufw") |
| Docker Compose plugin | v5 (`docker-compose-plugin`; 5.8.0 installed on test 2026-11-25) | 2026-11-25 | /docker/compose (v5.6.1) | systemd unit uses `up --detach --wait --remove-orphans`; images built with `network: host` (Docker's build network cannot reach some local resolvers, e.g. WSL's) |
| ufw | Ubuntu 24.04 package | 2026-11-25 | none in context7 (only add-ons) — read the Ubuntu noble man page, manpages.ubuntu.com ufw(8) | Port ranges need a protocol (`10000:20000/udp`); `limit` for SSH; `--force enable` for scripts |
| nginx (web container) | **1.30.8** (`nginx:1.30.8-trixie`, = `stable` on 2026-11-26) | 2026-11-26 | /websites/nginx_en, /nginx/docker-nginx | Serves Mira Desk, `/api` → Core (ADR 0012). `http2 on;` (not `listen … http2`), `add_header_inherit merge` (≥ 1.29.3) so security headers reach every location; image has `curl` (health check) |
| Node.js (build stage of the web image) | 24.22.3 (`node:24.22.3-trixie-slim`) | 2026-11-26 | — (Docker Hub) | Builds Mira Desk inside Docker: the server needs no Node |
| fail2ban | Ubuntu package (1.0.x on 24.04) | 2026-11-25 | /fail2ban/fail2ban | `backend = systemd` for sshd (needs `python3-systemd`; Ubuntu 24.04 may have no `/var/log/auth.log`), `banaction = ufw` |

## Telephony (telephony/) — task 0.3

All custom images are based on **Debian 13 "trixie" slim** (`debian:trixie-slim`); they run on the Ubuntu 24.04 host under Docker.

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Asterisk | 22.12.0 (image `mira/asterisk:22.12.0`) | 2026-11-25 | /asterisk/asterisk (22.6.0), /websites/asterisk | Compiled from the release tarball, SHA256 `f8b2ba98…e35e2` checked in the Dockerfile. Bundled pjproject. In 22, `chan_sip`, `chan_mgcp` and `chan_skinny` are gone and AMI (`manager`) is built in (switched off in `manager.conf`). Prompts: EN + FR (ulaw, G.722); no official Arabic set |
| unixODBC + psqlODBC | Debian trixie `unixodbc-dev` (build), `odbc-postgresql` (runtime, driver "PostgreSQL Unicode") | 2026-11-25 | /websites/asterisk (Setting up PJSIP Realtime) | Asterisk realtime (task 1.1): `res_odbc` + `res_config_odbc`, preloaded; build fails if either module or the driver is missing. Asterisk 22: `auth_type=digest` + `password_digest` (`md5_cred` deprecated) |
| Kamailio | 6.1.6 (`6.1.6+bpo13`, image `mira/kamailio:6.1.6`) | 2026-11-25 | /kamailio/kamailio | deb.kamailio.org `kamailio61` trixie; key fingerprint `E79ACECB87D8DCD23A20AD2FFB40D3E6508EA4C8` checked at build. context7 thin on module docs: path, tls, rtpengine read on kamailio.org/docs/modules/6.1.x |
| RTPengine | 26.0.1.29 LTS (`26.0.1.29-1~bpo13+1`, image `mira/rtpengine:26.0.1.29`) | 2026-11-25 | /sipwise/rtpengine (mr26.3.1.2) | rtpengine.dfx.at (repo named in the rtpengine docs), LTS series 26.0; keyring .deb SHA256 `78fe26f0…e088` checked. Debian's own package is 12.5 (too old). Userspace forwarding (`table = -1`) |
| coturn | 4.19.2 (`coturn/coturn:4.19.2-trixie`, wrapped as `mira/coturn:4.19.2`) | 2026-11-25 | /coturn/coturn | Official image; Mira adds an entrypoint that writes the config so the TURN secret is not on the command line. `no-cli` is deprecated in 4.19 (CLI off by default) |
| Valkey | 9.1.4 (`valkey/valkey:9.1.4-trixie`) | 2026-11-26 | /valkey-io/valkey-doc (9.1.4) | Live call state + pub/sub (ADR 0008), the BSD-licensed Redis fork (Redis 8 is RSALv2/SSPLv1/AGPLv3). `bind 127.0.0.1`, `protected-mode yes`, `requirepass` from a config file (never argv), `save ''` + `appendonly no` (rebuilt from Asterisk) |
| Asterisk ARI events (task 1.3) | 22.12.0 | 2026-11-26 | /websites/asterisk | `GET /events?app=mira&subscribeAll=true` (all channels, no Stasis); `PUT /applications/{app}/eventFilter` with an `allowed` list; Channel JSON has `tenantid`; `ari.conf channelvars = CHANNEL(linkedid)` works with a function (tested on 22.12); originate `POST /channels` (endpoint, context, extension, callerId, timeout); hangup `DELETE /channels/{id}?reason=normal` |
| Asterisk ARI for Mira Flow (task 1.4) | 22.12.0 | 2026-11-26 | /websites/asterisk | Stasis app `mira-ivr`: `POST /channels/{id}/answer`, `/play?media=sound:…&lang=&playbackId=`, `DELETE /playbacks/{id}`, `/variable`, `/continue?context=&extension=&priority=1`, `/record?name=&format=wav&maxDurationSeconds=&maxSilenceSeconds=&beep=true&terminateOn=%23`, `GET/DELETE /recordings/stored/{name}[/file]`. **Sounds: Asterisk 22 looks up `<lang>/<path>` only, not `<dir>/<lang>/<file>`** (tested): the engine plays `sound:mira/<tenant>/<lang>/<prompt>` |
| JsSIP (lab test page only) | 3.13.9 | 2026-11-25 | /versatica/jssip (3.10.1 indexed) | npm package ships CommonJS only; the browser bundle is built with esbuild (`npm run build`). The production choice JsSIP vs SIP.js is task 1.7 |
| esbuild (test tooling) | 0.28.2 | 2026-11-25 | /evanw/esbuild (v0.28.1) | `--bundle --format=iife --global-name=JsSIP --platform=browser` |
| Playwright (test tooling) | 1.65.1 | 2026-11-25 | (resolve in task 1.7) | Chromium with fake media; WebRTC calls checked with getStats + Web Audio tone analysis |
| baresip (test tooling) | 1.0.0 (Ubuntu 24.04 `baresip-core`) | 2026-11-25 | none — Ubuntu package docs (`baresip -h`) | Command-line softphone for the call tests. 1.0 quirks: `ausine` only 48 kHz (tests use WAV tones), `-t` does not always exit (tests use `timeout`), no catch-all account (it answers only its own user). DTMF from scripts: module `ctrl_tcp` (`ctrl_tcp_listen`), netstring JSON `{"command":"sndcode","params":"1"}` |
| Kamailio modules for trunks (task 1.2) | 6.1.6 | 2026-11-26 | /kamailio/kamailio (+ kamailio.org/docs/modules/6.1.x dispatcher, jsonrpcs: context7 lacks the parameter text) | `ds_is_from_list(2, "3")` = ignore port and protocol; on a match `attrs_pvname` gets the row's attributes. Carrier rows flag 32 = never pinged (`ds_probing_mode 1` kept). `jsonrpcs transport 1` = HTTP only via xhttp, `jsonrpc_dispatch()` in `event_route[xhttp:request]`. `reload_delta` (default 5 s, 0 = tests only) set to 1: a too-soon `dispatcher.reload` answers **HTTP 500 Ongoing reload** (Core retries) |
| Asterisk trunk objects (task 1.2) | 22.12.0 | 2026-11-26 | /websites/asterisk | `identify` + `match_header = X-Mira-Trunk: …` belongs to the `ip` identifier, hence `endpoint_identifier_order = ip,auth_username,username`; `Dial(PJSIP/number@trunk)`; failover only on DIALSTATUS `CHANUNAVAIL` / `CONGESTION`. A `registration` with `endpoint =` is refused in 22 unless `line = yes` (Mira sets neither) |
| SIPp (test tooling) | Ubuntu 24.04 `sip-tester` | 2026-11-26 | /websites/sipp_readthedocs_io_en | Fake carrier registrar with `verifyauth`, carrier calling in, forged-header test; `-aa` answers Asterisk's OPTIONS keepalives |

## Mira Core (core/) — task 0.4

Locked in `core/uv.lock` (exact versions of everything, including transitive dependencies). Python 3.12 (`python:3.12.16-slim-trixie` image).

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| FastAPI | 0.165.0 (`fastapi[standard]`) | 2026-11-25 | /websites/fastapi_tiangolo | OAuth2 password flow + JWT pattern from the FastAPI security tutorial; async tests with httpx `ASGITransport` + `pytest.mark.anyio` (FastAPI "Async Tests") |
| SQLAlchemy | 2.1.9 (`sqlalchemy[asyncio]`) | 2026-11-25 | /sqlalchemy/sqlalchemy (rel_2_1_6) | **2.1 no longer pulls in greenlet**: the asyncio extension needs the `[asyncio]` extra. `postgresql+psycopg://` selects sync or async automatically |
| Alembic | 1.20.1 | 2026-11-25 | /websites/alembic_sqlalchemy_en | Async env.py (cookbook "Using Asyncio"); naming convention on `Base.metadata`; `path_separator = os` set (1.20 deprecation); `alembic check` in the tests |
| psycopg | 3.3.9 (`psycopg[binary]`) | 2026-11-25 | (SQLAlchemy docs: psycopg dialect) | **Chosen over asyncpg**: one driver for the async app and the sync migrations/tests |
| Pydantic / pydantic-settings | 2.14.4 / 2.16.3 | 2026-11-25 | /pydantic/pydantic-settings (v2.16.2) | Settings read the same keys install.sh writes (`POSTGRES_*`, `MIRA_JWT_SECRET`); `validation_alias` for `MIRA_*` names |
| PyJWT | 2.15.1 | 2026-11-25 | /jpadilla/pyjwt (2.15.1) | HS256, `enforce_minimum_key_length=True`, `require: [exp, iat, sub, type]` |
| pwdlib | 0.4.2 (`pwdlib[argon2]`, argon2-cffi 25.1.0) | 2026-11-25 | /websites/fastapi_tiangolo (security tutorial) | `PasswordHash.recommended()` = Argon2id |
| Uvicorn | 0.54.0 | 2026-11-25 | (via fastapi[standard]) | Bound to 127.0.0.1:8000 |
| uv | 0.13.10 | 2026-11-25 | /websites/astral_sh_uv | Project and lock management; Docker pattern from the uv Docker guide (`ghcr.io/astral-sh/uv:0.13.10`) |
| pytest | 9.2.0 | 2026-11-25 | — | + anyio (FastAPI's async test approach; no pytest-asyncio) |
| testcontainers | 4.15.0 (`testcontainers[postgres]`) | 2026-11-25 | /testcontainers/testcontainers-python | `testcontainers.community.postgres` (old `testcontainers.postgres` path is deprecated); `driver=None` for psycopg 3 |
| mypy | 2.4.1 | 2026-11-25 | — | `strict = true` + pydantic plugin; clean |
| Jinja2 | 3.1.6 | 2026-11-25 | /websites/jinja_palletsprojects_en_stable | Dialplan template: `StrictUndefined`, `autoescape=False` (not HTML; identifiers validated instead) |
| httpx | 0.28.1 | 2026-11-25 | — | ARI client (`PUT /asterisk/modules/{module}` to reload) |
| cryptography | 50.0.2 | 2026-11-26 | /pyca/cryptography (50.0.2) | Task 1.2: Fernet / MultiFernet for carrier passwords (`MIRA_DATA_KEY`, comma-separated keys newest first; `rotate`). Key = 32 random bytes, URL-safe base64 (install.sh: `openssl rand -base64 32` with `+/` -> `-_`) |
| redis (Python client) | 8.2.0 (`redis>=8.1.0`) | 2026-11-26 | /redis/redis-py (v8.1.0) | Task 1.3, used against Valkey: `redis.asyncio.Redis.from_url(..., decode_responses=True)`, transactional pipelines (hset/expire/sadd/publish), pub/sub, `aclose()` |
| websockets | 16.0 (`websockets>=16.0`) | 2026-11-26 | /python-websockets/websockets (16.0) | ARI event stream: `async for ws in connect(url, additional_headers=...)` reconnects with exponential backoff; `extra_headers` was renamed `additional_headers` |
| Pydantic discriminated unions (Mira Flow) | 2.14 | 2026-11-26 | /pydantic/pydantic (v2.14.1) | Task 1.4: `Annotated[A | B | …, Field(discriminator='type')]` with `Literal` tags, `extra='forbid'`, `model_json_schema(by_alias=True)` for the builder |
| httpx `sni_hostname` extension | 0.28.1 | 2026-11-26 | /encode/httpx | Data dip: connect to the checked IP, `Host` header + `extensions={'sni_hostname': name}` keep TLS verification on the name; `client.stream` + `aiter_bytes` to cap answers at 64 KB |
| testcontainers redis module | 4.15.0 (`testcontainers[postgres,redis]`) | 2026-11-26 | /testcontainers/testcontainers-python | `testcontainers.community.redis.RedisContainer` with the Valkey image (`testcontainers.redis` is deprecated: path taken from the library's own DeprecationWarning, not context7) |
| PostgreSQL | 16.16 (`postgres:16.16-trixie`) | 2026-11-25 | — | Docker Hub official image; listens on 127.0.0.1 only |

## Mira Desk (desk/)

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Vue | 3.5.46 | 2026-11-26 | /websites/vuejs | Scaffolded with create-vue 3.24 (needs Node ≥ 22.18). Composition API, `<script setup lang="ts">` |
| Vite | 8.4.0 | 2026-11-26 | /vitejs/vite (v8.3.5 indexed) | `server.proxy` and `preview.proxy` forward `/api` to Mira Core (`MIRA_CORE_URL`) |
| vue-router | 5.5.2 | 2026-11-26 | /vuejs/router | `createWebHistory`, a `beforeEach` sign-in guard, `onBeforeRouteLeave` for unsaved drafts |
| vue-i18n | 11.4.24 | 2026-11-26 | /intlify/vue-i18n | `createI18n({ legacy: false })`; `en.ts` is the master, `ar.ts` / `fr.ts` are typed `typeof en` so a missing key fails `vue-tsc` |
| Vue Flow (`@vue-flow/core`, `background`, `controls`) | 1.48.2, 1.3.2, 1.1.3 | 2026-11-26 | /bcakmakoglu/vue-flow | Canvas for Mira Flow: custom node type, `Handle` ports, `onConnect`, `onNodeDragStop`. MIT. The canvas is forced `dir="ltr"` (a graph has no reading direction); everything around it mirrors |
| lucide-vue-next | 1.0.0 | 2026-11-26 | /lucide-icons/lucide | Icons per design-system §7, `aria-hidden` when next to text |
| @fontsource IBM Plex Sans / Sans Arabic / Mono | 5.3.0 | 2026-11-26 | — (fontsource.org) | Self-hosted fonts: Mira Server may have no internet |
| TypeScript | **6.0.3** (not 7) | 2026-11-25 | /microsoft/typescript (v6.0.2, v7.0.2 indexed) | TS 7.0.2 (the Go compiler) is `latest` on npm, but its README marks the **compiler API "not ready"**; `vue-tsc` and typescript-eslint need that API. Stay on 6.0 (the last JS-based release) until vue-tsc supports 7 |
| vue-tsc | 3.3.14 | 2026-11-26 | /vuejs/language-tools | `vue-tsc --build` over app, node (incl. `e2e/`) and vitest projects |
| ESLint + oxlint | 10.15.0, 1.82.0 | 2026-11-26 | /eslint/eslint, /oxc-project/oxc | create-vue's flat config: vue essential, vue-ts recommended, playwright, vitest, oxlint, prettier-skip |
| Vitest | 4.1.12 (create-vue 3.24 pins 4.x, not 5) | 2026-11-26 | /vitest-dev/vitest | **On Windows run it from PowerShell**: in Git Bash the lower-case `c:/` drive makes Vitest say "failed to find the current suite" |
| Playwright | 1.65.1 | 2026-11-26 | /microsoft/playwright | `@playwright/test`, Chromium; `webServer` = `vite preview` |
| @axe-core/playwright | 4.14.1 | 2026-11-26 | /dequelabs/axe-core-npm | `AxeBuilder().withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa'])`; the gate fails on serious or critical |
| `npm audit` | 5 moderate | 2026-11-26 | — | All in the dev-only chain `@vue/test-utils` 2.6.0 → `js-beautify` → `glob`/`minimatch`; nothing ships in `dist/`. Accepted; re-check at each phase tag |

## Mira Phone (phone/)

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Flutter | 3.50.1 (stable) target; **3.41.7 installed on the dev PC** | 2026-11-25 | /flutter/website, /websites/api_flutter_dev | Dart 3.14.0 with 3.50.1. `mira_design` requires Flutter ≥ 3.41 / Dart ≥ 3.11 and was tested with 3.41.7 (task 0.5); upgrade the dev PC with `flutter upgrade` before Phase 3. API used: `ThemeExtension` (copyWith/lerp), `ColorScheme(...)`, `InputDecorationThemeData`, `CardThemeData` |
| flutter_lints | 6.0.0 | 2026-11-25 | — (pub.dev) | Needs Dart ≥ 3.8. `formatter: page_width: 100` in analysis_options |

## Design tokens tooling — task 0.5

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Token generator | `design-system/tools/build-tokens.mjs` (Node ≥ 20, no dependencies) | 2026-11-25 | — | OKLCH → sRGB per CSS Color 4 (W3C), contrast per WCAG 2.2; `--check` runs as a pre-commit hook |
| TypeScript (type-check of generated tokens.ts) | 6.0.3 | 2026-11-25 | /microsoft/typescript | `tsc --strict` clean |
| Playwright (browser test of the CSS) | 1.65.1 | 2026-11-25 | — | `tests/integration/design/` — themes, OS dark mode, RTL, reduced motion, focus ring |

## Mira Connect (connect/mira_connect)

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| Frappe Framework | v16 (16.61.0) | 2026-11-25 | /frappe/frappe (v16.56.0 indexed), /websites/frappe_io_framework | Prerequisites for v16: Python 3.14, Node 24, MariaDB 11.8, Redis/Valkey 6+, Yarn 1.22+, pip 25.3+ |
| ERPNext | v16 (16.61.0) | 2026-11-25 | (resolve in task 2.2) | Target: ERPNext v16+ and Frappe CRM v16+ |

## Repository tooling

| Library / tool | Version used | Checked on | context7 library id | Notes |
| --- | --- | --- | --- | --- |
| pre-commit | 4.7.0 | 2026-11-25 | /pre-commit/pre-commit.com | Install with `pipx install pre-commit` |
| pre-commit-hooks | v6.0.0 | 2026-11-25 | /pre-commit/pre-commit-hooks | whitespace, EOF, YAML/TOML/JSON, large files, private keys |
| Ruff (ruff-pre-commit) | 0.17.6 | 2026-11-25 | /astral-sh/ruff (0.17.3 indexed) | Hooks `ruff-check --fix` then `ruff-format` (order from Ruff docs) |
| ShellCheck (shellcheck-py) | 0.11.0 (v0.11.0.1) | 2026-11-25 | /koalaman/shellcheck | Lints `deploy/*.sh`. shellcheck-py instead of koalaman/shellcheck-precommit, which needs Docker on the dev machine |
| Prettier | 3.10.1 | 2026-11-25 | /prettier/prettier (3.9.10 indexed) | `pre-commit/mirrors-prettier` is **archived** on GitHub, so it runs as a `repo: local` hook, `language: node`, pinned via `additional_dependencies`. Formats code, JSON, YAML, CSS, HTML — **not Markdown** (it pads tables to unreadable widths) |
