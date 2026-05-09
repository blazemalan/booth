#!/bin/bash
# Optional: wires Booth's voice protocol into Claude Code as a UserPromptSubmit
# hook. The hook injects ~/.local/share/booth/booth.md into Claude's context
# whenever an inbound Telegram voice message is detected in the prompt.
#
# Other agents (Codex CLI, OpenClaw, custom) — set up your own equivalent.
# This script ONLY touches Claude Code's settings.
#
# Re-running is safe (idempotent — skips if the hook is already wired).

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
HOOK_SCRIPT="$PROJECT_DIR/scripts/booth_hook.sh"
BOOTH_MD_SRC="$PROJECT_DIR/booth.md"
BOOTH_HOME="${BOOTH_HOME:-$HOME/.local/share/booth}"
SETTINGS="$HOME/.claude/settings.json"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m[ok]\033[0m %s\n" "$*"; }

bold "Booth: wire voice protocol into Claude Code"

# 1. Make sure booth.md is installed
mkdir -p "$BOOTH_HOME"
if [ ! -f "$BOOTH_HOME/booth.md" ]; then
  cp "$BOOTH_MD_SRC" "$BOOTH_HOME/booth.md"
  ok "booth.md installed at $BOOTH_HOME/booth.md"
else
  ok "booth.md already at $BOOTH_HOME/booth.md (kept)"
fi

# 2. Make sure the hook script is executable
chmod +x "$HOOK_SCRIPT"

# 3. Wire the hook into Claude Code settings
if [ ! -f "$SETTINGS" ]; then
  echo "Claude Code settings not found at $SETTINGS"
  echo "Skipping hook wire-up. Booth still works via the CLI without the hook."
  exit 0
fi

if grep -q "$HOOK_SCRIPT" "$SETTINGS" 2>/dev/null; then
  ok "Hook already wired in $SETTINGS"
  exit 0
fi

# Add the hook via jq if available
# Claude Code expects each entry to be a matcher group: { hooks: [ { type, command } ] }
# The matcher field is omitted (matches all prompts).
if command -v jq >/dev/null 2>&1; then
  TMP=$(mktemp)
  jq --arg cmd "$HOOK_SCRIPT" '
    .hooks //= {}
    | .hooks.UserPromptSubmit //= []
    | .hooks.UserPromptSubmit += [{"hooks": [{"type": "command", "command": $cmd}]}]
  ' "$SETTINGS" > "$TMP"
  mv "$TMP" "$SETTINGS"
  ok "Hook added to $SETTINGS"
  echo "Restart Claude Code to pick up the change."
else
  echo "jq not found. Add this manually to $SETTINGS under .hooks.UserPromptSubmit:"
  echo
  echo "  { \"hooks\": [ { \"type\": \"command\", \"command\": \"$HOOK_SCRIPT\" } ] }"
  echo
  echo "Or: brew install jq && re-run this script."
fi
