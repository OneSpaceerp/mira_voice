# syntax=docker/dockerfile:1
# Mira Voice — coturn TURN/STUN (3478 UDP+TCP) on top of the official coturn image.
# Adds only an entrypoint that writes turnserver.conf from environment variables, so the
# TURN secret is never on the command line (visible to every user via `ps`).
# Build:  docker build -t mira/coturn:4.19.2 telephony/coturn
FROM coturn/coturn:4.19.2-trixie
LABEL org.opencontainers.image.title="mira-coturn" \
	org.opencontainers.image.version="4.19.2" \
	org.opencontainers.image.vendor="Nest Software Development"
COPY --chmod=0755 entrypoint.sh /usr/local/bin/mira-coturn-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/mira-coturn-entrypoint.sh"]
