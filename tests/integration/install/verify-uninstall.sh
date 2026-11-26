#!/usr/bin/env bash
# Checks deploy/uninstall.sh (keep data, refused purge, full purge, reinstall). DESTRUCTIVE:
# deletes /opt/mira and Docker. Test machines only: sudo bash tests/integration/install/verify-uninstall.sh
set -uo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
if [ "${MIRA_TEST_MACHINE:-}" != "yes" ]; then
	echo "Refusing to run: this deletes /opt/mira and Docker. On a throwaway test machine run:"
	echo "  sudo MIRA_TEST_MACHINE=yes bash $0"
	exit 2
fi
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

echo "### default uninstall keeps data"
env_hash=$(sha256sum /opt/mira/.env | cut -d' ' -f1)
"$REPO/deploy/uninstall.sh" >/tmp/u1.out 2>&1
check "uninstall exits 0" test $? -eq 0
check "mira.service removed" test ! -e /etc/systemd/system/mira.service
check "fail2ban jail file removed" test ! -e /etc/fail2ban/jail.d/mira.local
check "SIP/RTP rules removed" bash -c "! ufw status | grep -qE '5060|10000:20000|3478|8089|443/tcp'"
check "ssh rule kept" bash -c "ufw status | grep -qE '^22/tcp'"
check "ufw still active" bash -c "ufw status | grep -q 'Status: active'"
check "/opt/mira kept with same secrets" test "$env_hash" = "$(sha256sum /opt/mira/.env | cut -d' ' -f1)"
check "docker still installed" command -v docker

echo "### reinstall reuses the kept secrets"
"$REPO/deploy/install.sh" >/tmp/i2.out 2>&1
check "reinstall exits 0" test $? -eq 0
check "secrets reused" test "$env_hash" = "$(sha256sum /opt/mira/.env | cut -d' ' -f1)"

echo "### --purge needs confirmation"
echo "wrong-name" | "$REPO/deploy/uninstall.sh" --purge >/tmp/u2.out 2>&1
check "wrong answer aborts with error" test $? -ne 0
check "data still there after refused purge" test -f /opt/mira/.env
check "service untouched after refused purge" test -e /etc/systemd/system/mira.service

echo "### --purge --remove-docker with confirmation"
hostname | "$REPO/deploy/uninstall.sh" --purge --remove-docker >/tmp/u3.out 2>&1
check "purge exits 0" test $? -eq 0
check "/opt/mira deleted" test ! -e /opt/mira
check "docker removed" bash -c "! command -v docker"
check "docker apt source removed" test ! -e /etc/apt/sources.list.d/docker.sources
check "ssh still allowed" bash -c "ufw status | grep -qE '^22/tcp'"

echo "### install from scratch again after purge"
"$REPO/deploy/install.sh" >/tmp/i3.out 2>&1
check "fresh install after purge exits 0" test $? -eq 0
check "new secrets generated" test "$env_hash" != "$(sha256sum /opt/mira/.env | cut -d' ' -f1)"

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
