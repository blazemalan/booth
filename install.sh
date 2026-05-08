#!/bin/bash
# Pager installer for macOS.
#
# Sets up the menu-bar app, downloads Kokoro TTS + Whisper STT models,
# wires the launchd agent, and prompts for a Telegram bot token.
#
# Usage:
#   ./install.sh
#
# Prereqs: Homebrew, macOS 13+. Apple Silicon strongly recommended.

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
KOKORO_DIR="$HOME/.local/share/kokoro-tts"
WHISPER_DIR="$HOME/.local/share/whisper"
PAGER_HOME="$HOME/.local/share/pager"
APP_DEST="/Applications/Pager.app"
TOKEN_FILE="$PAGER_HOME/telegram_bot_token"
CHAT_FILE="$PAGER_HOME/allowlist"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m[ok]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[warn]\033[0m %s\n" "$*"; }

bold "Pager installer"
echo "Project: $PROJECT_DIR"
echo

# ── 1. System checks
bold "Step 1: system checks"
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }

OS_MAJOR=$(sw_vers -productVersion | cut -d. -f1)
if [ "$OS_MAJOR" -lt 13 ]; then
  warn "macOS $OS_MAJOR detected. Pager targets macOS 13+ (Ventura). Continuing — TTS may be slower."
fi

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
  warn "Intel Mac detected. TTS synthesis will be 3-5x slower without the Neural Engine. Pager will still work."
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

# ── 5. Pager state directory
bold "Step 5: Pager state directory"
mkdir -p "$PAGER_HOME"
ok "$PAGER_HOME"

# ── 6. Telegram bot token
bold "Step 6: Telegram bot token"
if [ ! -f "$TOKEN_FILE" ]; then
  echo
  echo "Need a Telegram bot token. Don't have one yet?"
  echo "→ See docs/BOT_SETUP.md for the 5-minute walkthrough."
  echo
  read -rp "Paste your bot token (or press Enter to skip and add later): " TOKEN
  if [ -n "$TOKEN" ]; then
    echo "$TOKEN" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    ok "Token saved to $TOKEN_FILE (mode 600)"
  else
    warn "Skipped. Add it later with: echo 'YOUR_TOKEN' > $TOKEN_FILE && chmod 600 $TOKEN_FILE"
  fi
else
  ok "Token already configured at $TOKEN_FILE"
fi

# ── 7. Build the .app bundle (TODO: py2app config in app/setup.py)
bold "Step 7: Build Pager.app"
warn "App bundle build is not wired yet — running in CLI mode for now."
warn "TODO: cd $PROJECT_DIR/app && python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python setup.py py2app"

# ── 8. Hotkey daemon (skhd) + Accessibility prompt (TODO)
bold "Step 8: Hotkey daemon"
warn "skhd integration coming soon. For now, run the daemon manually with: bin/pager-daemon"

echo
bold "Done. (mostly)"
echo
echo "Next steps:"
echo "  1. Pair your Telegram bot: open it on your phone and send /start"
echo "  2. Run: $PROJECT_DIR/bin/pager say 'Hello, world.' to test outbound voice"
echo "  3. Send a voice note to your bot from Telegram to test inbound STT"
echo
echo "Troubleshooting:"
echo "  - logs: $PAGER_HOME/pager.log"
echo "  - bot token: $TOKEN_FILE"
echo "  - models: $KOKORO_DIR, $WHISPER_DIR"
echo
