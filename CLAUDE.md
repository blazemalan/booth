# Booth — repo context for AI agents

This file is the canonical context for any AI agent (Claude Code, Codex CLI, OpenClaw, custom) working on this codebase. Read it first.

## What Booth is

Booth is a free MIT-licensed macOS menu-bar app + CLI that adds **voice** to whatever Telegram bridge an AI agent already uses. The picture: an agent at a radio booth, broadcasting from a back room while the user is out running their life.

- **Outbound:** `booth say "..."` → Kokoro TTS (Apple Neural Engine via CoreML) → Opus → Telegram `sendVoice` → real voice bubble on the user's phone in ~2.5s.
- **Inbound:** when the user sends a voice note, the existing Telegram bridge delivers the audio file path; the agent calls `booth transcribe path.oga` → whisper.cpp returns text.

**Architecture rule (load-bearing):** Booth NEVER polls Telegram. The MCP bridge does that. Booth is `sendVoice` outbound + audio-file transcription inbound only. This is intentional so it can coexist on the same bot token with Claude Code Channels, OpenClaw, TeleCodex, Composio, etc.

## Key files

```
src/voice_daemon.py     Kokoro TTS daemon. Unix domain socket at $TMPDIR/booth_voice.sock,
                        30-min idle timeout, CoreML-accelerated. Kokoro-only by design.
src/elevenlabs_synth.py ElevenLabs HTTP synth backend. Bypasses the daemon entirely —
                        nothing to keep loaded. Outputs WAV symmetric with the daemon's
                        shape so the rest of the pipeline doesn't care which backend ran.
src/say.py              text → backend dispatch → opusenc → Telegram sendVoice. The
                        dispatcher (synth_dispatch) reads $BOOTH_HOME/config.json.
src/stt.py              afconvert + whisper-cli wrapper for transcription.
src/injector.py         AppleScript-types into front Terminal.app — for booth inject.
bin/booth               CLI entrypoint: say / transcribe / inject / daemon / status.
app/main.py             rumps menu-bar app that supervises the daemon.
install.sh              One-shot installer. Detects curl-pipe and self-clones if needed.
                        Asks for backend choice; writes config.json only for elevenlabs.
scripts/install_claude_hook.sh  Wires booth.md as a Claude Code UserPromptSubmit hook.
scripts/booth_hook.sh   The hook itself — injects booth.md when a voice channel block hits.
booth.md                Voice protocol injected into the agent's context. Lives in the
                        repo AND gets copied to $BOOTH_HOME/booth.md by install.sh.
docs/ARCHITECTURE.md    Full technical reference — read for deep-dive questions.
docs/BOT_SETUP.md       5-minute @BotFather walkthrough.
```

## Multi-bot architecture (important — read before touching daemon code)

Multiple AI agents on one Mac (e.g. Cinder + Hans) each send through their **own** Telegram bot, but they all share **one** voice daemon. The daemon does pure text-to-audio synthesis and has zero notion of bot identity. Whichever bot's `booth say` made the call uploads the result via *its* token.

**Per-agent state (lives in `$BOOTH_HOME`, default `~/.local/share/booth/`):**
- `telegram_bot_token` — the bot identity
- `chat_ids` — default recipients
- `booth.md` — voice protocol

**Shared state (lives outside `$BOOTH_HOME`, one copy per Mac):**
- daemon socket + PID at `$TMPDIR/booth_voice.{sock,pid}`
- daemon log at `~/.local/share/booth/voice_daemon.log`
- Kokoro TTS models, Whisper STT model, runtime venv, Booth.app

To add a second agent (Hans, etc.): create `~/.local/share/booth-<name>/` with its own token + chat_ids + a copy of booth.md, then set `BOOTH_HOME=/Users/.../booth-<name>` in the agent's project `.claude/settings.json` env block. No second daemon needed.

Voice is per-request — Kokoro loads all 50+ voices at startup, so a shared daemon serves Cinder's `af_heart` and Hans's whatever-voice with no cross-talk.

## Backend dispatch (Kokoro vs ElevenLabs)

`say.py` reads `$BOOTH_HOME/config.json` and dispatches to one of two synth backends. The split is *load-bearing*: the daemon does pure Kokoro synthesis with no notion of identity or alternative engines, and ElevenLabs bypasses the daemon entirely with direct HTTP. Don't conflate.

**Resolution order** for backend + voice + speed (all per-call, evaluated top to bottom): CLI flag (e.g. `--backend`, `--voice`) → `config.json` per-backend block (e.g. `"kokoro": {"voice": "..."}`) → built-in defaults.

**Missing config.json = Kokoro.** Existing installs without a `config.json` keep working as if Kokoro is configured. Don't write a config file for the default case; it'd be noise.

**Fail-loud contract on ElevenLabs failures.** When ElevenLabs returns 401 / 429 / network error, `elevenlabs_synth.py` raises `SystemExit` with the API's message. Booth never silently falls back to Kokoro — voice identity is the contract, silent backend swaps would break it. The calling agent (whatever invoked `booth say`) decides what to do: drop, retry, or send a text reply on Telegram instead. **Don't add a silent fallback PR.** A 429 mid-conversation that flips an agent's voice from a custom ElevenLabs voice back to Kokoro is not graceful degradation — it's *somebody else just started talking*. The user paid money to anchor that voice; preserve the contract. Future-you, hold the line.

**WAV symmetry.** `elevenlabs_synth.synth_to_wav` MUST produce a WAV with the exact shape `voice_daemon.synth_to_wav` produces — mono, 16-bit PCM, 24 kHz (matches `output_format=pcm_24000` in the ElevenLabs request). Both feed the same `encode_opus()` downstream. If you ever change the daemon's output shape, change the ElevenLabs side in lockstep.

**ElevenLabs has no daemon.** The daemon's CoreML monkey-patch (`patch_providers_for_coreml`) is Kokoro-only and stays Kokoro-only — there's nothing to load for ElevenLabs because each call is a self-contained HTTP request. If a setup is ElevenLabs-only, the Kokoro daemon will idle out at 30 min and exit. That's correct behaviour, not a bug.

## Conventions and gotchas

**`BOOTH_HOME` honored everywhere.** Any code that reads bot-identity state (token, chat_ids) must use `Path(os.environ.get("BOOTH_HOME", HOME / ".local/share/booth"))`. Daemon socket / PID / log paths intentionally do NOT honor BOOTH_HOME — they're shared.

**Python entry points subprocess-launch through `$BOOTH_HOME/.venv/bin/python`** with fallback to the default install's venv (so per-agent BOOTH_HOMEs don't need to duplicate kokoro_onnx + onnxruntime + numpy). `bin/booth` resolves symlinks before computing `BOOTH_DIR` so it works when invoked through `~/.local/bin/booth → repo/bin/booth`.

**Token prompt reads from `/dev/tty` in `install.sh`.** Plain `read -rp` silently skips when stdin is the curl pipe. The three-branch logic (TTY / /dev/tty / fully non-interactive) is in `install.sh:113`.

**Booth.app is locally built via py2app.** No code-signing, no notarization. Because the user builds it themselves on their own Mac, macOS doesn't slap a quarantine xattr on the bundle, so first launch does NOT trigger the "unidentified developer" Gatekeeper warning. Don't add codesign steps unless we start distributing pre-built bundles.

**Install path is curl-pipe one-liner:** `curl -fsSL https://raw.githubusercontent.com/blazemalan/booth/main/install.sh | bash`. Auto-clones into `~/.local/share/booth/repo/` and re-execs from there if invoked piped. CLI lands at `~/.local/bin/booth` and the installer adds that dir to the user's shell rc PATH.

**Don't reintroduce per-agent daemons.** The previous architecture (commit `9a806b7`) had per-instance sockets under `$BOOTH_HOME/voice.sock` — superseded by `e6b7fec` which moved sockets back to `$TMPDIR` for daemon sharing. Reverting wastes ~290 MB RAM per extra bot.

**`scripts/booth_hook.sh` already honors `BOOTH_HOME`.** The hook injects `$BOOTH_HOME/booth.md` into the agent's context whenever a voice channel block hits the prompt. Keeps voice protocol per-agent.

## Sibling project

[Claudible](https://github.com/blazemalan/claudible) is a separate desk-side TTS app — same author, same Kokoro engine — but it speaks Claude's responses aloud *at the Mac*, not over Telegram. Booth and Claudible share visual identity (cream radio + ember dial) but solve different pains. Don't conflate.

## Brand

Cream radio + ember dial + cream speech bubble + circuit grille. Locked 2026-05-08. Also serves as the Cinder Works brand mark — see `app/icon.png`. Palette: ember `#ff6b35`, cream `#f5e6cc`, near-black `#0a0a0a`.

## Related repos for cross-context

- `blazemalan/claudible` — sibling TTS app (desk-side, not Telegram).
- `anthropics/claude-plugins-official` — the Claude Code Telegram channel plugin Booth assumes alongside.

## When to update this file

Update CLAUDE.md when:
- An architectural rule changes (e.g., the never-poll-Telegram rule, the shared-daemon design)
- A new convention or gotcha is established that would surprise a fresh agent
- A key file's purpose changes

Don't update for:
- Routine bug fixes — the commit message is the right place
- Implementation details derivable from the code — agents can read source
