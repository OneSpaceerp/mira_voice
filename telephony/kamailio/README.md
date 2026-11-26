# telephony/kamailio/

Kamailio 6.1.6 from deb.kamailio.org (signing key pinned by fingerprint). `kamailio.cfg.tmpl` is the routing logic; read its header comment first.

What it does, in order: flood and scanner protection (pike + htable ban, User-Agent filter) → NAT detection (WebSocket clients always NATed; their Contact is rewritten to `<real ip:port;alias=…>` because Asterisk has no WS transport) → in-dialog routing (`loose_route`, `handle_ruri_alias`) → REGISTER gets a `Path` with the received address → dispatcher picks an Asterisk node (hash on From URI) → RTPengine flags by direction and transport → explicit outgoing socket per transport (WSS 8089, TLS 5061, TCP/UDP 5060, loopback to Asterisk).

| File | Purpose |
| --- | --- |
| `kamailio.cfg.tmpl` | Routing; `${MIRA_LOCAL_IP}`, `${MIRA_PUBLIC_IP}`, `${MIRA_SIP_DOMAIN}` filled at start |
| `tls.cfg` | TLS 1.2+ for SIP-TLS and WSS; certificate from `/opt/mira/config/tls/` |
| `dispatcher.list` | Fallback list (local Asterisk only). At start the entrypoint links the list Mira Core generates (`/etc/kamailio/generated/dispatcher.list`, shared volume): set 1 = Asterisk nodes, set 2 = carrier signalling IPs with their trunk id |

Carriers (task 1.2, ADR 0007): a request from a set-2 IP gets `X-Mira-Trunk: trunk_<id>` (the header is removed from everyone else first), skips the pike flood limit, and a call to a registration Contact (`sip:trunk_<id>@…`) is re-addressed to the DID from `To`. Asterisk's REGISTER to a carrier leaves with Kamailio's public address in `Contact`. JSON-RPC for Mira Core listens on `127.0.0.1:8095` (`POST /RPC`, header `X-Mira-Token` = `KAMAILIO_RPC_TOKEN`); `reload_delta` is 1 s.
| `entrypoint.sh` | Renders the config, installs the certificate, `kamailio -c` check, runs as user `kamailio` |

Rules learned in the lab (keep them): aliases always with a port; always force the outgoing socket (double Record-Route is filled from it); offer only AES_CM_128 SDES suites to TLS phones.
