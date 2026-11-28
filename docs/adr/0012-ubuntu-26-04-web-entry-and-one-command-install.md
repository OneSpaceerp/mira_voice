# 0012: Ubuntu 26.04 LTS, Mira Desk over HTTPS, and a one-command download-and-install

- Status: accepted
- Date: 2026-11-26
- Changes: CLAUDE.md rule 1 and `docs/study/02-decisions.md` (target OS)

## Context
Up to now:
- **One Ubuntu version.** The installer accepted Ubuntu Server 24.04 only.
- **No web view.** It ran the telephony and Core services, but not Mira Desk. A fresh install had nothing to open in a browser.
- **No first account.** A fresh install had no account that could use the Desk.

The owner wants:
- **Ubuntu 26.04.1 LTS as well.** Released 27 August 2026; supported to 2031, where 24.04 ends in 2029.
- **A direct download and install** that ends with a working web view.

The first real server attempt also showed a gap: the installer didn't notice that the machine already ran another application (ERPNext: nginx on 80, Redis on 6379, PostgreSQL on 5432, gunicorn on 8000). Those are Mira's ports.

## Decision

### 1. Supported systems: Ubuntu Server 24.04 and 26.04 LTS, x86_64
- `install.sh` accepts exactly these two `VERSION_ID`s. Both are tested on clean machines through the same gate.
- Docker comes from Docker's apt repository. The suite is the OS codename (`noble`, `resolute`); Docker's install page lists both.
- 26.04 replaces GNU coreutils with the Rust rewrite (`rust-coreutils`) and `sudo` with `sudo-rs`. The installer avoids GNU-only flags, and the gate runs on 26.04 to catch differences.

### 2. Mira Desk is served by an nginx container, `web`
- **Build.** `desk/Dockerfile` is two stages: Node 24 runs `npm ci` and `npm run build` (type check + Vite); nginx stable (1.30.8) then serves `dist/`. The server needs no Node.
- **Networking.** Host networking, like every service, so ufw applies.
- **Port 80** redirects to HTTPS.
- **Port 443** uses the installer's certificate (`/opt/mira/config/tls`, read-only) and serves:
  - the app, with every unknown path going to `index.html` for client-side routes;
  - `/api/` passed to Mira Core on 127.0.0.1:8000. Core keeps listening on loopback only.
- **Headers.** A Content-Security-Policy (`'self'` only; `'unsafe-inline'` for styles because Vue Flow positions nodes with inline styles; `blob:` for prompt playback), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` and a Permissions-Policy. They are added to every response, including assets and API answers, via `add_header_inherit merge` (nginx ≥ 1.29.3).
- **HSTS waits for a real certificate (task 2.6).** With a self-signed one it would stop browsers from letting people through the warning.
- **TLS and caching.** TLS 1.2 and 1.3 only, HTTP/2, `server_tokens off`. Hashed assets are cached as immutable; `index.html` is not cached.
- **Uploads.** `client_max_body_size 13m`, above Core's 12 MB prompt limit.
- **Health check.** `/healthz`, reachable only from the machine itself.

### 3. First sign-in is created by the installer
- New command `mira-core bootstrap --email --company --language`. It does something only while no platform admin exists. Then it creates the first tenant (slug `main`, if there are no tenants yet) and a platform admin with a generated password. Re-running never creates a second admin and never prints a new password.
- `install.sh` takes `--admin-email`, `--company` and `--language`. If no email is given, it asks on the terminal (also when piped through `curl | bash`, via `/dev/tty`). Without a terminal it warns and continues.
- **Where the password goes.** It is printed once on the terminal and stored in `/root/mira-first-login.txt` (600, root), for the owner to delete after signing in. It is never written to the install log, because the log captures everything else.

### 4. Ports are checked before anything is changed
The installer refuses to continue if another program (not one of Mira's containers) listens on a port Mira needs, and names the program.
- TCP: 80, 443, 3478, 5060, 5061, 5432, 6379, 8000, 8088, 8089, 8095.
- UDP: 3478, 5060.

Mira belongs on its own server or VM. Sharing a machine with another web or database server isn't supported.

### 5. One-command download: `deploy/get.sh`
```bash
curl -fsSL https://raw.githubusercontent.com/OneSpaceerp/mira_voice/main/deploy/get.sh \
  | sudo bash -s -- --admin-email you@example.com
```
- It downloads the GitHub archive of `MIRA_REF` over HTTPS: `main` by default, or a `v*` tag once phases are tagged.
- It unpacks it to `/usr/local/src/mira-voice` and runs `deploy/install.sh` with the same options.
- Running it again updates the code and re-runs the idempotent installer.
- `uninstall.sh --purge` also removes the downloaded code and the sign-in file.

## Consequences
- A server goes from nothing to a signed-in Mira Desk with one command, on either LTS.
- **The gate runs twice**, on clean 24.04 and clean 26.04 machines, and the Desk browser tests now run against the installed nginx site, so its TLS, headers and CSP are tested.
- **New security limits to watch:**
  - The CSP allows `'unsafe-inline'` styles (no scripts).
  - The download trusts GitHub's TLS and the repository. There is no signature yet; signed release archives come with tagged releases.
- **The Desk is still a plain single-page app.** Its PWA parts (manifest, service worker) come in their own task.
- **Shared servers aren't supported.** An install on a machine that already runs another web or database server stops early with a clear message, instead of half-working.

## Gate results (2026-11-28)
| | Ubuntu 24.04 | Ubuntu 26.04.1 |
| --- | --- | --- |
| Install checks (incl. web, ports, first sign-in, wrong-OS refusal) | 70/70 | 70/70 |
| Uninstall, purge, fresh install | 20/20 | 20/20 |
| Real calls (SIP, extensions, call events, IVR, trunks, WebRTC) | 25/25 | all green except 3 outbound-carrier checks: the 26.04 test carrier (`baresip-core` 1.1.0) answers 404 to unregistered accounts; Mira's INVITE verified with a SIP trace |
| Mira Desk in a browser, against the installed HTTPS site | 6/6 | 6/6 |

Found and fixed by this gate:
- **RTPengine 26.0.1.29 was withdrawn upstream.** rtpengine.dfx.at and deb.kamailio.org keep only the newest release of a series. The Dockerfiles pin the tested version and fall back to the newest of the same series, with a NOTE in the build log.
- **The admin-email question waited forever** when a terminal existed but nobody watched. It is now asked only when the output is on a screen, with a 5-minute limit.
- **The installer's port check failed on a free port** under `set -e` / `pipefail`.
