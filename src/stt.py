#!/usr/bin/env python3
"""Pager — inbound voice transcription.

Pipeline: Telegram .ogg attachment → afconvert → wav → whisper.cpp → text.

Usage:
    python -m pager.stt path/to/voice.oga
    # prints transcript to stdout
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path.home()
WHISPER_MODEL = HOME / ".local/share/whisper/ggml-base.en.bin"


def transcribe(input_audio: Path) -> str:
    """Return whisper.cpp transcript text for the given audio file (any common format)."""
    if not WHISPER_MODEL.exists():
        raise SystemExit(f"Whisper model missing at {WHISPER_MODEL}. Run install.sh.")

    with tempfile.TemporaryDirectory(prefix="pager_stt_") as td_str:
        td = Path(td_str)
        wav_path = td / "audio.wav"

        # Convert to whisper-friendly WAV (16 kHz, 16-bit, mono)
        res = subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
             str(input_audio), str(wav_path)],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            raise SystemExit("afconvert failed:\n" + res.stderr)

        res = subprocess.run(
            ["whisper-cli", "-m", str(WHISPER_MODEL), "-f", str(wav_path), "-nt"],
            capture_output=True, text=True,
        )
        if res.returncode != 0:
            raise SystemExit("whisper-cli failed:\n" + res.stderr)

        return res.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="Path to a Telegram voice .oga (or any audio file)")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        sys.exit(f"Audio file not found: {audio}")

    text = transcribe(audio)
    print(text)


if __name__ == "__main__":
    main()
