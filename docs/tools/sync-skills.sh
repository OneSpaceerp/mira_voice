#!/usr/bin/env bash
# Copy the project skills from .agents/skills into .claude/skills, where Claude Code discovers them.
set -euo pipefail
cd "$(dirname "$0")/../.."
SRC=.agents/skills; DST=.claude/skills
mkdir -p "$DST"
# 1. folders that have a SKILL.md at their top
for d in "$SRC"/*/; do
  n=$(basename "$d")
  [ -f "$d/SKILL.md" ] && rsync -a --delete --exclude .git "$d" "$DST/$n/"
done
# 2. the loose SKILL.md at the root (progressive-web-app)
if [ -f "$SRC/SKILL.md" ]; then mkdir -p "$DST/progressive-web-app"; cp "$SRC/SKILL.md" "$DST/progressive-web-app/SKILL.md"; fi
# 3. nested skill collections (PWA_Skills): each folder holding a SKILL.md becomes its own skill.
#    Two nested skills may share a folder name, so later ones get -2, -3…
rm -rf "$DST"/pwa-nested-*
find "$SRC/PWA_Skills" -name SKILL.md -not -path '*/.git/*' | sort | while read -r f; do
  p=$(dirname "$f"); base="pwa-nested-$(basename "$p" | tr ' ' '-' | tr '[:upper:]' '[:lower:]')"
  n=$base; i=2; while [ -e "$DST/$n" ]; do n="$base-$i"; i=$((i+1)); done
  rsync -a --exclude .git "$p/" "$DST/$n/"
  # give each copy a unique skill name (the folder name)
  sed -i "0,/^name:.*/s//name: $n/" "$DST/$n/SKILL.md"
done
# 4. packaged .skill files (zip archives)
for z in "$SRC"/*.skill; do [ -f "$z" ] && unzip -oq "$z" -d "$DST"; done
echo "Skills in $DST:"; ls "$DST"
