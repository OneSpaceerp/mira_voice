# Mira Voice — build guide (VS Code + Claude Code)

This guide takes you from an empty folder to a running Mira Voice on Ubuntu. Part A is a one-time setup. Part B is the phase plan: each task has a prompt you paste into Claude Code. Claude Code reads `CLAUDE.md` automatically and follows its rules (Ubuntu target, context7 first, project skills).

---

## Part A — one-time setup

### A1. Where the code runs

Mira is built for **Ubuntu Server 24.04 LTS**, so develop on Ubuntu, not on Windows directly:

| Option | Use it for |
| --- | --- |
| **WSL2 + Ubuntu 24.04** on your laptop | Writing code, running Mira Core, Mira Desk, Frappe and tests |
| **Ubuntu 24.04 VM** (Hyper-V or VirtualBox, **bridged** network, 4 vCPU / 8 GB / 60 GB) | Asterisk, Kamailio and real SIP/WebRTC calls (WSL's NAT breaks SIP audio) and testing `install.sh` on a clean machine |
| **Contabo VPS** (later) | Tests with a real SIP trunk and remote agents |

Steps:

1. Install WSL: open PowerShell as admin → `wsl --install -d Ubuntu-24.04`, reboot, create your Linux user.
2. In VS Code install the extensions **WSL**, **Claude Code**, **Python**, **Vue - Official**, **Flutter**, **Docker**.
3. Put the project inside WSL for speed (Linux file system is much faster than `/mnt/c`):
   ```bash
   mkdir -p ~/dev && cp -r /mnt/c/dev/Mira_Voice ~/dev/mira_voice
   cd ~/dev/mira_voice
   # files copied from a Windows drive arrive marked executable; reset: only *.sh stay executable
   find . -path ./.git -prune -o -type f -exec chmod 644 {} + && find . -name '*.sh' -exec chmod 755 {} +
   code .
   ```
   VS Code reopens "in WSL". From now on work in `~/dev/mira_voice` (back up or push to GitHub; don't edit both copies).
4. In the WSL terminal install the basics:
   ```bash
   sudo apt update && sudo apt install -y git curl build-essential python3.12-venv pipx libatomic1 unzip rsync
   # Node.js 24 LTS (Ubuntu's apt nodejs is 18 — too old for Vite 8, Vitest and Frappe v16)
   curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash && source ~/.bashrc
   nvm install 24
   pipx ensurepath && pipx install pre-commit           # git hooks: ruff + prettier (see .pre-commit-config.yaml)
   curl -fsSL https://claude.ai/install.sh | bash      # Claude Code CLI (the VS Code extension uses it too)
   ```
5. Create the GitHub repo and push: `git init && pre-commit install && git add . && git commit -m "Mira Voice: study, design system, instructions"`.

### A2. Run the setup script (context7 + skills)

In the WSL terminal, inside the project:

```bash
echo 'export CONTEXT7_API_KEY="your_key_here"' >> ~/.bashrc && source ~/.bashrc   # free key: context7.com/dashboard (optional, raises rate limits)
bash setup/setup-claude-code.sh
```

The script:
1. copies `setup/mcp.json` to `.mcp.json` — registers the **context7** MCP server (`https://mcp.context7.com/mcp`) for this project;
2. copies `setup/claude-settings.json` to `.claude/settings.json` — enables context7 and stops Claude Code reading `.env` secrets;
3. runs `docs/tools/sync-skills.sh` — copies every skill from `.agents/skills/` into `.claude/skills/`, where Claude Code discovers them (including the loose root `SKILL.md` as `progressive-web-app`, each skill inside `PWA_Skills/` as `pwa-nested-*`, and the packaged `erpnext-app-builder.skill`);
4. runs `claude mcp list` so you can see context7 "connected".

When Claude Code first opens the folder it asks you to approve the project's MCP server — approve **context7**. Check the skills with `/skills`. After adding or updating a skill in `.agents/skills/`, run `bash docs/tools/sync-skills.sh` again.

Alternative context7 setup in one command: `npx ctx7 setup --claude`.

### A3. First conversation (paste into Claude Code)

> Read CLAUDE.md, docs/study/02-decisions.md and docs/BUILD_GUIDE.md. Confirm context7 is connected and list the project skills you can load. Then summarise in 10 lines what Mira Voice is, the architecture, and the first task in Phase 0. Do not write code yet.

---

## Part B — phase plan

Tick tasks here as they finish. Each prompt starts the task; Claude Code plans, checks context7, codes, tests and reports.

### Phase 0 — Foundation (weeks 1–3)

- [x] **0.1 Repository skeleton** — done 2026-11-25 (versions in docs/stack-versions.md; `pre-commit run --all-files` passes)
  > Create the repository layout from CLAUDE.md with READMEs, .gitignore, .editorconfig, pre-commit (ruff, prettier), and docs/stack-versions.md. Use context7 to pick current stable versions of Python, FastAPI, SQLAlchemy, Alembic, Vue, Vite, TypeScript, Flutter and Frappe v16, and record them.
- [ ] **0.2 Ubuntu installer v0** — code done 2026-11-25; 43/43 automatic checks pass on a fresh Ubuntu 24.04.5 WSL instance. **Still to do: run [docs/runbooks/install-test-plan.md](runbooks/install-test-plan.md) on the bridged VM**, then tick
  > Write deploy/install.sh for Ubuntu 24.04: checks OS and resources, installs Docker Engine + Compose plugin from Docker's official repo, creates /opt/mira, generates secrets into /opt/mira/.env, sets ufw rules (22, 80, 443, 5060/udp+tcp, 5061/tcp, 8089/tcp, RTP 10000–20000/udp, TURN 3478), installs fail2ban, and a systemd unit that runs docker compose. Idempotent (safe to run twice). Use context7 for Docker and ufw. Add deploy/uninstall.sh. Test plan for a clean VM.
- [ ] **0.3 Telephony lab** — code done 2026-11-25 (ADR 0003). On a fresh Ubuntu 24.04.5 WSL instance after purge + install from nothing: install 30/30, uninstall 20/20, telephony gate 21/21 (softphones over UDP and TLS+SRTP, browsers over WSS, audio both ways verified by tone analysis). **Still to do: [telephony-lab-test-plan.md](runbooks/telephony-lab-test-plan.md) on the bridged VM with Linphone**, then tick
  > Build telephony/asterisk (Asterisk 22 LTS compiled from source in a Docker image, PJSIP only, ARI enabled), telephony/kamailio (TLS + WSS + dispatcher to Asterisk), telephony/rtpengine and coturn, wired in deploy/docker-compose.yml with host networking for SIP/RTP. Use context7 for each. Goal: two softphones (e.g. Linphone) register through Kamailio and call each other with audio both ways, and a browser test page calls over WSS.
- [x] **0.4 Mira Core skeleton** — done 2026-11-25 (ADR 0004): 45 pytest tests on a real PostgreSQL 16 (auth, roles, tenant isolation, DB constraints, migrations, CLI), mypy strict and ruff clean; running in the stack via install.sh (install checks 40/40, telephony gate still 21/21). Bridged-VM run is covered by the 0.2/0.3 test plans
  > Create core/ with FastAPI, settings, PostgreSQL + Alembic, tenants, users, roles, JWT auth, health endpoint, OpenAPI docs, pytest setup and Dockerfile. Data model v1: tenant, user, extension, trunk, queue, queue_member, ivr_flow, call, call_event, recording. Use context7.
- [x] **0.5 Design tokens in code** — done 2026-11-25 (ADR 0005): one generator for CSS / TS / Dart; Mira Desk = CSS variables (no Tailwind), follows the OS theme; Mira Phone = `mira_design` package (`MiraTokens` ThemeExtension + `MiraTheme`). Tests: generator 11/11 (incl. the 37-row contrast table, both themes), Flutter 13/13 + analyze clean, Chromium 8/8, `tsc --strict` clean
  > Load the design-system, design-system-generator and ui-styling skills. Generate design-system/tokens.css (already present — verify), a Tailwind or CSS-variables setup for desk/, and a Flutter ThemeExtension for phone/ from design-system/tokens.json, light and dark.

**Gate:** NSD's own test extensions call each other on Mira through the clean-VM install.

### Phase 1 — Core telephony (weeks 4–12)

- [x] **1.1 Config generation** — done 2026-11-25 (ADR 0006): extensions from PostgreSQL through read-only realtime views (role `asterisk`), dialplan generated and reloaded over ARI only when it changed. Extension API (SIP password shown once, HA1 only). `realtime-calls.sh` 13/13 (incl. tenant isolation and a deleted extension being refused)
- [x] **1.2 Trunks** — done 2026-11-26 (ADR 0007, runbook `docs/runbooks/trunks-and-gateways.md`): registration and IP-auth trunks (carrier passwords Fernet-encrypted), GSM gateway (registers to Mira; Yeastar/Dinstar settings in the runbook), outbound routes with ordered failover and caller-ID rules, inbound DID routes; Kamailio identifies carriers by IP. `trunk-calls.sh` 23/23 with fake carriers (inbound, outbound with failover and caller ID, digest registration, forged-header refusal, GSM gateway both ways), 4 runs in a row clean. Core 118 tests; install 41/41, uninstall 20/20, telephony gate 23/23 on a fresh install. Tested with fake carriers only: a real WE line is still to do (NTRA question first)
- [x] **1.3 ARI call control** — done 2026-11-26 (ADR 0008): event worker `core-events` (ARI subscribeAll + event filter, linkedid via `channelvars`), calls + `call_events` (no DTMF), live state in **Valkey 9.1** (BSD-licensed Redis fork; ADR 0008), calls API (history, live, hang-up, click-to-call), reconcile after restarts, Valkey-restart recovery. Core 130 tests; `call-events.sh` 22/22; install 48/48, uninstall 20/20, telephony gate 24/24 on a fresh install
- [x] **1.4 IVR engine + Mira Flow v1** — done 2026-11-26 (ADRs 0009–0011): `mira-flow/1` format (12 step types, versioned drafts → immutable published versions), prompts per language (AR/EN/FR), engine `core-ivr` over ARI (menu, play, collect, time conditions with holidays, language, set/branch, HTTP data dip with SSRF guard, transfer, voicemail; queue step waits for 1.5), first Mira Desk screens: sign-in, call flows, prompts and the **visual builder** (Vue Flow; every action also works by keyboard). Core 194 tests; `flow-calls.sh` 17/17; Desk unit 21, browser 5/5 (`tests/integration/desk/run.sh`: build + publish by keyboard, problems, Arabic RTL, axe light + dark); design-critic 81/100; install 50/50, uninstall 20/20, fresh install 50/50, telephony gate 25/25
  > Flow JSON schema, executor via ARI (menu, play, collect digits, time conditions, language choice AR/EN/FR, queue, voicemail, transfer, HTTP data dip); visual builder in desk/ (load ui-ux-pro-max, design-system).
- [ ] **1.5 Queues and agents** — app_queue strategies, skills, agent states and reason codes, wrap-up timer.
- [ ] **1.6 Recording** — MixMonitor stereo, upload to MinIO, retention per tenant, signed playback URLs.
- [ ] **1.7 Web softphone** — WebRTC softphone in desk/ (JsSIP or SIP.js via context7) through Kamailio WSS.

**Gate:** inbound call → IVR → queue → agent in the browser → recorded, end to end on the VM.

### Phase 2 — MVP for the 40-agent pilot (weeks 13–24)

- [ ] **2.1 Mira Desk PWA** — agent desk (rail, work area, call panel), status pill, incoming-call toast, dispositions, keyboard shortcuts; installable PWA (load progressive-web-app, pwa-expert, professional-pwa-builder, the pwa-nested-* skills, ui-ux-pro-max). Review with design-critic and design-justice.
- [ ] **2.2 Mira Connect** — Frappe app for ERPNext v16 + Frappe CRM v16: settings, agent mapping, Call Log custom fields, screen pop, click-to-call, recordings, dispositions, campaigns, signed webhooks (load erpnext-app-builder; erpnext-v16-pwa-builder for any SPA inside Frappe; frappe-desk-pwa to make ERPNext installable).
- [ ] **2.3 Outbound** — preview and progressive (auto) dialer, campaigns from ERPNext reports, retry rules, call windows.
- [ ] **2.4 Reports and wallboard** — event rollups, KPI catalogue from the study, real-time wallboard (dark, bento grid), exports.
- [ ] **2.5 Admin** — tenants, users, extensions, trunks, queues, IVR, retention, AR/EN/FR UI.
- [ ] **2.6 Server edition installer v1** — one command on Ubuntu 24.04: install, TLS (certbot or self-signed), first admin user, backup/restore scripts, upgrade script.
- [ ] **2.7 Pilot hardening** — SIPp load test at 2× the pilot's peak calls, security checklist, runbooks (docs/runbooks/).

**Gate:** pilot client live for 30 days, reports reconciled with ERPNext.

### Phase 3 — v1.0 (months 6–16)

Cloud on Contabo (multi-tenant, Kamailio + several Asterisk nodes) · Mira Phone Flutter (Android/iOS, push wake-up, CallKit/ConnectionService) · predictive dialer, AMD, DNC · supervisor monitor/whisper/barge · QA scorecards · WhatsApp Business, SMS, web chat · Arabic AI via APIs (transcription, summary, sentiment, QA) and AI voice agent in Mira Flow · Odoo + CRM connectors · ISO 27001 preparation. Break each into tasks here before starting it.

### Phase 4 — v2

Live agent assist, email channel, ISO 27001 certification, workforce management, in-country cloud for KSA and UAE (with licensed partners).

---

## Useful prompts at any time

- "Review this screen with design-critic and apple-design; list issues above Low and fix them."
- "Check every library used in core/ against context7 and update docs/stack-versions.md; list anything out of date."
- "Run deploy/install.sh on the test VM plan step by step and tell me what to check after each step."
- "Write an ADR for <decision> using docs/adr/template.md."

## Before going live (from the study — do not skip)

- Legal opinion on the NTRA model before carrying paying customers' calls on an NSD-hosted cloud; KSA via a CST-licensed partner with in-Kingdom data; UAE only as Server edition on the client's e&/du trunk.
- Ask WE whether its SIP trunk can register from outside Egypt.
- Apple developer (D-U-N-S) and Google Play accounts for Mira Phone.
