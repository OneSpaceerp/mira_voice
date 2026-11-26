# syntax=docker/dockerfile:1
# Mira Voice — Kamailio 6.1 SIP edge (UDP/TCP 5060, TLS 5061, WSS 8089) from deb.kamailio.org.
# Build:  docker build -t mira/kamailio:6.1.6 telephony/kamailio

FROM debian:trixie-slim
ARG KAMAILIO_SERIES=61
# Tested version. deb.kamailio.org keeps only the newest release of a series: if this one
# has been replaced, the build takes the newest 6.1.x and says so (same series).
ARG KAMAILIO_VERSION=6.1.6+bpo13
# Kamailio Package Team signing key (deb.kamailio.org)
ARG KAMAILIO_KEY_FPR=E79ACECB87D8DCD23A20AD2FFB40D3E6508EA4C8
LABEL org.opencontainers.image.title="mira-kamailio" \
	org.opencontainers.image.version="${KAMAILIO_VERSION}" \
	org.opencontainers.image.vendor="Nest Software Development"

RUN set -e; \
	apt-get update; \
	apt-get install -y --no-install-recommends ca-certificates curl gpg; \
	curl -fsSL https://deb.kamailio.org/kamailiodebkey.gpg | gpg --dearmor -o /usr/share/keyrings/kamailio.gpg; \
	fpr=$(gpg --show-keys --with-colons /usr/share/keyrings/kamailio.gpg | awk -F: '$1=="fpr"{print $10; exit}'); \
	[ "$fpr" = "$KAMAILIO_KEY_FPR" ] || { echo "Kamailio key fingerprint mismatch: $fpr"; exit 1; }; \
	echo "deb [signed-by=/usr/share/keyrings/kamailio.gpg] https://deb.kamailio.org/kamailio${KAMAILIO_SERIES} trixie main" \
		>/etc/apt/sources.list.d/kamailio.list; \
	apt-get update; \
	pin="=${KAMAILIO_VERSION}"; \
	if ! apt-cache madison kamailio | awk '{print $3}' | grep -qxF "${KAMAILIO_VERSION}"; then \
		echo "NOTE: kamailio ${KAMAILIO_VERSION} is no longer published; installing the newest ${KAMAILIO_SERIES} release"; \
		pin=""; \
	fi; \
	apt-get install -y --no-install-recommends \
		"kamailio${pin}" \
		"kamailio-tls-modules${pin}" \
		"kamailio-websocket-modules${pin}" \
		"kamailio-extra-modules${pin}" \
		gettext-base; \
	apt-get purge -y gpg; apt-get autoremove -y; \
	rm -rf /var/lib/apt/lists/*; \
	kamailio -v | head -1

COPY kamailio.cfg.tmpl tls.cfg dispatcher.list /etc/kamailio/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
	CMD kamcmd -s unix:/run/kamailio/kamailio_ctl core.uptime >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
