# Test plan — `deploy/install.sh` on a clean Ubuntu 24.04 VM

Run this before calling any deploy change done (CLAUDE.md rule 1). About 20 minutes.

## 0. The VM

- Ubuntu **Server** 24.04 LTS x86_64, fresh install, **OpenSSH server ticked** in the installer.
- Hyper-V or VirtualBox, **bridged** network, 4 vCPU / 8 GB / 60 GB (BUILD_GUIDE A1).
- Take a **snapshot named `clean`** before step 1, so every run starts from the same state.
- Work over **SSH from your laptop**, not the VM console — step 3 proves the firewall does not lock you out.

## 1. Copy the project and install

```bash
# on the laptop (WSL), from the project folder
rsync -a --exclude .agents --exclude .claude --exclude node_modules ./ USER@VM_IP:~/mira/
ssh USER@VM_IP
cd ~/mira && sudo ./deploy/install.sh
```

Expect: every step prints `ok:`, ends with `Mira Voice base install complete`, takes 1–3 minutes. A memory or disk **WARNING** is fine for a lab VM; an **ERROR** is not.

## 2. Automatic checks (40 checks)

```bash
sudo bash tests/integration/install/verify-install.sh
```

Expect `RESULT: 40 passed, 0 failed`. It re-runs the installer (idempotency), checks secrets, addresses and the TLS certificate, Docker, ufw, fail2ban, `mira.service` and the telephony containers (healthy, host networking, no secret on any command line, healthy again after a restart) and Mira Core (PostgreSQL and Core healthy, schema at the latest migration, 5432/8000 on loopback only, `create-admin` → login works, 401 without a token).

## 3. Manual checks

| # | Do | Expect |
| --- | --- | --- |
| 1 | Keep this SSH session open; open a **second** SSH session to the VM | It connects — the firewall did not lock you out |
| 2 | `sudo ufw status verbose` | Active; default deny incoming; 22/tcp LIMIT; 80, 443, 5060 udp+tcp, 5061, 8089, 10000:20000/udp, 3478 udp+tcp — each with a `mira:` comment, IPv4 and IPv6 |
| 3 | From the laptop: `nc -zv VM_IP 5432` and `nc -zv VM_IP 8000` (PostgreSQL, Mira Core) | Times out / refused (they listen on 127.0.0.1 only) |
| 4 | `sudo ls -l /opt/mira/.env` then `ls /opt/mira/.env` as your normal user without sudo | `-rw------- root root`; without sudo: Permission denied |
| 5 | `sudo grep -c . /var/log/mira-install.log` and look through it | apt output is there; **no passwords** |
| 6 | Run `sudo ./deploy/install.sh` a third time | Same output, secrets say `(kept)` |
| 7 | From **another machine you can afford to block** (not the laptop you work from): `ssh wronguser@VM_IP` six times with a wrong password | `sudo fail2ban-client status sshd` lists that IP as banned. Unban: `sudo fail2ban-client set sshd unbanip IP` |
| 8 | `sudo reboot`, reconnect, `systemctl is-enabled mira docker fail2ban ufw` | All `enabled`; `ufw status` still active |

## 4. Uninstall (20 checks — deletes everything on the VM)

```bash
sudo MIRA_TEST_MACHINE=yes bash tests/integration/install/verify-uninstall.sh
```

Expect `RESULT: 20 passed, 0 failed`: default uninstall keeps `/opt/mira`; `--purge` refuses a wrong hostname; `--purge --remove-docker` removes `/opt/mira` and Docker; SSH stays allowed throughout; a fresh install afterwards works.

## 5. Record the result

Restore the `clean` snapshot. In the BUILD_GUIDE checklist note the date, the Ubuntu point release (`lsb_release -d`) and the two RESULT lines.

## Results so far

| Date | Where | Ubuntu | install checks | uninstall checks | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-11-25 | Fresh WSL2 instance (systemd), by Claude Code | 24.04.5 | 23/23 | 20/20 | Task 0.2. Not a VM: no bridged network; fail2ban ban (manual 7) and reboot (manual 8) not tested. |
| 2026-11-25 | Same instance, with the telephony stack (task 0.3) | 24.04.5 | 30/30 | 20/20 | Uninstall suite ends with purge + install from nothing (Docker reinstalled, all images rebuilt, Asterisk compiled): 430 s. **Bridged VM run still needed.** |
