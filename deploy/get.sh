#!/usr/bin/env bash
# Mira Voice — download and install in one command (Ubuntu Server 24.04 or 26.04 LTS):
#
#   curl -fsSL https://raw.githubusercontent.com/OneSpaceerp/mira_voice/main/deploy/get.sh \
#     | sudo bash -s -- --admin-email you@example.com
#
# Downloads the code (MIRA_REF: a branch or tag, default main) over HTTPS from GitHub into
# /usr/local/src/mira-voice, then runs deploy/install.sh with the same options. Run it again
# to update: it replaces the code and re-runs the installer (data and secrets are kept).
set -Eeuo pipefail

REPO="${MIRA_REPO:-OneSpaceerp/mira_voice}"
REF="${MIRA_REF:-main}"
SRC=/usr/local/src/mira-voice

die() {
	printf '\nERROR: %s\n' "$*" >&2
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "run as root: curl -fsSL … | sudo bash -s -- [options]"
printf '%s' "$REF" | grep -Eq '^[A-Za-z0-9._/-]+$' || die "MIRA_REF: letters, digits, . _ / - only"
printf '%s' "$REPO" | grep -Eq '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$' || die "MIRA_REPO: owner/name"
command -v curl >/dev/null || die "curl is missing: sudo apt install curl"
command -v tar >/dev/null || die "tar is missing: sudo apt install tar"

# a tag (v0.2-mvp) or a branch (main)
url="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
case "$REF" in v[0-9]*) url="https://github.com/$REPO/archive/refs/tags/$REF.tar.gz" ;; esac

echo "==> Downloading Mira Voice ($REPO @ $REF)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$tmp/mira.tar.gz" "$url" ||
	die "download failed: $url"
mkdir -p "$tmp/src"
tar -xzf "$tmp/mira.tar.gz" -C "$tmp/src" --strip-components=1 ||
	die "the download is not a valid archive"
[ -x "$tmp/src/deploy/install.sh" ] || die "deploy/install.sh missing in the download"

rm -rf "$SRC"
mkdir -p "$(dirname "$SRC")"
mv "$tmp/src" "$SRC"
chmod 755 "$SRC"
echo "    ok: code in $SRC"

exec "$SRC/deploy/install.sh" "$@"
