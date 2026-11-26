# Runbook: connect a carrier trunk or a GSM gateway

For the person installing Mira Voice for a customer. The design is in ADR 0007.

> **Real carriers mean real calls and real money.** Before the first live call:
> - confirm the licensing model with the customer (NTRA in Egypt, CST in Saudi Arabia, TDRA in the UAE);
> - check that the carrier contract allows a PBX on that line;
> - have the carrier's signalling IP list in writing.
>
> Outbound routes decide who can call where: start with national numbers only.

Every step below uses the Mira Core API as a tenant admin. The Mira Desk admin screens (task 2.5) will do the same thing. `$API` is `https://<server>/api/v1` (on the server itself: `http://127.0.0.1:8000/api/v1`), and `$H` is the `Authorization: Bearer …` header.

## 1. Registration trunk (e.g. WE SIP trunk)
The carrier gives you a registrar host, a username (often the pilot number), a password, sometimes a domain, and the IPs its calls come from.

```bash
curl -s -H "$H" -H 'Content-Type: application/json' -X POST "$API/trunks" -d '{
  "name": "WE main",
  "kind": "sip_register",
  "host": "<registrar host or IP>",
  "port": 5060, "transport": "udp",
  "auth_username": "<username>",
  "password": "<password>",
  "from_domain": "<carrier domain, if given>",
  "caller_id_number": "+2022xxxxxxx",
  "inbound_ips": ["<carrier signalling IP>", "..."]
}'
```

- **The password is encrypted** with `MIRA_DATA_KEY` and is never shown again. Keep `/opt/mira/.env` in the backup: without it, every carrier password has to be entered again.
- **`inbound_ips` is required** when `host` is a name, not an IP. Mira only accepts calls from IPs on this list (a literal-IP `host` is added automatically). One IP belongs to one trunk only.
- To check the registration:
  ```bash
  docker exec mira-asterisk-1 asterisk -rx "pjsip show registrations"
  ```
  The trunk should say `Registered`. `Rejected` means a wrong username or password.

## 2. IP-authenticated trunk
Same request, with `"kind": "sip_ip_auth"`, no `auth_username` and no `password`. Give the carrier Mira's **public IP** and port (5060 UDP/TCP, or 5061 TLS). Only open the firewall to the carrier's IPs if the customer asks for it: ufw already opens 5060/5061 to everyone, and Kamailio does the filtering.

## 3. GSM gateway (Yeastar TG, Dinstar)
```bash
curl -s -H "$H" -H 'Content-Type: application/json' -X POST "$API/trunks" \
  -d '{"name": "Yeastar TG200", "kind": "gsm_gateway"}'
```
The answer contains `sip_username`, `sip_password` and `sip_realm` **once**. On the gateway, create a SIP trunk of type "register" (Yeastar: *Gateway → VoIP Settings → VoIP Trunk*, type *Register*) with these settings:

| Gateway field | Value |
| --- | --- |
| Server / domain | Mira's SIP domain (`MIRA_SIP_DOMAIN`), port 5060 (or 5061 with TLS) |
| Username / Authentication name | `sip_username` (`trunk_…`) |
| Password | `sip_password` |
| Realm (if asked) | `mira` |
| Codecs | G.711 A-law and µ-law (PCMA/PCMU) |
| DTMF | RFC 2833 / RFC 4733 |

Then route the GSM channels to that trunk on the gateway, in both directions. Lost the password? `POST $API/trunks/<id>/password` gives a new one, and the old one stops working.

## 4. Routes
**Outbound.** Numbers matching a pattern go out through trunks in order. The next trunk is tried only when one is down or congested.

```bash
curl -s -H "$H" -H 'Content-Type: application/json' -X POST "$API/outbound-routes" -d '{
  "name": "Egypt national", "pattern": "0Z.", "strip_digits": 1, "prepend": "+20",
  "trunk_ids": ["<WE trunk id>", "<GSM gateway trunk id>"]
}'
```

Patterns follow Asterisk syntax without the `_`:

| Symbol | Matches |
| --- | --- |
| `X` | 0–9 |
| `Z` | 1–9 |
| `N` | 2–9 |
| `.` | one or more digits |
| `[15-7]` | a set of digits |

Caller ID comes from the route's `caller_id_number`; if that is empty, from the trunk's; if that is empty too, the caller's own number is used.

**Inbound.** A called number (DID) rings an extension. Use `"did": "*"` for "every number on this trunk". Leave `trunk_id` out to mean "on any trunk".

```bash
curl -s -H "$H" -H 'Content-Type: application/json' -X POST "$API/inbound-routes" \
  -d '{"did": "+2022xxxxxxx", "trunk_id": "<WE trunk id>", "destination_number": "1001"}'
```

Carriers differ in how they send the DID (`+20…`, `0…`, or without the 0). Look at an incoming call first:

```bash
docker logs mira-asterisk-1 | grep -i "t_.*_in"
```

Then create the route in that same format.

## 5. If something does not work
| Symptom | Look at |
| --- | --- |
| Carrier calls get "invalid number" | The DID format (section 4). Check the inbound route list (`GET $API/inbound-routes`). |
| Carrier calls are refused (401/403) | The carrier's source IP is missing from `inbound_ips`. See the carrier list: `docker exec mira-kamailio-1 kamcmd -s unix:/run/kamailio/kamailio_ctl dispatcher.list` |
| Outbound calls fail at once | `docker exec mira-asterisk-1 asterisk -rx "pjsip show contacts"`. `Unavail` means the carrier does not answer Asterisk's OPTIONS keepalive (sent every 60 s), so Mira treats it as down. Ask the carrier to answer OPTIONS from Mira's IP. Mira has no setting yet to switch the keepalive off for one trunk (ADR 0007). |
| Registration `Rejected` | Username, password or `from_domain`. |
| One-way audio | RTPengine and the firewall: UDP 10000–20000 must be open (install.sh does this). |
| `config_applied: false` in an API answer | The files were written, but Asterisk or Kamailio did not reload. `docker exec mira-core-1 mira-core render-config` retries and prints the error. |

The automated end-to-end check of all of this, with fake carriers on local IPs, is `tests/integration/telephony/trunk-calls.sh`.
