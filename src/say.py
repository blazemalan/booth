#!/usr/bin/env python3
"""Booth — outbound voice. Send a Telegram voice bubble in the configured voice.

Pipeline: text → backend synth (Kokoro daemon OR ElevenLabs HTTP) →
Opus OGG → Telegram sendVoice.

Usage:
    python -m booth.say "Hello, Blaze."
    python -m booth.say --voice af_bella --speed 1.1 "Custom voice."
    python -m booth.say --backend elevenlabs --voice 21m00Tcm4TlvDq8ikWAM "..."
    python -m booth.say --dry-run "Test the synth without sending."

Reads bot token from $BOOTH_HOME/telegram_bot_token.
Defaults chat_id to the first entry in $BOOTH_HOME/chat_ids.
Backend + per-backend defaults come from $BOOTH_HOME/config.json (optional;
falls back to Kokoro with built-in defaults if absent).

Auto-spawns the Kokoro voice daemon if needed. ElevenLabs bypasses the
daemon entirely — it's HTTP-only.

Note: --voice overrides the configured voice per-call (Kokoro voice name OR
ElevenLabs voice_id, depending on backend). The ElevenLabs model isn't
exposed as a CLI flag — it's a set-once choice in config.json's
"elevenlabs": {"model": "..."} field.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HOME = Path.home()
BOOTH_HOME = Path(os.environ.get("BOOTH_HOME", HOME / ".local/share/booth"))
TOKEN_FILE = BOOTH_HOME / "telegram_bot_token"
CHAT_IDS_FILE = BOOTH_HOME / "chat_ids"
CONFIG_FILE = BOOTH_HOME / "config.json"

# Daemon socket lives in the per-user temp dir, shared across every bot on
# the Mac. The daemon does pure Kokoro synthesis — no bot identity in it,
# no notion of backends — so one daemon serves every Kokoro user.
# ElevenLabs bypasses this entirely (HTTP-only, nothing to keep loaded).
DAEMON_SOCKET = Path(tempfile.gettempdir()) / "booth_voice.sock"
DAEMON_SCRIPT = Path(__file__).parent / "voice_daemon.py"

DEFAULT_VOICE = "af_heart"


def load_config() -> dict:
    """Load $BOOTH_HOME/config.json. Falls back to Kokoro defaults if absent
    so existing installs (and anyone who never sets up a config) keep working
    exactly as before."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError as e:
            raise SystemExit(f"{CONFIG_FILE} is not valid JSON: {e}")
    return {"backend": "kokoro"}


def load_bot_token() -> str:
    if not TOKEN_FILE.exists():
        raise SystemExit(
            f"Bot token not configured. Run: echo 'YOUR_TOKEN' > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}"
        )
    return TOKEN_FILE.read_text().strip()


def load_default_chat_id() -> str:
    if not CHAT_IDS_FILE.exists():
        raise SystemExit(
            f"No default chat configured at {CHAT_IDS_FILE}. "
            "Add one with: echo 'YOUR_CHAT_ID' >> "
            f"{CHAT_IDS_FILE}\nOr pass --chat-id explicitly."
        )
    chats = [line.strip() for line in CHAT_IDS_FILE.read_text().splitlines() if line.strip()]
    if not chats:
        raise SystemExit(f"Empty {CHAT_IDS_FILE}. Pass --chat-id.")
    return chats[0]


def daemon_alive() -> bool:
    if not DAEMON_SOCKET.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(str(DAEMON_SOCKET))
        return True
    except Exception:
        return False


def spawn_daemon() -> None:
    # Prefer the runtime venv python (has kokoro_onnx + onnxruntime + numpy).
    # sys.executable might be system python3 if invoked via bin/booth before
    # the venv is populated, in which case the daemon would fail to import
    # kokoro_onnx and never bind the socket.
    venv_py = BOOTH_HOME / ".venv" / "bin" / "python"
    py = str(venv_py) if venv_py.exists() else sys.executable
    subprocess.Popen(
        [py, str(DAEMON_SCRIPT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if daemon_alive():
            return
        time.sleep(0.2)
    raise SystemExit(f"daemon failed to start within 15s — check {BOOTH_HOME}/voice_daemon.log")


def synth_via_daemon(text: str, voice: str, speed: float, out_wav: Path) -> dict:
    if not daemon_alive():
        sys.stderr.write("[daemon not running, spawning…]\n")
        spawn_daemon()
    req = {"text": text, "voice": voice, "speed": speed, "out_wav": str(out_wav)}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(60)
        s.connect(str(DAEMON_SOCKET))
        s.sendall((json.dumps(req) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(8192)
            if not chunk:
                break
            data += chunk
    resp = json.loads(data.decode().strip())
    if not resp.get("ok"):
        raise SystemExit("synth failed: " + resp.get("error", "unknown"))
    return resp


def synth_dispatch(text: str, args, config: dict, out_wav: Path) -> dict:
    """Pick a backend and synthesize. Returns {samples, sr, backend}.

    Resolution order for everything except the text itself:
      1. CLI flag (--backend, --voice, --speed) wins
      2. config.json's per-backend section wins next
      3. Built-in defaults

    Failures from either backend propagate as SystemExit. Booth never silently
    falls back from ElevenLabs to Kokoro — voice identity is the contract,
    silent backend swaps would break it. The calling agent decides what to
    do on failure (retry, drop, send a text reply on Telegram, etc.)."""
    backend = args.backend or config.get("backend", "kokoro")

    if backend == "kokoro":
        kk = config.get("kokoro", {})
        voice = args.voice or kk.get("voice") or DEFAULT_VOICE
        speed = args.speed if args.speed is not None else kk.get("speed", 1.0)
        info = synth_via_daemon(text, voice, speed, out_wav)
        return {**info, "backend": "kokoro"}

    if backend == "elevenlabs":
        # Imported lazily so installs that never touch ElevenLabs don't pay
        # the import cost (and so a missing module doesn't break Kokoro users).
        # Bare `from elevenlabs_synth ...` works because say.py is invoked as a
        # script (Python adds the script's dir to sys.path). If Booth ever
        # gets refactored into a real package, change to a relative import.
        from elevenlabs_synth import (
            synth_to_wav as eleven_synth,
            DEFAULT_VOICE_ID,
            DEFAULT_MODEL,
        )
        el = config.get("elevenlabs", {})
        voice_id = args.voice or el.get("voice_id") or DEFAULT_VOICE_ID
        model = el.get("model") or DEFAULT_MODEL
        samples, sr = eleven_synth(text, voice_id, model, out_wav)
        return {"samples": samples, "sr": sr, "backend": "elevenlabs"}

    raise SystemExit(f"unknown backend: {backend!r}. Valid: kokoro, elevenlabs.")


def encode_opus(wav_path: Path, ogg_path: Path) -> None:
    res = subprocess.run(
        ["opusenc", "--bitrate", "32", "--vbr", str(wav_path), str(ogg_path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit("opusenc failed:\n" + res.stderr)


def send_voice(token: str, chat_id: str, ogg_path: Path, caption: str | None) -> dict:
    boundary = "----BoothVoiceBoundary7393"
    parts = []

    def add_field(name: str, value: str):
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(value.encode() + b"\r\n")

    add_field("chat_id", chat_id)
    if caption:
        add_field("caption", caption)

    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="voice"; filename="{ogg_path.name}"\r\n'.encode()
    )
    parts.append(b"Content-Type: audio/ogg\r\n\r\n")
    parts.append(ogg_path.read_bytes())
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendVoice",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", help="text to speak (or use --text)")
    ap.add_argument("--text", dest="text_flag", help="text to speak")
    ap.add_argument(
        "--backend",
        choices=["kokoro", "elevenlabs"],
        help="override the backend in $BOOTH_HOME/config.json for this call",
    )
    ap.add_argument(
        "--voice",
        help="voice id — Kokoro voice name (e.g. af_heart) or ElevenLabs voice_id",
    )
    ap.add_argument("--speed", type=float, default=None,
                    help="Kokoro speed multiplier (1.0 = normal). Ignored on ElevenLabs.")
    ap.add_argument("--chat-id", help="Telegram chat ID (defaults to first entry in $BOOTH_HOME/chat_ids)")
    ap.add_argument("--caption", help="optional caption shown next to the voice bubble")
    ap.add_argument("--keep", action="store_true", help="keep intermediate files")
    ap.add_argument("--dry-run", action="store_true",
                    help="run synth + encode but skip the Telegram sendVoice")
    args = ap.parse_args()

    text = args.text_flag or args.text
    if not text:
        ap.error("provide text as positional arg or --text")

    config = load_config()

    with tempfile.TemporaryDirectory(prefix="booth_voice_") as td_str:
        td = Path("/tmp" if args.keep else td_str)
        wav_path = td / "voice.wav"
        ogg_path = td / "voice.ogg"

        t0 = time.time()
        info = synth_dispatch(text, args, config, wav_path)
        t_synth = time.time() - t0
        sys.stderr.write(
            f"[synth/{info['backend']}] {info['samples']} samples "
            f"@ {info['sr']}Hz in {t_synth:.2f}s\n"
        )

        encode_opus(wav_path, ogg_path)

        if args.dry_run:
            t_total = time.time() - t0
            sys.stderr.write(f"[dry-run] {ogg_path.stat().st_size} bytes ogg, total {t_total:.2f}s\n")
            return

        token = load_bot_token()
        chat_id = args.chat_id or load_default_chat_id()
        resp = send_voice(token, chat_id, ogg_path, args.caption)
        if not resp.get("ok"):
            raise SystemExit(f"Telegram API error: {resp}")
        msg_id = resp["result"]["message_id"]
        t_total = time.time() - t0
        sys.stderr.write(f"[sent] id={msg_id} in {t_total:.2f}s\n")


if __name__ == "__main__":
    main()
