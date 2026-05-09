# Architecture

Booth is small on purpose. Three parts: a TTS daemon, a CLI, and a menu-bar app that supervises the daemon.

## The shape

```
                  ┌────────────────────────────────────────────────┐
                  │              your AI agent (local)             │
                  │  Claude Code · Codex CLI · OpenClaw · custom   │
                  └────────────┬─────────────────────┬─────────────┘
                               │                     │
                  on outbound  │                     │  on inbound
                               ▼                     ▼
                       ┌──────────────┐     ┌──────────────────┐
                       │  booth say   │     │ booth transcribe │
                       │   (text →    │     │  (audio file →   │
                       │   bubble)    │     │       text)      │
                       └──────┬───────┘     └────────┬─────────┘
                              │                      │
              ┌───────────────▼──────┐    ┌──────────▼───────────┐
              │  voice_daemon (UDS)  │    │     whisper-cli      │
              │   Kokoro + CoreML    │    │   on a wav extracted │
              │  on the Neural Engine│    │   by macOS afconvert │
              └──────────┬───────────┘    └──────────┬───────────┘
                         │                           │
                  Opus encode                  text on stdout
                  via opusenc                       │
                         │                          ▼
                         ▼                   your AI agent reads it
            POST /sendVoice to Telegram             │
                         │                          │
                         ▼                          │
                  your phone 📱  ──── voice note ──┘
                            (delivered by your existing MCP bridge,
                             not by Booth)
```

## Why Booth doesn't poll Telegram

The "talk to your AI on Telegram" space already has solved chat: Anthropic's [Claude Code Channels](https://github.com/anthropics/claude-plugins-official), [OpenClaw's Telegram skill](https://docs.openclaw.ai/channels/telegram), [Ductor](https://github.com/PleasePrompto/ductor), [Composio's Telegram MCP](https://composio.dev/toolkits/telegram). These all `getUpdates` on your bot and route messages to your agent.

Telegram only allows ONE `getUpdates` consumer per bot at a time. If Booth also polled, it would fight whichever bridge you already use. Bad.

So Booth does the two things the bridges don't do: voice synthesis (text → sendVoice) and voice transcription (downloaded audio → text). Both are pull-only operations from Booth's side — `say` is a single POST, `transcribe` is a local CLI on a file. Neither touches `getUpdates`. They coexist with anything.

Your agent is the orchestrator: it receives the inbound message via the MCP, downloads via the MCP's `download_attachment` tool, calls `booth transcribe`, then thinks, then calls `booth say` for the reply.

## State on disk

```
~/.local/share/booth/                  # default $BOOTH_HOME (per-agent identity)
├── .venv/                             # runtime venv (shared across agents)
├── telegram_bot_token                 # 600-mode, plain text — the bot's identity
├── chat_ids                           # newline-separated, first is the say default
├── booth.md                           # voice protocol injected by the agent hook
├── voice_daemon.log                   # one log for every synth across every bot
└── daemon.stderr.log                  # menu-bar app captures the daemon's stderr

~/.local/share/booth-<agent>/          # second agent's $BOOTH_HOME (Hans, etc.)
├── telegram_bot_token                 # *its* bot's identity
├── chat_ids
└── booth.md

~/.local/share/kokoro-tts/             # Kokoro model files (~196 MB)
~/.local/share/whisper/                # Whisper.cpp model files (~150 MB)

$TMPDIR/                               # per-user, e.g. /var/folders/.../T/
├── booth_voice.sock                   # ONE daemon socket, shared by every bot
└── booth_voice.pid                    # the running daemon's PID
```

## Why a separate runtime venv

`Booth.app` is built with py2app, and its bundled python only carries what the menu-bar UI needs (rumps). The TTS pipeline needs kokoro_onnx + onnxruntime + numpy, which are heavy and have native extensions that py2app can't always bundle cleanly.

So `install.sh` creates `~/.local/share/booth/.venv` against the user's Homebrew Python and installs the runtime deps there. Both the menu-bar app and the `bin/booth` CLI subprocess-launch the voice daemon through that venv's python (the CLI defaults to it; the menu-bar app's `_python_for_subprocess` looks for it explicitly). The .app stays small; the heavy stuff lives in the venv.

If you need to override which Python `bin/booth` uses — running against a custom kokoro_onnx fork, debugging in a different venv — set the `BOOTH_PY` env var to that python's path.

## The daemon

`src/voice_daemon.py` keeps Kokoro loaded so synth is fast on every call:

- Listens on `$TMPDIR/booth_voice.sock` (Unix domain socket, per-user, shared across every bot — see *Multi-bot* below).
- On startup, monkey-patches `onnxruntime.InferenceSession` to inject `CoreMLExecutionProvider` so Kokoro runs on the Apple Neural Engine.
- Each request is a newline-delimited JSON message: `{"text": "...", "voice": "af_heart", "speed": 1.0, "out_wav": "/tmp/foo.wav"}`. Response: `{"ok": true, "samples": N, "sr": 24000}`.
- 30-minute idle timeout: if no requests come in for 30 min, the daemon shuts down cleanly and unlinks its socket. The next `booth say` call auto-respawns it. First synth eats ~3-4s cold-start; warm calls are 0.7-1.0s.

The empty-connection trap: the menu-bar app pings the socket to check if the daemon is alive. The ping opens a connection and immediately closes it without sending data. The daemon needs to recognize that as a probe and not crash on `json.loads("")`. Hence the `if not data.strip(): return` at the top of `handle_client`.

## Multi-bot — one daemon, many agents

Each AI agent on the Mac sends through its own Telegram bot (so chat threads stay separate), but they all share **one** voice daemon. The daemon does pure synthesis — `text + voice → audio bytes` — and has zero notion of bot identity. Whichever bot's `booth say` made the request takes the bytes and uploads them via *its* token.

That's why a third bot doesn't cost another ~290 MB: bot identity (token, chat ids, voice protocol) is the only per-agent thing. It lives at `$BOOTH_HOME/`, defaulting to `~/.local/share/booth/` and overridable per-agent via the env var. Everything else — daemon, models, venv, app — is shared.

The daemon socket and PID file live at `$TMPDIR/booth_voice.sock` and `$TMPDIR/booth_voice.pid`. `$TMPDIR` is a per-user path on macOS (e.g. `/var/folders/.../T/`), so the socket isn't visible to other users on the machine but is shared by every Booth client this user runs.

Voice is per-request — Kokoro loads all 50+ voices at startup and any synth call can pick any of them, so a shared daemon serves Cinder's `af_heart` and Hans's whatever-voice equally well, no conflict.

## The injector

`src/injector.py` AppleScripts the front Terminal.app window's selected tab to "do script TEXT" — which types `TEXT` into whatever's running there as if the user typed it. Used so an always-on agent (Claude Code in particular) can fire `/compact` at itself when its context is tight and the human isn't at the keyboard.

Scope:
- Targets macOS Terminal.app only. iTerm and other terminals would need their own bindings.
- Targets the FRONT window's selected tab. Caller is responsible for ensuring that's the right session.
- Requires Accessibility permission (granted on first AppleScript run via System Settings).
- This is a self-write — Booth scripts the OWN terminal session that the agent is running in, not somebody else's.

## What's NOT in Booth

- A Telegram bridge. Use Anthropic's Claude Code Channels, OpenClaw, Composio, etc.
- A way to receive voice notes. Your bridge does that; Booth transcribes whatever audio file you hand it.
- A backend service. Booth is a Mac-local set of CLIs and a menu-bar app. Nothing runs in the cloud.
