# syntax=docker/dockerfile:1
# Mira Voice — Asterisk 22 LTS, compiled from source, PJSIP only, ARI enabled.
# Build:  docker build -t mira/asterisk:22.12.0 telephony/asterisk

ARG DEBIAN_RELEASE=trixie

# ---------- build stage ----------
FROM debian:${DEBIAN_RELEASE}-slim AS build
ARG ASTERISK_VERSION=22.12.0
# From downloads.asterisk.org/pub/telephony/asterisk/releases/asterisk-22.12.0.sha256
ARG ASTERISK_SHA256=f8b2ba98aac6c4ff3376bc0a2868bea6ed577ca684efb7ec739ae6e8ce6e35e2

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		ca-certificates curl bzip2 patch build-essential pkg-config \
		libedit-dev libjansson-dev libxml2-dev uuid-dev libsqlite3-dev \
		libssl-dev libsrtp2-dev libcurl4-openssl-dev xmlstarlet \
		unixodbc-dev \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/asterisk
RUN curl -fsSLo /tmp/asterisk.tar.gz \
		"https://downloads.asterisk.org/pub/telephony/asterisk/releases/asterisk-${ASTERISK_VERSION}.tar.gz" \
	&& echo "${ASTERISK_SHA256}  /tmp/asterisk.tar.gz" | sha256sum -c - \
	&& tar -xzf /tmp/asterisk.tar.gz --strip-components=1 \
	&& rm /tmp/asterisk.tar.gz

# Bundled pjproject (Asterisk's tested PJSIP). chan_sip no longer exists in 22.
RUN ./configure --with-pjproject-bundled --prefix=/usr --sysconfdir=/etc --localstatedir=/var >/dev/null

# Portable build (no -march=native) + prompts: English and French, ulaw and G.722.
# Arabic has no official Asterisk prompt set; Mira ships its own later (IVR prompts task).
RUN make menuselect.makeopts \
	&& menuselect/menuselect \
		--disable BUILD_NATIVE \
		--disable CORE-SOUNDS-EN-GSM \
		--enable CORE-SOUNDS-EN-ULAW --enable CORE-SOUNDS-EN-G722 \
		--enable CORE-SOUNDS-FR-ULAW --enable CORE-SOUNDS-FR-G722 \
		--disable MOH-OPSOUND-WAV --enable MOH-OPSOUND-ULAW --enable MOH-OPSOUND-G722 \
		--disable chan_iax2 --disable chan_unistim \
		menuselect.makeopts

# Parallel build; the bundled pjproject occasionally races under -j, so retry once serially
# and, if that fails too, show the real compiler errors instead of a bare "Error 2".
RUN (make -j"$(nproc)" >/tmp/make.log 2>&1 \
		|| { echo "parallel build failed, retrying serially"; make >>/tmp/make.log 2>&1; } \
		|| { grep -nE "error:|Error [0-9]|cannot find|No such file" /tmp/make.log | head -40; exit 1; }) \
	&& make install DESTDIR=/out >/dev/null \
	# Debian's /var/run is a symlink to /run: move Asterisk's run dir so COPY does not clash
	&& mkdir -p /out/run && mv /out/var/run/asterisk /out/run/asterisk && rm -rf /out/var/run

# Work out which Debian packages the runtime image needs from the real binaries.
RUN set -e; \
	find /out -type f \( -name '*.so*' -o -path '*/sbin/*' \) -exec ldd {} + 2>/dev/null \
		| awk '$2 == "=>" && $3 ~ /^\// {print $3}' | sort -u \
		| while read -r lib; do \
			real=$(readlink -f "$lib"); \
			dpkg-query -S "$real" 2>/dev/null || dpkg-query -S "/usr$real" 2>/dev/null || dpkg-query -S "${real#/usr}" 2>/dev/null || true; \
		done | cut -d: -f1 | sort -u > /out/runtime-packages.txt; \
	cat /out/runtime-packages.txt

# ---------- runtime stage ----------
FROM debian:${DEBIAN_RELEASE}-slim
ARG ASTERISK_VERSION=22.12.0
LABEL org.opencontainers.image.title="mira-asterisk" \
	org.opencontainers.image.version="${ASTERISK_VERSION}" \
	org.opencontainers.image.vendor="Nest Software Development"

COPY --from=build /out/runtime-packages.txt /tmp/runtime-packages.txt
RUN apt-get update \
	&& xargs -a /tmp/runtime-packages.txt apt-get install -y --no-install-recommends \
	&& apt-get install -y --no-install-recommends ca-certificates gettext-base odbc-postgresql \
	&& rm -rf /var/lib/apt/lists/* /tmp/runtime-packages.txt \
	&& groupadd --system asterisk \
	&& useradd --system --gid asterisk --home-dir /var/lib/asterisk --shell /usr/sbin/nologin asterisk \
	# Shared with Mira Core (same gid there): lets Asterisk read the generated trunk file
	# (0640, carrier passwords) without making it world-readable.
	&& groupadd --gid 2701 mira-config \
	&& usermod -aG mira-config asterisk

COPY --from=build /out/ /
RUN rm -f /runtime-packages.txt && ldconfig \
	&& rm -rf /etc/asterisk && mkdir -p /etc/asterisk/mira \
	&& chown -R asterisk:asterisk /var/lib/asterisk /var/spool/asterisk /var/log/asterisk /var/run/asterisk

COPY config/ /etc/asterisk/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
# Realtime (PJSIP objects from PostgreSQL over ODBC): fail the build if the pieces are missing.
RUN chmod 0755 /usr/local/bin/entrypoint.sh \
	&& asterisk -V \
	&& test -f /usr/lib/asterisk/modules/res_odbc.so \
	&& test -f /usr/lib/asterisk/modules/res_config_odbc.so \
	&& odbcinst -q -d | grep -q 'PostgreSQL Unicode'

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
	CMD asterisk -rx "core show uptime" >/dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
