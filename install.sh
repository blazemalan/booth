#!/bin/bash
# Booth installer for macOS.
#
# Sets up the menu-bar app, downloads Kokoro TTS + Whisper STT models,
# wires the launchd agent, and prompts for a Telegram bot token.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/blazemalan/booth/main/install.sh | bash
#   # or, from a cloned repo:
#   ./install.sh
#
# Prereqs: Homebrew, macOS 13+. Apple Silicon strongly recommended.

set -e

REPO_URL="https://github.com/blazemalan/booth.git"
CLONE_DIR="$HOME/.local/share/booth/repo"

# If we were piped from `curl | bash`, BASH_SOURCE won't point at a real file
# next to a bin/ dir. In that case, clone (or update) the repo to a stable
# location and re-exec the installer from there.
SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
if [ ! -f "$SCRIPT_PATH" ] || [ ! -d "$(dirname "$SCRIPT_PATH")/bin" ]; then
  command -v git >/dev/null || { echo "git required for curl-pipe install. Install Xcode CLI tools: xcode-select --install" >&2; exit 1; }
  if [ -d "$CLONE_DIR/.git" ]; then
    echo "Updating existing booth checkout at $CLONE_DIR..."
    git -C "$CLONE_DIR" fetch --quiet origin
    git -C "$CLONE_DIR" reset --hard --quiet origin/main
  else
    echo "Cloning booth into $CLONE_DIR..."
    mkdir -p "$(dirname "$CLONE_DIR")"
    git clone --quiet "$REPO_URL" "$CLONE_DIR"
  fi
  exec bash "$CLONE_DIR/install.sh"
fi

PROJECT_DIR="$( cd "$( dirname "$SCRIPT_PATH" )" && pwd )"
KOKORO_DIR="$HOME/.local/share/kokoro-tts"
WHISPER_DIR="$HOME/.local/share/whisper"
# BOOTH_HOME defaults to the standard location but can be overridden so a
# second agent on the same Mac (e.g. Hans alongside Cinder) can install its
# own state dir with a separate bot token. Each agent's `claude` session
# exports BOOTH_HOME from its project's .claude/settings.json env block.
BOOTH_HOME="${BOOTH_HOME:-$HOME/.local/share/booth}"
APP_DEST="/Applications/Booth.app"
TOKEN_FILE="$BOOTH_HOME/telegram_bot_token"
CHAT_IDS_FILE="$BOOTH_HOME/chat_ids"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m[ok]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[warn]\033[0m %s\n" "$*"; }

bold "Booth installer"
echo "Project: $PROJECT_DIR"
echo

# ── 1. System checks
bold "Step 1: system checks"
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }

OS_MAJOR=$(sw_vers -productVersion | cut -d. -f1)
if [ "$OS_MAJOR" -lt 13 ]; then
  warn "macOS $OS_MAJOR detected. Booth targets macOS 13+ (Ventura). Continuing — TTS may be slower."
fi

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
  warn "Intel Mac detected. TTS synthesis will be 3-5x slower without the Neural Engine. Booth will still work."
fi
ok "system checks"

# ── 2. Brew dependencies
bold "Step 2: dependencies (Python, opus-tools, whisper-cpp, jq)"
for pkg in python@3.12 opus-tools whisper-cpp jq; do
  brew list "$pkg" >/dev/null 2>&1 || brew install "$pkg"
done
ok "brew deps"

# ── 3. Kokoro TTS models
bold "Step 3: Kokoro TTS models"
mkdir -p "$KOKORO_DIR"
if [ ! -f "$KOKORO_DIR/kokoro-v1.0.fp16.onnx" ]; then
  echo "Downloading kokoro-v1.0.fp16.onnx (~169 MB)..."
  curl -L --progress-bar -o "$KOKORO_DIR/kokoro-v1.0.fp16.onnx" \
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16.onnx"
fi
if [ ! -f "$KOKORO_DIR/voices-v1.0.bin" ]; then
  echo "Downloading voices-v1.0.bin (~27 MB)..."
  curl -L --progress-bar -o "$KOKORO_DIR/voices-v1.0.bin" \
    "https://github.com/thewh1teagle/kokoro-onnx/releases/latest/download/voices-v1.0.bin"
fi
ok "Kokoro models in $KOKORO_DIR"

# ── 4. Whisper.cpp model
bold "Step 4: Whisper.cpp model (base.en)"
mkdir -p "$WHISPER_DIR"
if [ ! -f "$WHISPER_DIR/ggml-base.en.bin" ]; then
  echo "Downloading ggml-base.en.bin (~150 MB)..."
  curl -L --progress-bar -o "$WHISPER_DIR/ggml-base.en.bin" \
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
fi
ok "Whisper model in $WHISPER_DIR"

# ── 5. Booth state directory
bold "Step 5: Booth state directory"
mkdir -p "$BOOTH_HOME"
# Voice protocol — agent should re-read this on every inbound voice message
if [ -f "$PROJECT_DIR/booth.md" ]; then
  cp "$PROJECT_DIR/booth.md" "$BOOTH_HOME/booth.md"
fi
ok "$BOOTH_HOME"

# ── 6. Telegram bot token
bold "Step 6: Telegram bot token"
if [ ! -f "$TOKEN_FILE" ]; then
  echo
  echo "Need a Telegram bot token. Don't have one yet?"
  echo "→ See docs/BOT_SETUP.md for the 5-minute walkthrough."
  echo
  TOKEN=""
  # When the script is invoked via `curl | bash`, stdin is the pipe — a plain
  # `read` returns empty without ever showing the prompt. Detect that case
  # and read from /dev/tty (the user's actual terminal) so the prompt works
  # in both `./install.sh` and curl-pipe invocations. Fall back to a clean
  # skip-with-instructions if there's no controlling terminal at all (CI).
  if [ -t 0 ]; then
    read -rp "Paste your bot token (or press Enter to skip and add later): " TOKEN
  elif [ -e /dev/tty ]; then
    printf "Paste your bot token (or press Enter to skip and add later): "
    IFS= read -r TOKEN < /dev/tty || true
  else
    warn "Non-interactive install — skipping token prompt."
  fi
  if [ -n "$TOKEN" ]; then
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    ok "Token saved to $TOKEN_FILE (mode 600)"
  else
    warn "Add your token later with: echo 'YOUR_TOKEN' > $TOKEN_FILE && chmod 600 $TOKEN_FILE"
  fi
else
  ok "Token already configured at $TOKEN_FILE"
fi

# ── 7. Synth backend choice (Kokoro / ElevenLabs)
# Default = Kokoro (free, local, ships with Booth). ElevenLabs is opt-in for
# users who want a cloud-hosted voice catalogue (typically because they've
# created or chosen a specific voice on ElevenLabs's side they want to use).
# Existing installs that already have a config.json are left alone.
bold "Step 7: Synth backend"
CONFIG_FILE="$BOOTH_HOME/config.json"
ELEVEN_KEY_FILE="$BOOTH_HOME/elevenlabs_api_key"
if [ -f "$CONFIG_FILE" ]; then
  ok "Backend config already exists at $CONFIG_FILE — keeping it"
else
  echo
  echo "Booth ships with two synth backends:"
  echo "  kokoro      — local, free, Apple Neural Engine, ~50 voices (default)"
  echo "  elevenlabs  — paid HTTP API, your account's voice catalogue"
  echo
  BACKEND_CHOICE=""
  if [ -t 0 ]; then
    read -rp "Pick a backend [kokoro / elevenlabs] (default: kokoro): " BACKEND_CHOICE
  elif [ -e /dev/tty ]; then
    printf "Pick a backend [kokoro / elevenlabs] (default: kokoro): "
    IFS= read -r BACKEND_CHOICE < /dev/tty || true
  fi
  case "$(echo "${BACKEND_CHOICE:-kokoro}" | tr '[:upper:]' '[:lower:]')" in
    elevenlabs|el)
      ELEVEN_KEY=""
      if [ -t 0 ]; then
        read -rp "Paste your ElevenLabs API key (or Enter to skip): " ELEVEN_KEY
      elif [ -e /dev/tty ]; then
        printf "Paste your ElevenLabs API key (or Enter to skip): "
        IFS= read -r ELEVEN_KEY < /dev/tty || true
      fi
      if [ -n "$ELEVEN_KEY" ]; then
        echo "$ELEVEN_KEY" > "$ELEVEN_KEY_FILE"
        chmod 600 "$ELEVEN_KEY_FILE"
        ok "ElevenLabs API key saved at $ELEVEN_KEY_FILE (mode 600)"
      else
        warn "Skipped — add the key later: echo 'YOUR_KEY' > $ELEVEN_KEY_FILE && chmod 600 $ELEVEN_KEY_FILE"
      fi
      # Prompt for voice_id — voice catalogues are per-account, so we don't
      # bake in a default. A baked-in id would silently fail for users whose
      # account doesn't have it. Blank is OK at install time; say.py fails
      # loud with a clear remediation message if the user later runs
      # booth say without a voice_id configured.
      ELEVEN_VOICE=""
      echo
      echo "  Find your voice_id at https://elevenlabs.io/app/voice-library"
      echo "  (e.g. 'cgSgspJ2msm6clMCkdW9' for Jessica)."
      if [ -t 0 ]; then
        read -rp "Paste your ElevenLabs voice_id (or Enter to add later): " ELEVEN_VOICE
      elif [ -e /dev/tty ]; then
        printf "Paste your ElevenLabs voice_id (or Enter to add later): "
        IFS= read -r ELEVEN_VOICE < /dev/tty || true
      fi
      python3 -c "import json,sys; \
json.dump({'backend':'elevenlabs', \
'elevenlabs':{'voice_id': sys.argv[1], 'model':'eleven_flash_v2_5'}}, \
open(sys.argv[2],'w'), indent=2)" "$ELEVEN_VOICE" "$CONFIG_FILE"
      ok "Backend = elevenlabs (config: $CONFIG_FILE)"
      if [ -z "$ELEVEN_VOICE" ]; then
        warn "voice_id is blank — set it later by editing $CONFIG_FILE before running booth say."
      fi
      ;;
    *)
      # Kokoro is the default — say.py treats a missing config as Kokoro,
      # so we don't need to write a file. Keeps existing installs untouched.
      ok "Backend = kokoro (default — no config file needed)"
      ;;
  esac
fi

# ── 8. Runtime venv at $BOOTH_HOME/.venv
# This venv holds kokoro_onnx + onnxruntime + numpy. Booth.app's bundled python
# only has rumps; the menu-bar app subprocess-launches src/voice_daemon.py
# through THIS venv. Decouples UI deps from runtime deps.
bold "Step 8: Runtime venv"
RUNTIME_VENV="$BOOTH_HOME/.venv"
PY=$(brew --prefix python@3.12)/bin/python3.12
if [ ! -d "$RUNTIME_VENV" ]; then
  "$PY" -m venv "$RUNTIME_VENV"
fi
"$RUNTIME_VENV/bin/python" -m pip install --upgrade pip wheel >/dev/null
"$RUNTIME_VENV/bin/python" -m pip install kokoro-onnx onnxruntime numpy
ok "Runtime venv at $RUNTIME_VENV"

# ── 9. Install booth CLI on PATH
# Symlink bin/booth into ~/.local/bin (XDG user-local convention — same dir
# pipx, uv, rustup, and most modern Mac/Linux CLIs use). If ~/.local/bin
# isn't on PATH, append the export to the user's shell rc so a new terminal
# picks it up. We avoid /usr/local/bin (sudo on Apple Silicon) and brew's
# prefix (namespace violation, brew doctor complains).
bold "Step 9: Install booth CLI on PATH"
USER_BIN="$HOME/.local/bin"
mkdir -p "$USER_BIN"
CLI_LINK="$USER_BIN/booth"
if [ -L "$CLI_LINK" ] || [ -f "$CLI_LINK" ]; then
  CURRENT_TARGET="$(readlink "$CLI_LINK" 2>/dev/null || echo "")"
  if [ "$CURRENT_TARGET" = "$PROJECT_DIR/bin/booth" ]; then
    ok "booth CLI already linked at $CLI_LINK"
  else
    ln -sf "$PROJECT_DIR/bin/booth" "$CLI_LINK"
    ok "booth CLI relinked at $CLI_LINK → $PROJECT_DIR/bin/booth"
  fi
else
  ln -s "$PROJECT_DIR/bin/booth" "$CLI_LINK"
  ok "booth CLI linked at $CLI_LINK → $PROJECT_DIR/bin/booth"
fi

# Clean up legacy brew-prefix symlinks left by older installer versions
# (we briefly tried that; it pollutes brew's namespace).
LEGACY_BREW_LINK="$(brew --prefix)/bin/booth"
if [ -L "$LEGACY_BREW_LINK" ]; then
  LEGACY_TARGET="$(readlink "$LEGACY_BREW_LINK")"
  case "$LEGACY_TARGET" in
    */booth/bin/booth)
      rm -f "$LEGACY_BREW_LINK"
      ok "removed legacy brew-prefix symlink at $LEGACY_BREW_LINK"
      ;;
  esac
fi

# Make sure ~/.local/bin is on PATH for the user's shell. Detect zsh vs bash
# (macOS default is zsh since Catalina), edit the right rc file idempotently,
# and tell the user to open a new terminal.
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
PATH_MARKER='# Added by Booth installer — keep ~/.local/bin on PATH'
case ":$PATH:" in
  *":$USER_BIN:"*) PATH_OK=true ;;
  *) PATH_OK=false ;;
esac

if $PATH_OK; then
  ok "$USER_BIN already on PATH"
else
  USER_SHELL="$(basename "${SHELL:-/bin/zsh}")"
  case "$USER_SHELL" in
    zsh)  RC_FILE="$HOME/.zshrc" ;;
    bash) RC_FILE="$HOME/.bash_profile" ;;
    *)    RC_FILE="" ;;
  esac

  if [ -n "$RC_FILE" ]; then
    touch "$RC_FILE"
    if grep -Fq "$PATH_MARKER" "$RC_FILE" 2>/dev/null; then
      ok "PATH export already present in $RC_FILE (open a new terminal to pick it up)"
    else
      printf '\n%s\n%s\n' "$PATH_MARKER" "$PATH_LINE" >> "$RC_FILE"
      ok "added PATH export to $RC_FILE — open a new terminal (or run: source $RC_FILE)"
    fi
  else
    warn "Unrecognized shell '$USER_SHELL'. Add this line to your shell rc manually: $PATH_LINE"
  fi
fi

# ── 9b. Claude Code integration (auto-detected)
# Booth's CLI lives in $HOME/.local/bin, but Claude Code's Bash tool spawns
# non-interactive subshells that don't source ~/.zshrc. So even though the rc
# edit above makes booth reachable from a fresh terminal, Claude Code itself
# can't find it. Two fixes, both idempotent:
#
#   1. Merge env.PATH into ~/.claude/settings.json so every Bash tool call
#      Claude Code makes sees $HOME/.local/bin.
#   2. Inject booth.md content into ~/.claude/CLAUDE.md between markers, so
#      the voice protocol loads on every Claude Code session — including
#      mid-task voice messages that arrive via channel injection (which don't
#      trigger UserPromptSubmit hooks).
#
# Both steps no-op if Claude Code isn't installed (~/.claude missing).
bold "Step 9b: Claude Code integration"
CLAUDE_DIR="$HOME/.claude"
if [ ! -d "$CLAUDE_DIR" ]; then
  ok "Claude Code not detected at $CLAUDE_DIR — skipping. Booth still works for other agents."
else
  CC_SETTINGS="$CLAUDE_DIR/settings.json"
  CC_CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

  # 9b.1 — env.PATH in settings.json
  if command -v jq >/dev/null 2>&1; then
    if [ ! -f "$CC_SETTINGS" ]; then
      printf '{\n  "env": {\n    "PATH": "%s:${PATH}"\n  }\n}\n' "$USER_BIN" > "$CC_SETTINGS"
      ok "wrote $CC_SETTINGS with PATH = $USER_BIN:\${PATH}"
    else
      TMP=$(mktemp)
      jq --arg dir "$USER_BIN" '
        .env //= {}
        | if (.env.PATH // null) == null then
            .env.PATH = ($dir + ":${PATH}")
          elif (.env.PATH | contains($dir)) then
            .
          else
            .env.PATH = ($dir + ":" + .env.PATH)
          end
      ' "$CC_SETTINGS" > "$TMP" && mv "$TMP" "$CC_SETTINGS"
      ok "ensured $USER_BIN is on env.PATH in $CC_SETTINGS"
    fi
  else
    warn "jq not found — skipping settings.json merge. Install jq and re-run for Claude Code PATH fix."
  fi

  # 9b.2 — booth.md content in ~/.claude/CLAUDE.md (always-on voice protocol)
  if [ -f "$PROJECT_DIR/booth.md" ]; then
    BEGIN_MARKER='<!-- BEGIN BOOTH VOICE PROTOCOL — managed by booth installer, do not edit -->'
    END_MARKER='<!-- END BOOTH VOICE PROTOCOL -->'
    BOOTH_MD_CONTENT="$(cat "$PROJECT_DIR/booth.md")"

    touch "$CC_CLAUDE_MD"
    if grep -Fq "$BEGIN_MARKER" "$CC_CLAUDE_MD" 2>/dev/null; then
      # Markers exist — replace content between them with current booth.md
      python3 - "$CC_CLAUDE_MD" "$BEGIN_MARKER" "$END_MARKER" "$BOOTH_MD_CONTENT" <<'PYEOF'
import sys, pathlib
path, begin, end, content = sys.argv[1:5]
text = pathlib.Path(path).read_text()
bidx = text.find(begin)
eidx = text.find(end, bidx)
if bidx >= 0 and eidx >= 0:
    new = text[:bidx] + begin + "\n" + content + "\n" + end + text[eidx + len(end):]
    pathlib.Path(path).write_text(new)
PYEOF
      ok "refreshed booth voice protocol section in $CC_CLAUDE_MD"
    else
      # Markers don't exist — append the section
      {
        [ -s "$CC_CLAUDE_MD" ] && printf '\n'
        printf '%s\n' "$BEGIN_MARKER"
        printf '%s\n' "$BOOTH_MD_CONTENT"
        printf '%s\n' "$END_MARKER"
      } >> "$CC_CLAUDE_MD"
      ok "added booth voice protocol section to $CC_CLAUDE_MD"
    fi
  fi
fi

# ── 9c. Smoke test — verify booth CLI runs from a non-interactive bash subshell
# This is the install-time check that catches the "Claude Code can't find booth"
# class of regression. We deliberately strip PATH inheritance so the test only
# passes if the CLI is reachable from a default-ish PATH (the fix above
# guarantees it via Claude Code's settings.json, but here we just verify the
# symlink itself is executable from a subshell, with $USER_BIN on PATH).
bold "Step 9c: Smoke test"
if PATH="$USER_BIN:/usr/bin:/bin" bash -c 'command -v booth >/dev/null && booth --help' >/dev/null 2>&1; then
  ok "booth CLI reachable from a clean non-interactive subshell"
else
  warn "booth CLI failed the subshell smoke test. Check $CLI_LINK target and permissions."
fi

# ── 10. Build the .app bundle
bold "Step 10: Build Booth.app"
cd "$PROJECT_DIR/app"

if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip wheel >/dev/null
.venv/bin/python -m pip install -r requirements.txt

# Standalone build for distribution; alias build (-A) is faster for dev.
.venv/bin/python setup.py py2app

if [ -d "dist/Booth.app" ]; then
  rm -rf "$APP_DEST"
  cp -R "dist/Booth.app" "$APP_DEST"
  ok "Booth.app installed to $APP_DEST"
else
  warn "py2app build did not produce dist/Booth.app — check the output above."
fi

# ── 11. Hotkey daemon (skhd) — optional, for Cmd+Option+P toggle
bold "Step 11: Hotkey (skhd, optional)"
if command -v skhd >/dev/null 2>&1; then
  ok "skhd already installed"
else
  echo "Skipping skhd install. To enable Cmd+Option+P toggle later:"
  echo "  brew install koekeishiya/formulae/skhd"
  echo "  Then add to ~/.config/skhd/skhdrc:"
  echo "    cmd + alt - p : open -a Booth"
  echo "  And run: skhd --start-service"
fi

echo
bold "Done."
echo
echo "Next steps:"
echo "  1. Open Booth.app from /Applications — it idles in your menu bar and"
echo "     keeps the voice daemon warm so synth is fast on every call."
echo "  2. Set the default Telegram chat: echo 'YOUR_CHAT_ID' >> $CHAT_IDS_FILE"
echo "     (see docs/BOT_SETUP.md to find your chat_id)"
echo "  3. Test outbound: booth say 'Hello, world.'"
echo "  4. Wire your AI agent to call 'booth say \"...\"' for voice replies, and"
echo "     'booth transcribe <audio.oga>' when your Telegram MCP delivers a"
echo "     voice note. Booth doesn't bridge Telegram itself — your existing"
echo "     MCP plugin keeps doing that. Booth is the voice layer on top."
echo "  5. (Claude Code only) Wire the auto-injecting voice protocol hook:"
echo "       $PROJECT_DIR/scripts/install_claude_hook.sh"
echo "     Other agents — point yours at $BOOTH_HOME/booth.md however you like."
echo
echo "Troubleshooting:"
echo "  - daemon log: $BOOTH_HOME/voice_daemon.log"
echo "  - daemon stderr: $BOOTH_HOME/daemon.stderr.log"
echo "  - bot token: $TOKEN_FILE"
echo "  - models: $KOKORO_DIR, $WHISPER_DIR"
echo
