# Mira Voice — ميرا ڤويس

Contact-center platform by Nest Software Development (NSD): IVR, ACD queues, outbound dialer, recording, wallboards and reports, browser / desktop / mobile softphones, WhatsApp / SMS / web chat, and native ERPNext v16 / Frappe CRM v16 integration. One codebase ships as **Mira Server** (on-premise) and **Mira Cloud** (multi-tenant).

Target: **Ubuntu Server 24.04 or 26.04 LTS (x86_64)**, on a machine of its own (2+ cores, 4+ GB RAM, 20+ GB disk; 4 / 8 / 60 recommended).

## Install

One command downloads Mira and installs it:

```bash
sudo apt-get update && sudo apt-get install -y curl   # minimal installs have no curl
curl -fsSL https://raw.githubusercontent.com/OneSpaceerp/mira_voice/main/deploy/get.sh \
  | sudo bash -s -- --admin-email you@example.com --company "Your Company"
```

Or from a clone: `sudo ./deploy/install.sh --admin-email you@example.com`. When it finishes, open **https://*your-server-address*/** (Mira Desk) and sign in with that e-mail and the password the installer prints once (also saved in `/root/mira-first-login.txt`, root only: delete it after signing in). The certificate is self-signed until a real one is set up, so the browser warns once. Options and details: [deploy/README.md](deploy/README.md).

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
