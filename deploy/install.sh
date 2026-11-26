#!/usr/bin/env bash
# Mira Voice installer — Ubuntu Server 24.04 or 26.04 LTS (x86_64).
#
#   sudo ./deploy/install.sh [--admin-email EMAIL] [--company NAME] [--language ar|en|fr]
#                            [--public-ip IP] [--domain NAME] [--ssh-port PORT] [--allow-low-resources]
#
#   --admin-email  first install: the platform admin who signs in to Mira Desk (asked if missing)
#   --company      first install: the name of the first tenant (default: Mira)
#   --language     first install: language of that tenant and its admin (default: ar)
#   --public-ip    address phones and browsers reach (behind NAT; default: the server's own IP)
#   --domain       SIP domain / certificate name, e.g. voice.example.com (default: the public IP)
#
# Safe to run again: every step checks what is already there and only adds what is missing.
# Existing secrets in /opt/mira/.env are never changed (changing them would lock services
# out of their own data).
set -Eeuo pipefail

MIRA_DIR=/opt/mira
ENV_FILE="$MIRA_DIR/.env"
LOG_FILE=/var/log/mira-install.log
UNIT_FILE=/etc/systemd/system/mira.service
FIRST_LOGIN_FILE=/root/mira-first-login.txt
SUPPORTED_UBUNTU="24.04 26.04"
JAIL_FILE=/etc/fail2ban/jail.d/mira.local
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" # .../deploy

# Minimums (hard stop) and recommendations (warning) — 40-agent pilot sizing.
MIN_CPUS=2 REC_CPUS=4
MIN_MEM_MB=3800 REC_MEM_MB=7600 # 4 GB / 8 GB as reported by the kernel (a bit under nominal)
MIN_DISK_GB=20 REC_DISK_GB=60

ALLOW_LOW=0
SSH_PORTS=""
PUBLIC_IP=""
SIP_DOMAIN=""
ADMIN_EMAIL=""
COMPANY="Mira"
LANGUAGE="ar"

# --- helpers -----------------------------------------------------------------------------------
say() { printf '\n==> %s\n' "$*"; }
ok() { printf '    ok: %s\n' "$*"; }
warn() { printf '    WARNING: %s\n' "$*" >&2; }
die() {
	printf '\nERROR: %s\n' "$*" >&2
	exit 1
}
trap 'die "line $LINENO: \"$BASH_COMMAND\" failed — see $LOG_FILE"' ERR

usage() {
	sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
	exit 0
}

while [ $# -gt 0 ]; do
	case "$1" in
	--allow-low-resources) ALLOW_LOW=1 ;;
	--ssh-port)
		[ $# -ge 2 ] || die "--ssh-port needs a port number"
		SSH_PORTS="$2"
		shift
		;;
	--public-ip)
		[ $# -ge 2 ] || die "--public-ip needs an IPv4 address"
		printf '%s' "$2" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || die "--public-ip: not an IPv4 address"
		PUBLIC_IP="$2"
		shift
		;;
	--domain)
		[ $# -ge 2 ] || die "--domain needs a name"
		printf '%s' "$2" | grep -Eq '^[A-Za-z0-9.-]+$' || die "--domain: letters, digits, dots and dashes only"
		SIP_DOMAIN="$2"
		shift
		;;
	--admin-email)
		[ $# -ge 2 ] || die "--admin-email needs an address"
		ADMIN_EMAIL="$2"
		shift
		;;
	--company)
		[ $# -ge 2 ] || die "--company needs a name"
		COMPANY="$2"
		shift
		;;
	--language)
		[ $# -ge 2 ] || die "--language needs ar, en or fr"
		case "$2" in ar | en | fr) LANGUAGE="$2" ;; *) die "--language: ar, en or fr" ;; esac
		shift
		;;
	-h | --help) usage ;;
	*) die "unknown option: $1 (try --help)" ;;
	esac
	shift
done

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -q -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold -o DPkg::Lock::Timeout=300)

# apt output goes to the log only, so the screen shows the summary lines.
# A fresh Ubuntu server often runs its automatic updates right after boot: wait for apt's
# locks (up to 5 minutes) instead of failing.
apt_log() {
	local try
	for try in $(seq 1 30); do
		if apt-get -o DPkg::Lock::Timeout=300 "$@" >>"$LOG_FILE" 2>&1; then
			return 0
		fi
		tail -n 5 "$LOG_FILE" | grep -qE "Could not get lock|Unable to lock" || return 1
		[ "$try" -eq 1 ] && echo "    waiting for another apt process (automatic updates) to finish..."
		sleep 10
	done
	return 1
}

# --- 1. checks ---------------------------------------------------------------------------------
check_root() {
	[ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"
}

check_os() {
	say "Checking operating system"
	local want="Ubuntu Server ${SUPPORTED_UBUNTU// / or } LTS"
	[ -r /etc/os-release ] || die "/etc/os-release not found — Mira needs $want"
	# shellcheck disable=SC1091
	. /etc/os-release
	[ "${ID:-}" = "ubuntu" ] || die "this is '${ID:-unknown}', Mira needs $want"
	case " $SUPPORTED_UBUNTU " in
	*" ${VERSION_ID:-?} "*) ;;
	*) die "this is Ubuntu ${VERSION_ID:-?}, Mira needs $want" ;;
	esac
	[ "$(uname -m)" = "x86_64" ] || die "architecture $(uname -m) is not supported (x86_64 only)"
	[ -d /run/systemd/system ] || die "systemd is not running — Mira runs as a systemd service"
	ok "Ubuntu $VERSION_ID ($VERSION_CODENAME), $(uname -m), systemd"
}

check_resources() {
	say "Checking resources"
	local cpus mem_mb disk_gb short=0
	cpus=$(nproc)
	mem_mb=$(awk '/^MemTotal:/ {print int($2/1024)}' /proc/meminfo)
	disk_gb=$(df -P -BG / | awk 'NR==2 {gsub("G","",$4); print $4}')

	check_one() { # name have min rec unit
		if [ "$2" -lt "$3" ]; then
			warn "$1: $2 $5 — below the minimum of $3 $5"
			short=1
		elif [ "$2" -lt "$4" ]; then
			warn "$1: $2 $5 — works for a lab; $4 $5 recommended for a 40-agent pilot"
		else ok "$1: $2 $5"; fi
	}
	check_one "CPU cores" "$cpus" "$MIN_CPUS" "$REC_CPUS" "cores"
	check_one "Memory" "$mem_mb" "$MIN_MEM_MB" "$REC_MEM_MB" "MB"
	check_one "Free disk on /" "$disk_gb" "$MIN_DISK_GB" "$REC_DISK_GB" "GB"

	if [ "$short" -eq 1 ]; then
		[ "$ALLOW_LOW" -eq 1 ] || die "not enough resources (re-run with --allow-low-resources to install anyway, labs only)"
		warn "continuing because --allow-low-resources was given"
	fi
}

# --- 1b. ports ---------------------------------------------------------------------------------
# Mira's services bind these ports on the host (host networking). Another program on one of
# them (e.g. an ERPNext site with its own nginx, Redis and PostgreSQL) would leave Mira half
# started, so stop before changing anything. Mira's own containers are fine (re-runs).
MIRA_TCP_PORTS="80 443 3478 5060 5061 5432 6379 8000 8088 8089 8095"
MIRA_UDP_PORTS="3478 5060"

port_owner() { # PROTO PORT -> "name (pid N)" of listeners that are not in a container
	local flag=-tlnpH u name pid
	[ "$1" = udp ] && flag=-ulnpH
	ss "$flag" "sport = :$2" 2>/dev/null | grep -oE '"[^"]+",pid=[0-9]+' | sort -u |
		while IFS= read -r u; do
			name=${u%%,pid=*}
			pid=${u##*pid=}
			grep -qE 'docker|containerd' "/proc/$pid/cgroup" 2>/dev/null && continue
			printf '%s (pid %s) ' "${name//\"/}" "$pid"
		done
}

check_ports() {
	say "Checking that Mira's ports are free"
	local p who busy=""
	for p in $MIRA_TCP_PORTS; do
		who=$(port_owner tcp "$p")
		[ -z "$who" ] || busy="$busy      tcp $p: $who"$'\n'
	done
	for p in $MIRA_UDP_PORTS; do
		who=$(port_owner udp "$p")
		[ -z "$who" ] || busy="$busy      udp $p: $who"$'\n'
	done
	if [ -n "$busy" ]; then
		printf '    in use by other programs:\n%s' "$busy" >&2
		die "Mira needs these ports itself: install it on its own server or VM, not next to another web or database server"
	fi
	ok "tcp ${MIRA_TCP_PORTS// /,} and udp ${MIRA_UDP_PORTS// /,} free (or already Mira's)"
}

# --- 2. base packages --------------------------------------------------------------------------
install_base_packages() {
	say "Installing base packages"
	apt_log update -q
	apt_log install "${APT_OPTS[@]}" ca-certificates curl openssl ufw fail2ban python3-systemd
	ok "ca-certificates curl openssl ufw fail2ban python3-systemd"
}

# --- 3. Docker Engine + Compose plugin (docs.docker.com/engine/install/ubuntu) -----------------
install_docker() {
	say "Installing Docker Engine and the Compose plugin from Docker's repository"
	local keyring=/etc/apt/keyrings/docker.asc sources=/etc/apt/sources.list.d/docker.sources

	# Remove Ubuntu's unofficial Docker packages if present (they conflict with docker-ce).
	local conflicts=() p
	for p in docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc; do
		if dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed"; then
			conflicts+=("$p")
		fi
	done
	if [ ${#conflicts[@]} -gt 0 ]; then
		warn "removing conflicting packages: ${conflicts[*]}"
		apt_log remove "${APT_OPTS[@]}" "${conflicts[@]}"
	fi

	if [ ! -s "$keyring" ]; then
		install -m 0755 -d /etc/apt/keyrings
		curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$keyring"
		chmod a+r "$keyring"
	fi
	local codename
	# shellcheck disable=SC1091
	codename=$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
	local want
	want="Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $codename
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: $keyring"
	if [ ! -f "$sources" ] || [ "$(cat "$sources")" != "$want" ]; then
		printf '%s\n' "$want" >"$sources"
		apt_log update -q
	fi

	apt_log install "${APT_OPTS[@]}" docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
	systemctl enable --now docker >/dev/null 2>&1
	docker info >/dev/null 2>&1 || die "Docker is installed but not running (journalctl -u docker)"
	ok "$(docker --version)"
	ok "$(docker compose version)"
}

# --- 4. /opt/mira ------------------------------------------------------------------------------
create_layout() {
	say "Creating $MIRA_DIR"
	install -d -m 0750 -o root -g root "$MIRA_DIR"
	local d
	for d in data recordings logs config backups config/asterisk config/tls; do
		install -d -m 0750 -o root -g root "$MIRA_DIR/$d"
	done
	if [ -f "$SRC_DIR/docker-compose.yml" ]; then
		install -m 0644 "$SRC_DIR/docker-compose.yml" "$MIRA_DIR/docker-compose.yml"
		ok "docker-compose.yml installed"
	else
		warn "no deploy/docker-compose.yml yet (comes in task 0.3) — the service will start once it exists"
	fi
	ok "$MIRA_DIR/{data,recordings,logs,config,backups}"
}

# --- 5. secrets --------------------------------------------------------------------------------
gen_hex() { openssl rand -hex "$1"; } # hex: safe in .env, URLs and config files

ensure_secret() { # KEY BYTES — add only if missing
	if grep -q "^$1=" "$ENV_FILE"; then
		ok "$1 (kept)"
	else
		printf '%s=%s\n' "$1" "$(gen_hex "$2")" >>"$ENV_FILE"
		ok "$1 (generated)"
	fi
}

ensure_value() { # KEY VALUE — add only if missing
	grep -q "^$1=" "$ENV_FILE" || printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"
}

set_value() { # KEY VALUE — add or replace (used for values given on the command line)
	if grep -q "^$1=" "$ENV_FILE"; then
		sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
	else
		printf '%s=%s\n' "$1" "$2" >>"$ENV_FILE"
	fi
}

env_get() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -1; }

generate_secrets() {
	say "Generating secrets in $ENV_FILE"
	if [ ! -f "$ENV_FILE" ]; then
		(
			umask 077
			cat >"$ENV_FILE" <<-EOF
				# Mira Voice secrets — generated by install.sh on $(date -u +%Y-%m-%dT%H:%MZ).
				# Readable by root only. Never commit, e-mail or paste this file.
				# Back it up with the data: without it the database and recordings cannot be opened.
			EOF
		)
	fi
	chown root:root "$ENV_FILE"
	chmod 600 "$ENV_FILE"

	ensure_value COMPOSE_PROJECT_NAME mira
	ensure_value POSTGRES_USER mira
	ensure_value POSTGRES_DB mira
	ensure_secret POSTGRES_PASSWORD 24
	ensure_secret REDIS_PASSWORD 24
	ensure_value MINIO_ROOT_USER mira-admin
	ensure_secret MINIO_ROOT_PASSWORD 24
	ensure_value ARI_USER mira-core
	ensure_secret ARI_PASSWORD 24
	ensure_secret ASTERISK_DB_PASSWORD 24
	ensure_secret TURN_SECRET 32
	ensure_secret MIRA_JWT_SECRET 32
	ensure_secret MIRA_WEBHOOK_SECRET 32
	ensure_secret KAMAILIO_RPC_TOKEN 32
	# Fernet key (32 random bytes, URL-safe base64) that encrypts carrier passwords at rest.
	# Kept on upgrades: a new key would make the stored passwords unreadable.
	if grep -q "^MIRA_DATA_KEY=" "$ENV_FILE"; then
		ok "MIRA_DATA_KEY (kept)"
	else
		printf 'MIRA_DATA_KEY=%s\n' "$(openssl rand -base64 32 | tr '+/' '-_')" >>"$ENV_FILE"
		ok "MIRA_DATA_KEY (generated)"
	fi
}

# --- 5b. network addresses and TLS certificate -------------------------------------------------
is_ipv4() { printf '%s' "$1" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$'; }

configure_network() {
	say "Network addresses"
	local detected
	detected=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") {print $(i + 1); exit}}')
	[ -n "$detected" ] || die "could not detect this server's IPv4 address (no default route?)"

	ensure_value MIRA_LOCAL_IP "$detected"
	[ "$(env_get MIRA_LOCAL_IP)" = "$detected" ] ||
		warn "MIRA_LOCAL_IP in $ENV_FILE is $(env_get MIRA_LOCAL_IP) but this server now has $detected — edit $ENV_FILE if the address changed"
	ensure_value MIRA_PUBLIC_IP "$(env_get MIRA_LOCAL_IP)"
	[ -z "$PUBLIC_IP" ] || set_value MIRA_PUBLIC_IP "$PUBLIC_IP"
	ensure_value MIRA_SIP_DOMAIN "$(env_get MIRA_PUBLIC_IP)"
	[ -z "$SIP_DOMAIN" ] || set_value MIRA_SIP_DOMAIN "$SIP_DOMAIN"

	is_ipv4 "$(env_get MIRA_LOCAL_IP)" || die "MIRA_LOCAL_IP is not an IPv4 address"
	is_ipv4 "$(env_get MIRA_PUBLIC_IP)" || die "MIRA_PUBLIC_IP is not an IPv4 address (use --public-ip)"
	ok "local $(env_get MIRA_LOCAL_IP), public $(env_get MIRA_PUBLIC_IP), SIP domain $(env_get MIRA_SIP_DOMAIN)"
	if [ "$(env_get MIRA_LOCAL_IP)" = "$(env_get MIRA_PUBLIC_IP)" ]; then
		ok "if this server is behind NAT, re-run with --public-ip <public IP> and forward the ufw ports"
	fi
}

create_tls_cert() {
	say "TLS certificate for SIP-TLS (5061) and WSS (8089)"
	local dir="$MIRA_DIR/config/tls" domain san
	domain=$(env_get MIRA_SIP_DOMAIN)
	if [ -s "$dir/mira.crt" ] && [ -s "$dir/mira.key" ]; then
		ok "kept $dir/mira.crt (expires $(openssl x509 -in "$dir/mira.crt" -noout -enddate | cut -d= -f2))"
		return
	fi
	san="IP:$(env_get MIRA_LOCAL_IP),IP:$(env_get MIRA_PUBLIC_IP)"
	is_ipv4 "$domain" || san="DNS:$domain,$san"
	(
		umask 077
		openssl req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes \
			-subj "/O=Mira Voice/CN=$domain" -addext "subjectAltName=$san" \
			-keyout "$dir/mira.key" -out "$dir/mira.crt" 2>>"$LOG_FILE"
	)
	chmod 600 "$dir/mira.key" "$dir/mira.crt"
	ok "self-signed certificate for $domain ($san), valid 825 days — replace with a real one in task 2.6"
}

# --- 5c. container images ----------------------------------------------------------------------
build_images() {
	say "Building Mira images (first run compiles Asterisk: 10-20 minutes)"
	local compose=(docker compose --env-file "$ENV_FILE" -f "$SRC_DIR/docker-compose.yml" -f "$SRC_DIR/docker-compose.build.yml")
	if ! "${compose[@]}" build >>"$LOG_FILE" 2>&1; then
		die "image build failed — see the end of $LOG_FILE"
	fi
	local img
	for img in $("${compose[@]}" config --images | sort -u); do
		ok "$img"
	done
}

# --- 6. firewall (ufw) -------------------------------------------------------------------------
detect_ssh_ports() {
	if [ -z "$SSH_PORTS" ]; then
		SSH_PORTS=$(sshd -T 2>/dev/null | awk '$1=="port" {print $2}' | sort -u | tr '\n' ' ' || true)
	fi
	# Always keep 22 open as well so a wrong guess can never lock the admin out.
	SSH_PORTS=$(printf '%s 22' "$SSH_PORTS" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -un | tr '\n' ' ')
}

ufw_rule() { # ufw arguments… — ufw itself skips rules that already exist
	ufw "$@" >/dev/null
}

configure_firewall() {
	say "Configuring the firewall (ufw)"
	detect_ssh_ports
	local p
	for p in $SSH_PORTS; do
		ufw_rule limit "$p/tcp" comment 'mira: ssh (rate limited)'
	done
	ufw_rule default deny incoming
	ufw_rule default allow outgoing
	ufw_rule allow 80/tcp comment 'mira: http (certbot, redirect to https)'
	ufw_rule allow 443/tcp comment 'mira: https (Mira Desk, API)'
	ufw_rule allow 5060/udp comment 'mira: sip udp'
	ufw_rule allow 5060/tcp comment 'mira: sip tcp'
	ufw_rule allow 5061/tcp comment 'mira: sip tls'
	ufw_rule allow 8089/tcp comment 'mira: sip over wss (webrtc)'
	ufw_rule allow 10000:20000/udp comment 'mira: rtp media'
	ufw_rule allow 3478/udp comment 'mira: turn/stun udp'
	ufw_rule allow 3478/tcp comment 'mira: turn/stun tcp'
	ufw --force enable >/dev/null
	ok "ufw active; ssh on ${SSH_PORTS% }; sip 5060/5061, wss 8089, rtp 10000-20000/udp, turn 3478, web 80/443"
}

# --- 7. fail2ban -------------------------------------------------------------------------------
configure_fail2ban() {
	say "Configuring fail2ban"
	local ports
	ports=$(echo "$SSH_PORTS" | xargs | tr ' ' ',')
	local want
	want="# Managed by Mira Voice install.sh — changes here are overwritten on the next install.
[DEFAULT]
banaction = ufw
banaction_allports = ufw
bantime = 1h
bantime.increment = true
findtime = 10m
maxretry = 5
ignoreip = 127.0.0.1/8 ::1

[sshd]
enabled = true
port = $ports
backend = systemd"
	if [ ! -f "$JAIL_FILE" ] || [ "$(cat "$JAIL_FILE")" != "$want" ]; then
		printf '%s\n' "$want" >"$JAIL_FILE"
		chmod 644 "$JAIL_FILE"
	fi
	fail2ban-client -t >>"$LOG_FILE" 2>&1 || die "fail2ban configuration test failed (fail2ban-client -t)"
	systemctl enable fail2ban >/dev/null 2>&1
	systemctl restart fail2ban
	for _ in $(seq 1 10); do
		fail2ban-client ping >/dev/null 2>&1 && break
		sleep 1
	done
	fail2ban-client status sshd >/dev/null 2>&1 || die "fail2ban sshd jail is not running (journalctl -u fail2ban)"
	ok "fail2ban active, sshd jail on port(s) $ports (5 failures in 10 min → ban 1 h, growing)"
}

# --- 8. systemd unit ---------------------------------------------------------------------------
install_service() {
	say "Installing the mira systemd service"
	install -m 0644 "$SRC_DIR/systemd/mira.service" "$UNIT_FILE"
	systemctl daemon-reload
	systemctl enable mira.service >/dev/null 2>&1
	if [ -f "$MIRA_DIR/docker-compose.yml" ]; then
		systemctl restart mira.service
		ok "mira.service enabled and started"
	else
		ok "mira.service enabled (starts automatically once docker-compose.yml is installed)"
	fi
}

# --- 9. first sign-in: the first tenant and its platform admin ---------------------------------
compose_exec() { (cd "$MIRA_DIR" && docker compose --env-file "$ENV_FILE" exec -T "$@"); }

admin_count() {
	local sql="SELECT count(*) FROM users WHERE role = 'platform_admin'"
	# shellcheck disable=SC2016 # $POSTGRES_* expand inside the postgres container
	compose_exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "$1"' sh "$sql" 2>/dev/null | tr -dc '0-9'
}

create_first_admin() {
	say "First sign-in"
	local count
	count=$(admin_count)
	[ -n "$count" ] || die "could not read the user list from PostgreSQL (cd $MIRA_DIR && docker compose ps)"
	if [ "$count" -gt 0 ]; then
		ok "a platform admin already exists (more: docker compose exec core mira-core create-admin)"
		return
	fi
	if [ -z "$ADMIN_EMAIL" ] && { : </dev/tty; } 2>/dev/null; then
		printf '    E-mail address of the first administrator: ' >/dev/tty
		read -r ADMIN_EMAIL </dev/tty || true
	fi
	if [ -z "$ADMIN_EMAIL" ]; then
		warn "no administrator yet: run the installer again with --admin-email you@example.com"
		return
	fi
	local out password url
	if ! out=$(compose_exec core mira-core bootstrap --email "$ADMIN_EMAIL" --company "$COMPANY" --language "$LANGUAGE" 2>&1); then
		die "could not create the administrator: $(printf '%s' "$out" | tail -1)"
	fi
	password=$(printf '%s\n' "$out" | sed -n 's/^Password.*: //p')
	[ -n "$password" ] || die "the administrator was not created: $(printf '%s' "$out" | tail -1)"
	url="https://$(env_get MIRA_SIP_DOMAIN)/"
	(
		umask 077
		printf 'Mira Desk:  %s\nE-mail:     %s\nPassword:   %s\n\nSign in, then delete this file: sudo rm %s\n' \
			"$url" "$ADMIN_EMAIL" "$password" "$FIRST_LOGIN_FILE" >"$FIRST_LOGIN_FILE"
	)
	ok "tenant \"$COMPANY\" and platform admin $ADMIN_EMAIL created"
	# the password goes to the screen and a root-only file, never into the install log
	if { : >/dev/tty; } 2>/dev/null; then
		printf '\n    Password (shown once): %s\n\n' "$password" >/dev/tty
	fi
	ok "sign-in details in $FIRST_LOGIN_FILE (root only): delete it after the first sign-in"
}

# --- main --------------------------------------------------------------------------------------
main() {
	check_root
	touch "$LOG_FILE" && chmod 600 "$LOG_FILE"
	exec > >(tee -a "$LOG_FILE") 2>&1
	printf '\n===== Mira Voice install %s =====\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

	check_os
	check_resources
	check_ports
	install_base_packages
	install_docker
	create_layout
	generate_secrets
	configure_network
	create_tls_cert
	configure_firewall
	configure_fail2ban
	build_images
	install_service
	create_first_admin

	say "Mira Voice is installed"
	cat <<-EOF
		    Mira Desk: https://$(env_get MIRA_SIP_DOMAIN)/   (self-signed certificate: the browser warns once)
		    Folder:    $MIRA_DIR   (secrets in $ENV_FILE, root only)
		    Service:   systemctl status mira
		    Firewall:  ufw status verbose
		    fail2ban:  fail2ban-client status sshd
		    Log:       $LOG_FILE
	EOF
}

main "$@"
