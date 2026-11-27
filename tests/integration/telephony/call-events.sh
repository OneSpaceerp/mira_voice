#!/usr/bin/env bash
# Mira Voice — task 1.3 gate: Mira Core follows every call through ARI.
#   • calls land in PostgreSQL (calls + call_events) with direction, numbers, agent, outcome
#   • active calls are live in Valkey (GET /calls/live) and published on the tenant's channel
#   • call control: hang up through the API, click-to-call (ring my phone, then dial)
#   • the event worker can restart mid-call; calls that ended meanwhile are closed
#
#   sudo bash tests/integration/telephony/call-events.sh
#
# Needs: Mira installed and running, `apt install baresip-core`. Uses a throw-away tenant.
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_NAME=events
# shellcheck source=SCRIPTDIR/lib.sh
. "$HERE/lib.sh"

API=http://127.0.0.1:8000/api/v1
RUN=$(date +%s)
SLUG="ev-$RUN"
ADMIN="ev-$RUN@example.com" AGENT1="ev1-$RUN@example.com" AGENT2="ev2-$RUN@example.com"
dc() { (cd "$MIRA_DIR" && docker compose "$@"); }
json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }
psql_q() { # shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -q' <<<"$1"
}

cleanup() {
	pkill -f "baresip -f $WORK" 2>/dev/null
	pkill -f "valkey-cli.*SUBSCRIBE" 2>/dev/null
	psql_q "
		DELETE FROM call_events WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM calls WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM extensions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM users WHERE email IN ('$ADMIN', '$AGENT1', '$AGENT2');
		DELETE FROM tenants WHERE slug = '$SLUG';" >/dev/null 2>&1
	dc exec -T core mira-core render-config >/dev/null 2>&1
	docker start mira-core-events-1 >/dev/null 2>&1
}
trap 'cleanup; rm -rf "$WORK"' EXIT

echo "### 1. tenant, two agents with extensions"
pw=$(dc exec -T core mira-core create-admin --email "$ADMIN" --name ev 2>&1 | sed -n 's/^Password.*: //p')
token() { curl -s -X POST "$API/auth/token" --data-urlencode "username=$1" --data-urlencode "password=$2" | json "d['access_token']"; }
TOKEN=$(token "$ADMIN" "$pw")
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
post() { curl -s "${H[@]}" -X POST "$API/$1" -d "$2"; }
get() { curl -s "${H[@]}" "$API/$1"; }
T=$(post tenants "{\"name\":\"Events test\",\"slug\":\"$SLUG\"}" | json "d['id']")
AGENT_PW="agent-$RUN-pass"
U1=$(post users "{\"tenant_id\":\"$T\",\"email\":\"$AGENT1\",\"full_name\":\"Agent One\",\"password\":\"$AGENT_PW\",\"role\":\"agent\"}" | json "d['id']")
U2=$(post users "{\"tenant_id\":\"$T\",\"email\":\"$AGENT2\",\"full_name\":\"Agent Two\",\"password\":\"$AGENT_PW\",\"role\":\"agent\"}" | json "d['id']")
E1=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"4001\",\"display_name\":\"One\",\"user_id\":\"$U1\"}")
E2=$(post extensions "{\"tenant_id\":\"$T\",\"number\":\"4002\",\"display_name\":\"Two\",\"user_id\":\"$U2\"}")
user() { echo "$1" | json "d['sip_username']"; }
secret() { echo "$1" | json "d['sip_password']"; }
if [ -n "$U1" ] && [ -n "$U2" ] && [ "$(user "$E1")" = "$SLUG-4001" ]; then ok "API created agents and extensions 4001, 4002"; else bad "setup: $U1 $U2 $E1"; fi

acct() { echo "<sip:$(user "$1")@$DOMAIN;transport=udp>;auth_pass=$(secret "$1");answermode=$2;audio_codecs=PCMU,PCMA;regint=120"; }
make_phone p1 5083 51000 440 "$(acct "$E1" auto)"
make_phone p2 5085 51200 880 "$(acct "$E2" auto)"
make_phone p2m 5087 51400 880 "$(acct "$E2" manual)" # rings, never answers

latest_call() { get "calls?tenant_id=$T&limit=1"; }
field() { echo "$1" | json "d[0]['$2'] if d else ''"; }
wait_ended() { # wait until the newest call has ended_at
	for _ in $(seq 1 20); do field "$(latest_call)" ended_at | grep -qv None && return 0; sleep 1; done
	return 1
}

echo "### 2. an answered internal call is recorded, live while it lasts, and published"
docker exec mira-valkey-1 sh -c "REDISCLI_AUTH=\"\$REDIS_PASSWORD\" timeout 30 valkey-cli -h 127.0.0.1 SUBSCRIBE mira:tenant:$T:events" >"$WORK/pubsub.txt" 2>&1 &
run_phone p2 30
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
run_phone p1 16 "/dial sip:4002@$DOMAIN"
sleep 7
live=$(get "calls/live?tenant_id=$T")
if [ "$(echo "$live" | json "len(d)")" = 1 ] && [ "$(echo "$live" | json "d[0]['state']")" = up ]; then
	ok "GET /calls/live shows the call, answered (state up)"
else bad "live view during the call: $live"; fi
sleep 7
stop_phone p1
stop_phone p2
if wait_ended; then ok "the call ended in the database when the phones hung up"; else bad "call never ended"; fi
c=$(latest_call)
if [ "$(field "$c" direction)" = internal ] && [ "$(field "$c" caller_number)" = 4001 ] && [ "$(field "$c" called_number)" = 4002 ]; then
	ok "internal call 4001 -> 4002"
else bad "call row: $c"; fi
if [ "$(field "$c" disposition)" = answered ] && [ "$(field "$c" agent_user_id)" = "$U1" ]; then ok "answered, agent = Agent One (who placed it)"; else bad "disposition/agent: $c"; fi
secs=$(echo "$c" | json "int((__import__('datetime').datetime.fromisoformat(d[0]['ended_at']) - __import__('datetime').datetime.fromisoformat(d[0]['answered_at'])).total_seconds())")
if [ "$secs" -ge 8 ] && [ "$secs" -le 16 ]; then ok "talk time ${secs}s matches the call"; else bad "talk time ${secs}s"; fi
CID=$(field "$c" id)
types=$(get "calls/$CID" | json "' '.join(sorted(set(e['type'] for e in d['events'])))")
if echo "$types" | grep -q ChannelCreated && echo "$types" | grep -q Dial && echo "$types" | grep -q ChannelDestroyed; then
	ok "call events stored: $types"
else bad "events: $types"; fi
if [ "$(get "calls/live?tenant_id=$T" | json "len(d)")" = 0 ]; then ok "live view empty again"; else bad "call still live"; fi
sleep 1
if grep -q '"call.started"' "$WORK/pubsub.txt" && grep -q '"call.ended"' "$WORK/pubsub.txt"; then
	ok "call.started / call.ended published on mira:tenant:<id>:events"
else bad "pub/sub: $(head -c 300 "$WORK/pubsub.txt")"; fi
rm -f "$WORK"/p1/rec/*.wav "$WORK"/p2/rec/*.wav

echo "### 3. an unanswered call"
run_phone p2m 20
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
run_phone p1 8 "/dial sip:4002@$DOMAIN"
sleep 7
stop_phone p1
stop_phone p2m
wait_ended
c=$(latest_call)
if [ "$(field "$c" disposition)" = no_answer ] && [ "$(field "$c" answered_at)" = None ]; then ok "recorded as no_answer"; else bad "unanswered call: $c"; fi

echo "### 4. hang up a live call through the API"
run_phone p2 40
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
run_phone p1 40 "/dial sip:4002@$DOMAIN"
sleep 5
CID=$(get "calls/live?tenant_id=$T" | json "d[0]['call_id'] if d else ''")
code=$(curl -s -o "$WORK/hangup.json" -w '%{http_code}' "${H[@]}" -X POST "$API/calls/$CID/hangup")
if [ "$code" = 202 ]; then ok "POST /calls/{id}/hangup accepted ($(cat "$WORK/hangup.json"))"; else bad "hangup returned $code $(cat "$WORK/hangup.json")"; fi
sleep 3
if wait_ended && [ "$(field "$(latest_call)" id)" = "$CID" ]; then ok "the call ended at once"; else bad "call did not end after hangup"; fi
if grep -qiE "terminated|session closed" "$WORK/p1/log.txt"; then ok "the caller's phone saw the hang-up"; else bad "caller phone still in the call"; fi
stop_phone p1
stop_phone p2

echo "### 5. click-to-call: Mira rings 4001, then dials 4002 from it"
A1=$(token "$AGENT1" "$AGENT_PW")
run_phone p1 30
run_phone p2 30
for _ in $(seq 1 15); do registered "$(user "$E1")" && registered "$(user "$E2")" && break; sleep 1; done
code=$(curl -s -o "$WORK/c2c.json" -w '%{http_code}' -H "Authorization: Bearer $A1" -H 'Content-Type: application/json' -X POST "$API/calls" -d '{"number":"4002"}')
if [ "$code" = 202 ]; then ok "POST /calls accepted for Agent One ($(cat "$WORK/c2c.json"))"; else bad "click-to-call returned $code $(cat "$WORK/c2c.json")"; fi
sleep 12
stop_phone p1
stop_phone p2
wait_ended
c=$(latest_call)
if [ "$(field "$c" caller_number)" = 4001 ] && [ "$(field "$c" called_number)" = 4002 ] && [ "$(field "$c" disposition)" = answered ]; then
	ok "click-to-call recorded as 4001 -> 4002, answered"
else bad "click-to-call row: $c"; fi
check_tone p1 880 "4001 hears 4002"
check_tone p2 440 "4002 hears 4001"
rm -f "$WORK"/p1/rec/*.wav "$WORK"/p2/rec/*.wav

echo "### 6. the event worker restarts: mid-call, and while a call ends"
run_phone p2 60
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
run_phone p1 60 "/dial sip:4002@$DOMAIN"
sleep 5
docker restart mira-core-events-1 >/dev/null
for _ in $(seq 1 40); do [ "$(docker inspect -f '{{.State.Health.Status}}' mira-core-events-1)" = healthy ] && break; sleep 2; done
live=$(get "calls/live?tenant_id=$T")
CID=$(echo "$live" | json "d[0]['call_id'] if isinstance(d, list) and d else ''" 2>/dev/null)
if [ -n "$CID" ]; then ok "after the restart the call is still live (picked up again)"; else bad "call lost by the restart: $live"; fi
docker stop mira-core-events-1 >/dev/null
stop_phone p1
stop_phone p2
sleep 2
docker start mira-core-events-1 >/dev/null
for _ in $(seq 1 40); do [ "$(docker inspect -f '{{.State.Health.Status}}' mira-core-events-1)" = healthy ] && break; sleep 2; done
d=$(get "calls/$CID")
if [ "$(echo "$d" | json "d['ended_at'] is not None")" = True ] && echo "$d" | grep -q MiraReconciled; then
	ok "a call that ended while the worker was stopped is closed (MiraReconciled)"
else bad "reconcile: $d"; fi
if [ "$(echo "$d" | json "d['disposition']")" = answered ]; then ok "and keeps its outcome: answered"; else bad "reconciled disposition: $(echo "$d" | json "d['disposition']")"; fi

echo "### 6b. Valkey restarts mid-call: the live view comes back"
run_phone p2 60
for _ in $(seq 1 15); do registered "$(user "$E2")" && break; sleep 1; done
run_phone p1 60 "/dial sip:4002@$DOMAIN"
sleep 4
docker restart mira-valkey-1 >/dev/null
back=""
for _ in $(seq 1 30); do
	[ "$(get "calls/live?tenant_id=$T" | json "len(d)" 2>/dev/null)" = 1 ] && back=yes && break
	sleep 1
done
if [ "$back" = yes ]; then ok "the worker published the live call again after Valkey's restart"; else bad "live view stayed empty after Valkey restarted"; fi
stop_phone p1
stop_phone p2
wait_ended

echo "### 7. the record has no caller-typed digits"
if [ "$(psql_q "SELECT count(*) FROM call_events WHERE tenant_id = '$T' AND (type ILIKE '%dtmf%' OR data::text ILIKE '%digit%')")" = 0 ]; then
	ok "no DTMF in call_events"
else bad "DTMF found in call_events"; fi

# finish() drops the EXIT trap on failure (to keep the logs), so remove the test data first
cleanup
finish
