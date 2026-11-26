#!/bin/sh
# Mira Voice — coturn entrypoint. TURN credentials are time-limited HMACs of TURN_SECRET
# (TURN REST API), issued by Mira Core to logged-in agents; there are no static TURN users.
set -eu
: "${MIRA_LOCAL_IP:?MIRA_LOCAL_IP is not set}"
: "${MIRA_PUBLIC_IP:?MIRA_PUBLIC_IP is not set}"
: "${MIRA_SIP_DOMAIN:?MIRA_SIP_DOMAIN is not set}"
: "${TURN_SECRET:?TURN_SECRET is not set}"

conf=$(mktemp -d)/turnserver.conf
umask 077
cat >"$conf" <<CONF
listening-ip=${MIRA_LOCAL_IP}
relay-ip=${MIRA_LOCAL_IP}
external-ip=${MIRA_PUBLIC_IP}/${MIRA_LOCAL_IP}
listening-port=3478
min-port=15000
max-port=19999
realm=${MIRA_SIP_DOMAIN}
use-auth-secret
static-auth-secret=${TURN_SECRET}
fingerprint
no-tls
no-dtls
no-multicast-peers
no-software-attribute
log-file=stdout
simple-log
# Relay only to Mira's own media server, never into private or loopback networks.
denied-peer-ip=0.0.0.0-0.255.255.255
denied-peer-ip=10.0.0.0-10.255.255.255
denied-peer-ip=100.64.0.0-100.127.255.255
denied-peer-ip=127.0.0.0-127.255.255.255
denied-peer-ip=169.254.0.0-169.254.255.255
denied-peer-ip=172.16.0.0-172.31.255.255
denied-peer-ip=192.168.0.0-192.168.255.255
denied-peer-ip=::1
allowed-peer-ip=${MIRA_LOCAL_IP}
CONF
exec turnserver -c "$conf"
