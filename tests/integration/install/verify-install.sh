#!/usr/bin/env bash
# Checks deploy/install.sh on a clean Ubuntu 24.04 machine, after a first install.
# Run as root from the repo: sudo bash tests/integration/install/verify-install.sh
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
pass=0 fail=0
check() { # description, command...
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

echo "### re-run installer (idempotency)"
env_before=$(sha256sum /opt/mira/.env | cut -d' ' -f1)
rules_before=$(ufw status numbered | grep -c '^\[')
"$REPO/deploy/install.sh" >/tmp/run.out 2>&1
check "install.sh exits 0 on re-run" test $? -eq 0
check "secrets unchanged after re-run" test "$env_before" = "$(sha256sum /opt/mira/.env | cut -d' ' -f1)"
check "no duplicate ufw rules after re-run" test "$rules_before" -eq "$(ufw status numbered | grep -c '^\[')"
check "ufw has 20 rules (10 IPv4 + 10 IPv6)" test "$rules_before" -eq 20

echo "### secrets"
check ".env is 600 root:root" test "$(stat -c '%a %U:%G' /opt/mira/.env)" = "600 root:root"
check ".env has 18 settings" test "$(grep -c '^[A-Z_]*=' /opt/mira/.env)" -eq 18
check "MIRA_DATA_KEY is a Fernet key" bash -c "sed -n 's/^MIRA_DATA_KEY=//p' /opt/mira/.env | grep -qE '^[A-Za-z0-9_-]{43}=\$'"
check "MIRA_LOCAL_IP is this server's address" bash -c "ip -4 addr | grep -q \"inet \$(sed -n 's/^MIRA_LOCAL_IP=//p' /opt/mira/.env)/\""
check "TLS key is 600 root" test "$(stat -c '%a %U' /opt/mira/config/tls/mira.key)" = "600 root"
check "TLS certificate names the SIP domain" bash -c "openssl x509 -in /opt/mira/config/tls/mira.crt -noout -ext subjectAltName | grep -q \"\$(sed -n 's/^MIRA_SIP_DOMAIN=//p' /opt/mira/.env)\""
check ".env has no empty values" bash -c "! grep -qE '^[A-Z_]+=$' /opt/mira/.env"
check "secrets are 48+ hex chars" bash -c "grep -E '_(PASSWORD|SECRET)=' /opt/mira/.env | cut -d= -f2 | grep -vqE '^[0-9a-f]{48,}$' && exit 1 || exit 0"
check "secrets not printed in install log" bash -c "! grep -qF \"\$(grep POSTGRES_PASSWORD /opt/mira/.env | cut -d= -f2)\" /var/log/mira-install.log"
check "/opt/mira is 750 root" test "$(stat -c '%a %U' /opt/mira)" = "750 root"

echo "### services"
check "docker active" systemctl is-active --quiet docker
check "docker compose v2+ plugin works" docker compose version
check "ufw active" bash -c "ufw status | grep -q 'Status: active'"
check "ufw default deny incoming" bash -c "ufw status verbose | grep -q 'deny (incoming)'"
check "ssh 22/tcp is LIMIT" bash -c "ufw status | grep -qE '^22/tcp +LIMIT'"
check "rtp range open" bash -c "ufw status | grep -q '10000:20000/udp'"
check "fail2ban sshd jail running" fail2ban-client status sshd
check "mira.service enabled" systemctl is-enabled --quiet mira
check "mira.service active" systemctl is-active --quiet mira

echo "### telephony stack started by mira.service"
for svc in asterisk kamailio rtpengine; do
	check "$svc healthy" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-$svc-1 | grep -qx healthy"
done
check "coturn running" bash -c "docker inspect -f '{{.State.Status}}' mira-coturn-1 | grep -qx running"
check "containers use host networking" bash -c "[ \$(docker inspect -f '{{.HostConfig.NetworkMode}}' mira-asterisk-1 mira-kamailio-1 mira-rtpengine-1 mira-coturn-1 mira-postgres-1 mira-core-1 | sort -u) = host ]"
# snapshot first, pattern via a file descriptor: the secret must not appear on grep's own command line
check "no secrets on any process command line" bash -c "ps -eo args >/var/tmp/mira-ps.txt; ! grep -qFf <(sed -n 's/^TURN_SECRET=//p' /opt/mira/.env) /var/tmp/mira-ps.txt"
systemctl restart mira
check "mira.service restart brings the stack back healthy" bash -c "sleep 15; docker inspect -f '{{.State.Health.Status}}' mira-kamailio-1 | grep -qx healthy"

echo "### Mira Core and PostgreSQL"
dc() { (cd /opt/mira && docker compose "$@"); }
check "postgres healthy" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-postgres-1 | grep -qx healthy"
check "core healthy" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-core-1 | grep -qx healthy"
check "core-migrate finished with exit 0" bash -c "[ \$(docker inspect -f '{{.State.ExitCode}}' mira-core-migrate-1) = 0 ]"
check "database schema at the latest migration" bash -c "cd /opt/mira && docker compose exec -T core alembic current 2>/dev/null | grep -q '(head)'"
check "core API ready (database up)" bash -c "curl -s --max-time 5 http://127.0.0.1:8000/health/ready | grep -q '\"database\":\"up\"'"
check "PostgreSQL on 127.0.0.1:5432 only" bash -c "[ \"\$(ss -H -ltn 'sport = :5432' | awk '{print \$4}' | sort -u)\" = 127.0.0.1:5432 ]"
check "Mira Core on 127.0.0.1:8000 only" bash -c "[ \"\$(ss -H -ltn 'sport = :8000' | awk '{print \$4}' | sort -u)\" = 127.0.0.1:8000 ]"

echo "### live state (Valkey) and the ARI event worker (task 1.3)"
check "valkey healthy" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-valkey-1 | grep -qx healthy"
check "Valkey on 127.0.0.1:6379 only" bash -c "[ \"\$(ss -H -ltn 'sport = :6379' | awk '{print \$4}' | sort -u)\" = 127.0.0.1:6379 ]"
check "Valkey refuses commands without the password" bash -c "docker exec mira-valkey-1 valkey-cli -h 127.0.0.1 ping 2>&1 | grep -q NOAUTH"
check "Valkey password not on any command line" bash -c "ps -eo args >/var/tmp/mira-ps.txt; ! grep -qFf <(sed -n 's/^REDIS_PASSWORD=//p' /opt/mira/.env) /var/tmp/mira-ps.txt"
check "Valkey keeps nothing on disk" bash -c "docker exec mira-valkey-1 sh -c 'REDISCLI_AUTH=\"\$REDIS_PASSWORD\" valkey-cli -h 127.0.0.1 config get save' | tail -1 | grep -qx ''"
check "core-events healthy (connected to ARI)" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-core-events-1 | grep -qx healthy"
check "core-ivr healthy (Mira Flow engine connected to ARI)" bash -c "docker inspect -f '{{.State.Health.Status}}' mira-core-ivr-1 | grep -qx healthy"
check "Asterisk lists the mira-ivr application" bash -c "curl -s -u \"\$(sed -n 's/^ARI_USER=//p' /opt/mira/.env):\$(sed -n 's/^ARI_PASSWORD=//p' /opt/mira/.env)\" http://127.0.0.1:8088/ari/applications | grep -q '\"name\":\"mira-ivr\"'"
check "Asterisk lists the Mira ARI application" bash -c "curl -s -u \"\$(sed -n 's/^ARI_USER=//p' /opt/mira/.env):\$(sed -n 's/^ARI_PASSWORD=//p' /opt/mira/.env)\" http://127.0.0.1:8088/ari/applications | grep -q '\"name\":\"mira\"'"
probe="probe-$(date +%s)@example.com"
out=$(dc exec -T core mira-core create-admin --email "$probe" --name probe 2>&1)
pw=$(printf '%s\n' "$out" | sed -n 's/^Password.*: //p')
check "mira-core create-admin works" test -n "$pw"
token=$(curl -s --max-time 5 -X POST http://127.0.0.1:8000/api/v1/auth/token \
	--data-urlencode "username=$probe" --data-urlencode "password=$pw" | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
check "admin can log in and is platform_admin" bash -c "curl -s --max-time 5 -H 'Authorization: Bearer $token' http://127.0.0.1:8000/api/v1/auth/me | grep -q '\"role\":\"platform_admin\"'"
check "API refuses requests without a token" bash -c "[ \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/api/v1/tenants) = 401 ]"
# shellcheck disable=SC2016 # $POSTGRES_* must expand inside the postgres container
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -qc "DELETE FROM users WHERE email = '"'$probe'"'"' >/dev/null 2>&1

echo "### refuses wrong OS"
sed 's/VERSION_ID="24.04"/VERSION_ID="22.04"/' /etc/os-release >/tmp/os-release.fake
check "OS check rejects 22.04" bash -c "unshare -m bash -c 'mount --bind /tmp/os-release.fake /etc/os-release && $REPO/deploy/install.sh' 2>&1 | grep -q 'needs 24.04'"

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
