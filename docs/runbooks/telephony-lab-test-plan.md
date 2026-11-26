# Test plan — telephony lab (task 0.3 gate) on the bridged Ubuntu 24.04 VM

Goal from BUILD_GUIDE 0.3: *two softphones register through Kamailio and call each other with audio both ways, and a browser test page calls over WSS.* Run after [install-test-plan.md](install-test-plan.md). About 30 minutes.

## 1. Install and create test extensions

```bash
cd ~/mira && sudo ./deploy/install.sh        # first run compiles Asterisk (3-15 min)
sudo ./deploy/lab-extensions.sh              # prints 1001-1004 with their passwords
```

Behind a router (Contabo later, or a VM that phones reach through NAT): `sudo ./deploy/install.sh --public-ip <public IP>` and forward the ufw ports (5060-5061, 8089, 3478, 10000-20000/udp).

## 2. Automatic gate (23 checks)

```bash
sudo apt install -y baresip-core sip-tester
# browser part (once): Node 24 via nvm (BUILD_GUIDE A1), then
cd tests/integration/telephony/webrtc && npm ci && npx playwright install --with-deps chromium && cd -
sudo -E env "PATH=$PATH" bash tests/integration/telephony/run-tests.sh
```

Expect `TELEPHONY RESULT: 23 passed, 0 failed` (each sub-suite counts as one; the trunk suite alone has 23 checks and adds the extra IPs .200–.204 of the VM's subnet for its fake carriers, removing them at the end): services healthy; public ports only on the VM's IP and internal ones (Asterisk SIP 5080, ARI 8088, RTPengine 2223) only on 127.0.0.1; TLS 1.2 yes / 1.1 no; ARI needs its password; softphones over UDP and over TLS + mandatory SRTP each hear the other side's tone; two browsers over WSS do the same and hang-ups reach the far end.

## 3. Manual — two real softphones (Linphone)

On two devices on the LAN (laptop + phone, or two laptops):

| Setting | Phone 1 | Phone 2 |
| --- | --- | --- |
| Username / password | 1001 / from lab-extensions | 1002 / from lab-extensions |
| Domain | the VM's IP (or `MIRA_SIP_DOMAIN`) | same |
| Transport | **UDP** | **TLS** |
| Media encryption | none | **SRTP** (mandatory) |
| TLS certificate | — | the lab certificate is self-signed: allow it, or import `/opt/mira/config/tls/mira.crt` |

| # | Do | Expect |
| --- | --- | --- |
| 1 | Both register | Green / "Connected". On the VM: `docker exec mira-asterisk-1 asterisk -rx "pjsip show contacts"` lists 1001 and 1002 |
| 2 | 1001 dials 600 | Prompt, then you hear yourself (echo) |
| 3 | 1002 dials 602 | "Hello world" in French |
| 4 | 1001 calls 1002, talk both ways for 30 s | Clear audio both ways, no one-way audio |
| 5 | Hang up on either side | Both phones end the call |
| 6 | Put phone 2 on mobile data (not Wi-Fi) and repeat 4 (needs the NAT/port-forward setup above) | Audio both ways |

## 4. Manual — a real browser

```bash
cd tests/integration/telephony/webrtc && npm run serve     # http://127.0.0.1:8765/softphone.html
```

1. Open `https://<VM IP>:8089` once and accept the certificate warning (lab certificate).
2. Open `http://127.0.0.1:8765/softphone.html`, fill WSS `wss://<VM IP>:8089`, domain, 1003 + password, Register, call 600 with a headset: you hear the prompt and yourself.
3. Call 1001 (Linphone) from the browser and back: audio both ways.

## 5. Security spot checks

| # | Do | Expect |
| --- | --- | --- |
| 1 | From the laptop: `nc -vz <VM IP> 5080` and `nc -vz <VM IP> 8088` | Refused / timeout (Asterisk not reachable) |
| 2 | Register with a wrong password 3 times | 401/403, no registration |
| 3 | `sipvicious`-style flood (e.g. 50 OPTIONS in 2 s with `sipp -sn uac -r 50`) | Kamailio logs `pike: blocking`, the source IP is ignored for 5 min |

## 6. Record the result

In BUILD_GUIDE (task 0.3) note the date, Ubuntu point release, the TELEPHONY RESULT line, and which manual rows passed.

## Results so far

| Date | Where | Automatic | Manual | Notes |
| --- | --- | --- | --- | --- |
| 2026-11-25 | Fresh WSL2 Ubuntu 24.04.5 instance `mira-test`, by Claude Code | 21/21 after a purge + fresh install from nothing | not run | Clients on the same host as the server (no NAT, no real phones). **Bridged VM + Linphone run still needed.** |
