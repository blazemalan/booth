#!/bin/bash
# UserPromptSubmit hook: inject booth.md into the agent's context when an
# inbound Telegram voice message is detected in the prompt.
#
# Reads the prompt content on stdin. Stdout is what gets injected.
# No-ops (silent exit) on prompts without a voice channel block.
#
# Wire-up: add to ~/.claude/settings.json under hooks.UserPromptSubmit:
#   { "command": "/path/to/booth/scripts/booth_hook.sh" }

set -e

BOOTH_HOME="${BOOTH_HOME:-$HOME/.local/share/booth}"
BOOTH_MD="$BOOTH_HOME/booth.md"

# Read whole stdin
prompt="$(cat)"

# Look for a voice channel block. We match either:
#   - inbound voice from a Telegram channel block: attachment_kind="voice"
#   - the agent about to call booth say (heuristic: "booth say" appearing in
#     the prompt as a tool plan)
if echo "$prompt" | grep -q 'attachment_kind="voice"' || echo "$prompt" | grep -qE '\bbooth say\b'; then
  if [ -f "$BOOTH_MD" ]; then
    cat "$BOOTH_MD"
  fi
fi

exit 0
