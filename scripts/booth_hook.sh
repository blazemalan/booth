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
# `attachment_kind=\"voice\"` (JSON-escaped).
#
# Tightened 2026-05-15: previously matched the substring `attachment_kind="voice"`
# anywhere, which false-positive'd on bug reports / docs that quoted the literal
# string. Now requires it to appear as an attribute on an actual <channel ...>
# opening tag (single-line — channel tags don't span lines in practice).
prompt="$(cat)"

VOICE_RE='<channel[^>]*attachment_kind=\\?"voice'
BOOTH_SAY_RE='\bbooth say\b'

if echo "$prompt" | grep -qE "$VOICE_RE" || echo "$prompt" | grep -qE "$BOOTH_SAY_RE"; then
  if [ -f "$BOOTH_MD" ]; then
    cat "$BOOTH_MD"
  fi
fi

exit 0
