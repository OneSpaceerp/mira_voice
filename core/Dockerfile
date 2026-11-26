# syntax=docker/dockerfile:1
# Mira Core image. Pattern from docs.astral.sh/uv/guides/integration/docker (cached dependency
# layer, non-editable install, runtime image without build tools, non-root user).
# Build:  docker build -t mira/core:0.1.0 core

ARG PYTHON_IMAGE=python:3.12.16-slim-trixie

FROM ${PYTHON_IMAGE} AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src
# 1. dependencies only (changes rarely -> cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
	--mount=type=bind,source=uv.lock,target=uv.lock \
	--mount=type=bind,source=pyproject.toml,target=pyproject.toml \
	uv sync --locked --no-install-project --no-dev
# 2. the project itself, installed as a normal (non-editable) package
COPY . /src
RUN --mount=type=cache,target=/root/.cache/uv \
	uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.title="mira-core" \
	org.opencontainers.image.version="0.1.0" \
	org.opencontainers.image.vendor="Nest Software Development"
RUN groupadd --system mira \
	&& useradd --system --gid mira --home-dir /app --shell /usr/sbin/nologin mira \
	# gid 2701 is shared with the Asterisk image: the generated trunk file holds carrier
	# passwords, so it is 0640 mira:mira-config and Asterisk reads it through this group.
	&& groupadd --gid 2701 mira-config \
	&& usermod -aG mira-config mira \
	# generated config: shared volumes; Docker copies this ownership into a new volume
	&& install -d -m 2750 -o mira -g mira-config /var/lib/mira/asterisk \
	# prompt recordings (task 1.4): Asterisk reads them as sounds/mira/ through the same group
	&& install -d -m 2750 -o mira -g mira-config /var/lib/mira/prompts \
	&& install -d -m 0755 -o mira -g mira /var/lib/mira/kamailio
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
USER mira

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
	CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).status != 200)"]

# Loopback only: the public entry point (443) will be a reverse proxy (task 2.1/2.6).
CMD ["uvicorn", "mira_core.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-server-header"]
