#!/bin/sh
# Mira Voice — Asterisk container entrypoint.
# Renders the templated configs from environment variables, copies the host-provided
# configs (written by deploy scripts) into place, then runs Asterisk in the foreground as
# the unprivileged "asterisk" user. PJSIP extensions come from PostgreSQL (realtime, read-only
# views); the generated dialplan is a shared volume written by Mira Core (task 1.1).
set -eu

: "${ARI_USER:?ARI_USER is not set}"
: "${ARI_PASSWORD:?ARI_PASSWORD is not set}"
: "${POSTGRES_DB:?POSTGRES_DB is not set}"
: "${ASTERISK_DB_PASSWORD:?ASTERISK_DB_PASSWORD is not set}"

# shellcheck disable=SC2016 # envsubst takes the literal variable names as its list
VARS='${ARI_USER} ${ARI_PASSWORD} ${POSTGRES_DB} ${ASTERISK_DB_PASSWORD}'

umask 027

# 1. Templates: only the listed variables are substituted (dialplan ${EXTEN} etc. stay intact).
for tmpl in /etc/asterisk/templates/*.tmpl; do
	[ -e "$tmpl" ] || continue
	out="/etc/asterisk/$(basename "$tmpl" .tmpl)"
	envsubst "$VARS" <"$tmpl" >"$out"
	chown root:asterisk "$out"
	chmod 0640 "$out"
done

# ODBC data source for realtime: PostgreSQL on 127.0.0.1, read-only role "asterisk".
envsubst "$VARS" </etc/asterisk/templates/odbc.ini.src >/etc/odbc.ini
chown root:asterisk /etc/odbc.ini
chmod 0640 /etc/odbc.ini

# 2. Host-provided configs (/opt/mira/config/asterisk on the host), read-only mount.
if [ -d /run/mira-config/asterisk ]; then
	find /etc/asterisk/mira -mindepth 1 -delete
	for f in /run/mira-config/asterisk/*.conf; do
		[ -e "$f" ] || continue
		install -m 0640 -o root -g asterisk "$f" /etc/asterisk/mira/
	done
fi

mkdir -p /var/run/asterisk /var/lib/asterisk/astdb
chown asterisk:asterisk /var/run/asterisk /var/lib/asterisk/astdb
# voicemail recordings (ARI, task 1.4): a fresh volume starts root-owned
mkdir -p /var/spool/asterisk/recording
chown asterisk:asterisk /var/spool/asterisk/recording
chmod 0750 /var/spool/asterisk/recording

exec /usr/sbin/asterisk -f -U asterisk -G asterisk -vvv
