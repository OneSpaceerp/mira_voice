# telephony/rtpengine/

RTPengine 26.0 LTS from rtpengine.dfx.at (keyring checksum pinned), userspace forwarding. Two interfaces: `external` (MIRA_LOCAL_IP, advertised as MIRA_PUBLIC_IP, UDP 10000–14999) and `internal` (127.0.0.1, towards Asterisk). Control (ng) on 127.0.0.1:2223, CLI on 127.0.0.1:9900 (`rtpengine-ctl -ip 127.0.0.1:9900 list totals`). Kamailio decides the SRTP/DTLS/ICE flags per call.
