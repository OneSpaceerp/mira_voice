# telephony/

The voice stack: four Docker images, built on the server by `deploy/install.sh` and run by `mira.service` (`deploy/docker-compose.yml`). Design and reasons: [ADR 0003](../docs/adr/0003-sip-edge-and-media-path.md).

```
 phones / browsers                         this server (host networking)
 ─────────────────                         ─────────────────────────────────────────────
 UDP/TCP 5060, TLS 5061, WSS 8089  ──►  Kamailio ──UDP 127.0.0.1──►  Asterisk :5080 (PJSIP)
 RTP / SRTP / DTLS-SRTP 10000-14999 ◄─►  RTPengine ◄──RTP 127.0.0.1──►  Asterisk RTP 30000-34999
 TURN 3478 (relay 15000-19999)     ──►  coturn (relays only to this server)
                                         Asterisk ARI 127.0.0.1:8088 ◄── Mira Core (config reloads, call control) + core-events (all call events, task 1.3) ──► Valkey 127.0.0.1:6379 (live state)
```

| Folder | Image | Role |
| --- | --- | --- |
| [kamailio/](kamailio/) | `mira/kamailio:6.1.6` | The only public SIP endpoint: TLS, WSS for WebRTC, dispatcher to Asterisk, Path, NAT and WebSocket contact handling, pike flood ban, scanner filter |
| [asterisk/](asterisk/) | `mira/asterisk:22.12.0` | Call engine: PJSIP only on 127.0.0.1, registrar and auth, app_queue, MixMonitor, ConfBridge, AMD, ARI. AMI off |
| [rtpengine/](rtpengine/) | `mira/rtpengine:26.0` | Media relay: DTLS-SRTP (browsers) / SDES-SRTP (TLS phones) / RTP ↔ plain RTP to Asterisk |
| [coturn/](coturn/) | `mira/coturn:4.19.2` | TURN for clients that cannot send UDP directly; time-limited credentials from `TURN_SECRET` |

Configs are **templates**: each entrypoint renders them from `/opt/mira/.env` at start; generated pieces come from Mira Core: extensions live from PostgreSQL (realtime views), the dialplan and trunks from files Core writes into shared volumes (`asterisk-generated`, `kamailio-generated`). Never hand-edit a running server.

Lab: `sudo ./deploy/lab-extensions.sh` creates 1001–1004; test numbers 600 (echo with prompt), 609 (echo, no prompt), 601/602 (hello world EN/FR). Tests: `sudo bash tests/integration/telephony/run-tests.sh` (includes `trunk-calls.sh`: fake carriers and a GSM gateway on extra local IPs; needs `apt install sip-tester`). Connecting a real carrier: [docs/runbooks/trunks-and-gateways.md](../docs/runbooks/trunks-and-gateways.md).
