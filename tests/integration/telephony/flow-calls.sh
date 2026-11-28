#!/usr/bin/env bash
# Mira Voice — task 1.4 gate (engine): Mira Flow runs real IVR calls through ARI.
#   • prompts uploaded through the API play from the prompts volume, per language (ar, fr)
#   • menu keys (RFC 4733 DTMF from the test phone), language switch, transfer to an agent
#   • collect digits + data dip to a web service on the LAN + branch (VIP or not)
#   • voicemail recorded, listed and downloaded through the API
#   • time condition (a holiday today -> closed)
#   • the IVR path is in call_events; the digits typed are not
#
#   sudo bash tests/integration/telephony/flow-calls.sh
#
# Needs: Mira installed and running, `apt install baresip-core`. Uses a throw-away tenant.
# Prompts are pure tones, so the test can tell which one the caller heard:
#   welcome (ar) 600 Hz · welcome (fr) 1000 Hz · menu (ar) 700 Hz · closed (ar) 500 Hz
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_NAME=flows
# shellcheck source=SCRIPTDIR/lib.sh
. "$HERE/lib.sh"

API=http://127.0.0.1:8000/api/v1
RUN=$(date +%s)
SLUG="fl-$RUN"
ADMIN="fl-$RUN@example.com" AGENT="fla-$RUN@example.com"
DIP_PORT=8766 CTRL_PORT=4445
dc() { (cd "$MIRA_DIR" && docker compose "$@"); }
json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }
psql_q() { # shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -q' <<<"$1"
}

cleanup() {
	pkill -f "baresip -f $WORK" 2>/dev/null
	pkill -f "mira-test-dip-$RUN" 2>/dev/null
	psql_q "
		DELETE FROM voicemails WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM call_events WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM calls WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM inbound_routes WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM ivr_flows WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM prompts WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM extensions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM users WHERE email IN ('$ADMIN', '$AGENT');
		DELETE FROM tenants WHERE slug = '$SLUG';" >/dev/null 2>&1
	dc exec -T core mira-core render-config >/dev/null 2>&1
}
trap 'cleanup; rm -rf "$WORK"' EXIT

tone_wav() { # FILE HZ SECONDS
	python3 - "$1" "$2" "$3" <<-'PY'
		import sys, wave, struct, math
		path, hz, secs, rate = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), 8000
		w = wave.open(path, "w"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
		w.writeframes(b"".join(struct.pack("<h", int(12000 * math.sin(2 * math.pi * hz * i / rate))) for i in range(int(rate * secs))))
	PY
}

# which tones a recording contains: dominant frequency of every 0.5 s with real sound
tones_in() { # FILE
	python3 - "$1" <<-'PY'
		import sys, wave, struct, math
		w = wave.open(sys.argv[1]); n = w.getnframes(); rate = w.getframerate()
		data = struct.unpack("<%dh" % n, w.readframes(n)); step = rate // 2; found = []
		for i in range(0, len(data) - step, step):
		    chunk = data[i:i + step]
		    if math.sqrt(sum(x * x for x in chunk) / len(chunk)) < 800:
		        continue
		    hz = sum(1 for a, b in zip(chunk, chunk[1:]) if (a < 0) != (b < 0)) / 2 / 0.5
		    found.append(int(round(hz / 50.0) * 50))
		print(" ".join(str(f) for f in sorted(set(found))))
	PY
}

# send DTMF from the test phone (baresip ctrl_tcp, netstring JSON "sndcode")
press() { # DIGITS
	python3 - "$CTRL_PORT" "$1" <<-'PY'
		import json, socket, sys, time
		port, digits = int(sys.argv[1]), sys.argv[2]
		s = socket.create_connection(("127.0.0.1", port), timeout=5)
		for d in digits:
		    msg = json.dumps({"command": "sndcode", "params": d, "token": "t"}).encode()
		    s.sendall(str(len(msg)).encode() + b":" + msg + b",")
		    time.sleep(0.4)
		s.close()
	PY
}

echo "### 1. tenant, agent, extensions, prompts and flows through the API"
pw=$(dc exec -T core mira-core create-admin --email "$ADMIN" --name fl 2>&1 | sed -n 's/^Password.*: //p')
token() { curl -s -X POST "$API/auth/token" --data-urlencode "username=$1" --data-urlencode "password=$2" | json "d['access_token']"; }
TOKEN=$(token "$ADMIN" "$pw")
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
post() { curl -s "${H[@]}" -X POST "$API/$1" -d "$2"; }
get() { curl -s "${H[@]}" "$API/$1"; }
T=$(post tenants "{\"name\":\"Flow test\",\"slug\":\"$SLUG\",\"default_locale\":\"ar\"}" | json "d['id']")
AGENT_PW="agent-$RUN-pass"
U=$(post users "{\"tenant_id\":\"$T\",\"email\":\"$AGENT\",\"full_name\":\"Agent\",\"password\":\"$AGENT_PW\",\"role\":\"agent\"}" | json "d['id']")
# 5001 = the agent's extension (its mailbox gets the voicemail); never registered in this test
MAILBOX=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"5001\",\"display_name\":\"Mailbox\",\"user_id\":\"$U\"}")
E2=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"5002\",\"display_name\":\"Agent desk\"}")
CALLER=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"5009\",\"display_name\":\"Caller\"}")
user() { echo "$1" | json "d['sip_username']"; }
secret() { echo "$1" | json "d['sip_password']"; }
if [ "$(user "$MAILBOX")" = "$SLUG-5001" ] && [ -n "$(user "$E2")" ] && [ -n "$(user "$CALLER")" ]; then
	ok "agent with mailbox 5001, desk 5002 and a caller 5009 created"
else bad "extensions: $MAILBOX"; fi

mkdir -p "$WORK/prompts"
upload() { # PROMPT_ID LANG HZ SECONDS
	tone_wav "$WORK/prompts/$1-$2.wav" "$3" "$4"
	curl -s -o /dev/null -H "Authorization: Bearer $TOKEN" -H 'Content-Type: audio/wav' \
		-X PUT "$API/prompts/$1/audio/$2" --data-binary "@$WORK/prompts/$1-$2.wav"
}
prompt() { # NAME LANG HZ SECONDS -> id
	local id
	id=$(post prompts "{\"tenant_id\":\"$T\",\"name\":\"$1\"}" | json "d['id']")
	upload "$id" "$2" "$3" "$4"
	echo "$id"
}
P_WELCOME=$(prompt welcome ar 600 2)
upload "$P_WELCOME" fr 1000 2
P_MENU=$(prompt menu ar 700 3)
P_CLOSED=$(prompt closed ar 500 2)
langs=$(get "prompts?tenant_id=$T" | json "' '.join(sorted(a['language'] for p in d if p['name'] == 'welcome' for a in p['audio']))")
if [ "$langs" = "ar fr" ]; then ok "prompts uploaded (welcome in ar + fr, menu, closed)"; else bad "prompt upload: $langs"; fi

DIP_URL="http://$LOCAL_IP:$DIP_PORT/api/method/lookup?account={{account}}&from={{caller_number}}"
MAIN=$(python3 - "$P_WELCOME" "$P_MENU" "$DIP_URL" <<-'PY'
	import json, sys
	welcome, menu, url = sys.argv[1:4]
	print(json.dumps({"schema": "mira-flow/1", "start": "welcome", "nodes": {
	  "welcome": {"type": "play", "prompt": welcome, "next": "menu"},
	  "menu": {"type": "menu", "prompt": menu, "options": {"1": "desk", "2": "french", "3": "account"},
	           "timeout_seconds": 6, "retries": 1, "invalid_next": "vm"},
	  "desk": {"type": "transfer", "number": "5002"},
	  "french": {"type": "language", "language": "fr", "next": "again"},
	  "again": {"type": "play", "prompt": welcome, "next": "bye"},
	  "account": {"type": "collect", "prompt": menu, "variable": "account", "min_digits": 4,
	              "max_digits": 8, "timeout_seconds": 6, "next": "lookup", "timeout_next": "vm"},
	  "lookup": {"type": "http", "url": url, "extract": {"vip": "message.vip"}, "next": "is_vip", "error_next": "vm"},
	  "is_vip": {"type": "branch", "variable": "vip", "conditions": [{"op": "eq", "value": "1", "next": "desk"}], "default_next": "vm"},
	  "vm": {"type": "voicemail", "mailbox": "5001", "max_seconds": 30},
	  "bye": {"type": "hangup"}}}))
PY
)
CLOSED=$(python3 - "$P_CLOSED" "$(date +%F)" <<-'PY'
	import json, sys
	closed, today = sys.argv[1:3]
	print(json.dumps({"schema": "mira-flow/1", "start": "hours", "nodes": {
	  "hours": {"type": "time", "weekly": [{"days": ["mon","tue","wed","thu","fri","sat","sun"], "from": "00:00", "to": "23:59"}],
	            "holidays": [today], "open_next": "desk", "closed_next": "closed"},
	  "desk": {"type": "transfer", "number": "5002"},
	  "closed": {"type": "play", "prompt": closed, "next": "bye"},
	  "bye": {"type": "hangup"}}}))
PY
)
F1=$(post flows "{\"tenant_id\":\"$T\",\"name\":\"Main\",\"number\":\"7000\",\"draft\":$MAIN}" | json "d['id']")
F2=$(post flows "{\"tenant_id\":\"$T\",\"name\":\"Holiday\",\"number\":\"7001\",\"draft\":$CLOSED}" | json "d['id']")
p1=$(curl -s "${H[@]}" -X POST "$API/flows/$F1/publish")
p2=$(curl -s "${H[@]}" -X POST "$API/flows/$F2/publish")
if [ "$(echo "$p1" | json "d.get('published_version')")" = 1 ] && [ "$(echo "$p2" | json "d.get('published_version')")" = 1 ]; then
	ok "flows published as 7000 (menu) and 7001 (holiday)"
else bad "publish: $p1 / $p2"; fi
if docker exec mira-asterisk-1 asterisk -rx "dialplan show 7000@t_${T//-/}" | grep -q "Stasis(mira-ivr,${F1//-/})"; then ok "dialplan sends 7000 to the Mira Flow engine"; else bad "7000 not in the dialplan"; fi
if [ "$(docker inspect -f '{{.State.Health.Status}}' mira-core-ivr-1)" = healthy ]; then ok "core-ivr connected to ARI"; else bad "core-ivr not healthy"; fi

# the "ERP": a small JSON service on this machine's LAN address
python3 - "$LOCAL_IP" "$DIP_PORT" "$WORK/dip.log" "mira-test-dip-$RUN" <<-'PY' &
	import json, sys
	from http.server import BaseHTTPRequestHandler, HTTPServer
	from urllib.parse import parse_qs, urlsplit
	host, port, log = sys.argv[1], int(sys.argv[2]), sys.argv[3]
	class H(BaseHTTPRequestHandler):
	    def do_GET(self):
	        q = parse_qs(urlsplit(self.path).query)
	        open(log, "a").write(self.path + " host=" + self.headers.get("Host", "") + "\n")
	        body = json.dumps({"message": {"vip": q.get("account") == ["5501"]}}).encode()
	        self.send_response(200); self.send_header("Content-Type", "application/json")
	        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
	    def log_message(self, *a): pass
	HTTPServer((host, port), H).serve_forever()
PY
sleep 1

acct() { echo "<sip:$(user "$1")@$DOMAIN;transport=udp>;auth_pass=$(secret "$1");answermode=$2;audio_codecs=PCMU,PCMA;regint=120"; }
make_phone caller 5093 52000 440 "$(acct "$CALLER" auto)"
printf 'module_app\t\tctrl_tcp.so\nctrl_tcp_listen\t\t127.0.0.1:%s\n' "$CTRL_PORT" >>"$WORK/caller/config"
make_phone desk 5095 52200 880 "$(acct "$E2" auto)"

call_flow() { # NUMBER SECONDS [KEYS AFTER SECONDS]...  -> runs the caller, presses keys
	local number=$1 secs=$2
	shift 2
	rm -f "$WORK"/caller/rec/*.wav
	run_phone caller "$secs" "/dial sip:$number@$DOMAIN"
	local elapsed=0
	while [ $# -ge 2 ]; do
		sleep $(($1 - elapsed))
		elapsed=$1
		press "$2"
		shift 2
	done
	sleep $((secs - 2 - elapsed))
	stop_phone caller
}
latest_call() { get "calls?tenant_id=$T&limit=1"; }

echo "### 2. 7000, key 1: welcome + menu prompts (ar), then the agent desk 5002"
run_phone desk 40
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
call_flow 7000 18 6 1
stop_phone desk
heard=$(tones_in "$(received caller)")
if echo " $heard " | grep -q " 600 " && echo " $heard " | grep -q " 700 "; then ok "caller heard welcome (600 Hz) and menu (700 Hz): $heard"; else bad "prompts heard: '$heard'"; fi
if echo " $heard " | grep -q " 1000 "; then bad "French prompt played without choosing French"; else ok "no French prompt (tenant language is Arabic)"; fi
# after the transfer the caller hears the desk phone's 880 Hz tone
if grep -q "Call established" "$WORK/desk/log.txt" && echo " $heard " | grep -qE " (850|900) "; then
	ok "key 1 transferred the call to 5002 (caller heard the desk)"
else bad "transfer to 5002: desk log $(grep -c 'Call established' "$WORK/desk/log.txt"), heard '$heard'"; fi
sleep 2
lc=$(latest_call)
CID=$(echo "$lc" | json "d[0]['id'] if isinstance(d, list) and d else ''" 2>/dev/null)
path=$(get "calls/$CID" | json "' '.join(e['data'].get('node', '') for e in d['events'] if e['type'] == 'FlowNode')" 2>/dev/null)
if [ "$path" = "welcome menu desk" ]; then ok "IVR path in call_events: $path"; else bad "IVR path: '$path' (latest call: ${lc:0:300})"; fi

echo "### 3. 7000, key 2: switch to French, the French welcome plays"
call_flow 7000 14 6 2
heard=$(tones_in "$(received caller)")
if echo " $heard " | grep -q " 1000 "; then ok "caller heard the French welcome (1000 Hz): $heard"; else bad "French prompt not heard: '$heard'"; fi

echo "### 4. 7000, key 3, account 5501#: data dip says VIP -> agent desk"
run_phone desk 40
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
before=$(grep -c "Call established" "$WORK/desk/log.txt" || true)
call_flow 7000 22 6 3 9 "5501#"
stop_phone desk
after=$(grep -c "Call established" "$WORK/desk/log.txt" || true)
if grep -q "account=5501" "$WORK/dip.log" && grep -q "host=$LOCAL_IP:$DIP_PORT" "$WORK/dip.log"; then ok "data dip reached the web service with account=5501"; else bad "data dip: $(cat "$WORK/dip.log" 2>/dev/null)"; fi
if [ "$after" -gt "$before" ]; then ok "VIP caller transferred to the agent desk"; else bad "VIP caller not transferred"; fi

echo "### 5. 7000, key 3, account 1111#: not VIP -> voicemail for 5001"
call_flow 7000 26 6 3 9 "1111#"
sleep 3
A=$(token "$AGENT" "$AGENT_PW")
vms=$(curl -s -H "Authorization: Bearer $A" "$API/voicemails")
count=$(echo "$vms" | json "len(d)")
secs=$(echo "$vms" | json "d[0]['duration_seconds'] if d else 0")
if [ "$count" = 1 ] && [ "$secs" -ge 3 ]; then ok "voicemail for 5001 listed for its agent (${secs}s)"; else bad "voicemail list: $vms"; fi
VM=$(echo "$vms" | json "d[0]['id'] if d else ''")
curl -s -H "Authorization: Bearer $A" -o "$WORK/vm.wav" "$API/voicemails/$VM/audio"
vm_tones=$(tones_in "$WORK/vm.wav" 2>/dev/null)
if echo " $vm_tones " | grep -q " 450 \| 400 \| 440 "; then ok "the message is the caller's 440 Hz tone: $vm_tones"; else bad "voicemail audio: '$vm_tones'"; fi
if [ "$(curl -s -H "Authorization: Bearer $A" "$API/voicemails" | json "d[0]['heard']")" = True ]; then ok "listening marked it heard"; else bad "not marked heard"; fi
lc=$(latest_call)
CID=$(echo "$lc" | json "d[0]['id'] if isinstance(d, list) and d else ''" 2>/dev/null)
events=$(get "calls/$CID" | json "json.dumps(d['events'])" 2>/dev/null || get "calls/$CID")
if echo "$events" | grep -q '"FlowEnded"' && ! echo "$events" | grep -q "1111"; then ok "flow ended in voicemail; the typed account is not in call_events"; else bad "events: ${events:0:400} (latest call: ${lc:0:300})"; fi

echo "### 6. 7001 on a holiday: closed prompt"
call_flow 7001 10
heard=$(tones_in "$(received caller)")
if echo " $heard " | grep -q " 500 "; then ok "holiday today: caller heard the closed prompt (500 Hz)"; else bad "closed prompt: '$heard'"; fi

# finish() drops the EXIT trap on failure (to keep the logs), so remove the test data first
cleanup
finish
