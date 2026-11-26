#!/usr/bin/env bash
# Mira Voice — task 1.2 gate: trunks and call routing, end to end, with fake carriers on
# extra IP addresses of this machine (no real call ever leaves the server).
#
#   IP trunk      carrier at .200 (baresip): inbound DID -> extension, outbound with caller ID
#   failover      dead carrier at .202 first in the route, then .200 takes the call
#   registration  carrier registrar at .201 (SIPp): digest auth, public Contact, call in on it
#   spoofing      a stranger at .204 sends a forged X-Mira-Trunk header: refused
#   GSM gateway   Yeastar-like box at .203 (baresip) registers to Mira; calls both ways
#
#   sudo bash tests/integration/telephony/trunk-calls.sh
#
# Needs: Mira installed and running, `apt install baresip-core sip-tester`. Uses a throw-away
# tenant and removes it, its trunks and the extra IPs at the end.
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SIPP_DIR="$(cd "$HERE/../../sipp/trunks" && pwd)"
TEST_NAME=trunks
# shellcheck source=SCRIPTDIR/lib.sh
. "$HERE/lib.sh"

command -v sipp >/dev/null || {
	echo "sipp missing: sudo apt install sip-tester"
	exit 2
}

API=http://127.0.0.1:8000/api/v1
RUN=$(date +%s)
SLUG="tk-$RUN"
ADMIN="tk-$RUN@example.com"
NET=${LOCAL_IP%.*}
CARRIER=$NET.200 REGISTRAR=$NET.201 DEAD=$NET.202 GSM=$NET.203 STRANGER=$NET.204
IFACE=$(ip -o -4 addr show | awk -v ip="$LOCAL_IP" '$4 ~ "^"ip"/" {print $2; exit}')
REG_USER=0225550101 REG_PASS="reg-$RUN-pass"
dc() { (cd "$MIRA_DIR" && docker compose "$@"); }
ast() { docker exec mira-asterisk-1 asterisk -rx "$1"; }
json() { python3 -c "import sys, json; print(json.load(sys.stdin)$1)"; }
hex() { echo "${1//-/}"; }

for ip in $CARRIER $REGISTRAR $DEAD $GSM $STRANGER; do
	ip addr add "$ip/32" dev "$IFACE" 2>/dev/null || true
done

cleanup() {
	pkill -f "baresip -f $WORK" 2>/dev/null
	pkill -f "sipp .*-i $NET.20" 2>/dev/null
	# shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' >/dev/null 2>&1 <<-SQL
		DELETE FROM call_events WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM calls WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM inbound_routes WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM outbound_routes WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM trunks WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM extensions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM users WHERE email = '$ADMIN';
		DELETE FROM tenants WHERE slug = '$SLUG';
	SQL
	dc exec -T core mira-core render-config >/dev/null 2>&1
	for ip in $CARRIER $REGISTRAR $DEAD $GSM $STRANGER; do
		ip addr del "$ip/32" dev "$IFACE" 2>/dev/null
	done
}
trap 'cleanup; rm -rf "$WORK"' EXIT

echo "### 1. tenant, extension, trunks and routes through the API"
pw=$(dc exec -T core mira-core create-admin --email "$ADMIN" --name tk 2>&1 | sed -n 's/^Password.*: //p')
TOKEN=$(curl -s -X POST "$API/auth/token" --data-urlencode "username=$ADMIN" --data-urlencode "password=$pw" | json "['access_token']")
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
# every change answers config_applied (files written + Asterisk/Kamailio reloaded): keep them
post() { curl -s "${H[@]}" -X POST "$API/$1" -d "$2" | tee -a "$WORK/api-answers.jsonl"; echo >>"$WORK/api-answers.jsonl"; }
T=$(post tenants "{\"name\":\"Trunk test\",\"slug\":\"$SLUG\"}" | json "['id']")
EXT=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"3001\",\"display_name\":\"Reception\"}")
ext_user=$(echo "$EXT" | json "['sip_username']")
ext_pass=$(echo "$EXT" | json "['sip_password']")

# the fake WE registrar runs from the start: Mira registers as soon as the trunk exists
mkdir -p "$WORK/sipp"
sed -e "s/@USER@/$REG_USER/" -e "s/@PASS@/$REG_PASS/" "$SIPP_DIR/carrier-registrar.xml" >"$WORK/sipp/registrar.xml"
(cd "$WORK/sipp" && timeout 200 sipp -sf registrar.xml -i "$REGISTRAR" -p 5060 -aa -trace_msg -message_file reg-msgs.log >/dev/null 2>&1) &
sleep 1

trunk() { post trunks "{\"tenant_id\":\"$T\",$1}"; }
IPT=$(trunk "\"name\":\"Carrier\",\"kind\":\"sip_ip_auth\",\"host\":\"$CARRIER\",\"caller_id_number\":\"+20225550100\"" | json "['id']")
DEADT=$(trunk "\"name\":\"Dead carrier\",\"kind\":\"sip_ip_auth\",\"host\":\"$DEAD\"" | json "['id']")
REGT=$(trunk "\"name\":\"WE-like\",\"kind\":\"sip_register\",\"host\":\"$REGISTRAR\",\"auth_username\":\"$REG_USER\",\"password\":\"$REG_PASS\",\"from_domain\":\"carrier.test\"" | json "['id']")
GW=$(trunk "\"name\":\"GSM gateway\",\"kind\":\"gsm_gateway\"")
GWT=$(echo "$GW" | json "['id']")
gw_user=$(echo "$GW" | json "['sip_username']")
gw_pass=$(echo "$GW" | json "['sip_password']")
if [ -n "$IPT" ] && [ -n "$DEADT" ] && [ -n "$REGT" ] && [ "$gw_user" = "trunk_$(hex "$GWT")" ]; then
	ok "API created 4 trunks (IP, IP, registration, GSM gateway account $gw_user)"
else
	bad "trunk creation: IPT=$IPT DEADT=$DEADT REGT=$REGT GW=$GW"
fi

route() { post outbound-routes "{\"tenant_id\":\"$T\",$1}" | json "['id']"; }
inroute() { post inbound-routes "{\"tenant_id\":\"$T\",$1}" | json "['id']"; }
# 0Z.  -> national: drop the 0, add +20, dead carrier first (failover), caller ID of the route
# 9X.  -> registration trunk; 7X. -> GSM gateway (strip the 7)
r1=$(route "\"name\":\"National\",\"pattern\":\"0Z.\",\"strip_digits\":1,\"prepend\":\"+20\",\"caller_id_number\":\"+20225550100\",\"trunk_ids\":[\"$DEADT\",\"$IPT\"]")
r2=$(route "\"name\":\"Via GSM\",\"pattern\":\"7X.\",\"strip_digits\":1,\"trunk_ids\":[\"$GWT\"]")
i1=$(inroute "\"did\":\"+20225550100\",\"trunk_id\":\"$IPT\",\"destination_number\":\"3001\"")
i2=$(inroute "\"did\":\"+20225550101\",\"destination_number\":\"3001\"")
i3=$(inroute "\"did\":\"*\",\"trunk_id\":\"$GWT\",\"destination_number\":\"3001\"")
if [ -n "$r1" ] && [ -n "$r2" ] && [ -n "$i1" ] && [ -n "$i2" ] && [ -n "$i3" ]; then ok "API created 2 outbound and 3 inbound routes"; else bad "routes: $r1 $r2 $i1 $i2 $i3"; fi
applied=$(python3 -c "
import json, sys
vals = [json.loads(l).get('config_applied') for l in open(sys.argv[1]) if l.strip().startswith('{')]
vals = [v for v in vals if v is not None]
print(len(vals), sum(1 for v in vals if v))" "$WORK/api-answers.jsonl")
if [ "${applied% *}" = "${applied#* }" ]; then ok "every change reported config_applied (${applied% *} of ${applied% *})"; else bad "config_applied true for only ${applied#* } of ${applied% *} changes"; fi

echo "### 2. generated config is live"
IPT_ID="trunk_$(hex "$IPT")" DEAD_ID="trunk_$(hex "$DEADT")" REG_ID="trunk_$(hex "$REGT")"
# the res_pjsip reload runs in the background in Asterisk: give it a few seconds
for _ in $(seq 1 10); do ast "pjsip show endpoint $IPT_ID" | grep -q "Endpoint:  *$IPT_ID" && break; sleep 1; done
if ast "pjsip show endpoint $IPT_ID" | grep -q "Endpoint:  *$IPT_ID"; then ok "Asterisk has trunk endpoint $IPT_ID"; else
	bad "trunk endpoint missing in Asterisk (in file: $(docker exec mira-asterisk-1 grep -c "^\[$IPT_ID\]" /etc/asterisk/generated/pjsip_mira.conf))"
	echo "--- pjsip show endpoint $IPT_ID:"; ast "pjsip show endpoint $IPT_ID" | head -6
	echo "--- trunk endpoints Asterisk has:"; ast "pjsip show endpoints" | grep -E "Endpoint: +trunk_" | head
fi
for _ in $(seq 1 5); do ast "dialplan show t_$(hex "$T")" | grep -q "_0Z." && break; sleep 1; done
if ast "dialplan show t_$(hex "$T")" | grep -q "_0Z."; then ok "outbound route _0Z. in the tenant's dialplan"; else
	bad "route missing from the dialplan (in file: $(docker exec mira-asterisk-1 grep -c "_0Z\." /etc/asterisk/generated/extensions_mira.conf))"
	docker logs --since 2m mira-asterisk-1 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "ERROR|WARNING|pbx_config" | tail -4
fi
if docker exec mira-kamailio-1 kamcmd -s unix:/run/kamailio/kamailio_ctl dispatcher.list | grep -q "sip:$CARRIER"; then
	ok "Kamailio reloaded its carrier list (has $CARRIER)"
else bad "Kamailio carrier list lacks $CARRIER"; fi
if docker exec mira-asterisk-1 stat -c '%a' /etc/asterisk/generated/pjsip_mira.conf | grep -qx 640; then
	ok "trunk file with carrier passwords is 0640"
else bad "pjsip_mira.conf permissions"; fi

make_phone ext 5073 50400 440 "<sip:$ext_user@$DOMAIN;transport=udp>;auth_pass=$ext_pass;answermode=auto;audio_codecs=PCMU,PCMA;regint=120"
# baresip 1.0 only accepts calls addressed to its own user (no catch-all), so the fake
# carrier is named after the number Mira dials out to.
make_phone carrier 5060 50600 880 "<sip:+20225550199@$CARRIER>;regint=0;answermode=auto;audio_codecs=PCMU,PCMA" "$CARRIER"
make_phone gsm 5060 50800 660 "<sip:$gw_user@$DOMAIN;transport=udp>;auth_pass=$gw_pass;answermode=auto;audio_codecs=PCMU,PCMA;regint=120" "$GSM"
run_phone ext 200
for _ in $(seq 1 15); do registered "$ext_user" && break; sleep 1; done
registered "$ext_user" || bad "extension 3001 did not register"

echo "### 3. IP trunk: carrier calls DID +20225550100 -> 3001"
run_phone carrier 14 "/dial sip:+20225550100@$LOCAL_IP"
sleep 12
stop_phone carrier
check_tone carrier 440 "carrier hears 3001"
check_tone ext 880 "3001 hears the carrier"
rm -f "$WORK"/ext/rec/*.wav "$WORK"/carrier/rec/*.wav

echo "### 4. outbound 0225550199 -> dead carrier first, failover to $CARRIER, caller ID +20225550100"
# Asterisk checks every trunk with OPTIONS every 60 s. The fake carrier was not running a
# moment ago, so ask for a fresh check now: the live carrier must be "Avail", the dead one not.
carrier_lines=$(wc -l <"$WORK/carrier/log.txt")
run_phone carrier 30
sleep 2
ast "pjsip qualify $IPT_ID" >/dev/null
ast "pjsip qualify $DEAD_ID" >/dev/null
for _ in $(seq 1 15); do
	ast "pjsip show contacts" | grep -E "$IPT_ID/" | grep -q Avail &&
		ast "pjsip show contacts" | grep -E "$DEAD_ID/" | grep -q Unavail && break
	sleep 1
done
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
stop_phone ext
run_phone ext 16 "/dial sip:0225550199@$DOMAIN"
sleep 14
stop_phone ext
stop_phone carrier
log=$(docker logs --since "$since" mira-asterisk-1 2>&1 | sed 's/\x1b\[[0-9;]*m//g')
if echo "$log" | grep -q "Mira out: +20225550199 via $DEAD_ID" && echo "$log" | grep -q "Mira out: +20225550199 via $IPT_ID"; then
	ok "Asterisk tried $DEAD_ID, then failed over to $IPT_ID"
else bad "no failover seen in the Asterisk log"; fi
carrier_log=$(tail -n +"$((carrier_lines + 1))" "$WORK/carrier/log.txt")
if echo "$log" | grep -q "via $IPT_ID as +20225550100" && echo "$carrier_log" | grep -q "+20225550100"; then
	ok "call left with caller ID +20225550100 and the carrier saw it"
else
	bad "caller ID: $(echo "$log" | grep -m1 "via $IPT_ID") / carrier: $(echo "$carrier_log" | grep -m2 -iE 'call|sip:' | tr '\n' ' ')"
fi
check_tone carrier 440 "carrier hears 3001 (outbound)"
check_tone ext 880 "3001 hears the carrier (outbound)"
rm -f "$WORK"/ext/rec/*.wav "$WORK"/carrier/rec/*.wav
run_phone ext 200

# Mira Core's ARI worker (task 1.3) recorded both carrier calls with their trunk
sleep 2
recorded=$(curl -s "${H[@]}" "$API/calls?tenant_id=$T&limit=20" | python3 -c "
import json, sys
calls, trunk = json.load(sys.stdin), sys.argv[1]
def has(**want):
    return any(all(c.get(k) == v for k, v in want.items()) for c in calls)
print(has(direction='inbound', trunk_id=trunk, called_number='+20225550100', disposition='answered'),
      has(direction='outbound', trunk_id=trunk, called_number='0225550199', disposition='answered'))" "$IPT")
if [ "$recorded" = "True True" ]; then ok "both carrier calls recorded: inbound and outbound on trunk $IPT_ID, answered"; else bad "call records (inbound, outbound): $recorded"; fi

echo "### 5. registration trunk: Mira registers to $REGISTRAR with digest auth"
for _ in $(seq 1 30); do ast "pjsip show registrations" | grep -E "$REG_ID-reg" | grep -q Registered && break; sleep 1; done
if ast "pjsip show registrations" | grep -E "$REG_ID-reg" | grep -q Registered; then ok "trunk $REG_ID registered (password accepted)"; else bad "registration not accepted: $(ast 'pjsip show registrations' | grep "$REG_ID")"; fi
pkill -f "sipp -sf registrar.xml" 2>/dev/null
sleep 1
# Contact headers of the REGISTER requests only (the trace also holds OPTIONS keepalives)
# (a deleted trunk of an earlier run may still be de-registering here: look at ours, and make
# sure no REGISTER at all leaks the internal 127.0.0.1:5080 address)
all_contacts=$(awk '/^REGISTER /{r=1} /^(OPTIONS|SIP\/2\.0) /{r=0} r && /^Contact:/' "$WORK/sipp/reg-msgs.log" | tr -d '\r' | sort -u)
reg_contacts=$(echo "$all_contacts" | grep "$REG_ID")
public=$(sed -n 's/^MIRA_PUBLIC_IP=//p' "$MIRA_DIR/.env")
if [ "$reg_contacts" = "Contact: <sip:$REG_ID@$public:5060>" ] && ! echo "$all_contacts" | grep -q "127.0.0.1"; then
	ok "REGISTER Contact carries Mira's public address ($public:5060), never 127.0.0.1"
else bad "REGISTER Contact: $all_contacts"; fi

echo "### 6. carrier calls in on the registered Contact (DID +20225550101 in To) -> 3001"
callin() { # FROM_IP RURI_USER EXTRA_HEADER OUT
	sed -e "s/@RURI_USER@/$2/" -e "s/@DID@/+20225550101/" -e "s/@EXTRA_HEADER@/$3/" \
		"$SIPP_DIR/carrier-call-in.xml" >"$WORK/sipp/$4.xml"
	(cd "$WORK/sipp" && timeout 25 sipp -sf "$4.xml" -i "$1" -p 5062 -m 1 -timeout 20 -timeout_error \
		-trace_msg -message_file "$4.log" "$LOCAL_IP:5060" >/dev/null 2>&1)
}
# Did Asterisk ring 3001 for the SIPp caller (+201000000001)? Its dialplan logs every
# extension call as "Mira: <caller> -> <endpoint>" (auto-answering baresip prints nothing).
dialled_3001() { # SINCE TRUNK_CHANNEL_PREFIX
	docker logs --since "$1" mira-asterisk-1 2>&1 | sed 's/\x1b\[[0-9;]*m//g' |
		grep "NoOp(\"PJSIP/$2" | grep -q "Mira: +201000000001 -> $ext_user"
}
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if callin "$REGISTRAR" "$REG_ID" "X-Test: normal" regcall; then ok "call from the registration carrier answered"; else
	bad "registration carrier call failed: $(grep -m1 '^SIP/2.0 [3-6]' "$WORK/sipp/regcall.log")"
	docker exec mira-kamailio-1 kamcmd -s unix:/run/kamailio/kamailio_ctl dispatcher.list | grep -E "URI" | head -8
fi
if dialled_3001 "$since" "$REG_ID"; then ok "it arrived on trunk $REG_ID and rang 3001 (DID +20225550101)"; else bad "3001 was not dialled for the registration carrier"; fi

echo "### 7. a stranger forging X-Mira-Trunk is refused"
since=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if callin "$STRANGER" "+20225550101" "X-Mira-Trunk: $IPT_ID" spoof; then
	bad "forged call was answered"
else
	ok "forged call not answered ($(grep -oE '^SIP/2.0 [2-6][0-9]{2}' "$WORK/sipp/spoof.log" | tail -1))"
fi
if dialled_3001 "$since" ""; then bad "stranger reached 3001"; else ok "3001 never rang for the stranger"; fi

echo "### 8. GSM gateway registers to Mira and calls both ways"
run_phone gsm 60
for _ in $(seq 1 15); do registered "$gw_user" && break; sleep 1; done
if registered "$gw_user"; then ok "gateway registered as $gw_user"; else bad "gateway did not register"; fi
stop_phone gsm
run_phone gsm 16 "/dial sip:01012345678@$DOMAIN"
sleep 14
stop_phone gsm
check_tone gsm 440 "gateway hears 3001 (mobile caller -> any number -> 3001)"
check_tone ext 660 "3001 hears the gateway"
rm -f "$WORK"/ext/rec/*.wav "$WORK"/gsm/rec/*.wav
run_phone gsm 25
sleep 3
stop_phone ext
run_phone ext 16 "/dial sip:701012345678@$DOMAIN"
sleep 14
stop_phone ext
stop_phone gsm
# Asterisk sends the call to the gateway's registered address with the number as R-URI user.
# A real gateway (Yeastar, Dinstar) takes any number; baresip 1.0 has no catch-all and answers
# "UA not found" for a user other than its own, which still proves where the call went.
if grep -qE "Incoming call|UA not found: 01012345678" "$WORK/gsm/log.txt"; then
	ok "gateway received the outbound call for 01012345678 at its registered address"
else bad "gateway never received the outbound call"; fi

# finish() drops the EXIT trap on failure (to keep the logs), so remove the test data first
cleanup
finish
