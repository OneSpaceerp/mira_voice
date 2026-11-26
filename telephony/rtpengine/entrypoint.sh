#!/bin/sh
# Mira Voice — RTPengine container entrypoint: render the config and run in the foreground.
set -eu
: "${MIRA_LOCAL_IP:?MIRA_LOCAL_IP is not set}"
: "${MIRA_PUBLIC_IP:?MIRA_PUBLIC_IP is not set}"
# shellcheck disable=SC2016 # envsubst takes the literal variable names as its list
envsubst '${MIRA_LOCAL_IP} ${MIRA_PUBLIC_IP}' \
	</etc/rtpengine/rtpengine.conf.tmpl >/etc/rtpengine/rtpengine.conf
exec rtpengine --config-file=/etc/rtpengine/rtpengine.conf --pidfile=none
