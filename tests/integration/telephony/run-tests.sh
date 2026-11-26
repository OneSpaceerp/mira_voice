#!/usr/bin/env bash
# Mira Voice — task 0.3 gate: the telephony lab works end to end.
#
#   sudo bash tests/integration/telephony/run-tests.sh
#
# 1. services healthy; ports open where they should be and ONLY there
# 2. TLS / WSS / ARI checks
# 3. softphones over UDP and TLS+SRTP (sip-calls.sh, needs baresip-core)
# 4. browsers over WSS with WebRTC (webrtc/, needs Node 24 + Playwright Chromium)
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRA_DIR=/opt/mira
pass=0 fail=0
check() {
	local d=$1
	shift
	if "$@" >/dev/null 2>&1; then
		echo "PASS  $d"
		pass=$((pass + 1))
	else
		echo "FAIL  $d"
		fail=$((fail + 1))
	fi
}
envv() { sed -n "s/^$1=//p" "$MIRA_DIR/.env" | tail -1; }

[ "$(id -u)" -eq 0 ] || {
	echo "run as root"
	exit 2
}
IP=$(envv MIRA_LOCAL_IP)
DOMAIN=$(envv MIRA_SIP_DOMAIN)

echo "### 1. services and ports"
for s in asterisk kamailio rtpengine; do
	check "$s container healthy" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-$s-1 | grep -qx healthy"
done
check "coturn container running" bash -c "docker inspect -f '{{.State.Status}}' mira-coturn-1 | grep -qx running"
listening() { ss -H -l"$1"n "sport = :$2" | awk '{print $4}' | grep -q "^$3:$2$"; } # proto port addr
check "Kamailio SIP UDP $IP:5060" listening u 5060 "$IP"
check "Kamailio SIP TCP $IP:5060" listening t 5060 "$IP"
check "Kamailio SIP TLS $IP:5061" listening t 5061 "$IP"
check "Kamailio WSS $IP:8089" listening t 8089 "$IP"
check "coturn TURN UDP $IP:3478" listening u 3478 "$IP"
check "Asterisk SIP on 127.0.0.1:5080 only" bash -c "[ \"\$(ss -H -lun 'sport = :5080' | awk '{print \$4}')\" = 127.0.0.1:5080 ]"
check "Asterisk ARI on 127.0.0.1:8088 only" bash -c "[ \"\$(ss -H -ltn 'sport = :8088' | awk '{print \$4}')\" = 127.0.0.1:8088 ]"
check "RTPengine control on 127.0.0.1:2223 only" bash -c "[ \"\$(ss -H -lun 'sport = :2223' | awk '{print \$4}')\" = 127.0.0.1:2223 ]"
check "no chan_sip (PJSIP only)" bash -c "! docker exec mira-asterisk-1 asterisk -rx 'module show like chan_sip.so' | grep -q chan_sip.so"
check "Kamailio dispatcher sees Asterisk as active" bash -c "docker exec mira-kamailio-1 kamcmd -s unix:/run/kamailio/kamailio_ctl dispatcher.list | grep -A3 '127.0.0.1:5080' | grep -q 'FLAGS: AP'"

echo "### 2. TLS, WSS, ARI"
check "SIP TLS accepts TLS 1.2" bash -c "echo | timeout 5 openssl s_client -connect $IP:5061 -tls1_2 2>&1 | grep -q 'Protocol *: TLSv1.2'"
check "SIP TLS refuses TLS 1.1" bash -c "! echo | timeout 5 openssl s_client -connect $IP:5061 -tls1_1 2>&1 | grep -q 'Protocol *: TLSv1.1'"
check "WSS port answers HTTPS" bash -c "curl -sk --max-time 5 https://$IP:8089/ | grep -q 'WebSocket endpoint is up'"
ARI="$(envv ARI_USER):$(envv ARI_PASSWORD)"
check "ARI with credentials -> 200" bash -c "[ \$(curl -s -o /dev/null -w '%{http_code}' -u '$ARI' http://127.0.0.1:8088/ari/asterisk/info) = 200 ]"
check "ARI without credentials -> 401" bash -c "[ \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088/ari/asterisk/info) = 401 ]"

echo "### 3. softphones (UDP and TLS+SRTP)"
if bash "$HERE/sip-calls.sh"; then pass=$((pass + 1)); else fail=$((fail + 1)); fi

echo "### 3b. extensions created through Mira Core (realtime + generated dialplan)"
if bash "$HERE/realtime-calls.sh"; then pass=$((pass + 1)); else fail=$((fail + 1)); fi

echo "### 3b2. call records, live state and call control over ARI (task 1.3)"
if bash "$HERE/call-events.sh"; then pass=$((pass + 1)); else fail=$((fail + 1)); fi

echo "### 3b3. Mira Flow IVR: prompts, menu keys, data dip, voicemail, time conditions (task 1.4)"
if bash "$HERE/flow-calls.sh"; then pass=$((pass + 1)); else fail=$((fail + 1)); fi

echo "### 3c. trunks and call routing (fake carriers on extra local IPs)"
if command -v sipp >/dev/null; then
	if bash "$HERE/trunk-calls.sh"; then pass=$((pass + 1)); else fail=$((fail + 1)); fi
else
	echo "SKIP  trunk test: sudo apt install sip-tester"
fi

echo "### 4. browsers (WSS + WebRTC)"
if command -v npx >/dev/null && [ -d "$HERE/webrtc/node_modules/@playwright/test" ]; then
	creds="$MIRA_DIR/config/lab-extensions.txt"
	cred() { awk -v e="$1" '$1==e {print $2}' "$creds"; }
	if (cd "$HERE/webrtc" && MIRA_WSS="wss://$DOMAIN:8089" MIRA_DOMAIN="$DOMAIN" \
		EXT_A=1003 PASS_A="$(cred 1003)" EXT_B=1004 PASS_B="$(cred 1004)" npx playwright test); then
		pass=$((pass + 1))
	else fail=$((fail + 1)); fi
else
	echo "SKIP  WebRTC test: install Node 24, then: cd $HERE/webrtc && npm ci && npx playwright install --with-deps chromium"
fi

echo
echo "TELEPHONY RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
