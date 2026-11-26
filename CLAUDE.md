# Mira Voice — instructions for Claude Code

You are building **Mira Voice** (ميرا ڤويس), a contact-center platform by Nest Software Development (NSD): IVR / auto attendant, ACD queues, outbound dialer, recording, wallboards and reports, browser + desktop + mobile softphones, WhatsApp / SMS / web chat, and native ERPNext v16 / Frappe CRM v16 integration. It ships as **Mira Server** (on-premise) and **Mira Cloud** (multi-tenant), from one codebase. The owner, Khaled, builds it alone with you; he is not a career programmer, so explain decisions briefly and keep the code conventional.

Read before any work:
1. `docs/study/01-product-technical-study.md` — the full study (architecture, scope, KPIs, regulation, roadmap, Ziwo comparison, decisions).
2. `docs/study/02-decisions.md` — the short list of decisions and open questions.
3. `docs/BUILD_GUIDE.md` — the phase plan and the task you are on.
4. `design-system/README.md` and its numbered sections — the visual rules. Tokens live in `design-system/tokens.json` / `tokens.css`.

## Non-negotiable rules

1. **Installable on Ubuntu.** Every component must install and run on **Ubuntu Server 24.04 LTS and 26.04 LTS (x86_64)** with one command: `sudo ./deploy/install.sh` (or the download one-liner `deploy/get.sh`, ADR 0012). Test on clean 24.04 and 26.04 VMs before calling a phase done. Do not depend on Windows, macOS or a specific cloud.
2. **context7 before code.** Before writing or changing code that uses any library, framework, API or config format, call the **context7** MCP server: `resolve-library-id`, then `get-library-docs` for the exact version we use. Never write Asterisk, Kamailio, FastAPI, SQLAlchemy, Vue, Vite, frappe-ui, Frappe, Flutter or plugin code from memory. Record every library and the version you checked in `docs/stack-versions.md` (name, version, date checked, context7 id). If context7 has no entry, say so, read the official docs on the web, and note it.
3. **Use the project skills** (table below). Before a task, load the skills that match it and follow them. If two skills disagree, the design system in `design-system/` and this file win.
4. **Small, verified steps.** One task at a time from `docs/BUILD_GUIDE.md`. For each: plan → context7 → code → tests → run it → update docs and the checklist. Never claim something works without running it.
5. **Security by default.** TLS for SIP (5061) and WSS, SRTP media, no default passwords, secrets in `.env` (never committed), fail2ban + ufw rules from the installer, per-tenant call limits and spend caps, signed webhooks (HMAC-SHA256).
6. **Trilingual and RTL.** Every UI string and IVR prompt set exists in Arabic, English and French. Use logical CSS properties / `EdgeInsetsDirectional`; phone numbers, timers and the dial pad stay LTR.
7. **Design tokens only.** No raw hex, px values off the scale, or fonts outside the design system. One red thing per screen. Errors use `danger` (terracotta), never the brand red.
8. **Ask before** anything irreversible or legal: deleting data, changing the NTRA/CST/TDRA model, sending real calls through a hosted cloud, publishing apps to stores.

## Architecture (summary — details in the study)

| Part | Folder | Stack |
| --- | --- | --- |
| SIP edge | `telephony/kamailio` | Kamailio (TLS, WSS for WebRTC, dispatcher, pike/anti-fraud) |
| Media relay / NAT | `telephony/rtpengine`, `telephony/coturn` | RTPengine, coturn |
| Call engine | `telephony/asterisk` | **Asterisk 22 LTS**, PJSIP only (no chan_sip), app_queue, MixMonitor, ConfBridge, ARI |
| Control plane | `core/` | **Mira Core**: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 16, Redis (later NATS), ARI client, background workers, REST API + webhooks, push gateway (APNs/FCM) |
| Reports | `core/` + ClickHouse (TimescaleDB acceptable for MVP) | Event stream → per-call and 15-minute rollups |
| Recordings | MinIO (S3-compatible) | Encrypted, per-tenant retention |
| Web app | `desk/` | **Mira Desk**: Vue 3 + TypeScript + Vite, installable **PWA** (agent desk, Mira Flow IVR builder, Mira Pulse reports, admin) with WebRTC softphone (JsSIP or SIP.js — choose via context7) |
| Mobile app | `phone/` | **Mira Phone**: Flutter, `sip_ua` (dart-sip-ua) + flutter-webrtc, CallKit / ConnectionService, own push gateway. Open-source only. |
| ERPNext app | `connect/mira_connect` | **Mira Connect**: Frappe app for ERPNext v16+ and Frappe CRM v16+ |
| Deployment | `deploy/` | Docker Engine + Compose plugin on Ubuntu 24.04 / 26.04, `install.sh`, `get.sh`, systemd unit, ufw, nginx (web), certbot |

Desktop softphone: the installable Mira Desk PWA covers Windows and macOS at MVP; a Flutter desktop build comes later only if the PWA cannot meet a requirement.

## Repository layout

```
CLAUDE.md                 this file
.mcp.json                 context7 MCP server (created by setup/setup-claude-code.sh)
.claude/skills/           the project skills (copied from .agents/skills by the setup script)
setup/                    one-time Claude Code setup (mcp.json, settings, script)
docs/                     study, decisions, BUILD_GUIDE, stack-versions, ADRs, runbooks
design-system/            brand book, tokens.json, tokens.css, reference components
telephony/                asterisk/, kamailio/, rtpengine/, coturn/  (Dockerfiles + config templates)
core/                     Mira Core (FastAPI)
desk/                     Mira Desk PWA (Vue 3)
phone/                    Mira Phone (Flutter)
connect/mira_connect/     Frappe app
deploy/                   docker-compose.yml, install.sh, upgrade.sh, backup.sh, systemd/
tests/                    sipp/ (load and call scenarios), e2e/ (Playwright), integration/
```

## Skills: which to load for what

All skills are in `.claude/skills/` (originals in `.agents/skills/`; run `bash setup/setup-claude-code.sh` if `.claude/skills/` is missing). Skill folder names: the root `SKILL.md` becomes `progressive-web-app`; each skill inside `PWA_Skills/` becomes `pwa-nested-<name>`.

| Work | Load these skills |
| --- | --- |
| Any UI screen, component or layout (Desk, Flow, Pulse, admin) | `ui-ux-pro-max`, `ui-styling`, `design-system`, `design-system-creator` |
| Turning design tokens into CSS / Tailwind / Flutter theme | `design-system`, `design-system-generator`, `brand` |
| Documenting components and tokens | `design-system-documenter` |
| Reviewing a finished screen before calling it done | `design-critic` (score it; fix anything under 75), `apple-design` (mobile and desktop) |
| Choosing or checking visual direction | `design-trend-analyzer`, `design` |
| Competitor or pattern research (Ziwo, Genesys, Maqsam…) | `design-archivist` |
| Accessibility, error states, shared PCs, offline behaviour | `design-justice` |
| Mira Desk as an installable app: manifest, service worker, offline, updates, push | `progressive-web-app`, `pwa-expert`, `professional-pwa-builder`, the `pwa-nested-*` skills (from `PWA_Skills`) |
| Mira Connect (Frappe app): DocTypes, hooks, whitelisted APIs, patches, tests | `erpnext-app-builder` |
| A Vue SPA served from inside a Frappe app (agent view inside ERPNext) | `erpnext-v16-pwa-builder` |
| Making ERPNext Desk itself installable / push from Frappe | `frappe-desk-pwa` |
| Mira Phone (Flutter) look and native call UX | `apple-design`, `ui-ux-pro-max` |
| Marketing pages, social banners, app-store graphics | `banner-design`, `brand`, `design` |
| Sales and demo decks | `slides`, `brand` |

## Conventions

- Python: `ruff` + `mypy`, `pytest`; type hints everywhere; settings via pydantic-settings; one Alembic migration per change.
- TypeScript: strict mode, ESLint + Prettier, Vitest, Playwright for e2e.
- Flutter: `flutter analyze`, `flutter test`; Riverpod or Bloc (pick one in Phase 3 with context7 and record it in an ADR).
- Frappe: follow `erpnext-app-builder`; app name `mira_connect`; `bench run-tests --app mira_connect` must pass.
- Telephony configs are **generated** by Mira Core from the database and templates; never hand-edit a running server's dialplan.
- Commit small, with clear messages (`core: add queue model`). Each phase ends with a tag (`v0.1-foundation`, `v0.2-mvp`…).
- Every decision that changes the study goes in `docs/adr/NNNN-title.md` (context, decision, consequences).

## Definition of done (every task)

- [ ] context7 checked and `docs/stack-versions.md` updated
- [ ] Tests written and passing; lint clean
- [ ] Runs on clean Ubuntu 24.04 and 26.04 VMs through `deploy/install.sh` (for anything deployable)
- [ ] UI tasks: tokens only, AR/EN/FR strings, RTL checked, light + dark, `design-critic` score ≥ 75
- [ ] Docs and the BUILD_GUIDE checklist updated
