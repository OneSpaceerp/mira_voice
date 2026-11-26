# deploy/

Everything that puts Mira on an Ubuntu Server 24.04 LTS machine with one command:

```bash
sudo ./deploy/install.sh                       # install or update (safe to run again)
sudo ./deploy/install.sh --public-ip 203.0.113.7 --domain voice.example.com   # behind NAT / with a name
sudo ./deploy/lab-extensions.sh                # lab: create test extensions 1001-1004
cd /opt/mira && sudo docker compose exec core mira-core create-admin --email it@example.com   # first platform admin
sudo ./deploy/uninstall.sh                     # remove Mira, keep data in /opt/mira
sudo ./deploy/uninstall.sh --purge             # …and delete the data (asks for the hostname)
```

| File | Purpose | Task |
| --- | --- | --- |
| `install.sh` | Checks OS (Ubuntu 24.04, x86_64, systemd) and resources; installs Docker Engine + Compose plugin from Docker's apt repo; creates `/opt/mira`; generates secrets into `/opt/mira/.env`; ufw + fail2ban; detects the server's IP; self-signed TLS certificate; builds the telephony images; installs and starts `mira.service`. Idempotent. Options: `--public-ip IP`, `--domain NAME`, `--ssh-port PORT`, `--allow-low-resources` | 0.2, 0.3 |
| `uninstall.sh` | Undoes `install.sh`. Keeps data unless `--purge`; `--remove-docker` removes Docker too. Never turns the firewall off or closes SSH | 0.2 |
| `systemd/mira.service` | Runs `docker compose up --detach --wait` in `/opt/mira`; skipped until a compose file exists | 0.2 |
| `docker-compose.yml` | PostgreSQL 16, Valkey 9.1 (live state, 127.0.0.1:6379, no persistence), `core-migrate` (one-shot: `alembic upgrade head`, Asterisk DB role, `render-config`), Mira Core, `core-events` (ARI event worker), `core-ivr` (Mira Flow engine), Kamailio, Asterisk, RTPengine, coturn — host networking, only the env vars each needs, `no-new-privileges`; installed to `/opt/mira` | 0.3, 0.4, 1.2, 1.3 |
| `docker-compose.build.yml` | Build overlay used by `install.sh` (contexts in `../core/` and `../telephony/`, `network: host`) | 0.3, 0.4 |
| `lab-extensions.sh` | Test extensions 1001–1004 with random passwords (`--rotate` for new ones) until Mira Core manages extensions | 0.3 |
| `upgrade.sh`, `backup.sh` | Upgrade and backup/restore | 2.6 |

Test plans: [install](../docs/runbooks/install-test-plan.md), [telephony lab](../docs/runbooks/telephony-lab-test-plan.md); automatic checks in [tests/integration/](../tests/integration/).

## What lands on the server

| Path | What |
| --- | --- |
| `/opt/mira/` (750 root) | `docker-compose.yml`, `.env`, `data/`, `recordings/`, `logs/`, `config/`, `backups/` |
| `/opt/mira/.env` (600 root) | Generated secrets (PostgreSQL, Redis, MinIO, ARI, TURN, JWT, webhook signing, Kamailio RPC token — hex, 48–64 chars; `MIRA_DATA_KEY` = Fernet key that encrypts carrier passwords — all **never regenerated** on re-run; back it up with the data: without `MIRA_DATA_KEY` the stored carrier passwords are lost) and addresses `MIRA_LOCAL_IP`, `MIRA_PUBLIC_IP`, `MIRA_SIP_DOMAIN` |
| `/opt/mira/config/tls/mira.{crt,key}` (600 root) | Self-signed certificate for SIP-TLS and WSS (825 days) until a real one (task 2.6) |
| `/opt/mira/config/asterisk/` | Generated Asterisk pieces (`pjsip_lab.conf` now; Mira Core from Phase 1) |
| `/etc/systemd/system/mira.service` | The service |
| `/etc/fail2ban/jail.d/mira.local` | sshd jail (systemd journal backend, bans via ufw). SIP floods are blocked by Kamailio itself (pike); SIP auth-failure jails come with task 2.7 |
| `/etc/apt/sources.list.d/docker.sources` | Docker's apt repository |
| `/var/log/mira-install.log` (600 root) | Full install log |

## Firewall rule for later tasks — Docker bypasses ufw

Docker's docs ("Docker and ufw"): **ports published with `ports:` skip ufw entirely**. So in `docker-compose.yml`:

- SIP, RTP, WSS and TURN services (Kamailio, RTPengine, coturn, Asterisk) use `network_mode: host`; ufw then applies to them.
- Everything else also uses host networking but **listens on `127.0.0.1` only**: PostgreSQL (`listen_addresses=127.0.0.1`, port 5432), Mira Core (uvicorn `--host 127.0.0.1`, port 8000); Redis and MinIO will follow the same rule. The web entry point (443) goes through one reverse proxy.
- Never publish a database or admin port on `0.0.0.0`.
