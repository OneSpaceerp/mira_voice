# Mira Voice — ميرا ڤويس

Contact-center platform by Nest Software Development (NSD): IVR, ACD queues, outbound dialer, recording, wallboards and reports, browser / desktop / mobile softphones, WhatsApp / SMS / web chat, and native ERPNext v16 / Frappe CRM v16 integration. One codebase ships as **Mira Server** (on-premise) and **Mira Cloud** (multi-tenant).

Target: **Ubuntu Server 24.04 LTS (x86_64)**, installed with `sudo ./deploy/install.sh`.

## Where things are

| Folder | What it holds |
| --- | --- |
| [docs/](docs/) | Study, decisions, [build guide](docs/BUILD_GUIDE.md), [stack versions](docs/stack-versions.md), ADRs, runbooks |
| [design-system/](design-system/) | Brand book, tokens (`tokens.json`, `tokens.css`), reference components |
| [telephony/](telephony/) | Asterisk 22, Kamailio, RTPengine, coturn — Dockerfiles and config templates |
| [core/](core/) | **Mira Core** — FastAPI control plane, REST API, ARI client, workers |
| [desk/](desk/) | **Mira Desk** — Vue 3 PWA: agent desk, Mira Flow, Mira Pulse, admin, WebRTC softphone |
| [phone/](phone/) | **Mira Phone** — Flutter mobile softphone |
| [connect/mira_connect/](connect/mira_connect/) | **Mira Connect** — Frappe app for ERPNext v16 / Frappe CRM v16 |
| [deploy/](deploy/) | Docker Compose, `install.sh`, upgrade, backup, systemd |
| [tests/](tests/) | SIPp call scenarios, Playwright e2e, integration tests |
| [setup/](setup/) | One-time Claude Code setup (context7, skills) |

## Developer setup

Follow [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md) Part A (WSL2 Ubuntu 24.04 + a bridged Ubuntu VM for SIP). Then:

```bash
pipx install pre-commit      # or: uv tool install pre-commit
pre-commit install           # run ruff + prettier on every commit
pre-commit run --all-files   # check the whole tree
```

Rules for contributors (human or Claude Code) are in [CLAUDE.md](CLAUDE.md).
