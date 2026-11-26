# 0003 — SIP edge and media path: Kamailio in front, Asterisk on loopback, RTPengine bridges media

- Status: accepted
- Date: 2026-11-25

## Context
The study puts Kamailio, RTPengine and coturn in front of Asterisk 22 but leaves open who registers phones, how browsers (WSS + DTLS-SRTP) reach an Asterisk that should never face the internet, and how the containers are networked and built. Task 0.3 had to settle this to get calls working end to end.

## Decision
1. **Kamailio is the only public SIP endpoint** (UDP/TCP 5060, TLS 5061, WSS 8089). Asterisk's PJSIP listens on `127.0.0.1:5080` only; ARI on `127.0.0.1:8088`; AMI is off.
2. **Asterisk is the registrar and authenticates** every REGISTER and INVITE (digest). Kamailio adds a `Path` header (with the phone's received address) so Asterisk reaches phones back through Kamailio; the dispatcher (hash on From URI) picks the Asterisk node, ready for several nodes in Mira Cloud. One contact per extension (`max_contacts=1`, newest wins).
3. **Browsers:** Kamailio rewrites a WebSocket client's `Contact` (`…@x.invalid;transport=ws`) to its real address plus an `alias` that maps back to the WSS connection, because Asterisk has no WebSocket transport by design.
4. **All media goes through RTPengine** with two interfaces: *external* (LAN/public IP, UDP 10000–14999) and *internal* (`127.0.0.1`). Towards Asterisk: plain RTP/AVP. Towards clients: DTLS-SRTP for WebRTC, SDES-SRTP (AES_CM_128_HMAC_SHA1_80/32 only) for SIP-TLS phones, RTP for plain UDP/TCP phones. coturn relays on UDP 15000–19999 and may only relay to Mira's own IP.
5. **Every service uses host networking**, because Docker-published ports bypass ufw; nothing internal binds to a public address.
6. **Images are built on the server** by `install.sh` from pinned sources (Asterisk tarball SHA256, Kamailio and RTPengine apt keys pinned by fingerprint / checksum, official coturn image). No private registry is needed for the Server edition.

## Consequences
- Asterisk can be upgraded or multiplied behind Kamailio without touching phones; scanners and floods hit Kamailio (pike, scanner filter, fail2ban), not Asterisk.
- Mira Core must write endpoints with the `mira-endpoint`/`mira-aor` templates (Path support, loopback media); trunks (task 1.2) need their own inbound identification via Kamailio.
- Kamailio routing is now critical code: `tests/integration/telephony/run-tests.sh` (softphones over UDP and TLS+SRTP, browsers over WSS) must pass after any change to `telephony/`.
- Userspace RTPengine forwarding is enough for the 40-agent pilot; the in-kernel module (outside containers) is the lever if CPU becomes a limit.
- First install compiles Asterisk (~3–15 min depending on CPU).
