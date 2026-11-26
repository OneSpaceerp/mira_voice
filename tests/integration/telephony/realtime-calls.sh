#!/usr/bin/env bash
# Mira Voice — task 1.1 gate: extensions created through the Mira Core API work at once.
#   • Asterisk reads them live from PostgreSQL (realtime views) — no file, no reload
#   • the generated dialplan routes calls inside a tenant, and only inside it
#   • a deleted extension can neither register nor be called
#
#   sudo bash tests/integration/telephony/realtime-calls.sh
#
# Needs: Mira installed and running, `apt install baresip-core`. Uses throw-away tenants
# (unique slugs per run) and removes them at the end.
# No pipefail: checks are written "cmd | grep -q ...", and grep -q stops reading at the
# first match, so the writer gets SIGPIPE and pipefail would turn a match into a failure.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_NAME=realtime
# shellcheck source=SCRIPTDIR/lib.sh
. "$HERE/lib.sh"

API=http://127.0.0.1:8000/api/v1
RUN=$(date +%s)
SLUG_A="rt-a-$RUN" SLUG_B="rt-b-$RUN"
ADMIN="rt-$RUN@example.com"
dc() { (cd "$MIRA_DIR" && docker compose "$@"); }
ast() { docker exec mira-asterisk-1 asterisk -rx "$1"; }
json() { python3 -c "import sys, json; print(json.load(sys.stdin)$1)"; }

cleanup() {
	pkill -f "baresip -f $WORK" 2>/dev/null
	# shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q' >/dev/null 2>&1 <<-SQL
		DELETE FROM call_events WHERE tenant_id IN (SELECT id FROM tenants WHERE slug IN ('$SLUG_A', '$SLUG_B'));
		DELETE FROM calls WHERE tenant_id IN (SELECT id FROM tenants WHERE slug IN ('$SLUG_A', '$SLUG_B'));
		DELETE FROM extensions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug IN ('$SLUG_A', '$SLUG_B'));
		DELETE FROM users WHERE email = '$ADMIN';
		DELETE FROM tenants WHERE slug IN ('$SLUG_A', '$SLUG_B');
	SQL
	dc exec -T core mira-core render-config >/dev/null 2>&1
}
trap 'cleanup; rm -rf "$WORK"' EXIT

echo "### 1. tenants and extensions through the API"
pw=$(dc exec -T core mira-core create-admin --email "$ADMIN" --name rt 2>&1 | sed -n 's/^Password.*: //p')
TOKEN=$(curl -s -X POST "$API/auth/token" --data-urlencode "username=$ADMIN" --data-urlencode "password=$pw" | json "['access_token']")
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
post() { curl -s "${H[@]}" -X POST "$API/$1" -d "$2"; }
TA=$(post tenants "{\"name\":\"RT A\",\"slug\":\"$SLUG_A\"}" | json "['id']")
TB=$(post tenants "{\"name\":\"RT B\",\"slug\":\"$SLUG_B\"}" | json "['id']")
mk() { post extensions "{\"tenant_id\":\"$1\",\"number\":\"$2\",\"display_name\":\"RT $2\"}"; }
A1=$(mk "$TA" 2001) A2=$(mk "$TA" 2002) B1=$(mk "$TB" 2001)
user() { echo "$1" | json "['sip_username']"; }
secret() { echo "$1" | json "['sip_password']"; }
reloaded() { echo "$1" | json "['config_applied']"; }
if [ "$(user "$A1")" = "$SLUG_A-2001" ]; then ok "API created $SLUG_A-2001, $SLUG_A-2002, $SLUG_B-2001"; else bad "extension creation: $A1"; fi
if [ "$(reloaded "$A2")" = True ]; then ok "Mira Core regenerated the config and reloaded Asterisk over ARI"; else bad "dialplan not reloaded: $(reloaded "$A2")"; fi

echo "### 2. Asterisk sees them (realtime from PostgreSQL, generated dialplan)"
if ast "pjsip show endpoint $(user "$A1")" | grep -q "Endpoint:  *$(user "$A1")"; then ok "Asterisk loads endpoint $(user "$A1") from the database"; else bad "endpoint not visible in Asterisk"; fi
CTX_A="t_${TA//-/}"
if ast "dialplan show $CTX_A" | grep -q "'2002'"; then ok "dialplan context $CTX_A has extension 2002"; else bad "dialplan context $CTX_A missing 2002"; fi
if ast "dialplan show t_${TB//-/}" | grep -q "'2002'"; then bad "tenant B's context contains 2002"; else ok "tenant B's context does not contain tenant A's 2002"; fi

echo "### 3. call inside tenant A (2001 -> 2002)"
acct() { echo "<sip:$(user "$1")@$DOMAIN;transport=udp>;auth_pass=$(secret "$1");answermode=auto;audio_codecs=PCMU,PCMA;regint=120"; }
make_phone a1 5073 50400 440 "$(acct "$A1")"
make_phone a2 5075 50600 880 "$(acct "$A2")"
make_phone b1 5077 50800 660 "$(acct "$B1")"
run_phone a2 40
for _ in $(seq 1 15); do registered "$(user "$A2")" && break; sleep 1; done
if registered "$(user "$A2")"; then ok "$(user "$A2") registered with the API-issued password"; else bad "$(user "$A2") did not register"; fi
run_phone a1 14 "/dial sip:2002@$DOMAIN"
sleep 12
stop_phone a1
check_tone a1 880 "2001 hears 2002"
check_tone a2 440 "2002 hears 2001"
rm -f "$WORK"/a1/rec/*.wav "$WORK"/a2/rec/*.wav

echo "### 4. tenant B cannot reach tenant A's 2002"
before=$(grep -c "Incoming call" "$WORK/a2/log.txt" || true)
run_phone b1 10 "/dial sip:2002@$DOMAIN"
sleep 8
stop_phone b1
after=$(grep -c "Incoming call" "$WORK/a2/log.txt" || true)
if [ "$after" = "$before" ]; then ok "tenant A's 2002 never rang for tenant B"; else bad "cross-tenant call reached tenant A"; fi
stop_phone a2

echo "### 5. a deleted extension stops working"
code=$(curl -s -o /dev/null -w '%{http_code}' "${H[@]}" -X DELETE "$API/extensions/$(echo "$A2" | json "['id']")")
if [ "$code" = 204 ]; then ok "API deleted $(user "$A2")"; else bad "delete returned $code"; fi
if ast "pjsip show endpoint $(user "$A2")" | grep -q "Unable to find object"; then ok "Asterisk no longer has the endpoint"; else bad "endpoint still in Asterisk"; fi
if ast "dialplan show $CTX_A" | grep -q "'2002'"; then bad "2002 still in the dialplan"; else ok "2002 removed from the dialplan"; fi
: >"$WORK/a2/log.txt"
run_phone a2 8
sleep 6
stop_phone a2
if grep -qE "(401|403) |Unauthorized|Forbidden" "$WORK/a2/log.txt" && ! grep -q "200 OK" "$WORK/a2/log.txt"; then
	ok "the deleted extension's phone is refused"
else
	bad "deleted extension could still register"
fi

# finish() drops the EXIT trap on failure (to keep the logs), so remove the test data first
cleanup
finish
