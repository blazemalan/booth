<p align="center">
  <img src="app/icon.png" alt="Pager" width="160" />
</p>

# Pager

> Voice notes from your local AI agent, over Telegram.

There are already a dozen Telegram bridges for AI coding agents. Every one of them ships **text only**.

Pager ships **voice**. Your agent sends you proper voice bubbles. You reply with voice notes. Local TTS. Local STT. No API keys. No cloud bills. Mac menu-bar app, free forever.

## Why this exists

The "talk to your AI agent over Telegram" space is real and getting bigger:

- [Claude Code Channels](https://github.com/anthropics/claude-plugins-official) — Anthropic's official MCP plugin
- [OpenClaw Telegram skill](https://docs.openclaw.ai/channels/telegram) — 8.3k+ installs
- [Ductor](https://github.com/PleasePrompto/ductor) — Claude Code + Codex + Gemini in one bridge
- [TeleCodex](https://github.com/benedict2310/telecodex) — Codex CLI bridge
- [Composio's Telegram MCP](https://composio.dev/toolkits/telegram) — generic agent bridge

These all give you text. They're great. We use Claude Code Channels ourselves — it's how we built Pager in the first place.

But text on its own is cold. When your AI sends you a 200-word status update at 3pm and you're in a meeting, you read it later. When your AI sends you a **voice note**, you hear it. You hear the urgency. You hear the personality. The bandwidth is different.

Pager is the voice layer. It drops in alongside whatever bridge you already use, or runs standalone with its own thin Telegram bot poller. Your agent calls a local script with text; Pager synthesizes locally and ships a real voice bubble to your phone. You record a voice note back; Pager transcribes it locally and hands the text to your agent.

That's the whole product.

## What it does

- **Outbound voice:** your agent calls `pager say "..."`. Pager synthesizes the audio locally with [Kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) on the Apple Neural Engine, encodes Opus, sends it to your Telegram bot. Your phone buzzes with a voice bubble in ~2.5 seconds.
- **Inbound voice:** when you send your bot a voice note, Pager downloads it, transcribes it locally with [whisper.cpp](https://github.com/ggerganov/whisper.cpp), and writes the text where your agent will pick it up.
- **Self-trigger (Claude Code only):** Pager ships an AppleScript helper your agent can call to send slash commands like `/compact` to its own terminal session — useful when you're not at the keyboard.

## Why Telegram (and not iMessage)

We picked Telegram because Telegram has a real Bot API: clean voice-bubble support, two-way without sandbox fights, free for everyone. iMessage is downgraded in three places that actually matter:

- **No native voice bubble for bots.** AppleScript can send an audio attachment, but recipients see "play this audio file," not a proper waveform voice bubble.
- **No inbound API.** Receiving an iMessage programmatically means polling SQLite or wrestling with AppleScript event handlers. Brittle and slow.
- **macOS TCC sandboxing** keeps blocking automation paths Apple used to allow. Every macOS update is a new fight.

We may add an iMessage adapter later (it's on the roadmap) but the experience will be a downgrade. Telegram is the intended channel.

## Who it's for

People running an always-on AI coding agent locally — Claude Code, Codex CLI, OpenClaw, custom Python — who want to actually *talk* to it from their phone.

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

- **Already have a bot?** Skip ahead — paste your token when asked.
- **Don't have one?** Five-minute setup walkthrough in [docs/BOT_SETUP.md](docs/BOT_SETUP.md). Then run install.

## System requirements

- **Mac:** Apple Silicon (M1, M2, M3, M4) recommended. Intel Macs work but TTS synthesis is 3–5× slower.
- **macOS:** 13.0 (Ventura) or newer.
- **RAM:** 8 GB minimum, 16 GB recommended.
- **Disk:** ~1 GB free (models + app bundle).
- **Permissions:** Accessibility (for the hotkey + the AppleScript self-trigger trick).

## How it works

```
Your AI agent  →  pager say "..."  →  Kokoro TTS  →  Opus encode
                                                          ↓
                                              Telegram sendVoice
                                                          ↓
                                                   your phone 📱

your phone 🎤  →  Telegram bot getUpdates  →  download .ogg
                                                  ↓
                                          afconvert → wav
                                                  ↓
                                          whisper.cpp → text
                                                  ↓
                                            your AI agent
```

All synthesis and transcription happen on your Mac. The only network traffic is to Telegram's servers. Your conversations never touch any AI vendor's API.

## Voices

Kokoro ships 50+ voices, graded A through F by the model author based on training data quality. Pager defaults to `af_heart` — the only A-grade voice in the roster. Swap voices via the menu-bar settings.

## Compatibility

| Agent | Outbound voice | Inbound voice | Self-trigger (`/compact`) |
|-----|-----|-----|-----|
| Claude Code | ✅ | ✅ | ✅ |
| Codex CLI | ✅ | ✅ | ✅ |
| OpenClaw | ✅ | ✅ | ⚠️ (CLI mode) |
| Custom Python/CLI agent | ✅ | ✅ | ⚠️ (terminal-based only) |
| Cloud-only bots (ChatGPT web, Claude.ai) | ❌ | ❌ | ❌ |

If your agent runs locally and can shell out to a script, Pager works. The self-trigger trick is specific to terminal-based agents that read keyboard input.

> **IDE-based agents** (Cursor, Aider) work for one-shot voice exchanges if you script them, but they're session-based, not always-on, so they're not Pager's primary use case.

## Roadmap

- **v0.1** *(you're here)*: outbound voice + inbound voice + self-trigger, Mac only
- **v0.2:** per-conversation voice profiles, idle-eviction tuning, log viewer in menu bar
- **v0.3:** optional iMessage adapter (downgraded UX, see "Why Telegram" above)
- **v0.4:** optional Slack/Discord adapters

Linux and Windows ports are not on our roadmap. Fork and adapt if you need them — the core (Python + Kokoro + Whisper) is portable; the menu-bar UI and CoreML acceleration are the Mac-specific parts.

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
