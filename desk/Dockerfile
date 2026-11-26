# Mira Desk web image (ADR 0012): builds the Vue app, then serves it with nginx, which also
# forwards /api to Mira Core. Built by deploy/install.sh; the server itself needs no Node.
#   docker build -t mira/web:0.1.0 desk/

# ---- build: type-check and bundle (versions pinned in package-lock.json) ----
FROM node:24.22.3-trixie-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error
COPY . .
RUN npm run build

# ---- serve: nginx stable ----
FROM nginx:1.30.8-trixie
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/mira.conf /etc/nginx/conf.d/default.conf
# the entrypoint's IPv6 helper edits default.conf; ours already listens on both
ENV NGINX_ENTRYPOINT_QUIET_LOGS=1
