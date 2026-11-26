#!/usr/bin/env bash
# One-time Claude Code setup for Mira Voice. Run from the project root inside WSL/Ubuntu:
#   bash setup/setup-claude-code.sh
set -euo pipefail
cd "$(dirname "$0")/.."
command -v rsync >/dev/null || sudo apt-get install -y rsync
command -v unzip >/dev/null || sudo apt-get install -y unzip
# 1. context7 MCP server for this project
if [ -f .mcp.json ]; then echo ".mcp.json exists — leaving it"; else cp setup/mcp.json .mcp.json; fi
# 2. project settings (enables context7, blocks reading .env files)
mkdir -p .claude
if [ -f .claude/settings.json ]; then echo ".claude/settings.json exists — leaving it"; else cp setup/claude-settings.json .claude/settings.json; fi
# 3. skills: .agents/skills -> .claude/skills
bash docs/tools/sync-skills.sh
# 4. checks
[ -n "${CONTEXT7_API_KEY:-}" ] || echo "NOTE: CONTEXT7_API_KEY is not set — context7 works with lower rate limits. Get a key at context7.com/dashboard."
command -v claude >/dev/null && claude mcp list || echo "Install Claude Code: curl -fsSL https://claude.ai/install.sh | bash"
echo "Done. Open the folder in VS Code and start Claude Code."
