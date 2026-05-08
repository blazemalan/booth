#!/usr/bin/env python3
"""Pager — outbound voice. Send a Telegram voice bubble in the configured voice.

Pipeline: text → Kokoro daemon → Opus OGG → Telegram sendVoice.

Usage:
    python -m pager.say "Hello, Blaze."
    python -m pager.say --voice af_bella --speed 1.1 "Custom voice."
    python -m pager.say --dry-run "Test the synth without sending."

Reads bot token from $PAGER_HOME/telegram_bot_token (default: ~/.local/share/pager/).
Defaults the chat_id to the first entry in $PAGER_HOME/allowlist.

Auto-spawns the voice daemon if the socket isn't there.
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
PAGER_HOME = Path(os.environ.get("PAGER_HOME", HOME / ".local/share/pager"))
TOKEN_FILE = PAGER_HOME / "telegram_bot_token"
ALLOWLIST_FILE = PAGER_HOME / "allowlist"

DAEMON_SOCKET = Path("/tmp/pager_voice.sock")
DAEMON_SCRIPT = Path(__file__).parent / "voice_daemon.py"

DEFAULT_VOICE = "af_heart"


def load_bot_token() -> str:
    if not TOKEN_FILE.exists():
        raise SystemExit(
            f"Bot token not configured. Run: echo 'YOUR_TOKEN' > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}"
        )
    return TOKEN_FILE.read_text().strip()


def load_default_chat_id() -> str:
    if not ALLOWLIST_FILE.exists():
        raise SystemExit(f"No allowlist at {ALLOWLIST_FILE}. Pass --chat-id explicitly.")
    chats = [line.strip() for line in ALLOWLIST_FILE.read_text().splitlines() if line.strip()]
    if not chats:
        raise SystemExit("Empty allowlist. Pass --chat-id.")
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
    py = sys.executable
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
    raise SystemExit("daemon failed to start within 15s — check ~/.local/share/pager/voice_daemon.log")


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


def encode_opus(wav_path: Path, ogg_path: Path) -> None:
    res = subprocess.run(
        ["opusenc", "--bitrate", "32", "--vbr", str(wav_path), str(ogg_path)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit("opusenc failed:\n" + res.stderr)


def send_voice(token: str, chat_id: str, ogg_path: Path, caption: str | None) -> dict:
    boundary = "----PagerVoiceBoundary7393"
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
    ap.add_argument("--voice", default=DEFAULT_VOICE, help=f"Kokoro voice id (default: {DEFAULT_VOICE})")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--chat-id", help="Telegram chat ID (defaults to first allowlist entry)")
    ap.add_argument("--caption", help="optional caption shown next to the voice bubble")
    ap.add_argument("--keep", action="store_true", help="keep intermediate files")
    ap.add_argument("--dry-run", action="store_true",
                    help="run synth + encode but skip the Telegram sendVoice")
    args = ap.parse_args()

    text = args.text_flag or args.text
    if not text:
        ap.error("provide text as positional arg or --text")

    with tempfile.TemporaryDirectory(prefix="pager_voice_") as td_str:
        td = Path("/tmp" if args.keep else td_str)
        wav_path = td / "voice.wav"
        ogg_path = td / "voice.ogg"

        t0 = time.time()
        info = synth_via_daemon(text, args.voice, args.speed, wav_path)
        t_synth = time.time() - t0
        sys.stderr.write(f"[synth] {info['samples']} samples @ {info['sr']}Hz in {t_synth:.2f}s\n")

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
