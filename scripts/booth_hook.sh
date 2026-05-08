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

# Read whole stdin. Claude Code passes a JSON envelope with a "prompt" field
# (and other metadata). Inside the JSON the channel block's quotes are
# backslash-escaped, so we match BOTH `attachment_kind="voice"` (raw) and
# `attachment_kind=\"voice\"` (JSON-escaped). Same for the booth-say heuristic.
prompt="$(cat)"

if echo "$prompt" | grep -qE 'attachment_kind=\\?"voice\\?"' || echo "$prompt" | grep -qE '\bbooth say\b'; then
  if [ -f "$BOOTH_MD" ]; then
    cat "$BOOTH_MD"
  fi
fi

exit 0
