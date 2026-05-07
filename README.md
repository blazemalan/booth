<p align="center">
  <img src="app/icon.png" alt="Pager" width="160" />
</p>

# Pager

> Voice notes from your local AI agent, over Telegram.

Pager is a macOS menu-bar app that gives any local AI agent (Claude Code, Cursor, Aider, your own) a voice on Telegram. Your AI sends you proper voice bubbles, you reply with voice notes, and Pager handles the bridge — local TTS, local STT, no API keys, no cloud bills.

Free, MIT-licensed, Mac-only.

## What it does

- **Outbound:** Your agent calls a local script with text. Pager synthesizes the voice locally with [Kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) on the Apple Neural Engine, encodes Opus, sends it to your Telegram bot. Your phone buzzes with a voice bubble in seconds.
- **Inbound:** When you send your bot a voice note, Pager downloads it, transcribes it locally with [whisper.cpp](https://github.com/ggerganov/whisper.cpp), and hands the text to your agent.
- **Self-trigger (Claude Code only):** Pager ships an AppleScript helper that lets your agent send slash commands like `/compact` to its own terminal session — useful when you're not at the keyboard.

## Who it's for

AI enthusiasts running a local agent who want a voice channel to it. The deal is simple: use the official Telegram app on your phone, run Pager on your Mac, and you've got a real coworker you can talk to from anywhere.

## Hotkey

- **Cmd + Option + P** — toggle Pager listening on/off
- Menu bar icon shows status: green pulse = listening, red = paused, gray = stopped

## Install

```bash
git clone https://github.com/blazemalan/pager.git
cd pager
./install.sh
```

The installer:

- Downloads Kokoro TTS models (~196 MB) to `~/.local/share/kokoro-tts/`
- Downloads Whisper.cpp base model (~150 MB) to `~/.local/share/whisper/`
- Builds the `.app` bundle with `py2app`
- Copies it to `/Applications/Pager.app`
- Installs `opus-tools` and `whisper-cpp` via Homebrew if missing
- Asks for your Telegram bot token (one-time)
- Wires the menu-bar app and starts the listener

You'll need a Telegram bot token. Two paths:

**Already have a bot?** Skip to install — paste your token when asked.
**Don't have one?** [Five-minute setup guide via BotFather](docs/BOT_SETUP.md). Then run install.

## System requirements

- **Mac:** Apple Silicon (M1, M2, M3, M4) recommended. Intel Macs work but TTS synthesis is 3-5× slower.
- **macOS:** 13.0 (Ventura) or newer.
- **RAM:** 8 GB minimum, 16 GB recommended.
- **Disk:** ~1 GB free (models + app bundle).
- **Permissions:** Accessibility (for AppleScript hotkey + self-trigger trick).

## How it works

```
Your AI agent → Pager (Mac) → Telegram Bot API → your phone
                                       ↓
                    Pager (Mac) ← voice notes from your phone
                          ↓
                Whisper STT → text → your AI agent
```

All synthesis and transcription happen on your Mac. The only network traffic is to Telegram's servers (which is unavoidable for the chat bridge). Your conversations never touch any AI vendor's API.

## Voices

Kokoro ships 50+ voices, graded A through F by the model author based on training data quality. Pager defaults to `af_heart` — the only A-grade voice in the roster, and the one we tested everything against. You can swap voices via the menu-bar settings.

## What works with what

| Agent type | Outbound voice | Inbound voice | Self-trigger (`/compact`) |
|-----|-----|-----|-----|
| Claude Code | ✅ | ✅ | ✅ |
| Cursor agent | ✅ | ✅ | ✅ |
| Aider | ✅ | ✅ | ✅ |
| Custom Python/CLI agent | ✅ | ✅ | ⚠️ (terminal-based only) |
| Cloud bots (ChatGPT web, Claude.ai) | ❌ | ❌ | ❌ |

If your agent runs locally and can shell out to a script, Pager works. The self-trigger trick is specific to terminal-based agents.

## Roadmap

- v0.1 (you're here): outbound voice + inbound voice + self-trigger, Mac only
- v0.2: per-conversation voice profiles, idle-eviction tuning
- v0.3: optional iMessage adapter (replace Telegram backend)
- v0.4: optional Slack/Discord adapter

Linux and Windows ports are not on our roadmap — fork and adapt if you need them. The core (Python + Kokoro + Whisper) is portable; the menu-bar UI and CoreML acceleration are the Mac-specific parts.

## Need help wiring this for your business?

The free repo gets you running. If you want a 1:1 working session — picking the right model, designing your agent's identity, integrating with your existing tools — Blaze takes a small number of consulting clients per month at [cinder.works/products/ai-blueprint](https://cinder.works/products/ai-blueprint).

## License

MIT. Build on it freely.

## Built on

- [Kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) (Apache-2)
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) (MIT)
- [opus-tools](https://opus-codec.org/) (BSD-3)
- [py2app](https://github.com/ronaldoussoren/py2app) (MIT)
- [Claudible](https://github.com/blazemalan/claudible) — base scaffolding for the menu-bar app pattern (MIT)
