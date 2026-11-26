#!/usr/bin/env bash
# Mira Voice — task 1.4 gate (builder): the Mira Flow builder in Mira Desk, in a real browser,
# against the installed Mira Core.
#   • build a flow with the inspector and the keyboard only, save, publish; the published
#     version read back through the API is exactly what was built
#   • the problems panel lists an unfinished step and selects it; publishing is refused
#   • Arabic switches the page to right-to-left; numbers stay left-to-right
#   • axe finds no serious or critical accessibility problem, in light and dark
#
#   sudo bash tests/integration/desk/run.sh
#
# Needs: Mira installed and running, Node 24 (node + npm). Uses a throw-away tenant.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
MIRA_DIR=/opt/mira
API=http://127.0.0.1:8000/api/v1
RUN=$(date +%s)
SLUG="de-$RUN"
ROOT_ADMIN="de-$RUN@example.com" EDITOR="ded-$RUN@example.com"
EDITOR_PW="desk-$RUN-$(openssl rand -hex 6)"

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 2; }
# Node 24 from nvm (docs/stack-versions.md) when it is not already on PATH
if ! command -v npm >/dev/null && [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
	# shellcheck disable=SC1091
	. "${NVM_DIR:-$HOME/.nvm}/nvm.sh" >/dev/null
fi
command -v npm >/dev/null || { echo "Node 24 missing (node + npm): install it with nvm"; exit 2; }

WORK=$(mktemp -d -p /var/tmp mira-desk-test.XXXXXX)
dc() { (cd "$MIRA_DIR" && docker compose "$@"); }
json() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }
psql_q() { # shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -q' <<<"$1"
}
cleanup() {
	psql_q "
		DELETE FROM ivr_flows WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM prompts WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM extensions WHERE tenant_id IN (SELECT id FROM tenants WHERE slug = '$SLUG');
		DELETE FROM users WHERE email IN ('$ROOT_ADMIN', '$EDITOR');
		DELETE FROM tenants WHERE slug = '$SLUG';" >/dev/null 2>&1
	dc exec -T core mira-core render-config >/dev/null 2>&1
}
trap 'cleanup; rm -rf "$WORK"' EXIT

echo "### 1. a tenant, its admin, an extension and a recorded prompt"
pw=$(dc exec -T core mira-core create-admin --email "$ROOT_ADMIN" --name de 2>&1 | sed -n 's/^Password.*: //p')
TOKEN=$(curl -s -X POST "$API/auth/token" --data-urlencode "username=$ROOT_ADMIN" --data-urlencode "password=$pw" | json "d['access_token']")
H=(-H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json')
post() { curl -s "${H[@]}" -X POST "$API/$1" -d "$2"; }
T=$(post tenants "{\"name\":\"Desk test\",\"slug\":\"$SLUG\",\"default_locale\":\"en\"}" | json "d['id']")
U=$(post users "{\"tenant_id\":\"$T\",\"email\":\"$EDITOR\",\"full_name\":\"Flow editor\",\"password\":\"$EDITOR_PW\",\"role\":\"tenant_admin\",\"locale\":\"en\"}" | json "d.get('id', d)")
post extensions "{\"tenant_id\":\"$T\",\"number\":\"1001\",\"display_name\":\"Front desk\"}" >/dev/null
P=$(post prompts "{\"tenant_id\":\"$T\",\"name\":\"welcome\"}" | json "d['id']")
python3 - "$WORK/welcome.wav" <<-'PY'
	import sys, wave, struct, math
	w = wave.open(sys.argv[1], "w"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
	w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 600 * i / 8000))) for i in range(8000)))
PY
curl -s -o /dev/null -H "Authorization: Bearer $TOKEN" -H 'Content-Type: audio/wav' \
	-X PUT "$API/prompts/$P/audio/ar" --data-binary "@$WORK/welcome.wav"
check=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/auth/token" --data-urlencode "username=$EDITOR" --data-urlencode "password=$EDITOR_PW")
[ -n "$T" ] && [ -n "$P" ] && [ "$check" = 200 ] || { echo "FAIL  setup (tenant $T, prompt $P, editor $U, sign-in $check)"; exit 1; }
echo "tenant $SLUG, editor $EDITOR, prompt welcome (ar)"

echo "### 2. build Mira Desk (outside the source tree: node_modules are per platform)"
tar -C "$REPO" --exclude=desk/node_modules --exclude=desk/dist --exclude='desk/test-results' \
	-cf - desk design-system | tar -C "$WORK" -xf -
cd "$WORK/desk" || exit 1
npm ci --no-audit --no-fund --loglevel=error || exit 1
npx playwright install --with-deps chromium >/dev/null || exit 1
npm run build-only >/dev/null || { echo "FAIL  vite build"; exit 1; }

echo "### 3. browser tests"
MIRA_CORE_URL=http://127.0.0.1:8000 MIRA_E2E_EMAIL="$EDITOR" MIRA_E2E_PASSWORD="$EDITOR_PW" \
	MIRA_E2E_PROMPT=welcome MIRA_E2E_RUN="$RUN" npx playwright test
status=$?
# screenshots (for the design review), lesser axe findings and failure traces
rm -rf /var/tmp/mira-desk-e2e-results && cp -r test-results /var/tmp/mira-desk-e2e-results 2>/dev/null
cat /var/tmp/mira-desk-e2e-results/*/axe-minor.txt 2>/dev/null | sort -u | sed 's/^/NOTE  axe /'
if [ $status -eq 0 ]; then echo "PASS  Mira Desk browser tests (screenshots in /var/tmp/mira-desk-e2e-results)"
else echo "FAIL  Mira Desk browser tests (traces in /var/tmp/mira-desk-e2e-results)"; fi
exit $status
