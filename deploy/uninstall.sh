#!/usr/bin/env bash
# Mira Voice uninstaller — undoes deploy/install.sh on Ubuntu Server 24.04 / 26.04 LTS.
#
#   sudo ./deploy/uninstall.sh                     stop Mira, remove service, firewall rules, fail2ban jail
#   sudo ./deploy/uninstall.sh --remove-docker     …and remove Docker Engine and its apt repository
#   sudo ./deploy/uninstall.sh --purge             …and DELETE /opt/mira (database, recordings, secrets),
#                                                  Mira's images and volumes, the downloaded code
#
# By default all data in /opt/mira is KEPT. --purge asks you to type the hostname to confirm;
# add --yes-delete-all-data to skip the question (scripts only).
# The firewall stays on and SSH stays allowed, so you are never locked out.
set -Eeuo pipefail

MIRA_DIR=/opt/mira
UNIT_FILE=/etc/systemd/system/mira.service
JAIL_FILE=/etc/fail2ban/jail.d/mira.local

REMOVE_DOCKER=0 PURGE=0 ASSUME_YES=0

say() { printf '\n==> %s\n' "$*"; }
ok() { printf '    ok: %s\n' "$*"; }
die() {
	printf '\nERROR: %s\n' "$*" >&2
	exit 1
}

while [ $# -gt 0 ]; do
	case "$1" in
	--remove-docker) REMOVE_DOCKER=1 ;;
	--purge) PURGE=1 ;;
	--yes-delete-all-data) ASSUME_YES=1 ;;
	-h | --help)
		sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
		exit 0
		;;
	*) die "unknown option: $1 (try --help)" ;;
	esac
	shift
done

[ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"

if [ "$PURGE" -eq 1 ] && [ "$ASSUME_YES" -eq 0 ]; then
	printf '\n--purge will permanently delete %s: the database, all call recordings and the secrets.\n' "$MIRA_DIR"
	printf 'This cannot be undone. Type the hostname (%s) to confirm: ' "$(hostname)"
	read -r answer
	[ "$answer" = "$(hostname)" ] || die "not confirmed — nothing deleted"
fi

say "Stopping Mira"
if [ -f "$UNIT_FILE" ]; then
	systemctl disable --now mira.service >/dev/null 2>&1 || true
fi
if command -v docker >/dev/null 2>&1 && [ -f "$MIRA_DIR/docker-compose.yml" ]; then
	if [ "$PURGE" -eq 1 ]; then
		# also delete Mira's images and volumes (Asterisk database)
		(cd "$MIRA_DIR" && docker compose --env-file "$MIRA_DIR/.env" down --remove-orphans --volumes --rmi all) || true
	else
		(cd "$MIRA_DIR" && docker compose --env-file "$MIRA_DIR/.env" down --remove-orphans) || true
	fi
fi
ok "stopped"

say "Removing the systemd service"
rm -f "$UNIT_FILE"
systemctl daemon-reload
systemctl reset-failed mira.service >/dev/null 2>&1 || true
ok "mira.service removed"

say "Removing the fail2ban jail"
if [ -f "$JAIL_FILE" ]; then
	rm -f "$JAIL_FILE"
	systemctl is-active --quiet fail2ban && systemctl restart fail2ban
fi
ok "$JAIL_FILE removed (fail2ban itself stays installed)"

say "Removing Mira firewall rules (SSH rules and the firewall itself stay on)"
if command -v ufw >/dev/null 2>&1; then
	for rule in 80/tcp 443/tcp 5060/udp 5060/tcp 5061/tcp 8089/tcp 10000:20000/udp 3478/udp 3478/tcp; do
		ufw delete allow "$rule" >/dev/null 2>&1 || true
	done
fi
ok "web, SIP, WSS, RTP and TURN rules removed"

if [ "$REMOVE_DOCKER" -eq 1 ]; then
	say "Removing Docker Engine"
	apt-get purge -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker-ce-rootless-extras || true
	apt-get autoremove -y -q || true
	rm -f /etc/apt/sources.list.d/docker.sources /etc/apt/keyrings/docker.asc
	if [ "$PURGE" -eq 1 ]; then
		rm -rf /var/lib/docker /var/lib/containerd
		ok "Docker removed, including /var/lib/docker"
	else
		ok "Docker removed (images and volumes in /var/lib/docker kept; --purge deletes them)"
	fi
fi

if [ "$PURGE" -eq 1 ]; then
	say "Deleting $MIRA_DIR"
	rm -rf "$MIRA_DIR"
	rm -f /var/log/mira-install.log /root/mira-first-login.txt
	# code downloaded by deploy/get.sh (this script may be running from it: Linux keeps it open)
	rm -rf /usr/local/src/mira-voice
	ok "$MIRA_DIR, the first sign-in file and the downloaded code deleted"
else
	say "Keeping data"
	ok "$MIRA_DIR left in place (run with --purge to delete it)"
fi

say "Mira Voice uninstalled"
