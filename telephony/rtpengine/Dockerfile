# syntax=docker/dockerfile:1
# Mira Voice — RTPengine media relay (userspace forwarding), LTS series from rtpengine.dfx.at,
# the package repository named in the rtpengine docs.
# Build:  docker build -t mira/rtpengine:26.0 telephony/rtpengine

FROM debian:trixie-slim
ARG RTPENGINE_SERIES=26.0
ARG RTPENGINE_VERSION=26.0.1.29-1~bpo13+1
# Keyring package and its SHA256 as published on https://dfx.at/rtpengine/
ARG DFX_KEYRING_URL=https://rtpengine.dfx.at/latest/pool/main/r/rtpengine-dfx-repo-keyring/rtpengine-dfx-repo-keyring_1.0_all.deb
ARG DFX_KEYRING_SHA256=78fe26f0251138f4e3c749c88dc4df29666c8efe0823858d3a4ab49d2fa2e088
LABEL org.opencontainers.image.title="mira-rtpengine" \
	org.opencontainers.image.version="${RTPENGINE_VERSION}" \
	org.opencontainers.image.vendor="Nest Software Development"

RUN set -e; \
	apt-get update; \
	apt-get install -y --no-install-recommends ca-certificates curl; \
	curl -fsSLo /tmp/keyring.deb "$DFX_KEYRING_URL"; \
	echo "${DFX_KEYRING_SHA256}  /tmp/keyring.deb" | sha256sum -c -; \
	dpkg -i /tmp/keyring.deb; rm /tmp/keyring.deb; \
	echo "deb [signed-by=/usr/share/keyrings/dfx.at-rtpengine-archive-keyring.gpg] https://rtpengine.dfx.at/${RTPENGINE_SERIES} trixie main" \
		>/etc/apt/sources.list.d/rtpengine.list; \
	apt-get update; \
	apt-get install -y --no-install-recommends rtpengine-daemon="${RTPENGINE_VERSION}" rtpengine-utils gettext-base; \
	rm -rf /var/lib/apt/lists/*; \
	rtpengine --version

COPY rtpengine.conf.tmpl /etc/rtpengine/rtpengine.conf.tmpl
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
	CMD rtpengine-ctl -ip 127.0.0.1:9900 list numsessions >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
