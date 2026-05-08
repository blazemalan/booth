#!/usr/bin/env python3
"""Pager — inbound listener. Polls Telegram for new voice notes from your bot.

For each voice note received from an allowlisted chat:
  1. Download the .ogg
  2. Transcribe with stt.transcribe()
  3. Append the transcript to ~/.local/share/pager/inbox.jsonl

Your AI agent watches inbox.jsonl (or you wire it however you want).

Usage:
    python -m pager.listen
    # runs forever, long-polling getUpdates

Configure:
    $PAGER_HOME/telegram_bot_token  — bot token
    $PAGER_HOME/allowlist           — newline-separated chat_ids (only these are accepted)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .stt import transcribe

HOME = Path.home()
PAGER_HOME = Path(os.environ.get("PAGER_HOME", HOME / ".local/share/pager"))
TOKEN_FILE = PAGER_HOME / "telegram_bot_token"
ALLOWLIST_FILE = PAGER_HOME / "allowlist"
INBOX_FILE = PAGER_HOME / "inbox.jsonl"
OFFSET_FILE = PAGER_HOME / "update_offset"
LOG_FILE = PAGER_HOME / "listen.log"
DOWNLOAD_DIR = PAGER_HOME / "voice_inbox"

LONG_POLL_TIMEOUT = 30


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def load_token() -> str:
    if not TOKEN_FILE.exists():
        sys.exit(f"No bot token at {TOKEN_FILE}. Run install.sh.")
    return TOKEN_FILE.read_text().strip()


def load_allowlist() -> set[str]:
    if not ALLOWLIST_FILE.exists():
        return set()
    return {line.strip() for line in ALLOWLIST_FILE.read_text().splitlines() if line.strip()}


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset))


def tg_get(token: str, method: str, params: dict | None = None, timeout: int = 35) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def download_file(token: str, file_id: str, dest_dir: Path) -> Path:
    info = tg_get(token, "getFile", {"file_id": file_id}, timeout=15)
    if not info.get("ok"):
        raise RuntimeError(f"getFile failed: {info}")
    file_path = info["result"]["file_path"]
    dest = dest_dir / Path(file_path).name
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with urllib.request.urlopen(url, timeout=30) as r, dest.open("wb") as f:
        f.write(r.read())
    return dest


def write_inbox_entry(entry: dict) -> None:
    INBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with INBOX_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def handle_voice(token: str, message: dict) -> None:
    chat_id = str(message["chat"]["id"])
    msg_id = message["message_id"]
    voice = message.get("voice") or message.get("video_note") or {}
    file_id = voice.get("file_id")
    if not file_id:
        return

    log(f"voice msg from chat={chat_id} msg_id={msg_id}, downloading…")
    audio_path = download_file(token, file_id, DOWNLOAD_DIR)
    try:
        text = transcribe(audio_path)
    except Exception as e:
        log(f"transcribe failed for msg_id={msg_id}: {e}")
        text = ""

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "message_id": msg_id,
        "audio_path": str(audio_path),
        "text": text,
    }
    write_inbox_entry(entry)
    log(f"transcript for msg_id={msg_id}: {text[:80]!r}")


def main():
    token = load_token()
    allow = load_allowlist()
    offset = load_offset()
    log(f"listener starting offset={offset} allowlist={sorted(allow) if allow else 'empty (denying all)'}")

    while True:
        try:
            params = {"timeout": LONG_POLL_TIMEOUT, "allowed_updates": json.dumps(["message"])}
            if offset:
                params["offset"] = offset
            resp = tg_get(token, "getUpdates", params, timeout=LONG_POLL_TIMEOUT + 5)
            if not resp.get("ok"):
                log(f"getUpdates error: {resp}")
                time.sleep(5)
                continue

            for update in resp.get("result", []):
                offset = max(offset, update["update_id"] + 1)
                save_offset(offset)
                msg = update.get("message")
                if not msg:
                    continue
                chat_id = str(msg["chat"]["id"])
                if allow and chat_id not in allow:
                    log(f"rejected chat_id={chat_id} (not in allowlist)")
                    continue
                if msg.get("voice") or msg.get("video_note"):
                    try:
                        handle_voice(token, msg)
                    except Exception as e:
                        log(f"handle_voice error: {e}")
        except Exception as e:
            log(f"main loop error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
